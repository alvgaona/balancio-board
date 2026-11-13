"""Interactive 3D view of the board: writes build/render/viewer.html (three.js, one self-contained file)
and keeps the 3D model it is made from, build/render/balancio.glb. Same viewer as ~/git/board-challenge.
Run: python3 scripts/viewer.py

KiCad exports the board as GLB with every face as its own mesh (about 34,000 of them, 10 MB). This merges
the faces by material, stores positions as 16-bit integers and embeds the result in the page as a PNG:
the bytes travel as pixel values, which compresses them and lets the page read them back through a canvas.
"""
import base64
import json
import os
import struct
import subprocess
import zlib
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "render"
KICAD = "/Applications/KiCad/KiCad.app/Contents"

# KiCad's part models leave metallicFactor out (glTF reads that as fully metal, this viewer as plastic). These
# are the metal ones, by material index in this board's export: leads, pins, shields and gold contacts. The colour
# (sRGB) each must have catches a re-export that reorders them. TIN recolours: micro-USB shell (KiCad blue-grey),
# ESP32-WROOM shield can (white in the DevKit model); both tin-plated steel on the real parts.
METAL = {1: (0.824, 0.82, 0.781), 3: (0.824, 0.82, 0.781), 9: (0.824, 0.82, 0.78), 11: (0.62, 0.63, 0.66),
         14: (0.85, 0.85, 0.82), 15: (0.667, 0.698, 0.769), 17: (0.647, 0.518, 0.0), 18: (1.0, 0.808, 0.459),
         20: (0.8, 0.8, 0.8), 21: (1.0, 1.0, 1.0), 23: (1.0, 0.667, 0.184), 27: (0.831, 0.831, 0.82),
         28: (0.502, 0.502, 0.502), 29: (0.769, 0.769, 0.769), 31: (0.569, 0.569, 0.588)}
TIN = {15: 0.8, 21: 0.78}  # linear grey


def export_glb(path):
    env = dict(os.environ, KICAD10_3DMODEL_DIR=f"{KICAD}/SharedSupport/3dmodels")
    subprocess.run([f"{KICAD}/MacOS/kicad-cli", "pcb", "export", "glb", "-f", "--subst-models", "--include-tracks",
                    "--include-pads", "--include-zones", "--include-silkscreen", "--include-soldermask",
                    "-o", str(path), str(ROOT / "hw" / "balancio.kicad_pcb")], env=env, check=True, capture_output=True)


def node_matrix(n):
    if "matrix" in n:
        m = n["matrix"]
        return [[m[c * 4 + r] for c in range(4)] for r in range(4)]
    t, s = n.get("translation", [0, 0, 0]), n.get("scale", [1, 1, 1])
    x, y, z, w = n.get("rotation", [0, 0, 0, 1])
    r = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
         [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    return [[r[i][c] * s[c] for c in range(3)] + [t[i]] for i in range(3)] + [[0, 0, 0, 1]]


def matmul(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]


def merge(glb):
    """{material index: (positions in mm as array('f'), indices as array('I'))} in world coordinates, and
    the power button SW2's origin (mm), which the viewer's key 4 looks at."""
    data = glb.read_bytes()
    jlen = struct.unpack("<I", data[12:16])[0]
    g = json.loads(data[20:20 + jlen])
    blob = data[20 + jlen + 8:]

    def read(acc_index, fmt, width):
        a = g["accessors"][acc_index]
        v = g["bufferViews"][a["bufferView"]]
        start = v.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = v.get("byteStride") or width * struct.calcsize(fmt)
        out = array(fmt)
        if stride == width * out.itemsize:
            out.frombytes(blob[start:start + a["count"] * stride])
        else:
            for i in range(a["count"]):
                out.frombytes(blob[start + i * stride:start + i * stride + width * out.itemsize])
        return out

    groups, sw2 = {}, []

    def walk(i, parent):
        n = g["nodes"][i]
        m = matmul(parent, node_matrix(n))
        if n.get("name") == "SW2":
            sw2.extend(1000 * m[r][3] for r in range(3))
        if "mesh" in n:
            for p in g["meshes"][n["mesh"]]["primitives"]:
                pos, idx = groups.setdefault(p.get("material", -1), (array("f"), array("I")))
                src = read(p["attributes"]["POSITION"], "f", 3)
                base = len(pos) // 3
                for k in range(0, len(src), 3):
                    x, y, z = src[k], src[k + 1], src[k + 2]
                    pos.extend((1000 * (m[r][0] * x + m[r][1] * y + m[r][2] * z + m[r][3]) for r in range(3)))
                if "indices" in p:
                    code = g["accessors"][p["indices"]]["componentType"]
                    idx.extend(base + v for v in read(p["indices"], {5121: "B", 5123: "H", 5125: "I"}[code], 1))
                else:
                    idx.extend(range(base, base + len(src) // 3))
        for c in n.get("children", []):
            walk(c, m)

    identity = [[1.0 if r == c else 0.0 for c in range(4)] for r in range(4)]
    for root in g["scenes"][g.get("scene", 0)]["nodes"]:
        walk(root, identity)
    assert sw2, "SW2 not in the export"
    return g["materials"], groups, sw2


def srgb(c):
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def png(payload, width=1024):
    """The payload as an 8-bit RGB PNG, three bytes per pixel."""
    row = width * 3
    rows = -(-len(payload) // row)
    raw = bytes(payload) + b"\0" * (rows * row - len(payload))
    scan = b"".join(b"\0" + raw[r * row:(r + 1) * row] for r in range(rows))  # filter type 0 on every row

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, rows, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(scan, 9)) + chunk(b"IEND", b""))


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    glb = OUT / "balancio.glb"
    export_glb(glb)
    materials, groups, sw2 = merge(glb)
    for i, want in METAL.items():
        got = [srgb(c) for c in materials[i]["pbrMetallicRoughness"]["baseColorFactor"][:3]]
        assert all(abs(a - b) < 0.01 for a, b in zip(got, want)), f"material {i} is {got}, not {want}: update METAL"
    lo = [min(min(p[k::3]) for p, _ in groups.values()) for k in range(3)]
    hi = [max(max(p[k::3]) for p, _ in groups.values()) for k in range(3)]
    payload, manifest = bytearray(), []
    for mat, (pos, idx) in sorted(groups.items()):
        q = array("H", (round((v - lo[k % 3]) / (hi[k % 3] - lo[k % 3]) * 65535) for k, v in enumerate(pos)))
        pbr = materials[mat].get("pbrMetallicRoughness", {}) if mat >= 0 else {}
        manifest.append({"color": pbr.get("baseColorFactor", [0.8, 0.8, 0.8, 1]), "metal": pbr.get("metallicFactor", 0),
                         "rough": pbr.get("roughnessFactor", 0.8), "pos": [len(payload), len(q)]})
        if mat in METAL:  # metal parts reflect their surroundings at full strength, as the pads do
            manifest[-1].update(metal=1, rough=0.3, env=1)
            if mat in TIN:
                manifest[-1]["color"] = [TIN[mat]] * 3 + [1]
        payload += q.tobytes()
        payload += b"\0" * (-len(payload) % 4)
        manifest[-1]["idx"] = [len(payload), len(idx)]
        payload += idx.tobytes()
    verts = sum(len(p) // 3 for p, _ in groups.values())
    assert verts > 10000 and all(max(i) < len(p) // 3 for p, i in groups.values()), "mesh merge went wrong"
    # the page carries the data itself, so it opens from disk with a double-click
    html = (Path(__file__).with_name("viewer.html").read_text()
            .replace("__META__", json.dumps({"lo": lo, "hi": hi, "bytes": len(payload), "meshes": manifest, "button": sw2}))
            .replace("__SRC__", "data:image/png;base64," + base64.b64encode(png(payload)).decode()))
    (OUT / "viewer.html").write_text(html)
    print(f"viewer: {len(groups)} meshes, {verts} vertices, {len(html) / 1e6:.1f} MB -> {OUT / 'viewer.html'}")


if __name__ == "__main__":
    build()

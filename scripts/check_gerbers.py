"""Fail unless the KiCad board's Gerbers and drill match the ones the working board was built from, apart from
the intended changes.

Usage: check_gerbers.py <our gerber dir> <built Gerber zip> [png dir]

Both sides are rasterized at 20 µm and XORed. Differences thinner than 2 pixels (40 µm, arc tessellation)
are ignored. Silkscreen may also differ inside SILK_CHANGES, and every layer and hole inside REV11_CHANGES.
Copper only fails where the built board has copper we don't: KiCad's pour fill adds slivers next to the built ones,
and DRC checks those for clearance. Drill holes are compared as sets. With a png dir, every layer that
differs gets an image (red = only ours, blue = only built).
"""
import math
import re
import sys
import zipfile
import zlib
from pathlib import Path

from design import REV11_CHANGES, SILK_CHANGES

RES = 0.02  # mm per pixel
X0, Y0, N = -35.5, -35.5, 3550  # raster window: the 70 x 70 mm board plus a margin
LAYERS = ["F_Cu", "B_Cu", "F_Mask", "B_Mask", "F_Paste", "B_Paste", "F_Silkscreen", "B_Silkscreen", "Edge_Cuts"]
BUILT_NAMES = {"F_Silkscreen": "f_silks", "B_Silkscreen": "b_silks"}  # the zip (exported by Flux) names them balancio-board-<layer>.gbr


def parse(text):
    """Gerber X2 as written by KiCad -> list of ("poly", pts) / ("seg", a, b, width) in mm."""
    out, ap, macros, cur, x, y, region, contour, mode = [], {}, {}, None, 0, 0, False, [], "1"
    scale = 1e6
    for blk in re.findall(r"%[^%]*%|[^*%]+\*", text):
        blk = blk.strip()
        if blk.startswith("%FS"):
            scale = 10 ** int(re.search(r"X\d(\d)", blk)[1])
        elif blk.startswith("%AM"):
            name, *prims = blk[3:-2].split("*")
            macros[name] = [p.strip() for p in prims if p.strip() and not p.strip().startswith("0")]
        elif blk.startswith("%ADD"):
            m = re.match(r"%ADD(\d+)([\w.]+),?([^*]*)\*%", blk)
            ap[int(m[1])] = (m[2], [float(v) for v in m[3].split("X") if v])
        elif blk.startswith("%LP"):
            assert blk == "%LPD*%", "clear polarity is not supported: " + blk
        elif blk.startswith(("%", "G04")) or blk in ("G75*", "M02*"):
            continue
        elif blk in ("G01*", "G02*", "G03*"):
            mode = blk[2]
        elif blk == "G36*":
            region, contour = True, []
        elif blk == "G37*":
            if len(contour) > 2:
                out.append(("poly", contour))
            region = False
        elif re.fullmatch(r"D(\d+)\*", blk) and int(blk[1:-1]) >= 10:
            cur = int(blk[1:-1])
        else:
            m = re.fullmatch(r"(?:G0?([123]))?(?:X(-?\d+))?(?:Y(-?\d+))?(?:I(-?\d+))?(?:J(-?\d+))?D0?([123])\*", blk)
            assert m, "unsupported Gerber command: " + blk
            mode = m[1] or mode
            nx = int(m[2]) / scale if m[2] else x
            ny = int(m[3]) / scale if m[3] else y
            op = m[6]
            path = [(nx, ny)]
            if op == "1" and mode in "23":  # circular arc, multi-quadrant (G75): tessellate in <= 3° steps
                cx, cy = x + int(m[4] or 0) / scale, y + int(m[5] or 0) / scale
                a0, a1 = math.atan2(y - cy, x - cx), math.atan2(ny - cy, nx - cx)
                sweep = (a1 - a0) % (2 * math.pi) if mode == "3" else -((a0 - a1) % (2 * math.pi))
                sweep = sweep or (2 * math.pi if mode == "3" else -2 * math.pi)
                r, k = math.hypot(x - cx, y - cy), max(2, int(abs(sweep) / math.radians(3)))
                path = [(cx + r * math.cos(a0 + sweep * i / k), cy + r * math.sin(a0 + sweep * i / k))
                        for i in range(1, k)] + [(nx, ny)]
            if region:
                if op == "2":
                    if len(contour) > 2:
                        out.append(("poly", contour))
                    contour = [(nx, ny)]
                else:
                    contour = contour or [(x, y)]
                    contour += path
            elif op == "1":
                kind, p = ap[cur]
                assert kind == "C", "only round apertures can draw"
                out += [("seg", a, b, p[0]) for a, b in zip([(x, y)] + path, path)]
            elif op == "3":
                out += flash(ap[cur], macros, nx, ny)
            x, y = nx, ny
    return out


def flash(aperture, macros, x, y):
    kind, p = aperture
    if kind == "C":
        return [("seg", (x, y), (x, y), p[0])] if p[0] > 0 else []
    if kind == "R":
        w, h = p[0] / 2, p[1] / 2
        return [("poly", [(x - w, y - h), (x + w, y - h), (x + w, y + h), (x - w, y + h)])]
    if kind == "O":
        w, h = p[0] / 2, p[1] / 2
        r = min(w, h)
        return [("seg", (x - w + r, y - h + r), (x + w - r, y + h - r), 2 * r)]
    out = []
    for prim in macros[kind]:  # KiCad's FreePoly macros: outline primitives, rotation in $1
        f = prim.split(",")
        assert f[0] == "4", "unsupported macro primitive in " + kind
        n = int(f[2])
        pts = [(float(f[3 + 2 * i]), float(f[4 + 2 * i])) for i in range(n + 1)]
        rot = p[0] if f[-1] == "$1" else float(f[-1])
        c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        out.append(("poly", [(x + u * c - v * s, y + u * s + v * c) for u, v in pts]))
    return out


def raster(shapes):
    """Rows of bits (Python ints), sampled at pixel centres."""
    rows = [bytearray(N) for _ in range(N)]
    ones = b"\x01" * N
    py = lambda j: Y0 + (j + 0.5) * RES

    def fill(j, xa, xb):
        a = max(0, math.ceil((xa - X0) / RES - 0.5))
        b = min(N, math.floor((xb - X0) / RES - 0.5) + 1)
        if b > a:
            rows[j][a:b] = ones[: b - a]

    for s in shapes:
        if s[0] == "poly":
            pts = s[1]
            cross = {}
            for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
                if y1 == y2:
                    continue
                lo, hi = min(y1, y2), max(y1, y2)
                for j in range(max(0, int((lo - Y0) / RES) - 1), min(N, int((hi - Y0) / RES) + 1)):
                    yy = py(j)
                    if lo <= yy < hi:  # half-open, so a vertex on a row centre counts once
                        cross.setdefault(j, []).append(x1 + (yy - y1) * (x2 - x1) / (y2 - y1))
            for j, xs in cross.items():
                xs.sort()
                for xa, xb in zip(xs[::2], xs[1::2]):
                    fill(j, xa, xb)
        else:
            (ax, ay), (bx, by), w = s[1], s[2], s[3]
            r = w / 2
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            for j in range(max(0, int((min(ay, by) - r - Y0) / RES)), min(N, int((max(ay, by) + r - Y0) / RES) + 1)):
                yy = py(j)
                # the capsule's row interval: union of the two end discs and the swept band (convex, so min/max)
                ivs = []
                for cx, cy in ((ax, ay), (bx, by)):
                    if abs(yy - cy) <= r:
                        h = (r * r - (yy - cy) ** 2) ** 0.5
                        ivs.append((cx - h, cx + h))
                if L2:
                    # band: within r of the line and projecting onto the segment (0 <= u <= 1)
                    if dy:
                        xc, ox = ax + (yy - ay) * dx / dy, r * L2 ** 0.5 / abs(dy)
                        band = [xc - ox, xc + ox]
                    else:
                        band = [-1e9, 1e9] if abs(yy - ay) <= r else None
                    if band and dx:
                        u0, u1 = sorted((ax - (yy - ay) * dy / dx, ax + (L2 - (yy - ay) * dy) / dx))
                        band = [max(band[0], u0), min(band[1], u1)]
                    elif band and not 0 <= (yy - ay) * dy / L2 <= 1:
                        band = None
                    if band and band[0] <= band[1]:
                        ivs.append(tuple(band))
                if ivs:  # a capsule is convex, so its row is one interval
                    fill(j, min(i[0] for i in ivs), max(i[1] for i in ivs))
    bits = bytes.maketrans(b"\x00\x01", b"01")
    return [int(r.translate(bits)[::-1], 2) for r in rows]  # bit i = pixel i


def differences(a, b, missing_only=False):
    """Pixels that differ (or only b has), eroded by one pixel so 1-pixel edge jitter does not count."""
    x = [q & ~p if missing_only else p ^ q for p, q in zip(a, b)]
    h = [v & (v << 1) & (v >> 1) for v in x]
    return [h[j] & h[j - 1] & h[j + 1] if 0 < j < N - 1 else 0 for j in range(N)]


def boxes(diff):
    """Bounding boxes (mm, Gerber coordinates) of the differing pixels, merged within 0.5 mm."""
    out = []
    for j, v in enumerate(diff):
        while v:
            i = (v & -v).bit_length() - 1
            run = i
            while v >> (run + 1) & 1:
                run += 1
            v &= ~((1 << (run + 1)) - (1 << i))
            bx = (X0 + i * RES, Y0 + j * RES, X0 + (run + 1) * RES, Y0 + (j + 1) * RES)
            for k, o in enumerate(out):
                if bx[0] <= o[2] + 0.5 and o[0] <= bx[2] + 0.5 and bx[1] <= o[3] + 0.5 and o[1] <= bx[3] + 0.5:
                    out[k] = (min(o[0], bx[0]), min(o[1], bx[1]), max(o[2], bx[2]), max(o[3], bx[3]))
                    break
            else:
                out.append(bx)
    return out


def png(path, ours, theirs):
    raw = bytearray()
    for j in reversed(range(N)):  # Gerber y is up
        raw.append(0)
        a, b = ours[j], theirs[j]
        for i in range(N):
            p, q = a >> i & 1, b >> i & 1
            raw += bytes((255, 60, 60) if p and not q else (60, 90, 255) if q and not p else
                         (200, 200, 200) if p else (255, 255, 255))
    chunk = lambda t, d: (len(d).to_bytes(4, "big") + t + d +
                          zlib.crc32(t + d).to_bytes(4, "big"))
    ihdr = N.to_bytes(4, "big") * 2 + bytes((8, 2, 0, 0, 0))
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
                           + chunk(b"IEND", b""))


def drill(text):
    tools, t, holes = {}, None, set()
    for line in text.splitlines():
        if m := re.match(r"T(\d+)C([\d.]+)", line):
            tools[m[1]] = float(m[2])
        elif m := re.match(r"T(\d+)$", line):
            t = m[1]
        elif m := re.match(r"X(-?[\d.]+)Y(-?[\d.]+)$", line):
            holes.add((round(float(m[1]), 2), round(float(m[2]), 2), tools[t]))
    return holes


def main(ours_dir, built_zip, png_dir=None):
    ours_dir = Path(ours_dir)
    with zipfile.ZipFile(built_zip) as z:
        built = {Path(n).name: n for n in z.namelist() if "/yg/balancio-board" in n}
        read = lambda name: z.read(built[name]).decode()
        theirs = {L: read(f"balancio-board-{BUILT_NAMES.get(L, L.lower())}.gbr") for L in LAYERS}
        their_holes = drill(read("balancio-board.drl"))
    bad = 0
    for L in LAYERS:
        mine = (ours_dir / f"balancio-{L}.gbr").read_text()
        a, b = raster(parse(mine)), raster(parse(theirs[L]))
        found = boxes(differences(a, b, missing_only=L.endswith("_Cu")))
        allowed = [w for name, w in SILK_CHANGES if name == L] + REV11_CHANGES
        inside = lambda o: any(w[0] <= o[0] and o[2] <= w[2] and w[1] <= o[1] and o[3] <= w[3] for w in allowed)
        unexpected = [o for o in found if not inside(o)]
        bad += len(unexpected)
        print(f"{L:13} {'OK' if not unexpected else 'DIFFERS'}"
              + (f" ({len(found) - len(unexpected)} intended changes)" if len(found) > len(unexpected) else ""))
        for o in unexpected[:10]:
            print(f"    x {o[0]:7.2f}..{o[2]:7.2f}  y {o[1]:7.2f}..{o[3]:7.2f}")
        if png_dir and found:
            Path(png_dir).mkdir(parents=True, exist_ok=True)
            png(Path(png_dir) / f"diff-{L}.png", a, b)
    our_holes = set().union(*(drill(p.read_text()) for p in ours_dir.glob("*.drl")))
    near = lambda h, pool: any(abs(h[0] - q[0]) <= 0.011 and abs(h[1] - q[1]) <= 0.011 and abs(h[2] - q[2]) < 0.001
                               for q in pool)
    changed = lambda h: any(w[0] <= h[0] <= w[2] and w[1] <= h[1] <= w[3] for w in REV11_CHANGES)
    holes_bad = [("only ours", h) for h in our_holes if not near(h, their_holes) and not changed(h)] + \
                [("only built", h) for h in their_holes if not near(h, our_holes) and not changed(h)]
    print(f"{'Drill':13} {'OK' if not holes_bad else 'DIFFERS'} ({len(our_holes)} holes)")
    for side, h in holes_bad[:10]:
        print("   ", side, h)
    bad += len(holes_bad)
    print("gerber check:", "match" if not bad else f"{bad} differences")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))

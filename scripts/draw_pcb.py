"""Draw hw/balancio.kicad_pcb and its footprint library hw/lib/balancio.pretty from the Flux board.

Usage: draw_pcb.py <KiCad netlist xml> <Flux Gerber zip>   (run by migrate.sh; overwrites hw/)

The board was built and works, so this copies it: Flux's pads, traces, vias and copper pours, plus the
front silkscreen from the Gerbers it was built from (minus Flux's title) and the back label from design.py.
Pads take KiCad's schematic net names. check_gerbers.py then proves the KiCad Gerbers match the built ones,
and KiCad's DRC with schematic parity proves footprints and nets match the schematic.

Flux (and Gerber) coordinates are y-up; KiCad's are y-down, so every y is negated on the way out.
"""
import json
import math
import struct
import sys
import xml.etree.ElementTree as ET
import zipfile
from datetime import date

from check_gerbers import parse as parse_gerber
from design import (FLUX, FOOTPRINT_OF, FOOTPRINTS, PARTS, PIN_NUMBERS, REV, SILK_AT, SILK_CAP, SILK_CAP_EM, SILK_CHANGES,
                    SILK_FONT, SILK_LABEL, SILK_PITCH, TITLE, flux_nets)
from draw_sch import uid as sch_uid
from sexpr import KICAD, ROOT, Sym, dump, find, first, parse

BOARD = FLUX["boards"][0]
LIB = ROOT / "hw/lib/balancio.pretty"
MODELS = "${KICAD10_3DMODEL_DIR}/"
# The built board has one GND stitching via that Flux's JSON export leaves out (Gerber pad "via.stitch.6").
EXTRA_VIAS = [dict(net="GND", center=dict(x=-30.1725, y=-0.6015), diameterMm=0.6, holeDiameterMm=0.3)]
HOLES = ["H1", "H2", "H3", "H4"]  # board mounting holes, Flux "Pad 1".."Pad 4"
# Design rules: what the built board has (JLCPCB made it and it works), so DRC passes on it as built.
# Flux poured GND at 0.5 mm from other nets, but its tessellated arcs come as close as 0.473 mm.
ZONE_CLEARANCE = 0.47
RULES = dict(min_clearance=0.12, min_track_width=0.15, min_hole_clearance=0.18, min_copper_edge_clearance=0.4,
             min_via_diameter=0.6, min_through_hole_diameter=0.3, min_via_annular_width=0.15, min_hole_to_hole=0.25)
NETCLASS = dict(clearance=0.12, track_width=0.254, via_diameter=0.6, via_drill=0.3, microvia_diameter=0.3,
                microvia_drill=0.1, diff_pair_gap=0.25, diff_pair_width=0.2, diff_pair_via_gap=0.25, wire_width=6,
                bus_width=12, line_style=0, schematic_color="rgba(0, 0, 0, 0.000)", pcb_color="rgba(0, 0, 0, 0.000)")
POWER_NETS = ["PWR8", "PWR37", "Net41", "Net47"]  # Flux rule "PISTAS GRUESAS": 30 mil tracks


def S(*a):
    return [Sym(a[0]), *a[1:]]


def uid(*k):
    return sch_uid("pcb", *k)


def r4(v):
    return round(v + 0.0, 4)


def font(size=1.0, thick=0.15):
    return S("effects", S("font", S("size", size, size), S("thickness", thick)))


# ---- footprints: Flux pads in footprint-local coordinates ----

def local(comp_center, rot, pt):
    """Board point (Flux, y-up) -> footprint-local point (KiCad, y-down)."""
    a = math.radians(-rot)
    dx, dy = pt["x"] - comp_center["x"], pt["y"] - comp_center["y"]
    return r4(dx * math.cos(a) - dy * math.sin(a)), r4(-(dx * math.sin(a) + dy * math.cos(a)))


def pads_of(comp):
    """[(number, kind, shape, (x, y), local angle, (w, h), rratio, drill)] in footprint-local coordinates."""
    pl, ref = comp["placement"], comp["designator"]
    out = []
    for p in pl["pads"]:
        num = PIN_NUMBERS.get(ref, {}).get(p["pin"], p["pin"])
        ang = (p.get("rotationDegrees", 0) - pl["rotationDegrees"]) % 180  # every pad shape is 180° symmetric
        w, h = p["widthMm"], p["heightMm"]
        if p["type"] == "non-plated-hole":
            out.append(("", "np_thru_hole", "circle", local(pl["center"], pl["rotationDegrees"], p["center"]), 0,
                        (p["holeWidthMm"],) * 2, None, p["holeWidthMm"]))
            continue
        assert p.get("holeWidthMm") == p.get("holeHeightMm"), "slotted holes are not handled"
        r = p.get("cornerRadiusMm") or 0
        shape = "circle" if p["shape"] == "circle" else "roundrect" if r else "rect"
        out.append((num, "smd" if p["type"] == "smd" else "thru_hole", shape,
                    local(pl["center"], pl["rotationDegrees"], p["center"]), ang, (w, h),
                    round(min(r / min(w, h), 0.5), 4) if r else None, p.get("holeWidthMm")))
    return sorted(out, key=lambda q: (q[0], q[3]))


def pad_node(p, rot=0, net=None):
    num, kind, shape, (x, y), ang, (w, h), rr, drill = p
    # non-plated holes get no mask opening: the built board's mask runs up to them and the drill cuts it
    layers = {"smd": ("F.Cu", "F.Paste", "F.Mask"), "thru_hole": ("*.Cu", "*.Mask"), "np_thru_hole": ("*.Cu",)}[kind]
    node = S("pad", num, Sym(kind), Sym(shape), S("at", x, y, (ang + rot) % 360), S("size", w, h))
    if drill:
        node.append(S("drill", drill))
    node.append(S("layers", *layers))
    if rr:
        node.append(S("roundrect_rratio", rr))
    if net:
        node.append(S("net", *net))
    return node


def footprint_body(name, pads, rot=0, nets=None, ref="REF**", value=None, fields=()):
    model = FOOTPRINTS.get(name, (None, None))[1]
    smd = all(p[1] == "smd" for p in pads)
    body = [S("attr", Sym("smd" if smd else "through_hole"), *([Sym("board_only"), Sym("exclude_from_pos_files"),
                                                                Sym("exclude_from_bom")] if name.startswith("Mounting")
                                                               else []))]
    # The built silkscreen carries the designators as drawn strokes, so the KiCad fields stay hidden.
    body += [S("property", "Reference", ref, S("at", 0, 0, rot), S("layer", "F.SilkS"), S("hide", Sym("yes")),
               S("uuid", uid("ref", ref, name)), font()),
             S("property", "Value", value or name, S("at", 0, 0, rot), S("layer", "F.Fab"), S("hide", Sym("yes")),
               S("uuid", uid("val", ref, name)), font())]
    body += [S("property", k, v, S("at", 0, 0, rot), S("layer", "F.Fab"), S("hide", Sym("yes")), S("uuid", uid(k, ref)),
               font()) for k, v in fields]
    body += [pad_node(p, rot, nets.get(p[0]) if nets else None) + [S("uuid", uid("pad", ref, i))]
             for i, p in enumerate(pads)]
    if model and model.startswith("flux/"):
        offset, angles = flux_model(FOOTPRINTS[name][0].split()[0])
        body.append(S("model", "${KIPRJMOD}/../" + model, S("offset", S("xyz", *offset)),
                      S("scale", S("xyz", 1, 1, 1)), S("rotate", S("xyz", *angles))))
    elif model:
        rot_z, (tx, ty) = model_fit(model, pads)
        # model offsets are y-up, unlike footprint coordinates, and a positive z rotation turns clockwise
        body.append(S("model", MODELS + model + ".step", S("offset", S("xyz", tx, -ty or 0, 0)),
                      S("scale", S("xyz", 1, 1, 1)), S("rotate", S("xyz", 0, 0, -rot_z % 360))))
    return body


def flux_model(ref):
    """KiCad model offset and rotation that put Flux's STEP for this part where Flux's GLB export has it.

    GLB (meters, y-up) -> board (mm, z-up): x - 45, 45 - z, y - 1.4936 (the board surface). The GLB mesh is the
    STEP turned y-up, so STEP -> board = C @ R(node) @ C^-1. KiCad applies Rz(-rz) Ry(-ry) Rx(-rx) to the model,
    then the footprint's rotation.
    """
    data = (ROOT / "balancio-board.glb").read_bytes()
    gltf = json.loads(data[20:20 + struct.unpack("<I", data[12:16])[0]])
    node = next(n for n in gltf["nodes"] if n.get("name") == ref)
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    q = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
         [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    to_board = [[1, 0, 0], [0, 0, -1], [0, 1, 0]]  # GLB axes -> board axes; its transpose undoes it
    mul = lambda a, b: [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    tr = lambda a: [list(r) for r in zip(*a)]
    pl = next(c["placement"] for c in FLUX["components"] if c["designator"] == ref)
    a = math.radians(-pl["rotationDegrees"])
    unturn = [[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]]
    r = mul(unturn, mul(to_board, mul(q, tr(to_board))))
    gx, gy, gz = (v * 1000 for v in node["translation"])
    d = (gx - 45 - pl["center"]["x"], 45 - gz - pl["center"]["y"], gy - 1.4936)
    offset = [r4(sum(unturn[i][k] * d[k] for k in range(3))) for i in range(3)]
    b = -math.asin(max(-1, min(1, r[2][0])))
    c, a_ = math.atan2(r[2][1], r[2][2]), math.atan2(r[1][0], r[0][0])
    return offset, [round(-math.degrees(v), 3) % 360 for v in (c, b, a_)]


def model_fit(model, pads):
    """Rotation and offset that put KiCad's library footprint's pins (its 3D model's frame) on these pads.

    Flux's footprints are KiCad's turned or shifted for some parts (pin 1 elsewhere, origin at the body centre).
    """
    lib_dir, name = model.split("/")
    kicad = parse((KICAD / "footprints" / lib_dir.replace(".3dshapes", ".pretty") / f"{name}.kicad_mod").read_text())
    theirs = {}
    for p in find(kicad, "pad"):
        theirs.setdefault(str(p[1]), []).append((float(first(p, "at")[1]), float(first(p, "at")[2])))
    ours = {}
    for p in pads:
        ours.setdefault(p[0], []).append(p[3])
    pairs = [(theirs[n][0], q[0]) for n, q in ours.items() if len(q) == 1 and len(theirs.get(n, [])) == 1]
    best = None
    for rot in (0, 90, 180, 270):  # counter-clockwise as seen from the top
        c, s_ = round(math.cos(math.radians(rot))), round(math.sin(math.radians(rot)))
        moved = [((x * c + y * s_, -x * s_ + y * c), o) for (x, y), o in pairs]
        t = tuple(sum(o[i] - k[i] for k, o in moved) / len(moved) for i in (0, 1))
        err = max(math.dist((k[0] + t[0], k[1] + t[1]), o) for k, o in moved)
        if best is None or err < best[0]:
            best = (err, rot, (r4(t[0]), r4(t[1])))
    assert best[0] < 0.5, f"{name}: no orientation puts KiCad's pins on the Flux pads"
    return best[1], best[2]


def library():
    """{footprint name: pads}, checking every part that shares a footprint has the same pads."""
    lib = {}
    for c in FLUX["components"]:
        name, pads = FOOTPRINT_OF[c["designator"]], pads_of(c)
        if name in lib:
            assert all(a[:3] == b[:3] and a[4:] == b[4:] and math.dist(a[3], b[3]) < 1e-3 for a, b in zip(lib[name], pads)) \
                   and len(lib[name]) == len(pads), f"{c['designator']} pads differ from other {name} parts"
        lib[name] = pads
    hole = BOARD["pads"][0]
    lib["MountingHole_3mm"] = [("", "np_thru_hole", "circle", (0, 0), 0, (hole["holeWidthMm"],) * 2, None,
                                hole["holeWidthMm"])]
    return lib


def write_library(lib):
    LIB.mkdir(parents=True, exist_ok=True)
    for old in LIB.glob("*.kicad_mod"):
        old.unlink()
    for name, pads in lib.items():
        fp = S("footprint", name, S("version", 20240108), S("generator", "balancio"), S("layer", "F.Cu"),
               S("descr", "Pads as on the built Balancio board (from Flux)"), *footprint_body(name, pads))
        (LIB / f"{name}.kicad_mod").write_text(dump(fp) + "\n")


# ---- polygons ----

def area(pts):
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1])) / 2


def inside(pt, poly):
    x, y, c = pt[0], pt[1], False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            c = not c
    return c


def fracture(outline, holes):
    """One outline with holes -> a single contour with zero-width bridges, as KiCad stores filled polygons.

    Each hole, taken left to right, is joined by a horizontal bridge from its leftmost point to the nearest edge
    on its left, so no bridge crosses a hole not yet joined.
    """
    poly = outline if area(outline) > 0 else outline[::-1]
    for hole in sorted(holes, key=lambda h: min(p[0] for p in h)):
        hole = hole if area(hole) < 0 else hole[::-1]
        k = min(range(len(hole)), key=lambda i: hole[i])
        hx, hy = hole[k]
        best = None
        for i, ((x1, y1), (x2, y2)) in enumerate(zip(poly, poly[1:] + poly[:1])):
            if y1 != y2 and min(y1, y2) <= hy <= max(y1, y2):
                x = x1 + (hy - y1) * (x2 - x1) / (y2 - y1)
                if x <= hx and (best is None or x > best[0]):
                    best = (x, i)
        assert best, "hole outside its outline"
        x, i = best
        ring = hole[k:] + hole[:k + 1]
        poly = poly[:i + 1] + [(x, hy)] + ring + [(x, hy)] + poly[i + 1:]
    return poly


def pts(poly):
    return S("pts", *[S("xy", r4(x), r4(-y)) for x, y in poly])


# ---- back label: IBM Plex Mono outlines read straight from the TrueType file ----

def glyph_outlines():
    """{char: (advance, [contours in font units])} for the label's characters (simple glyphs only)."""
    data = (ROOT / "hw/fonts" / SILK_FONT).read_bytes()
    n = struct.unpack(">H", data[4:6])[0]
    tables = {data[12 + 16 * i:16 + 16 * i].decode(): struct.unpack(">II", data[20 + 16 * i:28 + 16 * i])
              for i in range(n)}
    t = lambda tag: data[tables[tag][0]:tables[tag][0] + tables[tag][1]]
    head, hhea, hmtx, loca, glyf, cmap = t("head"), t("hhea"), t("hmtx"), t("loca"), t("glyf"), t("cmap")
    upem, long_loca = struct.unpack(">H", head[18:20])[0], struct.unpack(">h", head[50:52])[0]
    n_metrics = struct.unpack(">H", hhea[34:36])[0]
    # cmap format 4 (Windows Unicode BMP)
    for i in range(struct.unpack(">H", cmap[2:4])[0]):
        plat, enc, off = struct.unpack(">HHI", cmap[4 + 8 * i:12 + 8 * i])
        if (plat, enc) == (3, 1):
            break
    sub = cmap[off:]
    assert struct.unpack(">H", sub[:2])[0] == 4
    seg = struct.unpack(">H", sub[6:8])[0] // 2
    ends = struct.unpack(f">{seg}H", sub[14:14 + 2 * seg])
    starts = struct.unpack(f">{seg}H", sub[16 + 2 * seg:16 + 4 * seg])
    deltas = struct.unpack(f">{seg}h", sub[16 + 4 * seg:16 + 6 * seg])
    ro_at = 16 + 6 * seg
    ranges = struct.unpack(f">{seg}H", sub[ro_at:ro_at + 2 * seg])

    def gid(ch):
        c = ord(ch)
        for s_ in range(seg):
            if starts[s_] <= c <= ends[s_]:
                if not ranges[s_]:
                    return (c + deltas[s_]) & 0xFFFF
                at = ro_at + 2 * s_ + ranges[s_] + 2 * (c - starts[s_])
                g = struct.unpack(">H", sub[at:at + 2])[0]
                return (g + deltas[s_]) & 0xFFFF if g else 0
        return 0

    def offset(g):
        return struct.unpack(">I", loca[4 * g:4 * g + 4])[0] if long_loca else 2 * struct.unpack(">H", loca[2 * g:2 * g + 2])[0]

    out = {}
    for ch in set("".join(SILK_LABEL)):
        g = gid(ch)
        adv = struct.unpack(">H", hmtx[4 * min(g, n_metrics - 1):][:2])[0]
        start, stop = offset(g), offset(g + 1)
        contours = []
        if stop > start:
            b = glyf[start:stop]
            nc = struct.unpack(">h", b[:2])[0]
            assert nc >= 0, f"composite glyph for {ch!r} is not handled"
            end_pts = struct.unpack(f">{nc}H", b[10:10 + 2 * nc])
            npts = end_pts[-1] + 1
            p = 10 + 2 * nc
            p += 2 + struct.unpack(">H", b[p:p + 2])[0]  # skip hinting instructions
            flags = []
            while len(flags) < npts:
                f = b[p]
                p += 1
                flags.append(f)
                if f & 8:
                    flags += [f] * b[p]
                    p += 1
            coords = []
            for short, same in ((2, 16), (4, 32)):
                v, vals = 0, []
                for f in flags:
                    if f & short:
                        v += b[p] if f & same else -b[p]
                        p += 1
                    elif not f & same:
                        v += struct.unpack(">h", b[p:p + 2])[0]
                        p += 2
                    vals.append(v)
                coords.append(vals)
            pts_ = list(zip(coords[0], coords[1], (f & 1 for f in flags)))
            s0 = 0
            for e in end_pts:
                contours.append(flatten(pts_[s0:e + 1]))
                s0 = e + 1
        out[ch] = adv, contours
    return upem, out


def flatten(c, steps=6):
    """TrueType quadratic contour [(x, y, on_curve)] -> polyline."""
    if not any(on for _, _, on in c):
        c = [((c[0][0] + c[1][0]) / 2, (c[0][1] + c[1][1]) / 2, 1)] + c
    k = next(i for i, q in enumerate(c) if q[2])
    c = c[k:] + c[:k]
    out, prev, ctrl = [c[0][:2]], c[0][:2], None
    for x, y, on in c[1:] + c[:1]:
        if on:
            end = (x, y)
        elif ctrl is None:
            ctrl = (x, y)
            continue
        else:
            end = ((ctrl[0] + x) / 2, (ctrl[1] + y) / 2)
        if ctrl:
            out += [((1 - t) ** 2 * prev[0] + 2 * (1 - t) * t * ctrl[0] + t * t * end[0],
                     (1 - t) ** 2 * prev[1] + 2 * (1 - t) * t * ctrl[1] + t * t * end[1])
                    for t in (i / steps for i in range(1, steps + 1))]
        else:
            out.append(end)
        prev, ctrl = end, (None if on else (x, y))
    return out[:-1]


def label_polygons():
    """Back label as filled polygons in Flux board coordinates, mirrored so it reads from below."""
    upem, glyphs = glyph_outlines()
    s = SILK_CAP / SILK_CAP_EM / upem
    polys = []
    for i, line in enumerate(SILK_LABEL):
        base, u = SILK_AT[1] - SILK_CAP - i * SILK_PITCH, 0
        for ch in line:
            adv, contours = glyphs[ch]
            rings = [[(SILK_AT[0] - (u + x) * s, base + y * s) for x, y in c] for c in contours]
            for r in rings:
                if not any(inside(r[0], o) for o in rings if o is not r):
                    polys.append(fracture(r, [h for h in rings if h is not r and inside(h[0], r)]))
            u += adv
    return polys


# ---- silkscreen from the built board's Gerber ----

def front_silk(gerber_zip, comps):
    """{ref: [(a, b, width)]} of the built front silkscreen, each stroke group given to the nearest part."""
    with zipfile.ZipFile(gerber_zip) as z:
        name = next(n for n in z.namelist() if n.endswith("/yg/balancio-board-f_silks.gbr"))
        segs = [s[1:] for s in parse_gerber(z.read(name).decode())]
    drop = [w for layer, w in SILK_CHANGES if layer == "F_Silkscreen"]
    within = lambda p, w: w[0] <= p[0] <= w[2] and w[1] <= p[1] <= w[3]
    segs = [s for s in segs if not any(within(s[0], w) and within(s[1], w) for w in drop)]
    # group strokes that touch (glyphs, outlines)
    parent = list(range(len(segs)))
    find = lambda i: i if parent[i] == i else find(parent[i])
    at = {}
    for i, (a, b, _) in enumerate(segs):
        for p in (a, b):
            key = (round(p[0], 2), round(p[1], 2))
            if key in at:
                parent[find(i)] = find(at[key])
            at[key] = i
    groups = {}
    for i in range(len(segs)):
        groups.setdefault(find(i), []).append(segs[i])
    pad_pts = {c["designator"]: [(p["center"]["x"], p["center"]["y"]) for p in c["placement"]["pads"]] for c in comps}
    out = {}
    for g in groups.values():
        ends = [p for a, b, _ in g for p in (a, b)]
        score = lambda ref: sum(min(math.dist(e, q) for q in pad_pts[ref]) for e in ends) / len(ends)
        out.setdefault(min(pad_pts, key=score), []).extend(g)
    return out


# ---- board ----

def kicad_nets(netlist):
    pin_net = {}
    for n in ET.parse(netlist).getroot().find("nets"):
        for node in n:
            pin_net[(node.get("ref"), node.get("pin"))] = n.get("name")
    names = sorted(set(pin_net.values()))
    code = {name: i + 1 for i, name in enumerate(names)}
    # Flux net name -> KiCad net name, through the pins they share (check_netlist.py proved they match 1:1)
    flux = {}
    for fname, members in flux_nets().items():
        kn = {pin_net[m] for m in members}
        assert len(kn) == 1, f"Flux net {fname} maps to {kn}"
        flux[fname] = kn.pop()
    return pin_net, code, flux


def main(netlist, gerber_zip):
    lib = library()
    write_library(lib)
    pin_net, code, flux_to_kicad = kicad_nets(netlist)
    fnet = lambda fname: S("net", code[flux_to_kicad[fname]])  # tracks, vias and zones carry the net number only

    items = []
    comps = FLUX["components"]
    silk = front_silk(gerber_zip, comps)
    for c in comps:
        ref, pl = c["designator"], c["placement"]
        assert pl["side"] == "top"
        name, rot = FOOTPRINT_OF[ref], pl["rotationDegrees"] % 360
        x, y = r4(pl["center"]["x"]), r4(-pl["center"]["y"])
        nets = {num: (code[pin_net[(ref, num)]], pin_net[(ref, num)]) for num, *_ in lib[name] if (ref, num) in pin_net}
        fp = S("footprint", f"balancio:{name}", S("layer", "F.Cu"), S("uuid", uid("fp", ref)), S("at", x, y, rot),
               *footprint_body(name, lib[name], rot, nets, ref, PARTS[ref]["value"],
                               [("MPN", PARTS[ref]["mpn"]), ("Manufacturer", PARTS[ref]["mfr"]),
                                ("LCSC", PARTS[ref]["lcsc"])]),
               S("path", "/" + sch_uid("sym", ref)), S("sheetname", "/"), S("sheetfile", "balancio.kicad_sch"))
        # the part's share of the built silkscreen, in footprint-local coordinates
        for i, (a, b, w) in enumerate(silk.get(ref, [])):
            la, lb = (local(pl["center"], rot, dict(x=p[0], y=p[1])) for p in (a, b))
            fp.insert(-3, S("fp_line", S("start", *la), S("end", *lb), S("stroke", S("width", w), S("type", Sym("solid"))),
                            S("layer", "F.SilkS"), S("uuid", uid("silk", ref, i))))
        items.append(fp)
    for h, p in zip(HOLES, BOARD["pads"]):
        items.append(S("footprint", "balancio:MountingHole_3mm", S("layer", "F.Cu"), S("uuid", uid("fp", h)),
                       S("at", r4(p["center"]["x"]), r4(-p["center"]["y"]), 0),
                       *footprint_body("MountingHole_3mm", lib["MountingHole_3mm"], 0, None, h, "MountingHole_3mm")))

    o = BOARD["outline"]
    xs, ys = [p["x"] for p in o], [p["y"] for p in o]
    assert len(o) == 4 and len(set(xs)) == 2 and len(set(ys)) == 2, "board outline is not a rectangle"
    items.append(S("gr_rect", S("start", min(xs), -max(ys)), S("end", max(xs), -min(ys)),
                   S("stroke", S("width", 0.05), S("type", Sym("solid"))), S("fill", Sym("none")),
                   S("layer", "Edge.Cuts"), S("uuid", uid("edge"))))
    for i, poly in enumerate(label_polygons()):
        items.append(S("gr_poly", pts(poly), S("stroke", S("width", 0), S("type", Sym("solid"))), S("fill", Sym("solid")),
                       S("layer", "B.SilkS"), S("uuid", uid("label", i))))

    layer = {"top": "F.Cu", "bottom": "B.Cu", "Top Copper": "F.Cu", "Bottom Copper": "B.Cu"}
    for i, t in enumerate(BOARD["traces"]):
        s, e = t["start"], t["end"]
        items.append(S("segment", S("start", r4(s["x"]), r4(-s["y"])), S("end", r4(e["x"]), r4(-e["y"])),
                       S("width", t["widthMm"]), S("layer", layer[t["layer"]]), fnet(t["net"]), S("uuid", uid("seg", i))))
    for i, v in enumerate(BOARD["vias"] + EXTRA_VIAS):
        c = v["center"]
        items.append(S("via", S("at", r4(c["x"]), r4(-c["y"])), S("size", v["diameterMm"]), S("drill", v["holeDiameterMm"]),
                       S("layers", "F.Cu", "B.Cu"), fnet(v["net"]), S("uuid", uid("via", i))))
    edge = [(min(xs), min(ys)), (max(xs), min(ys)), (max(xs), max(ys)), (min(xs), max(ys))]
    for f in BOARD["copperFills"]:
        lay = layer[f["layer"]]
        # Flux's fill is kept as computed, so the Gerbers match the built board until someone refills (B)
        fills = [S("filled_polygon", S("layer", lay),
                   pts(fracture([(p["x"], p["y"]) for p in a["outline"]], [[(p["x"], p["y"]) for p in h]
                                                                             for h in a.get("holes", [])])))
                 for a in f["areas"]]
        items.append(S("zone", fnet(f["net"]), S("net_name", flux_to_kicad[f["net"]]), S("layer", lay),
                       S("uuid", uid("zone", lay)), S("hatch", Sym("edge"), 0.5),
                       S("connect_pads", Sym("yes"), S("clearance", ZONE_CLEARANCE)),  # solid, as Flux poured
                       S("min_thickness", 0.25), S("filled_areas_thickness", Sym("no")),
                       S("fill", Sym("yes"), S("thermal_gap", 0.5), S("thermal_bridge_width", 0.5)),
                       S("polygon", pts(edge)), *fills))

    stack = [("F.SilkS", "Top Silk Screen", [S("color", "White")]), ("F.Paste", "Top Solder Paste", []),
             ("F.Mask", "Top Solder Mask", [S("color", "Black"), S("thickness", 0.01)]),
             ("F.Cu", "copper", [S("thickness", 0.035)]),
             ("dielectric 1", "core", [S("thickness", 1.51), S("material", "FR4"), S("epsilon_r", 4.5),
                                       S("loss_tangent", 0.02)]),
             ("B.Cu", "copper", [S("thickness", 0.035)]),
             ("B.Mask", "Bottom Solder Mask", [S("color", "Black"), S("thickness", 0.01)]),
             ("B.Paste", "Bottom Solder Paste", []), ("B.SilkS", "Bottom Silk Screen", [S("color", "White")])]
    layers = [(0, "F.Cu", "signal"), (31, "B.Cu", "signal"), (32, "B.Adhes", "user", "B.Adhesive"),
              (33, "F.Adhes", "user", "F.Adhesive"), (34, "B.Paste", "user"), (35, "F.Paste", "user"),
              (36, "B.SilkS", "user", "B.Silkscreen"), (37, "F.SilkS", "user", "F.Silkscreen"),
              (38, "B.Mask", "user"), (39, "F.Mask", "user"), (40, "Dwgs.User", "user", "User.Drawings"),
              (41, "Cmts.User", "user", "User.Comments"), (44, "Edge.Cuts", "user"), (45, "Margin", "user"),
              (46, "B.CrtYd", "user", "B.Courtyard"), (47, "F.CrtYd", "user", "F.Courtyard"),
              (48, "B.Fab", "user"), (49, "F.Fab", "user")]
    pcb = S("kicad_pcb", S("version", 20240108), S("generator", "balancio"), S("generator_version", "8.0"),
            S("general", S("thickness", 1.6), S("legacy_teardrops", Sym("no"))), S("paper", "A4"),
            S("title_block", S("title", TITLE), S("date", date.today().isoformat()), S("rev", REV),
              S("comment", 1, "Copied from the built Flux board; Gerbers checked against it by scripts/build.sh")),
            S("layers", *[S(n, name, Sym(kind), *rest) for n, name, kind, *rest in layers]),
            S("setup", S("stackup", *[S("layer", n, S("type", t), *extra) for n, t, extra in stack],
                         S("copper_finish", "HAL lead-free"), S("dielectric_constraints", Sym("no"))),
              S("pad_to_mask_clearance", 0), S("allow_soldermask_bridges_in_footprints", Sym("no"))),
            S("net", 0, ""), *[S("net", i, name) for name, i in code.items()], *items)
    out = ROOT / "hw/balancio.kicad_pcb"
    out.write_text(dump(pcb) + "\n")
    power = [flux_to_kicad[n] for n in POWER_NETS]
    (ROOT / "hw/balancio.kicad_pro").write_text(json.dumps({
        "board": {"design_settings": {
            "rules": RULES,
            # each footprint carries its own share of the built silkscreen, so it differs from the library copy
            "rule_severities": {"lib_footprint_mismatch": "ignore"}}},
        "meta": {"filename": "balancio.kicad_pro", "version": 3},
        "net_settings": {"classes": [dict(name="Default", priority=2147483647, **NETCLASS),
                                     dict(NETCLASS, name="Power", priority=0, track_width=0.762)],
                         "meta": {"version": 4},
                         "netclass_patterns": [{"netclass": "Power", "pattern": n} for n in power]},
    }, indent=2) + "\n")
    # Two things the built board does below the general rules: Flux's pours reach a few GND pads through a
    # single thermal spoke, and one GND track passes the J2 pin 2 via at 0.119 mm.
    j2 = flux_to_kicad[next(n for n, m in flux_nets().items() if ("J2", "2") in m)]
    (ROOT / "hw/balancio.kicad_dru").write_text(
        '(version 1)\n(rule "as built: single-spoke thermals"\n\t(constraint min_resolved_spokes 1))\n'
        '(rule "pours keep clear of mounting holes, as Flux poured them"\n'
        f'\t(condition "A.Type == \'Zone\' && B.Pad_Type == \'NPTH, mechanical\'")\n'
        f'\t(constraint hole_clearance (min {ZONE_CLEARANCE}mm)))\n'
        f'(rule "as built: GND track by the J2 pin 2 via"\n\t(condition "A.NetName == \'GND\' && B.NetName == \'{j2}\'")'
        '\n\t(constraint clearance (min 0.119mm)))\n')
    print("wrote", out, f"{len(comps) + len(HOLES)} footprints ({len(lib)} in the library),",
          len(BOARD["traces"]), "tracks,", len(BOARD["vias"]) + len(EXTRA_VIAS), "vias", file=sys.stderr)


if __name__ == "__main__":
    main(*sys.argv[1:])

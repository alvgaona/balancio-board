"""Draw hw/balancio.kicad_sch: hand-placed layout, wired inside each block, net labels only between blocks.

Coordinates are schematic mm (y down) on the 1.27 mm grid. Wires must end on pins or on other wires;
junction dots and no-connect flags are added automatically. check_netlist.py then proves the result
connects exactly what the Flux board connects.
"""
import math
import sys
import uuid
from datetime import date

from design import FOOTPRINT_OF, PARTS, REV, TITLE
from sexpr import ROOT, Sym, dump, find, first, get_symbol, pins

PROJECT = "balancio"
NS = uuid.UUID("0c3f6a52-8b1e-4d7e-9a4b-5d2e7c1f9a30")
ROOT_UUID = str(uuid.uuid5(NS, "root"))
P = 2.54
POWER_LIB = {"GND": "power:GND", "+3V3": "power:+3V3", "VIN": "balancio:VIN", "VBAT": "balancio:VBAT",
             "BAT-": "balancio:BAT-", "FLAG": "power:PWR_FLAG"}


def uid(*k):
    return str(uuid.uuid5(NS, "/".join(map(str, k))))


def r2(v):
    return round(v + 0.0, 2)


def eff(size=1.27, just=None, hide=False, bold=False):
    f = [Sym("font"), [Sym("size"), size, size]] + ([[Sym("bold"), Sym("yes")]] if bold else [])
    return [Sym("effects"), f] + ([[Sym("justify"), *map(Sym, just.split())]] if just else []) + \
        ([[Sym("hide"), Sym("yes")]] if hide else [])


class Placed:
    def __init__(self, ref, lib, x, y, a, mirror):
        self.ref, self.lib, self.x, self.y, self.a, self.mirror = ref, lib, x, y, a, mirror
        self.fields = {}

    def T(self, px, py):
        """Library point (y up) -> schematic point (y down)."""
        if self.mirror == "y":
            px = -px
        if self.mirror == "x":
            py = -py
        r = math.radians(self.a)
        rx, ry = px * math.cos(r) - py * math.sin(r), px * math.sin(r) + py * math.cos(r)
        return r2(self.x + rx), r2(self.y - ry)

    def __getitem__(self, num):
        return self.pins[num][0]


class Sheet:
    def __init__(self):
        self.symdefs, self.parts, self.wires, self.labels, self.extra = {}, [], [], [], []
        self.n = {"#PWR": 0, "#FLG": 0}
        self.blocks = []

    # ---- placing ----
    def place(self, ref, x, y, a=0, mirror=None, lib=None, ref_at=None, val_at=None, value=None, hide_val=False):
        assert not (mirror and a), "mirror only with rotation 0"
        lib = lib or PARTS[ref]["sym"]
        if lib not in self.symdefs:
            self.symdefs[lib] = get_symbol(lib)
        d = self.symdefs[lib]
        s = Placed(ref, lib, x, y, a, mirror)
        s.pins = {num: (s.T(px, py), name, typ) for num, (name, px, py, _, typ) in pins(d).items()}
        val = value if value is not None else (PARTS[ref]["value"] if ref in PARTS else lib.split(":")[1])
        if ref.startswith("#"):  # power port / flag: keep the library's field placement
            props = {p[1]: first(p, "at") for p in find(d, "property")}
            s.fields = {"Reference": (ref, *s.T(float(props["Reference"][1]), float(props["Reference"][2])), None, True),
                        "Value": (val, *s.T(float(props["Value"][1]), float(props["Value"][2])), None, hide_val)}
        else:
            box = self._box(s, d)
            two_pin = lib.startswith("Device:")
            if two_pin and a in (0, 180):
                dr, dv = (x + P, y - 1.27, "left"), (x + P, y + 1.27, "left")
            elif two_pin:
                dr, dv = (x, y - P, None), (x, y + P, None)
            else:
                dr, dv = (box[0], box[1] - 1.27, "left"), (box[0], box[3] + 1.27, "left")
            rx, ry, rj = ref_at or dr
            vx, vy, vj = val_at or dv
            s.fields = {"Reference": (ref, rx, ry, rj, False), "Value": (val, vx, vy, vj, hide_val)}
        self.parts.append(s)
        return s

    def _box(self, s, d):
        pts = []
        for sub in find(d, "symbol"):
            for r in find(sub, "rectangle"):
                pts += [s.T(float(first(r, "start")[1]), float(first(r, "start")[2])),
                        s.T(float(first(r, "end")[1]), float(first(r, "end")[2]))]
        pts = pts or [p[0] for p in s.pins.values()]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)

    def power(self, name, pt, a=0):
        kind = "#FLG" if name == "FLAG" else "#PWR"
        self.n[kind] += 1
        return self.place(f"{kind}{self.n[kind]:02d}", pt[0], pt[1], a, lib=POWER_LIB[name],
                          hide_val=name in ("GND", "FLAG"))

    # ---- connecting ----
    def w(self, *pts):
        for a, b in zip(pts, pts[1:]):
            a, b = (r2(a[0]), r2(a[1])), (r2(b[0]), r2(b[1]))
            assert a[0] == b[0] or a[1] == b[1], f"wire not orthogonal: {a} {b}"
            if a != b:
                self.wires.append((a, b))

    def label(self, name, pt, a=0):
        self.labels.append((name, (r2(pt[0]), r2(pt[1])), a))

    # ---- annotation ----
    def text(self, s, x, y, size=1.27, bold=False):
        self.extra.append([Sym("text"), s, [Sym("exclude_from_sim"), Sym("no")], [Sym("at"), x, y, 0],
                           eff(size, "left bottom", bold=bold), [Sym("uuid"), uid("text", s, x, y)]])

    def frame(self, x1, y1, x2, y2, title):
        self.extra.append([Sym("rectangle"), [Sym("start"), x1, y1], [Sym("end"), x2, y2],
                           [Sym("stroke"), [Sym("width"), 0.254], [Sym("type"), Sym("dash")]],
                           [Sym("fill"), [Sym("type"), Sym("none")]], [Sym("uuid"), uid("frame", title)]])
        self.text(title, x1 + 2.54, y1 + 5.08, 2, bold=True)

    def block(self, title, col, row, draw):
        """Draw a block anywhere; arrange() later moves it into its cell of the page grid."""
        mark = len(self.parts), len(self.wires), len(self.labels), len(self.extra)
        draw(self)
        stop = len(self.parts), len(self.wires), len(self.labels), len(self.extra)
        pts = []
        for s in self.parts[mark[0]:]:
            b = self._box(s, self.symdefs[s.lib])
            pts += [(b[0], b[1]), (b[2], b[3])] + [pt for pt, _, _ in s.pins.values()]
            pts += [(x + d * len(v) * 0.55, y) for v, x, y, _, h in s.fields.values() if not h for d in (-1, 1)]
        pts += [p for seg in self.wires[mark[1]:] for p in seg] + [p for _, p, _ in self.labels[mark[2]:]]
        for t in self.extra[mark[3]:]:
            x, y = float(first(t, "at")[1]), float(first(t, "at")[2])
            pts += [(x, y - 1.27), (x + len(t[1]) * 1.05, y)]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        self.blocks.append(dict(title=title, col=col, row=row, mark=mark, stop=stop,
                                box=(min(xs), min(ys), max(xs), max(ys))))

    def arrange(self, margin=7.62, gap=5.08, title=7.62, area=(12.7, 12.7, 406.4, 251.46)):
        """Aligned grid of frames sized to their contents, centred on the page above the title block."""
        snap = lambda v: round(v / P) * P
        cols, rows = {}, {}
        for b in self.blocks:
            x1, y1, x2, y2 = b["box"]
            cols[b["col"]] = max(cols.get(b["col"], 0), x2 - x1 + 2 * margin)
            rows[b["row"]] = max(rows.get(b["row"], 0), y2 - y1 + 2 * margin + title)
        W = sum(cols.values()) + gap * (len(cols) - 1)
        H = sum(rows.values()) + gap * (len(rows) - 1)
        x0 = snap(area[0] + (area[2] - area[0] - W) / 2)
        y0 = snap(area[1] + (area[3] - area[1] - H) / 2)
        for b in self.blocks:
            cx1 = x0 + sum(cols[c] for c in cols if c < b["col"]) + gap * b["col"]
            cy1 = y0 + sum(rows[r] for r in rows if r < b["row"]) + gap * b["row"]
            cx2, cy2 = cx1 + cols[b["col"]], cy1 + rows[b["row"]]
            x1, y1, x2, y2 = b["box"]
            dx = snap((cx1 + cx2) / 2 - (x1 + x2) / 2)
            dy = snap((cy1 + title + cy2) / 2 - (y1 + y2) / 2)
            mv = lambda pt: (r2(pt[0] + dx), r2(pt[1] + dy))
            (p0, w0, l0, e0), (p1, w1, l1, e1) = b["mark"], b["stop"]
            for s in self.parts[p0:p1]:
                s.x, s.y = mv((s.x, s.y))
                s.pins = {n: (mv(pt), name, typ) for n, (pt, name, typ) in s.pins.items()}
                s.fields = {k: (v, *mv((x, y)), j, h) for k, (v, x, y, j, h) in s.fields.items()}
            self.wires[w0:w1] = [(mv(a), mv(c)) for a, c in self.wires[w0:w1]]
            self.labels[l0:l1] = [(n, mv(pt), a) for n, pt, a in self.labels[l0:l1]]
            for t in self.extra[e0:e1]:
                at = first(t, "at")
                at[1], at[2] = mv((float(at[1]), float(at[2])))
            self.frame(r2(cx1), r2(cy1), r2(cx2), r2(cy2), b["title"])

    # ---- output ----
    def finish(self):
        pin_pts = {}
        for s in self.parts:
            for num, (pt, _, _) in s.pins.items():
                pin_pts.setdefault(pt, []).append((s.ref, num))

        def inside(p, seg):
            (x1, y1), (x2, y2) = seg
            return (x1 == x2 == p[0] and min(y1, y2) < p[1] < max(y1, y2)) or \
                   (y1 == y2 == p[1] and min(x1, x2) < p[0] < max(x1, x2))

        # split wires wherever another wire ends, or a pin sits, on them (KiCad connects those points)
        changed = True
        while changed:
            changed = False
            ends = {p for seg in self.wires for p in seg} | set(pin_pts)
            for seg in list(self.wires):
                for p in ends:
                    if inside(p, seg):
                        self.wires.remove(seg)
                        self.wires += [(seg[0], p), (p, seg[1])]
                        changed = True
                        break
                if changed:
                    break
        ends = {}
        for seg in self.wires:
            for p in seg:
                ends[p] = ends.get(p, 0) + 1
        juncs = [p for p, k in ends.items() if k >= 2 and k + len(pin_pts.get(p, [])) >= 3]
        touched = set(ends) | {p for _, p, _ in self.labels}

        items = []
        for s in self.parts:
            items.append(self._symbol(s))
            if s.ref.startswith("#"):
                continue
            want = PARTS[s.ref]["pins"]
            for num, (pt, name, typ) in s.pins.items():
                shared = len(pin_pts[pt]) > 1
                if num in want and pt not in touched and not shared:
                    sys.exit(f"{s.ref} pin {num} ({name}) should be on net {want[num]} but nothing touches it")
                if num not in want and typ != "no_connect":
                    if pt in touched or shared:
                        sys.exit(f"{s.ref} pin {num} ({name}) has no net in Flux but is wired")
                    items.append([Sym("no_connect"), [Sym("at"), *pt], [Sym("uuid"), uid("nc", s.ref, num)]])
        for a, b in self.wires:
            items.append([Sym("wire"), [Sym("pts"), [Sym("xy"), *a], [Sym("xy"), *b]],
                          [Sym("stroke"), [Sym("width"), 0], [Sym("type"), Sym("default")]], [Sym("uuid"), uid("w", a, b)]])
        for p in juncs:
            items.append([Sym("junction"), [Sym("at"), *p], [Sym("diameter"), 0], [Sym("color"), 0, 0, 0, 0],
                          [Sym("uuid"), uid("j", p)]])
        for name, p, a in self.labels:
            items.append([Sym("label"), name, [Sym("at"), *p, a], [Sym("fields_autoplaced"), Sym("yes")],
                          eff(1.27, "left bottom" if a == 0 else "right bottom"), [Sym("uuid"), uid("l", name, p)]])
        sch = [Sym("kicad_sch"), [Sym("version"), 20231120], [Sym("generator"), "eeschema"],
               [Sym("generator_version"), "8.0"], [Sym("uuid"), ROOT_UUID], [Sym("paper"), "A3"],
               [Sym("title_block"), [Sym("title"), TITLE], [Sym("date"), date.today().isoformat()], [Sym("rev"), REV],
                [Sym("comment"), 1, "Rev 1.0 migrated from Flux (flux/project.json); Rev 1.1 changes in scripts/design.py; netlist checked by scripts/build.sh"]],
               [Sym("lib_symbols")] + list(self.symdefs.values())] + items + self.extra + \
              [[Sym("sheet_instances"), [Sym("path"), "/", [Sym("page"), "1"]]]]
        out = ROOT / "hw" / f"{PROJECT}.kicad_sch"
        out.write_text(dump(sch) + "\n")
        print("wrote", out, len(self.parts), "symbols,", len(self.wires), "wires,", len(juncs), "junctions,",
              len(self.labels), "labels")

    def _symbol(self, s):
        virtual = s.ref.startswith("#")
        p = None if virtual else PARTS[s.ref]
        node = [Sym("symbol"), [Sym("lib_id"), s.lib], [Sym("at"), s.x, s.y, s.a]]
        if s.mirror:
            node.append([Sym("mirror"), Sym(s.mirror)])
        node += [[Sym("unit"), 1], [Sym("exclude_from_sim"), Sym("no")],
                 [Sym("in_bom"), Sym("yes" if p and p["bom"] else "no")],
                 [Sym("on_board"), Sym("no" if virtual else "yes")], [Sym("dnp"), Sym("no")], [Sym("uuid"), uid("sym", s.ref)]]
        flip = {"left": "right", "right": "left"} if s.a == 180 or s.mirror == "y" else {}
        for k, (v, x, y, just, hide) in s.fields.items():
            node.append([Sym("property"), k, v, [Sym("at"), x, y, s.a % 180], eff(1.27, flip.get(just, just), hide)])
        hidden = [("Footprint", f"balancio:{FOOTPRINT_OF[s.ref]}" if p else ""), ("Datasheet", "~"), ("Description", "")]
        if p:
            hidden += [("MPN", p["mpn"]), ("Manufacturer", p["mfr"]), ("LCSC", p["lcsc"])]
        for k, v in hidden:
            node.append([Sym("property"), k, v, [Sym("at"), s.x, s.y, 0], eff(hide=True)])
        for num in s.pins:
            node.append([Sym("pin"), num, [Sym("uuid"), uid("pin", s.ref, num)]])
        node.append([Sym("instances"), [Sym("project"), PROJECT, [Sym("path"), "/" + ROOT_UUID,
                                                                 [Sym("reference"), s.ref], [Sym("unit"), 1]]]])
        return node


def power_block(s):
    j4 = s.place("J4", 30.48, 45.72, a=180, ref_at=(30.48, 39.37, None), val_at=(30.48, 52.07, None))
    s.text("2S Li-ion pack: 1 = B-, 2 = mid-cell, 3 = B+", 15.24, 58.42)
    # Rev 1.1 soft-latch power switch (see design.py): Q3 high side, R10 holds it off, SW2 or Q4 turn it on
    q3 = s.place("Q3", 160.02, 40.64, a=270, ref_at=(160.02, 46.99, None), val_at=(160.02, 49.53, None))
    s.w(j4["3"], q3["1"])  # VBAT rail
    s.w((45.72, 43.18), (45.72, 40.64))
    s.power("VBAT", (45.72, 40.64))
    s.power("FLAG", (45.72, 40.64))
    s.w(q3["5"], (190.5, 43.18))
    s.power("VIN", (182.88, 43.18))
    s.power("FLAG", (182.88, 43.18))
    r10 = s.place("R10", 149.86, 31.75)
    s.w(r10["2"], (149.86, 43.18))
    s.w(r10["1"], (149.86, 22.86), (165.1, 22.86))  # gate line
    s.w(q3["4"], (160.02, 22.86))
    q4 = s.place("Q4", 167.64, 27.94, mirror="y", ref_at=(167.64, 31.75, "left"), val_at=(167.64, 34.29, "left"))
    s.power("GND", q4["2"])
    s.w(q4["1"], (185.42, 27.94))
    s.label("PWR_HOLD", (185.42, 27.94))
    r11 = s.place("R11", 177.8, 31.75)
    s.power("GND", r11["2"])
    d1 = s.place("D1", 152.4, 17.78, a=180, ref_at=(161.29, 12.7, "left"), val_at=(161.29, 15.24, "left"))
    s.w(d1["1"], (160.02, 22.86))
    s.w(d1["3"], (152.4, 5.08))
    sw = s.place("SW2", 157.48, 5.08, ref_at=(157.48, -2.54, None), val_at=(157.48, 0, None))
    s.power("GND", sw["2"])
    s.w(d1["2"], (132.08, 17.78))
    s.label("PWR_BTN", (132.08, 17.78), 180)
    r12 = s.place("R12", 139.7, 13.97)
    s.power("+3V3", r12["1"])
    s.text("Power button: press to turn on; firmware holds PWR_HOLD high,", 116.84, 53.34)
    s.text("reads PWR_BTN (low = pressed) and turns off on a long press", 116.84, 55.88)
    r13 = s.place("R13", 190.5, 46.99)
    r14 = s.place("R14", 190.5, 57.15)
    s.w(r13["2"], r14["1"])
    c10 = s.place("C10", 200.66, 57.15)
    s.w(r14["1"], c10["1"], (208.28, 53.34))
    s.label("PWR_SENSE", (208.28, 53.34))
    s.power("GND", r14["2"])
    s.power("GND", c10["2"])

    s.w(j4["1"], (45.72, 48.26))
    s.power("BAT-", (45.72, 48.26), a=180)
    s.power("FLAG", (45.72, 48.26), a=180)

    u3 = s.place("U3", 88.9, 66.04, ref_at=(95.25, 59.69, "left"), val_at=(95.25, 62.23, "left"))
    r7 = s.place("R7", 71.12, 52.07, ref_at=(68.58, 50.8, "right"), val_at=(68.58, 53.34, "right"))
    s.w((71.12, 43.18), r7["1"])
    s.w(r7["2"], (71.12, 58.42), (88.9, 58.42), u3["5"])
    c8 = s.place("C8", 78.74, 62.23, ref_at=(76.2, 60.96, "right"), val_at=(76.2, 63.5, "right"))
    s.w((78.74, 58.42), c8["1"])
    s.power("BAT-", c8["2"], a=180)

    r8 = s.place("R8", 63.5, 73.66, a=90)
    s.w(j4["2"], (50.8, 45.72), (50.8, 73.66), r8["1"])
    s.w(r8["2"], u3["4"])
    c9 = s.place("C9", 71.12, 77.47)
    s.w((71.12, 73.66), c9["1"])
    s.power("BAT-", c9["2"], a=180)
    s.w(u3["6"], (88.9, 81.28))
    s.power("BAT-", (88.9, 81.28), a=180)

    r9 = s.place("R9", 104.14, 74.93)
    s.w(u3["3"], r9["1"])
    s.power("GND", r9["2"])

    q1 = s.place("Q1", 124.46, 76.2, ref_at=(118.11, 69.85, "right"), val_at=(118.11, 72.39, "right"))
    q2 = s.place("Q2", 149.86, 76.2, mirror="y", ref_at=(156.21, 69.85, "left"), val_at=(156.21, 72.39, "left"))
    s.w(u3["1"], (152.4, 66.04), q2["4"])  # OD -> both charge-side gates
    s.w((121.92, 66.04), q1["4"])
    s.w(u3["2"], (101.6, 68.58))  # OC -> both discharge-side gates
    s.label("OC", (101.6, 68.58))
    s.w(q1["5"], (127, 68.58), (147.32, 68.58), q2["5"])
    s.label("OC", (134.62, 68.58))
    for q, x, port in ((q1, 114.3, "BAT-"), (q2, 160.02, "BAT-")):
        s.w(q["2"], (x, 76.2), (x, 81.28))
        s.w(q["3"], (x, 78.74))
        s.power(port, (x, 81.28), a=180)
    s.w(q1["7"], (134.62, 76.2), (134.62, 81.28), (139.7, 81.28), (139.7, 76.2), q2["7"])
    s.w(q1["6"], (134.62, 78.74))
    s.w(q2["6"], (139.7, 78.74))
    s.power("GND", (137.16, 81.28))
    s.power("FLAG", (137.16, 81.28))
    s.w(q1["1"], (121.92, 86.36), (152.4, 86.36), q2["1"])  # common drains
    s.w(q1["8"], (127, 86.36))
    s.w(q2["8"], (147.32, 86.36))
    s.text("Q1 || Q2: common-drain FET pairs in the B- line; board GND is pack - after the FETs", 15.24, 93.98)


def mcu_block(s):
    ex, ey = 99.06, 129.54
    u1 = s.place("U1", ex, ey)
    row = lambda i: ey + i * P
    (x3, yt), (xv, _), (xg, yb) = u1["1"], u1["30"], u1["29"]
    u1.fields["Reference"] = ("U1", xv + 7.62, yt + 1.27, "left", False)
    u1.fields["Value"] = (u1.fields["Value"][0], xg + P, yb + 5.08, "left", False)
    s.w(u1["1"], (x3, yt - P), (x3 - 5.08, yt - P))
    s.power("+3V3", (x3 - 5.08, yt - P))
    s.power("FLAG", (x3 - 5.08, yt - P))
    s.text("+3V3 from the DevKit's regulator", x3 - 33.02, yt - 10.16)
    s.w(u1["30"], (xv, yt - P), (xv + 5.08, yt - P))
    s.power("VIN", (xv + 5.08, yt - P))
    s.w(u1["2"], (u1["2"][0], yb + P), (xg, yb + P), u1["29"])
    s.power("GND", (ex, yb + P))

    # left: connectors wired straight across (mirrored so their pins face the module)
    conns = (("J6", 0, "UART0: 3V3 / RX0 / TX0 / GND"), ("J5", 6, "UART2: 3V3 / RX2 / TX2 / GND"),
             ("J7", 12, "D2 / D4 / D5 / D15"), ("J3", 17, "D33 / D32 / D35 / D34"))
    for ref, r, note in conns:
        j = s.place(ref, 60.96, row(r) + P, mirror="y", ref_at=(57.15, row(r), "right"),
                    val_at=(57.15, row(r) + P, "right"))
        s.text(note, 15.24, row(r) + 2 * P + 0.64)
        for k in "1234":
            mine = PARTS[ref]["pins"][k]
            if mine in ("PWR38", "GND"):
                s.w(j[k], (68.58, j[k][1]))
                s.power("+3V3" if mine == "PWR38" else "GND", (68.58, j[k][1]))
            else:
                s.w(j[k], u1[[n for n, net in PARTS["U1"]["pins"].items() if net == mine][0]])

    # right: RGB LED, three anodes driven from GPIO, cathode resistors to GND
    led = s.place("LED1", 124.46, row(0), ref_at=(124.46, row(0) - 3.81, None), val_at=(124.46, row(4) + 3.81, None))
    for a, k, res, r in (("1", "6", "R6", 0), ("2", "5", "R5", 2), ("3", "4", "R4", 4)):
        s.w(u1[[n for n, net in PARTS["U1"]["pins"].items() if net == PARTS["LED1"]["pins"][a]][0]], led[a])
        rr = s.place(res, 139.7, row(r), a=90, ref_at=(137.16, row(r) - 1.91, None), val_at=(142.24, row(r) - 1.91, None))
        s.w(led[k], rr["1"])
        s.w(rr["2"], (147.32, row(r)))
    s.w((147.32, row(0)), (147.32, row(4) + P))
    s.power("GND", (147.32, row(4) + P))

    # right: signals that leave the block
    for pin, name in (("24", "SDA"), ("25", "SCL"), ("14", "MOT_IN1"), ("11", "MOT_IN2"), ("10", "MOT_IN3"),
                      ("9", "MOT_IN4"), ("15", "MOT_ENA"), ("23", "PWR_HOLD"), ("18", "PWR_BTN"), ("17", "PWR_SENSE")):
        end = (u1[pin][0] + 5.08, u1[pin][1])
        s.w(u1[pin], end)
        s.label(name, end)


def motor_block(s):
    ux, uy = 248.92, 63.5
    u2 = s.place("U2", ux, uy, ref_at=(ux - 10.16, uy + 13.97, "left"), val_at=(ux + 2.54, uy + 13.97, "left"))
    for pin, name in (("1", "MOT_ENA"), ("16", "MOT_IN1"), ("15", "MOT_IN2"), ("9", "MOT_IN3"), ("10", "MOT_IN4")):
        end = (u2[pin][0] - 5.08, u2[pin][1])
        s.w(u2[pin], end)
        s.label(name, end, 180)
    s.w(u2["11"], (218.44, u2["11"][1]))
    c6 = s.place("C6", 218.44, 52.07, a=180, ref_at=(215.9, 50.8, "right"), val_at=(215.9, 53.34, "right"))
    s.power("VIN", c6["2"])
    s.w(u2["3"], (233.68, u2["3"][1]), (233.68, u2["6"][1]), u2["6"])
    s.w((233.68, u2["6"][1]), (228.6, u2["6"][1]))
    s.power("GND", (228.6, u2["6"][1]))
    s.text("Sense pins grounded: no current limit", 198.12, 88.9)

    s.w(u2["12"], (256.54, 33.02), (266.7, 33.02))
    s.power("VIN", (256.54, 33.02))
    c7 = s.place("C7", 266.7, 36.83)
    s.power("GND", c7["2"])
    s.w(u2["14"], (254, 38.1), (236.22, 38.1))
    c5 = s.place("C5", 236.22, 41.91)
    s.power("GND", c5["2"])
    s.w((243.84, 38.1), (243.84, 35.56))
    s.power("FLAG", (243.84, 35.56))
    s.power("GND", u2["13"])

    j2 = s.place("J2", 274.32, 68.58, mirror="x", ref_at=(276.86, 66.04, "left"), val_at=(276.86, 68.58, "left"))
    j1 = s.place("J1", 274.32, 71.12, ref_at=(276.86, 71.12, "left"), val_at=(276.86, 73.66, "left"))
    s.w(u2["2"], j2["2"])
    s.w(u2["4"], j2["1"])
    s.w(u2["7"], j1["1"])
    s.w(u2["5"], j1["2"])
    s.text("Motor A", 302.26, 67.31)
    s.text("Motor B", 302.26, 72.39)


def imu_block(s):
    ix, iy = 276.86, 152.4
    ic1 = s.place("IC1", ix, iy, ref_at=(ix - 12.7, iy + 16.51, "left"), val_at=(ix + 3.81, iy + 20.32, "left"))
    s.w(ic1["24"], (251.46, 144.78))
    s.label("SDA", (251.46, 144.78), 180)
    s.w(ic1["23"], (238.76, 147.32))
    s.label("SCL", (238.76, 147.32), 180)
    r2_ = s.place("R2", 254, 140.97, ref_at=(256.54, 137.16, "left"), val_at=(256.54, 139.7, "left"))
    r3 = s.place("R3", 243.84, 143.51, ref_at=(241.3, 139.7, "right"), val_at=(241.3, 142.24, "right"))
    s.w(r3["1"], (243.84, 134.62), (254, 134.62), r2_["1"])
    s.power("+3V3", (248.92, 134.62))
    s.w(ic1["9"], (248.92, 149.86))
    r1 = s.place("R1", 248.92, 153.67, a=180)  # pin 2 on AD0, as on the built board
    s.power("GND", r1["1"])
    s.w(ic1["11"], (256.54, 157.48), (256.54, 162.56))
    s.w(ic1["1"], (256.54, 160.02))
    s.power("GND", (256.54, 162.56))

    s.w(ic1["8"], (274.32, 124.46), (299.72, 124.46))
    s.w(ic1["13"], (279.4, 124.46))
    s.power("+3V3", (274.32, 124.46))
    for ref, x in (("C3", 287.02), ("C4", 299.72)):
        c = s.place(ref, x, 128.27)
        s.power("GND", c["2"])
    s.power("GND", ic1["18"])

    s.w(ic1["20"], (314.96, 157.48))
    c1 = s.place("C1", 314.96, 161.29, ref_at=(312.42, 160.02, "right"), val_at=(312.42, 162.56, "right"))
    s.power("GND", c1["2"])
    s.w(ic1["10"], (299.72, 160.02))
    c2 = s.place("C2", 299.72, 163.83)
    s.power("GND", c2["2"])


if __name__ == "__main__":
    sheet = Sheet()
    sheet.block("Battery: 2S protection and soft-latch power switch", 0, 0, power_block)
    sheet.block("ESP32 DevKit, status LED, connectors", 0, 1, mcu_block)
    sheet.block("Motor driver", 1, 0, motor_block)
    sheet.block("IMU (I2C address 0x68)", 1, 1, imu_block)
    sheet.arrange()
    sheet.finish()

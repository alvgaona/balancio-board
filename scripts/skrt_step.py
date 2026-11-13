#!/usr/bin/env python3
"""Write the 3D model of SW2, the Alps SKRTLAE010 side-push switch, as STEP: neither KiCad's library nor the
vendor (automated download refused) gives one. Dimensions from the Alps SKRT drawing (4.5 x 2.56 x 3.3 body,
Ø2 actuator 1.7 up and 0.84 out, Ø0.7 guide bosses 4.25 apart and 0.45 deep), in the footprint's frame
(SW_Push_1P1T-MP_NO_Horizontal_Alps_SKRTLAE010: actuator towards +y). Planar faces only; the round parts are
16-sided prisms. Usage: skrt_step.py [out.step]"""
import math
import sys

OUT = sys.argv[1] if len(sys.argv) > 1 else "hw/lib/balancio.3dshapes/SW_Push_1P1T-MP_NO_Horizontal_Alps_SKRTLAE010.step"


def box(x0, x1, y0, y1, z0, z1):
    return prism([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], "z", z0, z1)


def disc(cu, cv, r, n=16):
    return [(cu + r * math.cos(2 * math.pi * k / n), cv + r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def prism(poly, axis, a0, a1):
    """Convex polygon in the plane across `axis`, extruded from a0 to a1: (vertices, faces as vertex indices)."""
    put = {"z": lambda u, v, w: (u, v, w), "y": lambda u, v, w: (u, w, v)}[axis]
    n = len(poly)
    verts = [put(u, v, a0) for u, v in poly] + [put(u, v, a1) for u, v in poly]
    faces = [list(range(n)), list(range(n, 2 * n))] + [[k, (k + 1) % n, n + (k + 1) % n, n + k] for k in range(n)]
    return verts, faces


TERM, METAL, BODY, KEY = (0.85, 0.85, 0.82), (0.62, 0.63, 0.66), (0.16, 0.16, 0.17), (0.93, 0.93, 0.9)
SOLIDS = [
    (box(-2.25, 2.25, -1.35, 1.21, 0.15, 3.3), METAL),                   # shell over the base
    (prism(disc(0, 1.7, 1.0), "y", 1.21, 2.05), KEY),                     # actuator, pushed along -y
    (prism(disc(-2.125, 0, 0.35), "z", -0.45, 0.15), BODY),               # guide bosses, in the Ø0.9 holes
    (prism(disc(2.125, 0, 0.35), "z", -0.45, 0.15), BODY),
    (box(-1.55, -0.9, -1.75, -0.6, 0, 0.15), TERM),                       # terminals 1, 2, 3 (pads 1, 2, 1)
    (box(-0.25, 0.25, -1.75, -0.6, 0, 0.15), TERM),
    (box(0.9, 1.55, -1.75, -0.6, 0, 0.15), TERM),
    (box(-2.25, -1.45, 0.75, 1.21, 0, 0.8), METAL),                       # shell legs on the MP pads
    (box(1.45, 2.25, 0.75, 1.21, 0, 0.8), METAL),
]


class Step:
    def __init__(self):
        self.lines = []

    def add(self, s):
        self.lines.append(s)
        return f"#{len(self.lines)}"

    def pt(self, p):
        return self.add("CARTESIAN_POINT('',(%s));" % ",".join(f"{c:.6f}" for c in p))

    def dir(self, d):
        return self.add("DIRECTION('',(%s));" % ",".join(f"{c:.9f}" for c in d))


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def norm(a):
    m = math.sqrt(sum(x * x for x in a))
    return tuple(x / m for x in a)


def newell(ps):
    return norm(tuple(sum(f(ps[i], ps[(i + 1) % len(ps)]) for i in range(len(ps))) for f in (
        lambda a, b: (a[1] - b[1]) * (a[2] + b[2]), lambda a, b: (a[2] - b[2]) * (a[0] + b[0]),
        lambda a, b: (a[0] - b[0]) * (a[1] + b[1]))))


def solid(st, verts, faces):
    verts = [(x, -y, z) for x, y, z in verts]  # footprint y points down the board, the model's y points up
    c = tuple(sum(v[i] for v in verts) / len(verts) for i in range(3))
    vp = [st.add(f"VERTEX_POINT('',{st.pt(v)});") for v in verts]
    edges, uses, out = {}, {}, []
    for f in faces:
        ps = [verts[i] for i in f]
        nrm = newell(ps)
        if sum(n * d for n, d in zip(nrm, sub(ps[0], c))) < 0:  # convex: outward normal points away from centre
            f, nrm = f[::-1], tuple(-n for n in nrm)
        oes = []
        for a, b in zip(f, f[1:] + f[:1]):
            uses[(a, b)] = uses.get((a, b), 0) + 1
            key = (min(a, b), max(a, b))
            if key not in edges:
                d = sub(verts[key[1]], verts[key[0]])
                vec = st.add(f"VECTOR('',{st.dir(norm(d))},1.);")
                ln = st.add(f"LINE('',{st.pt(verts[key[0]])},{vec});")
                edges[key] = st.add(f"EDGE_CURVE('',{vp[key[0]]},{vp[key[1]]},{ln},.T.);")
            oes.append(st.add(f"ORIENTED_EDGE('',*,*,{edges[key]},{'.T.' if a < b else '.F.'});"))
        loop = st.add(f"EDGE_LOOP('',({','.join(oes)}));")
        bound = st.add(f"FACE_OUTER_BOUND('',{loop},.T.);")
        ref = norm(sub(ps[1], ps[0]))
        ax = st.add(f"AXIS2_PLACEMENT_3D('',{st.pt(ps[0])},{st.dir(nrm)},{st.dir(ref)});")
        plane = st.add(f"PLANE('',{ax});")
        out.append(st.add(f"ADVANCED_FACE('',({bound}),{plane},.T.);"))
    # closed manifold: every edge used once in each direction
    assert set(uses.values()) == {1} and all((b, a) in uses for a, b in uses)
    shell = st.add(f"CLOSED_SHELL('',({','.join(out)}));")
    return st.add(f"MANIFOLD_SOLID_BREP('',{shell});")


def main():
    st = Step()
    ctx = st.add("APPLICATION_CONTEXT('automotive design');")
    st.add(f"APPLICATION_PROTOCOL_DEFINITION('international standard','automotive_design',2000,{ctx});")
    pctx = st.add(f"PRODUCT_CONTEXT('',{ctx},'mechanical');")
    prod = st.add(f"PRODUCT('SKRTLAE010','Alps SKRTLAE010 side-push switch','',({pctx}));")
    form = st.add(f"PRODUCT_DEFINITION_FORMATION('','',{prod});")
    dctx = st.add(f"PRODUCT_DEFINITION_CONTEXT('part definition',{ctx},'design');")
    pdef = st.add(f"PRODUCT_DEFINITION('design','',{form},{dctx});")
    pshape = st.add(f"PRODUCT_DEFINITION_SHAPE('','',{pdef});")
    mm = st.add("(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT(.MILLI.,.METRE.));")
    rad = st.add("(NAMED_UNIT(*)PLANE_ANGLE_UNIT()SI_UNIT($,.RADIAN.));")
    sr = st.add("(NAMED_UNIT(*)SI_UNIT($,.STERADIAN.)SOLID_ANGLE_UNIT());")
    unc = st.add(f"UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-07),{mm},'distance_accuracy_value','');")
    gctx = st.add(f"(GEOMETRIC_REPRESENTATION_CONTEXT(3)GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT(({unc}))"
                  f"GLOBAL_UNIT_ASSIGNED_CONTEXT(({mm},{rad},{sr}))REPRESENTATION_CONTEXT('',''));")
    origin = st.add(f"AXIS2_PLACEMENT_3D('',{st.pt((0, 0, 0))},{st.dir((0, 0, 1))},{st.dir((1, 0, 0))});")
    breps, styles = [], []
    for (verts, faces), rgb in SOLIDS:
        b = solid(st, verts, faces)
        col = st.add("COLOUR_RGB('',%s);" % ",".join(f"{c:.3f}" for c in rgb))
        fac = st.add(f"FILL_AREA_STYLE_COLOUR('',{col});")
        fill = st.add(f"FILL_AREA_STYLE('',({fac}));")
        sfa = st.add(f"SURFACE_STYLE_FILL_AREA({fill});")
        side = st.add(f"SURFACE_SIDE_STYLE('',({sfa}));")
        ssu = st.add(f"SURFACE_STYLE_USAGE(.BOTH.,{side});")
        psa = st.add(f"PRESENTATION_STYLE_ASSIGNMENT(({ssu}));")
        styles.append(st.add(f"STYLED_ITEM('color',({psa}),{b});"))
        breps.append(b)
    rep = st.add(f"ADVANCED_BREP_SHAPE_REPRESENTATION('SKRTLAE010',({origin},{','.join(breps)}),{gctx});")
    st.add(f"SHAPE_DEFINITION_REPRESENTATION({pshape},{rep});")
    st.add(f"MECHANICAL_DESIGN_GEOMETRIC_PRESENTATION_REPRESENTATION('',({','.join(styles)}),{gctx});")
    head = ["ISO-10303-21;", "HEADER;", "FILE_DESCRIPTION(('Alps SKRTLAE010, generated by scripts/skrt_step.py'),'2;1');",
            "FILE_NAME('SW_Push_1P1T-MP_NO_Horizontal_Alps_SKRTLAE010.step','2026-11-13T00:00:00',(''),(''),'','','');",
            "FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));", "ENDSEC;", "DATA;"]
    body = [f"#{i}={s}" for i, s in enumerate(st.lines, 1)]
    with open(OUT, "w") as fh:
        fh.write("\n".join(head + body + ["ENDSEC;", "END-ISO-10303-21;", ""]))
    print(f"{OUT}: {len(SOLIDS)} solids")


if __name__ == "__main__":
    main()

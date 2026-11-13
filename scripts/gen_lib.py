"""Generate hw/lib/balancio.kicad_sym: symbols for the parts with no matching KiCad library symbol, plus power ports.

Pin numbers and names come from the Flux parts. Pins are grouped by function, with empty rows where
draw_sch.py needs room to wire a connector straight across.
"""
import math

from design import FLUX, PIN_NUMBERS
from sexpr import ROOT, Sym, dump, get_symbol

P = 2.54
NAME_FIX = {("U1", "GND_1"): "GND"}

# Pin numbers per side: L/R top to bottom, T/B left to right. None = empty row.
SPECS = {
    "ESP32-DEVKIT-V1": ("U1", "U", dict(
        T=["1", "30"], B=["2", "29"],
        L=[None, "12", "13", None, None, None, None, "6", "7", None, None, None,
           "4", "5", "8", "3", None, "22", "21", "20", "19"],
        R=["26", None, "28", None, "27", None, None, "24", "25", None,
           "14", "11", "10", "9", "15", None, None, "16", "17", "18", "23"], pad=2)),
    "HY2120": ("U3", "U", dict(T=["5"], B=["6"], L=[None, None, None, "4"], R=["1", "2", "3", None])),
    "AP8205A": ("Q1", "Q", dict(T=["4", "5"], B=["1", "8"], L=["2", "3"], R=["7", "6"])),
}


def font(*extra):
    return [Sym("effects"), [Sym("font"), [Sym("size"), 1.27, 1.27]], *extra]


def prop(k, v, x, y, hide=False):
    return [Sym("property"), k, v, [Sym("at"), x, y, 0], font(*([[Sym("hide"), Sym("yes")]] if hide else []))]


def pin(num, name, x, y, ang):
    return [Sym("pin"), Sym("passive"), Sym("line"), [Sym("at"), round(x, 2), round(y, 2), ang], [Sym("length"), P],
            [Sym("name"), name, font()], [Sym("number"), num, font()]]


def head(name, ref, top, bottom, desc, pin_names=True):
    names = [Sym("pin_names"), [Sym("offset"), 1.016]] + ([] if pin_names else [[Sym("hide"), Sym("yes")]])
    return [Sym("symbol"), name, names, [Sym("exclude_from_sim"), Sym("no")], [Sym("in_bom"), Sym("yes")],
            [Sym("on_board"), Sym("yes")], prop("Reference", ref, 0, top + P), prop("Value", name, 0, bottom - P),
            prop("Footprint", "", 0, 0, True), prop("Datasheet", "", 0, 0, True), prop("Description", desc, 0, 0, True)]


def stroke(fill="none"):
    return [[Sym("stroke"), [Sym("width"), 0.254], [Sym("type"), Sym("default")]], [Sym("fill"), [Sym("type"), Sym(fill)]]]


def ic(name, ref, names, spec, desc):
    rows = max(len(spec["L"]), len(spec["R"]))
    spec = {k: v for k, v in spec.items()}
    spec.setdefault("T", []), spec.setdefault("B", [])
    cols = max(len(spec["T"]), len(spec["B"]))
    side_len = lambda s: max([len(names[n]) for n in spec[s] if n] or [0])
    w = max(5.08 * math.ceil(((side_len("L") + side_len("R")) * 1.2 + 4) / 5.08), 5.08 * (cols + 1))
    pad = spec.get("pad", 0) * P  # extra body above/below the side pins, for long top/bottom pin names
    top, bottom = P + pad, -rows * P - pad
    pins = []
    for side, x, ang in (("L", -w / 2 - P, 0), ("R", w / 2 + P, 180)):
        pins += [pin(n, names[n], x, -i * P, ang) for i, n in enumerate(spec[side]) if n]
    for side, y, ang in (("T", top + P, 270), ("B", bottom - P, 90)):
        k = len(spec[side])
        pins += [pin(n, names[n], (i - (k - 1) / 2) * 2 * P, y, ang) for i, n in enumerate(spec[side]) if n]
    body = [Sym("rectangle"), [Sym("start"), -w / 2, top], [Sym("end"), w / 2, bottom], *stroke("background")]
    return head(name, ref, top + P, bottom - P, desc) + [[Sym("symbol"), f"{name}_0_1", body],
                                                          [Sym("symbol"), f"{name}_1_1", *pins]]


def led_rgb(name, desc):
    """Three LEDs, anode pins 1-3 on the left, cathodes 6-4 on the right (the 5050 die pairs across: 1-6, 2-5, 3-4)."""
    def poly(*pts, fill="none"):
        return [Sym("polyline"), [Sym("pts"), *[[Sym("xy"), x, y] for x, y in pts]], *stroke(fill)]
    shapes, pins = [], []
    for i, (a, k) in enumerate((("1", "6"), ("2", "5"), ("3", "4"))):
        y = -i * 2 * P
        shapes += [poly((-5.08, y), (-1.27, y)), poly((1.27, y), (5.08, y)),
                   poly((-1.27, y + 1.27), (-1.27, y - 1.27), (1.27, y), (-1.27, y + 1.27), fill="outline"),
                   poly((1.27, y + 1.27), (1.27, y - 1.27))]
        pins += [pin(a, f"P{a}", -7.62, y, 0), pin(k, f"P{k}", 7.62, y, 180)]
    body = [Sym("rectangle"), [Sym("start"), -5.08, P], [Sym("end"), 5.08, -5 * P], *stroke("background")]
    return head(name, "LED", 2 * P, -6 * P, desc, pin_names=False) + [
        [Sym("symbol"), f"{name}_0_1", body, *shapes], [Sym("symbol"), f"{name}_1_1", *pins]]


def rename(node, old, new):
    if isinstance(node, list):
        return [rename(c, old, new) for c in node]
    if isinstance(node, Sym):
        return node
    return node.replace(old, new) if isinstance(node, str) else node


def power(name, template):
    """A power port named `name`, drawn like the KiCad `template` symbol."""
    lib, base = template.split(":")
    d = rename(get_symbol(template), base, name)
    d[1] = name
    return d


def main():
    comps = {c["designator"]: c for c in FLUX["components"]}
    syms = []
    for name, (ref, prefix, spec) in SPECS.items():
        c = comps[ref]
        num = PIN_NUMBERS.get(ref, {})
        names = {num.get(p["number"], p["number"]): NAME_FIX.get((ref, p["name"]), p["name"]) for p in c["pins"]}
        placed = [n for k, s in spec.items() if k in "LRTB" for n in s if n]
        assert sorted(placed) == sorted(names) and len(set(placed)) == len(placed), f"{name}: pins placed {placed}"
        syms.append(ic(name, prefix, names, spec, c["description"].split("\n")[0][:200]))
    syms.append(led_rgb("LED_RGB_5050-6", comps["LED1"]["description"].split("\n")[0][:200]))
    syms += [power("VIN", "power:VBUS"), power("VBAT", "power:VBUS"), power("BAT-", "power:-BATT")]
    lib = [Sym("kicad_symbol_lib"), [Sym("version"), 20231120], [Sym("generator"), "balancio_gen_lib"],
           [Sym("generator_version"), "8.0"], *syms]
    out = ROOT / "hw/lib/balancio.kicad_sym"
    out.write_text(dump(lib) + "\n")
    print("wrote", out, len(syms), "symbols")


if __name__ == "__main__":
    main()

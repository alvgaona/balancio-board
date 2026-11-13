"""Render the manufactured Flux board (flux/project.json) as top and bottom views: build/board-views.html.

Plain 2D view of the copper as built: solder mask, copper under mask, exposed pads, vias, drills, and part
outlines (bounding box of each part's pads) with reference designators. Not a 3D render.
"""
import json
import sys
from html import escape
from pathlib import Path

from design import ROOT, SILK_AT, SILK_CAP, SILK_CAP_EM, SILK_FONT, SILK_LABEL, SILK_PITCH

d = json.loads((ROOT / "flux/project.json").read_text())
board = d["boards"][0]
# JLCPCB black solder mask: copper under it shows as a slightly lighter black
MASK, COPPER, PAD, HOLE, SILK = "#141416", "#2a2a2e", "#d4a843", "#000", "#f5f5f0"


def view(side):
    mirror = side == "bottom"  # the bottom is seen from below, so x flips
    X = lambda x: -x if mirror else x
    Y = lambda y: -y  # Flux is y-up, SVG is y-down
    copper = "Top Copper" if side == "top" else "Bottom Copper"
    out = []
    pts = " ".join(f"{X(p['x'])},{Y(p['y'])}" for p in board["outline"])
    out.append(f'<polygon points="{pts}" fill="{MASK}" stroke="#c8c8c8" stroke-width="0.2"/>')
    for f in board["copperFills"]:
        if f["layer"] != copper:
            continue
        for a in f["areas"]:
            rings = [a["outline"]] + a.get("holes", [])
            path = " ".join("M" + " L".join(f"{X(p['x'])},{Y(p['y'])}" for p in r) + " Z" for r in rings)
            out.append(f'<path d="{path}" fill="{COPPER}" fill-rule="evenodd"/>')
    for t in board["traces"]:
        if t["layer"] == side:
            s, e = t["start"], t["end"]
            out.append(f'<line x1="{X(s["x"])}" y1="{Y(s["y"])}" x2="{X(e["x"])}" y2="{Y(e["y"])}" '
                       f'stroke="{COPPER}" stroke-width="{t["widthMm"]}" stroke-linecap="round"/>')
    for v in board["vias"]:
        c = v["center"]
        out.append(f'<circle cx="{X(c["x"])}" cy="{Y(c["y"])}" r="{v["diameterMm"] / 2}" fill="{COPPER}"/>'
                   f'<circle cx="{X(c["x"])}" cy="{Y(c["y"])}" r="{v["holeDiameterMm"] / 2}" fill="{HOLE}"/>')
    labels = []
    for comp in d["components"]:
        pads = comp["placement"]["pads"]
        xs, ys = [], []
        for p in pads:
            c, w, h = p["center"], p["widthMm"], p["heightMm"]
            cx, cy = X(c["x"]), Y(c["y"])
            r = p.get("rotationDegrees", 0)
            xs += [cx - max(w, h) / 2, cx + max(w, h) / 2]
            ys += [cy - max(w, h) / 2, cy + max(w, h) / 2]
            th = p["type"] != "smd"
            if p["type"] == "non-plated-hole":
                out.append(f'<circle cx="{cx}" cy="{cy}" r="{p["holeWidthMm"] / 2}" fill="{HOLE}"/>')
                continue
            if th or side == "top":
                if p["shape"] == "circle":
                    out.append(f'<circle cx="{cx}" cy="{cy}" r="{w / 2}" fill="{PAD}"/>')
                else:
                    rr = p.get("cornerRadiusMm", 0)
                    rot = r if mirror else -r
                    out.append(f'<rect x="{cx - w / 2}" y="{cy - h / 2}" width="{w}" height="{h}" rx="{rr}" '
                               f'fill="{PAD}" transform="rotate({rot} {cx} {cy})"/>')
            if th:
                out.append(f'<circle cx="{cx}" cy="{cy}" r="{p["holeWidthMm"] / 2}" fill="{HOLE}"/>')
        if side == "top" and xs:
            x1, y1, x2, y2 = min(xs) - 0.4, min(ys) - 0.4, max(xs) + 0.4, max(ys) + 0.4
            out.append(f'<rect x="{x1}" y="{y1}" width="{x2 - x1}" height="{y2 - y1}" fill="none" '
                       f'stroke="{SILK}" stroke-width="0.15" opacity="0.8"/>')
            c = comp["placement"]["center"]
            labels.append(f'<text x="{X(c["x"])}" y="{Y(c["y"])}" class="ref">{escape(comp["designator"])}</text>')
    if side == "bottom":
        for i, line in enumerate(SILK_LABEL):
            labels.append(f'<text x="{X(SILK_AT[0])}" y="{-(SILK_AT[1] - SILK_CAP - i * SILK_PITCH)}" class="label" '
                          f'font-size="{SILK_CAP / SILK_CAP_EM}">{escape(line)}</text>')
    for p in board["pads"]:  # board mounting holes
        c = p["center"]
        out.append(f'<circle cx="{X(c["x"])}" cy="{Y(c["y"])}" r="{p["holeWidthMm"] / 2}" fill="{HOLE}"/>')
    return (f'<svg viewBox="-37 -37 74 74" role="img" aria-label="Balancio board {side} view">'
            + "".join(out + labels) + "</svg>")


HTML = f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Balancio board views</title>
<style>
  body {{ margin: 0; font: 14px/1.4 var(--font-sans, system-ui, sans-serif); color: var(--foreground, #1d1d1b); }}
  .row {{ display: flex; flex-wrap: wrap; gap: 24px; justify-content: center; }}
  figure {{ margin: 0; flex: 1 1 360px; max-width: 560px; }}
  figcaption {{ font-weight: 600; margin-bottom: 6px; }}
  svg {{ width: 100%; height: auto; display: block; }}
  .ref {{ font: 1.15px ui-monospace, monospace; fill: {SILK}; text-anchor: middle; dominant-baseline: middle;
          paint-order: stroke; stroke: {MASK}; stroke-width: 0.35px; font-weight: 700; }}
  @font-face {{ font-family: "Silk Label"; src: url("../hw/fonts/{SILK_FONT}"); }}
  .label {{ font-family: "Silk Label", ui-monospace, monospace; fill: {SILK}; white-space: pre; }}
  p {{ color: var(--muted-foreground, #66665f); max-width: 1140px; margin: 16px auto 0; text-align: center; }}
</style></head><body>
<div class="row">
<figure><figcaption>Top (component side)</figcaption>{view("top")}</figure>
<figure><figcaption>Bottom (seen from below, mirrored)</figcaption>{view("bottom")}</figure>
</div>
<p>70 × 70 mm, 2 layers, from the Flux export. JLCPCB black solder mask. Gold: exposed pads; dark gray: copper under the mask;
black: drills. White boxes outline each part's pads. All parts are on the top side.</p>
</body></html>
"""

out = ROOT / "build/board-views.html"
out.parent.mkdir(exist_ok=True)
out.write_text(HTML)
print("wrote", out, file=sys.stderr)

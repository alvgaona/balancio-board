"""JLCPCB assembly files: BOM and CPL for the SMD parts, which JLCPCB places. The JST connectors and the DevKit
are through-hole and hand-soldered, so they are left out.

Usage: jlc.py <KiCad BOM csv> <KiCad pos csv, --smd-only> <out dir>
"""
import csv
import sys

bom, pos, out = sys.argv[1:]
rows = list(csv.DictReader(open(pos)))
smd = {r["Ref"] for r in rows}
with open(f"{out}/balancio-cpl.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
    for r in rows:
        w.writerow([r["Ref"], r["PosX"], r["PosY"], r["Side"].capitalize(), r["Rot"]])
missing = []
with open(bom) as f, open(f"{out}/balancio-bom.csv", "w", newline="") as g:
    rd, w = csv.DictReader(f), csv.writer(g)
    w.writerow(rd.fieldnames)
    for r in rd:
        refs = [x for x in r["Designator"].split(",") if x in smd]
        if refs:
            r["Designator"] = ",".join(refs)
            w.writerow(r.values())
            missing += refs if not r["LCSC Part #"] else []
print(f"JLCPCB files: {len(smd)} SMD parts", f"(no LCSC number, place by hand or pick one: {', '.join(missing)})"
      if missing else "")

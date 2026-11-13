"""Fail unless KiCad's exported netlist connects exactly the pins Flux connects (net names may differ)."""
import sys
import xml.etree.ElementTree as ET

from design import flux_nets

got = {}
for n in ET.parse(sys.argv[1]).getroot().find("nets"):
    conns = frozenset((x.get("ref"), x.get("pin")) for x in n if not x.get("ref").startswith("#"))
    if len(conns) > 1:
        got[conns] = n.get("name")
want = {frozenset(v): k for k, v in flux_nets().items()}
for conns in sorted(set(got) ^ set(want), key=sorted):
    side = f"KiCad {got[conns]}" if conns in got else f"Flux {want[conns]}"
    print("MISMATCH", side, sorted(conns))
bad = len(set(got) ^ set(want))
print(f"netlist check: {len(want)} Flux nets, {len(got)} KiCad nets, {bad} mismatches")
sys.exit(1 if bad else 0)

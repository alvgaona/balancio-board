"""Balancio board parts and netlist, read straight from the Flux export (flux/project.json).

The board was manufactured and works, so the KiCad schematic must connect exactly what Flux connects.
draw_sch.py draws it; check_netlist.py compares what KiCad exports against flux_nets().
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLUX = json.loads((ROOT / "flux/project.json").read_text())

REV = "1.0"
TITLE = "Balancio board"

# Back silkscreen label, Apple-style small print (replaces Flux's front "Balancio Board v0.1"), mirrored so it
# reads from below, left-aligned. Set in IBM Plex Mono Medium (hw/fonts, OFL): its thinnest stroke is the "e"
# crossbar, 70/1000 em, so 1.5 mm caps (2.149 mm em) keep every stroke >= 0.15 mm, the JLCPCB silkscreen minimum.
# SILK_AT is the block's top-left as read from the back, in Flux board mm (so its x is the block's max board x).
# Centered between the ESP32 header rows (pins x -13.4..22.1 at y -2.75 and 22.6). Vias sit in this area, so
# order with vias tented (JLCPCB "Tented", as the Gerber mask layers already draw them): the first batch was
# ordered with via openings (过孔开窗), and silkscreen can't print on exposed copper.
SILK_FONT, SILK_CAP_EM = "IBMPlexMono-Medium.ttf", 0.698  # cap height / em
SILK_LABEL = [
    f"Balancio Board  Rev {REV}",
    "Designed in the open by Balancio Team.",
    "Open hardware, CERN-OHL-S-2.0.",
]
SILK_AT, SILK_CAP, SILK_PITCH = (28.53, 13.1), 1.5, 2.2

# Parts with a matching KiCad library symbol (same pin numbers as the Flux part); the balancio: ones
# are built by gen_lib.py from the Flux pin lists. Everything else is Device:R or Device:C.
SYMBOLS = {"IC1": "Sensor_Motion:MPU-6050", "U2": "Driver_Motor:DRV8833PWP", "SW1": "Switch:SW_SPDT",
           "C7": "Device:C_Polarized", "J1": "Connector_Generic:Conn_01x02", "J2": "Connector_Generic:Conn_01x02",
           "J4": "Connector_Generic:Conn_01x03",
           "U1": "balancio:ESP32-DEVKIT-V1", "U3": "balancio:HY2120", "Q1": "balancio:AP8205A",
           "Q2": "balancio:AP8205A", "LED1": "balancio:LED_RGB_5050-6"}
for j in ("J3", "J5", "J6", "J7"):
    SYMBOLS[j] = "Connector_Generic:Conn_01x04"

# Flux names the HY2120 pads instead of numbering them. Numbers follow the pad positions on the built board
# (SOT-23-6, counter-clockwise from pin 1 at top-left, the same convention the other Flux footprints use).
PIN_NUMBERS = {"U3": {"OD": "1", "OC": "2", "CS": "3", "VC": "4", "VDD": "5", "VSS": "6"}}

PARTS = {}
for c in FLUX["components"]:
    ref = c["designator"]
    num = PIN_NUMBERS.get(ref, {})
    PARTS[ref] = dict(
        sym=SYMBOLS.get(ref) or {"R": "Device:R", "C": "Device:C"}[ref[0]],
        value=c.get("value") or c.get("manufacturerPartNumber") or c["partName"],
        mpn=c.get("manufacturerPartNumber") or "", mfr=c.get("manufacturer") or "",
        lcsc=c["properties"].get("LCSC Part Number", ""), bom=not c["excludedFromBom"],
        pins={num.get(p["number"], p["number"]): p["net"] for p in c["pins"] if p.get("net")})


def flux_nets():
    """{Flux net name: {(ref, KiCad pin number)}}."""
    return {n["name"]: {(p["component"], PIN_NUMBERS.get(p["component"], {}).get(p["pin"], p["pin"])) for p in n["pins"]}
            for n in FLUX["nets"]}


if __name__ == "__main__":
    from_parts = {}
    for ref, p in PARTS.items():
        for pin, net in p["pins"].items():
            from_parts.setdefault(net, set()).add((ref, pin))
    assert from_parts == flux_nets(), "component pins disagree with Flux nets"
    print(len(PARTS), "parts", len(from_parts), "nets")

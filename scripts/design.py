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
# Silkscreen changes from the built board, as Gerber-coordinate windows (x1, y1, x2, y2) that check_gerbers.py
# lets differ: Flux's front title "Balancio Board v0.1" is gone and the back label is new. The label window is
# its text block (monospace: 0.6 em per character; descenders reach 0.225 em) plus 0.3 mm.
_em = SILK_CAP / SILK_CAP_EM
SILK_CHANGES = [
    ("F_Silkscreen", (-9.1, -32.1, 25.4, -29.0)),
    ("B_Silkscreen", (SILK_AT[0] - 0.6 * _em * max(map(len, SILK_LABEL)) - 0.3,
                      SILK_AT[1] - SILK_CAP - (len(SILK_LABEL) - 1) * SILK_PITCH - 0.225 * _em - 0.3,
                      SILK_AT[0] + 0.3, SILK_AT[1] + 0.3)),
]

# Parts with a matching KiCad library symbol (same pin numbers as the Flux part); the balancio: ones
# are built by gen_lib.py from the Flux pin lists. Everything else is Device:R or Device:C.
SYMBOLS = {"IC1": "Sensor_Motion:MPU-6050", "U2": "Driver_Motor:DRV8833PWP", "SW1": "Switch:SW_SPDT",
           "C7": "Device:C_Polarized", "J1": "Connector_Generic:Conn_01x02", "J2": "Connector_Generic:Conn_01x02",
           "J4": "Connector_Generic:Conn_01x03",
           "U1": "balancio:ESP32-DEVKIT-V1", "U3": "balancio:HY2120", "Q1": "balancio:AP8205A",
           "Q2": "balancio:AP8205A", "LED1": "balancio:LED_RGB_5050-6"}
for j in ("J3", "J5", "J6", "J7"):
    SYMBOLS[j] = "Connector_Generic:Conn_01x04"

# Footprints in hw/lib/balancio.pretty, built by draw_pcb.py from the Flux pads (names follow the KiCad library
# footprint each one matches) -> (refs, 3D model).
FOOTPRINTS = {
    "C_0805_2012Metric": ("C1 C2 C3 C4 C5 C6 C8 C9", "Capacitor_SMD.3dshapes/C_0805_2012Metric"),
    "R_0805_2012Metric": ("R1 R2 R3 R4 R5 R6 R7 R8 R9", "Resistor_SMD.3dshapes/R_0805_2012Metric"),
    "CP_EIA-3528-21_Kemet-B": ("C7", "Capacitor_Tantalum_SMD.3dshapes/CP_EIA-3528-21_Kemet-B"),
    "QFN-24-1EP_4x4mm_P0.5mm": ("IC1", "Package_DFN_QFN.3dshapes/QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm"),
    "JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical": ("J1 J2", "Connector_JST.3dshapes/JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical"),
    "JST_PH_B4B-PH-K_1x04_P2.00mm_Vertical": ("J3 J5 J6 J7",
                                              "Connector_JST.3dshapes/JST_PH_B4B-PH-K_1x04_P2.00mm_Vertical"),
    "JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical": ("J4", "Connector_JST.3dshapes/JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical"),
    "LED_RGB_5050-6": ("LED1", "LED_SMD.3dshapes/LED_RGB_5050-6"),
    "TSSOP-8_4.4x3mm_P0.65mm": ("Q1 Q2", "Package_SO.3dshapes/TSSOP-8_4.4x3mm_P0.65mm"),
    "TSSOP-16-1EP_4.4x5mm_P0.65mm": ("U2", "Package_SO.3dshapes/TSSOP-16-1EP_4.4x5mm_P0.65mm"),
    "SOT-23-6": ("U3", "Package_TO_SOT_SMD.3dshapes/SOT-23-6"),
    # no KiCad model for these: use Flux's own STEP, placed where Flux's 3D export (balancio-board.glb) has it
    "E-Switch_100AWSP1T1B4M2RE": ("SW1", "flux/assets/100AWSP1T1B4M2RE-8235b81f-51df-4331-b117-80fe38289d24.stp"),
    "ESP32-DEVKIT-V1": ("U1", "flux/assets/ESP-WROOM32-6eb47d2f-f9fd-51d0-6081-4d9413e40023.STEP"),
}
FOOTPRINT_OF = {r: name for name, (refs, _) in FOOTPRINTS.items() for r in refs.split()}

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

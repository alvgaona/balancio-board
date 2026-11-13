"""Balancio board parts and netlist: the Flux export (flux/project.json) plus the Rev 1.1 changes below.

Rev 1.0 was manufactured and works, so everything Rev 1.1 doesn't change must connect exactly what Flux
connects. draw_sch.py draws the schematic; check_netlist.py compares what KiCad exports against nets().
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLUX = json.loads((ROOT / "flux/project.json").read_text())

REV = "1.1"
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
# Rev 1.1 board changes (see the Rev 1.1 notes below), as Gerber windows where any layer and any hole may differ
# from the built board: the soft-latch parts at the left edge where SW1 was, the PWR_HOLD/PWR_BTN routes under
# the DevKit with the GND pour they cut off, and the drops to GPIO25/39 with the GPIO36 divider by the header.
REV11_CHANGES = [(-35.5, 9.0, -12.0, 27.0), (-21.0, 10.5, 6.0, 22.0), (-14.5, -6.5, 6.0, 15.5)]

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


def nets():
    """{net name: {(ref, KiCad pin number)}} of PARTS (connections only: nets with two or more pins)."""
    out = {}
    for ref, p in PARTS.items():
        for pin, net in p["pins"].items():
            out.setdefault(net, set()).add((ref, pin))
    return {k: v for k, v in out.items() if len(v) > 1}


assert {k: v for k, v in flux_nets().items() if len(v) > 1} == nets(), "component pins disagree with Flux nets"

# ---- Rev 1.1 ----
# Power switch: SW1, a panel toggle in the battery line (no slim switch carries the motor current), becomes a
# P-FET soft latch. Q3 switches VBAT -> VIN, off while R10 holds its gate at VBAT. Pressing SW2 pulls the gate
# low through D1, the board boots, and firmware holds Q3 on by driving Q4's gate (GPIO25) high first thing in
# setup(). D1's other anode lets the ESP32 read the button on GPIO39 (R12 pull-up, active low); firmware turns
# the board off on a long press by dropping GPIO25. R13/R14/C10 put VIN/4 on GPIO36 (ADC) for the battery level.
# PWR37 = VBAT, PWR8 = VIN, PWR38 = +3V3 (Flux's net names).
del PARTS["SW1"]
FOOTPRINTS.pop("E-Switch_100AWSP1T1B4M2RE")
FOOTPRINTS["SOIC-8_3.9x4.9mm_P1.27mm"] = ("Q3", "Package_SO.3dshapes/SOIC-8_3.9x4.9mm_P1.27mm")
FOOTPRINTS["SOT-23"] = ("Q4 D1", "Package_TO_SOT_SMD.3dshapes/SOT-23")
FOOTPRINTS["SW_Push_1P1T-MP_NO_Horizontal_Alps_SKRTLAE010"] = (
    "SW2", "Button_Switch_SMD.3dshapes/SW_Push_1P1T-MP_NO_Horizontal_Alps_SKRTLAE010")
FOOTPRINTS["R_0805_2012Metric"] = (FOOTPRINTS["R_0805_2012Metric"][0] + " R10 R11 R12 R13 R14",
                                   FOOTPRINTS["R_0805_2012Metric"][1])
FOOTPRINTS["C_0805_2012Metric"] = (FOOTPRINTS["C_0805_2012Metric"][0] + " C10", FOOTPRINTS["C_0805_2012Metric"][1])
FOOTPRINT_OF = {r: name for name, (refs, _) in FOOTPRINTS.items() for r in refs.split()}
SYMBOLS.update({"Q3": "Transistor_FET:IRF7404", "Q4": "Transistor_FET:2N7002", "D1": "Diode:BAT54C",
                "SW2": "Switch:SW_Push"})  # IRF7404: same single P-FET SO-8 pinout as the AO4407A
for ref, value, mpn, mfr, pins in [
    ("Q3", "AO4407A", "AO4407A", "Alpha & Omega", {"1": "PWR37", "2": "PWR37", "3": "PWR37", "4": "PWR_GATE",
                                                   "5": "PWR8", "6": "PWR8", "7": "PWR8", "8": "PWR8"}),
    ("R10", "100kΩ", "", "", {"1": "PWR_GATE", "2": "PWR37"}),
    ("Q4", "2N7002", "2N7002", "Jiangsu Changjing", {"1": "PWR_HOLD", "2": "GND", "3": "PWR_GATE"}),
    ("R11", "100kΩ", "", "", {"1": "PWR_HOLD", "2": "GND"}),
    ("D1", "BAT54C", "BAT54C,215", "Nexperia", {"1": "PWR_GATE", "2": "PWR_BTN", "3": "PWR_KEY"}),
    ("SW2", "SKRTLAE010", "SKRTLAE010", "Alps Alpine", {"1": "PWR_KEY", "2": "GND"}),
    ("R12", "10kΩ", "", "", {"1": "PWR38", "2": "PWR_BTN"}),
    ("R13", "100kΩ", "", "", {"1": "PWR8", "2": "PWR_SENSE"}),
    ("R14", "33kΩ", "", "", {"1": "PWR_SENSE", "2": "GND"}),
    ("C10", "100nF", "", "", {"1": "PWR_SENSE", "2": "GND"}),
]:
    PARTS[ref] = dict(sym=SYMBOLS.get(ref) or {"R": "Device:R", "C": "Device:C"}[ref[0]], value=value, mpn=mpn,
                      mfr=mfr, lcsc="", bom=True, pins=pins)
PARTS["U1"]["pins"].update({"23": "PWR_HOLD", "18": "PWR_BTN", "17": "PWR_SENSE"})  # GPIO25, GPIO39, GPIO36

# LCSC numbers for JLCPCB assembly, by value, each checked on jlcpcb.com/partdetail/<number> (2026-11-13).
# Passives are JLCPCB Basic parts. 5060BRG4 (LED1) isn't stocked there.
LCSC = {"2.2nF": "C28260", "100nF": "C49678", "10nF": "C1710", "2.2uF": "C377773", "4.7kΩ": "C17673",
        "100Ω": "C17408", "330Ω": "C17630", "2kΩ": "C17604", "100kΩ": "C149504", "10kΩ": "C17414", "33kΩ": "C17633",
        "MPU-6050": "C24112", "HY2120-AB": "C168776", "AO4407A": "C16072", "2N7002": "C8545", "BAT54C": "C37704",
        "SKRTLAE010": "C110293", "B2B-PH-K-S(LF)(SN)": "C131337", "B4B-PH-K-S(LF)(SN)": "C131334",
        "B3B-XH-A(LF)(SN)": "C144394"}
for p in PARTS.values():
    p["lcsc"] = p["lcsc"] or LCSC.get(p["value"], "")


if __name__ == "__main__":
    print(len(PARTS), "parts", len(nets()), "nets")

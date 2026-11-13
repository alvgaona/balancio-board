"""The intended Balancio board, for build.sh's checks: its netlist, and where its Gerbers may differ from the
board JLCPCB built (Rev 1.0, which works on the robot).

hw/ is the source, edited in KiCad. A change to the circuit must be made here too, deliberately: the netlist
check fails on any connection that isn't listed. Rev 1.0 was migrated from Flux and checked against it net by
net (the Flux data is in git history up to commit 026d5a6); Rev 1.1 replaced the power switch.
"""

# KiCad net name: the pins it connects, as REF.PIN. Names are for messages only: the check compares pin sets.
NETS = {
    "+3V3": "C3.1 C4.1 IC1.8 IC1.13 J5.1 J6.1 R2.1 R3.1 R12.1 U1.1",
    "/MOT_ENA": "U1.15 U2.1",
    "/MOT_IN1": "U1.14 U2.16",
    "/MOT_IN2": "U1.11 U2.15",
    "/MOT_IN3": "U1.10 U2.9",
    "/MOT_IN4": "U1.9 U2.10",
    "/OC": "Q1.5 Q2.5 U3.2",
    "/PWR_BTN": "D1.2 R12.2 U1.18",
    "/PWR_HOLD": "Q4.1 R11.1 U1.23",
    "/PWR_SENSE": "C10.1 R13.2 R14.1 U1.17",
    "/SCL": "IC1.23 R3.2 U1.25",
    "/SDA": "IC1.24 R2.2 U1.24",
    "BAT-": "C8.2 C9.2 J4.1 Q1.2 Q1.3 Q2.2 Q2.3 U3.6",
    "GND": ("C1.2 C2.2 C3.2 C4.2 C5.2 C7.2 C10.2 IC1.1 IC1.11 IC1.18 J5.4 J6.4 Q1.6 Q1.7 Q2.6 Q2.7 Q4.2 R1.1 R4.2 "
        "R5.2 R6.2 R9.2 R11.2 R14.2 SW2.2 U1.2 U1.29 U2.3 U2.6 U2.13 U2.17"),
    "VBAT": "J4.3 Q3.1 Q3.2 Q3.3 R7.1 R10.2",
    "VIN": "C6.2 C7.1 Q3.5 Q3.6 Q3.7 Q3.8 R13.1 U1.30 U2.12",
    "Net-(D1-Pad3)": "D1.3 SW2.1",
    "Net-(IC1-AD0)": "IC1.9 R1.2",
    "Net-(IC1-CPOUT)": "C1.1 IC1.20",
    "Net-(IC1-REGOUT)": "C2.1 IC1.10",
    "Net-(J1-Pin_1)": "J1.1 U2.7",
    "Net-(J1-Pin_2)": "J1.2 U2.5",
    "Net-(J2-Pin_1)": "J2.1 U2.4",
    "Net-(J2-Pin_2)": "J2.2 U2.2",
    "Net-(J3-Pin_1)": "J3.1 U1.22",
    "Net-(J3-Pin_2)": "J3.2 U1.21",
    "Net-(J3-Pin_3)": "J3.3 U1.20",
    "Net-(J3-Pin_4)": "J3.4 U1.19",
    "Net-(J4-Pin_2)": "J4.2 R8.1",
    "Net-(J5-Pin_2)": "J5.2 U1.6",
    "Net-(J5-Pin_3)": "J5.3 U1.7",
    "Net-(J6-Pin_2)": "J6.2 U1.12",
    "Net-(J6-Pin_3)": "J6.3 U1.13",
    "Net-(J7-Pin_1)": "J7.1 U1.4",
    "Net-(J7-Pin_2)": "J7.2 U1.5",
    "Net-(J7-Pin_3)": "J7.3 U1.8",
    "Net-(J7-Pin_4)": "J7.4 U1.3",
    "Net-(LED1-P1)": "LED1.1 U1.26",
    "Net-(LED1-P2)": "LED1.2 U1.28",
    "Net-(LED1-P3)": "LED1.3 U1.27",
    "Net-(LED1-P4)": "LED1.4 R4.1",
    "Net-(LED1-P5)": "LED1.5 R5.1",
    "Net-(LED1-P6)": "LED1.6 R6.1",
    "Net-(Q1-D1)": "Q1.1 Q1.8 Q2.1 Q2.8",
    "Net-(Q1-G1)": "Q1.4 Q2.4 U3.1",
    "Net-(Q3-G)": "D1.1 Q3.4 Q4.3 R10.1",
    "Net-(U2-VCP)": "C6.1 U2.11",
    "Net-(U2-VINT)": "C5.1 U2.14",
    "Net-(U3-CS)": "R9.1 U3.3",
    "Net-(U3-VC)": "C9.1 R8.2 U3.4",
    "Net-(U3-VDD)": "C8.1 R7.2 U3.5",
}

# Gerber windows (x1, y1, x2, y2), mm, Gerber coordinates (y up: KiCad y = -y), where the Gerbers may differ
# from the built board. Silkscreen: Flux's front title "Balancio Board v0.1" is gone and the back label is new.
SILK_CHANGES = [("F_Silkscreen", (-9.1, -32.1, 25.4, -29.0)), ("B_Silkscreen", (-20.77, 6.41, 28.84, 13.4))]
# Rev 1.1, every layer and drill: the power switch area by the left edge, the button and hold lanes, and the
# GPIO36 divider under the DevKit.
REV11_CHANGES = [(-35.5, 9.0, -12.0, 27.0), (-21.0, 10.5, 6.0, 22.0), (-14.5, -6.5, 6.0, 15.5)]


def nets():
    """{net name: {(ref, pin)}}."""
    return {name: {tuple(p.rsplit(".", 1)) for p in pins.split()} for name, pins in NETS.items()}

# Balancio board

Controller board for the Balancio self-balancing robot: an ESP32 DevKit, a DRV8833 motor driver, an MPU-6050
IMU, 2S battery protection and a soft-latch power switch. Rev 1.0 was built by JLCPCB and works; Rev 1.1
replaces the slide switch with a soft latch (power button on the left edge).

## Layout

- `hw/`: the design, edited in KiCad 10. This is the source of truth.
  - `balancio.kicad_sch`, `balancio.kicad_pcb`: schematic and board.
  - `lib/`: the board's own symbols, footprints and the 3D models KiCad doesn't ship (`balancio.3dshapes/`).
- `scripts/build.sh`: checks the design and writes everything to `build/`.

## Build

```sh
scripts/build.sh
```

It runs ERC and DRC with schematic parity, and stops on any error before it exports anything.

It writes:

- `build/balancio-gerbers.zip`, `build/balancio-bom.csv` and `build/balancio-cpl.csv` for JLCPCB;
- `build/balancio-schematic.pdf`;
- `build/balancio.glb`, the assembled board in 3D, for Blender;
- `build/balancio-rev<rev>.zip`, the board package: all of the above plus the KiCad files, for descent.

## Viewing the board

Open `build/balancio-rev<rev>.zip` in [descent](https://github.com/alvgaona/descent): the 3D model, schematic,
PCB, BOM and every file, in the browser.

descent shows a part as metal when its colour is one of the metals of KiCad's standard 3D models, so our own
models (the DevKit's `.FCStd`) paint metal with those: `#d2d1c7` (metal grey pins) and `#dbbc7e` (gold pins).

`scripts/package.py` writes the package; its docstring describes the format.

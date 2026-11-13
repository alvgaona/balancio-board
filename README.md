# Balancio board

Controller board for the Balancio self-balancing robot: an ESP32 DevKit, a DRV8833 motor driver, an MPU-6050
IMU, 2S battery protection and a soft-latch power switch. Rev 1.0 was built by JLCPCB and works; Rev 1.1
replaces the slide switch with a soft latch (power button on the left edge).

## Layout

- `hw/`: the design, edited in KiCad 10. This is the source of truth.
  - `balancio.kicad_sch`, `balancio.kicad_pcb`: schematic and board.
  - `lib/`: the board's own symbols, footprints and the 3D models KiCad doesn't ship (`balancio.3dshapes/`).
- `scripts/build.sh`: checks the design and writes everything to `build/`.
- `viewer/`: an interactive 3D view of the board, in the browser.

## Build

```sh
scripts/build.sh
```

It runs ERC and DRC with schematic parity, and stops on any error before it exports anything.

It writes:

- `build/balancio-gerbers.zip`, `build/balancio-bom.csv` and `build/balancio-cpl.csv` for JLCPCB;
- `build/balancio-schematic.pdf`;
- `build/balancio.glb`, the assembled board in 3D for Blender or the viewer.

## 3D viewer

After a build, serve the repository and open the viewer:

```sh
python3 -m http.server 8000
```

Then open <http://localhost:8000/viewer/>.

Controls:

- Drag rotates, scroll zooms, right-drag pans.
- Space starts or stops the spin.
- Keys 1, 2 and 3 give the angled, top and bottom views. Key 4 shows the power button.
- `?view=4` in the URL opens on a view.

`viewer/board.json` holds the board-specific settings:

- the model;
- the pad finish;
- which part colours are metal (KiCad's part models don't say);
- the parts the number keys look at.

For another board, copy `viewer/` and edit that file.

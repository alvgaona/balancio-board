<div align="center">

# balancio-board

**Controller board for the Balancio self-balancing robot.**

[![Rev 1.1](https://img.shields.io/badge/rev-1.1-orange.svg)](hw/balancio.kicad_pcb)
[![KiCad 10](https://img.shields.io/badge/KiCad-10-314cb0.svg)](https://www.kicad.org)
[![Pixi](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/prefix-dev/pixi/main/assets/badge/v0.json)](https://pixi.sh)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-fe5196.svg)](https://www.conventionalcommits.org)

</div>

## Overview

The board carries the robot's brains, motor drive and power.

- ESP32 DevKit
- DRV8833 dual motor driver
- MPU-6050 IMU
- 2S battery protection
- Soft-latch power switch, with the power button on the left edge

Rev 1.0 was built by JLCPCB and works. Rev 1.1 replaces its slide switch with the soft latch.

## Layout

- `hw/`: the design, edited in KiCad 10. This is the source of truth.
  - `balancio.kicad_sch`, `balancio.kicad_pcb`: schematic and board.
  - `lib/`: the board's own symbols, footprints and the 3D models KiCad doesn't ship (`balancio.3dshapes/`).
- `scripts/build.sh`: checks the design and writes everything to `build/`.

## Build

You need KiCad 10. FreeCAD is needed only after you edit a model in `hw/lib/balancio.3dshapes/`.

```sh
scripts/build.sh   # or: pixi run build
```

It runs ERC and DRC with schematic parity, and stops on any error before it exports anything.

CI runs the same build in KiCad's Docker image on every push and pull request. The board package is attached to
each run as the `board-package` artifact.

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

## Development

The dev tools (lefthook, commitlint, git-cliff) come from [pixi](https://pixi.sh). Install the git hook once:

```sh
pixi run hooks
```

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org); the `commit-msg` hook checks
them with commitlint.

## Releases

Each board revision is tagged `rev-<rev>`, matching the `rev` in the schematic and PCB title blocks. Pushing the
tag runs the release workflow: it checks the tag against the title blocks, builds the board, and publishes a
GitHub release with the board package, Gerbers, BOM, CPL and schematic PDF. The notes come from git-cliff.

```sh
pixi run changelog   # write CHANGELOG.md from the commits
```

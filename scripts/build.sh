#!/bin/sh
# Schematic from the Flux export: symbols -> schematic -> ERC -> KiCad netlist vs Flux netlist.
set -e -o pipefail
cd "$(dirname "$0")/.."
K=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
quiet() { grep -v -E "wxApp|stdpbase|swig|Debug|Fontconfig" || true; }
mkdir -p build
python3 scripts/design.py
python3 scripts/gen_lib.py
python3 scripts/draw_sch.py
$K sch erc --severity-all -o build/erc.rpt hw/balancio.kicad_sch 2>&1 | quiet
# Known warnings: DRV8833 AISEN/BISEN tied straight to GND, as on the built board. Errors fail the build.
! grep -q '; error' build/erc.rpt || { cat build/erc.rpt; exit 1; }
$K sch export netlist --format kicadxml -o build/balancio.net.xml hw/balancio.kicad_sch 2>&1 | quiet
python3 scripts/check_netlist.py build/balancio.net.xml
$K sch export pdf -o build/balancio-schematic.pdf hw/balancio.kicad_sch 2>&1 | quiet

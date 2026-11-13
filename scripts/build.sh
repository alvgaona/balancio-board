#!/bin/sh
# Check and export the KiCad design. hw/ is the source: edit it in KiCad (scripts/migrate.sh is how it was
# first generated from Flux). Steps: ERC -> netlist vs Flux -> DRC with schematic parity -> Gerbers and drill
# -> compare with the Gerbers the working board was built from.
# Rev 1.0 must match the built board exactly. When Rev 1.1 changes it on purpose, replace the two Flux
# comparisons (check_netlist.py, check_gerbers.py) with checks of the intended change.
set -e -o pipefail
cd "$(dirname "$0")/.."
K=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
BUILT=alvgaona-balancio-board-Gerbers-Version89f23658_Y2.zip  # Flux's Gerbers for the first JLCPCB order
quiet() { grep -v -E "wxApp|stdpbase|swig|Debug|Fontconfig|Plotted to|Created file|^Done" || true; }
mkdir -p build
$K sch erc --severity-all -o build/erc.rpt hw/balancio.kicad_sch 2>&1 | quiet
# Known warnings: DRV8833 AISEN/BISEN tied straight to GND, as on the built board. Errors fail the build.
! grep -q '; error' build/erc.rpt || { cat build/erc.rpt; exit 1; }
$K sch export netlist --format kicadxml -o build/balancio.net.xml hw/balancio.kicad_sch 2>&1 | quiet
python3 scripts/check_netlist.py build/balancio.net.xml
$K sch export pdf -o build/balancio-schematic.pdf hw/balancio.kicad_sch 2>&1 | quiet

$K pcb drc --schematic-parity --severity-all -o build/drc.rpt hw/balancio.kicad_pcb 2>&1 | quiet
# Known warnings, all as built: silkscreen over pads and overlapping (JLCPCB clips silk off pads), and 7 track
# stubs with a dangling end. Errors, unconnected items or schematic parity issues fail the build.
grep -q 'Found 0 unconnected pads' build/drc.rpt && grep -q 'Found 0 Footprint errors' build/drc.rpt \
  && ! grep -q '; error' build/drc.rpt || { grep -E -A3 '; error|^\*\* Found' build/drc.rpt; exit 1; }
rm -rf build/gerbers && mkdir build/gerbers
$K pcb export gerbers --layers F.Cu,B.Cu,F.Mask,B.Mask,F.Paste,B.Paste,F.SilkS,B.SilkS,Edge.Cuts --no-protel-ext \
  --disable-aperture-macros -o build/gerbers/ hw/balancio.kicad_pcb 2>&1 | quiet
$K pcb export drill --format excellon --excellon-units mm -o build/gerbers/ hw/balancio.kicad_pcb 2>&1 | quiet
python3 scripts/check_gerbers.py build/gerbers $BUILT build/gerber-diff
rm -f build/balancio-gerbers.zip && (cd build/gerbers && zip -q ../balancio-gerbers.zip balancio-*.gbr balancio.drl)

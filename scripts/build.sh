#!/bin/sh
# Check and export the KiCad design. hw/ is the source: edit it in KiCad. Steps: ERC -> netlist vs design.py
# (the built board's netlist plus the Rev 1.1 changes) -> DRC with schematic parity -> Gerbers and drill
# -> compare with the Gerbers the working board was built from (differences allowed only where Rev 1.1
# changed it, design.REV11_CHANGES) -> JLCPCB BOM and pick-and-place for the SMD parts.
set -e -o pipefail
cd "$(dirname "$0")/.."
K=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
BUILT=alvgaona-balancio-board-Gerbers-Version89f23658_Y2.zip  # the Gerbers of the first JLCPCB order (Rev 1.0, exported by Flux)
quiet() { grep -v -E "wxApp|stdpbase|swig|Debug|Fontconfig|Plotted to|Created file|^Done|Loading|Writing" || true; }
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

# JLCPCB assembly: upload build/balancio-bom.csv and build/balancio-cpl.csv with the Gerber zip
$K sch export bom --fields "Value,Reference,Footprint,LCSC" --labels "Comment,Designator,Footprint,LCSC Part #" \
  --group-by "Value,Footprint,LCSC" --ref-range-delimiter "" -o build/bom-all.csv hw/balancio.kicad_sch 2>&1 | quiet
$K pcb export pos --format csv --units mm --side front --smd-only -o build/pos-smd.csv hw/balancio.kicad_pcb 2>&1 | quiet
python3 scripts/jlc.py build/bom-all.csv build/pos-smd.csv build

#!/bin/sh
# How hw/ was generated from the Flux export (Rev 1.0). It overwrites hw/, so it refuses to run over
# uncommitted changes there. Since the freeze, hw/ is the source: edit it in KiCad and run build.sh.
set -e -o pipefail
cd "$(dirname "$0")/.."
git diff --quiet HEAD -- hw || { echo "hw/ has uncommitted changes that this would overwrite"; exit 1; }
K=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
quiet() { grep -v -E "wxApp|stdpbase|swig|Debug|Fontconfig" || true; }
mkdir -p build
python3 scripts/design.py
python3 scripts/gen_lib.py
python3 scripts/draw_sch.py
$K sch export netlist --format kicadxml -o build/balancio.net.xml hw/balancio.kicad_sch 2>&1 | quiet
python3 scripts/draw_pcb.py build/balancio.net.xml alvgaona-balancio-board-Gerbers-Version89f23658_Y2.zip
exec sh scripts/build.sh

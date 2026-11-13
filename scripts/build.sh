#!/bin/sh
# Check the KiCad design and export everything needed to order and view the board, into build/.
#
#   scripts/build.sh
#
# hw/ is the source: edit it in KiCad. Any ERC or DRC error stops the build before anything is exported.
set -e -o pipefail
cd "$(dirname "$0")/.."

BOARD=balancio
SCH=hw/$BOARD.kicad_sch
PCB=hw/$BOARD.kicad_pcb
OUT=build
KICAD_CLI=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli

# Drop kicad-cli's progress chatter; reports and real errors still show.
quiet() {
  grep -v -E "wxApp|stdpbase|swig|Debug|Fontconfig|Plotted to|Created file|^Done|Loading|Writing|NSCocoaErrorDomain|file .* created|Export time|^$" || true
}

# kicad-cli, quietly. A kicad-cli failure still stops the build (pipefail).
kicad() {
  "$KICAD_CLI" "$@" 2>&1 | quiet
}

# Electrical rules check of the schematic.
# Known warnings: DRV8833 AISEN/BISEN tied straight to GND, as on the built board.
check_erc() {
  kicad sch erc --severity-all -o "$OUT/erc.rpt" "$SCH"
  if grep -q '; error' "$OUT/erc.rpt"; then
    cat "$OUT/erc.rpt"
    exit 1
  fi
}

# Design rules check of the board, including that it matches the schematic (schematic parity).
# Known warnings, all as built: silkscreen over pads and overlapping (JLCPCB clips silk off pads), and 7 track
# stubs with a dangling end. Errors, unconnected pads or parity issues fail.
check_drc() {
  kicad pcb drc --schematic-parity --severity-all -o "$OUT/drc.rpt" "$PCB"
  if ! grep -q 'Found 0 unconnected pads' "$OUT/drc.rpt" || ! grep -q 'Found 0 Footprint errors' "$OUT/drc.rpt" \
      || grep -q '; error' "$OUT/drc.rpt"; then
    grep -E -A3 '; error|^\*\* Found' "$OUT/drc.rpt"
    exit 1
  fi
}

# The schematic as a PDF.
export_schematic() {
  kicad sch export pdf -o "$OUT/$BOARD-schematic.pdf" "$SCH"
}

# Gerbers and drill file, zipped for the PCB order.
export_gerbers() {
  rm -rf "$OUT/gerbers" && mkdir "$OUT/gerbers"
  kicad pcb export gerbers --layers F.Cu,B.Cu,F.Mask,B.Mask,F.Paste,B.Paste,F.SilkS,B.SilkS,Edge.Cuts \
    --no-protel-ext --disable-aperture-macros -o "$OUT/gerbers/" "$PCB"
  kicad pcb export drill --format excellon --excellon-units mm -o "$OUT/gerbers/" "$PCB"
  rm -f "$OUT/$BOARD-gerbers.zip"
  (cd "$OUT/gerbers" && zip -q "../$BOARD-gerbers.zip" "$BOARD"-*.gbr "$BOARD.drl")
}

# Custom part models are edited in FreeCAD (hw/lib/balancio.3dshapes/*.FCStd); KiCad needs STEP.
# Regenerate a STEP only when its .FCStd is newer: each export opens FreeCAD for a few seconds,
# because FreeCAD keeps part colours in its GUI layer.
convert_models() {
  for model in hw/lib/balancio.3dshapes/*.FCStd; do
    if [ "$model" -nt "${model%.FCStd}.step" ]; then
      log=$(mktemp)
      FCSTD="$PWD/$model" FCSTD_LOG="$log" "${FREECAD:-/Applications/FreeCAD.app/Contents/MacOS/FreeCAD}" \
        scripts/fcstd2step.py >/dev/null 2>&1 || true  # the log, not FreeCAD's exit code, says if it worked
      if ! grep -qx OK "$log"; then
        echo "FreeCAD could not export $model:"
        [ -s "$log" ] && cat "$log" || echo "FreeCAD did not run; set FREECAD to the FreeCAD app binary."
        rm -f "$log"; exit 1
      fi
      rm -f "$log"
      echo "Exported ${model%.FCStd}.step"
    fi
  done
}

# The assembled board in 3D, every part's model in one GLB: open it in Blender or in the viewer
# (python3 -m http.server 8000, then http://localhost:8000/viewer/).
export_3d() {
  kicad pcb export glb -f --subst-models --include-tracks --include-pads --include-zones --include-silkscreen \
    --include-soldermask -o "$OUT/$BOARD.glb" "$PCB"
}

# JLCPCB assembly files for the SMD parts, BOM and pick-and-place (CPL), to upload with the Gerber zip.
# Through-hole parts are soldered by hand.
export_jlcpcb() {
  kicad sch export bom --fields "Value,Reference,Footprint,LCSC" --labels "Comment,Designator,Footprint,LCSC Part #" \
    --group-by "Value,Footprint,LCSC" --ref-range-delimiter "" -o "$OUT/bom-all.csv" "$SCH"
  kicad pcb export pos --format csv --units mm --side front --smd-only -o "$OUT/pos-smd.csv" "$PCB"
  python3 scripts/jlc.py "$OUT/bom-all.csv" "$OUT/pos-smd.csv" "$OUT"
}

main() {
  mkdir -p "$OUT"
  check_erc
  check_drc
  export_schematic
  export_gerbers
  convert_models
  export_3d
  export_jlcpcb
}

main "$@"

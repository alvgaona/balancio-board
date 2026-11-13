"""FreeCAD model -> coloured STEP for KiCad. Runs inside FreeCAD (colours live in its GUI layer):

    FCSTD=/abs/path/model.FCStd FreeCAD scripts/fcstd2step.py      (writes model.step next to it)

build.sh runs it. FreeCAD runs a script given as an argument but passes it no args, so the
model path comes in FCSTD and the result (OK or a traceback) goes to FCSTD_LOG.
"""
import os
import traceback

import FreeCAD
import ImportGui

src = os.environ["FCSTD"]
log = os.environ.get("FCSTD_LOG", src + ".log")
try:
    doc = FreeCAD.openDocument(src)
    # The top assembly keeps per-part colours; a model without one exports its loose solids instead.
    roots = [o for o in doc.RootObjects if o.TypeId == "App::Part"] or [o for o in doc.RootObjects if hasattr(o, "Shape")]
    if not roots:
        raise ValueError(f"nothing to export in {src}")
    ImportGui.export(roots, os.path.splitext(src)[0] + ".step")
    open(log, "w").write("OK\n")
except Exception:
    open(log, "w").write(traceback.format_exc())
os._exit(0)  # quit the GUI started for this script

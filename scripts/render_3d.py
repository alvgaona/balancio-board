"""Render the Flux 3D model (balancio-board.glb) with Blender: top, bottom and angled views.

Run: /Applications/Blender.app/Contents/MacOS/Blender -b -P scripts/render_3d.py -- balancio-board.glb build
"""
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

glb, outdir = sys.argv[sys.argv.index("--") + 1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
scene = bpy.context.scene

meshes = [o for o in scene.objects if o.type == "MESH"]

# Flux exports green solder mask; the boards were ordered from JLCPCB in black. Real mask is slightly
# translucent, so copper under it shows as faint lighter traces and pours with darker clearance gaps.
# The importer drops the glTF node names (input_soldermask), so match materials by Flux's colors.
def flux_mat(rgb):
    for m in bpy.data.materials:
        bsdf = m.node_tree.nodes.get("Principled BSDF") if m.node_tree else None
        if bsdf and all(abs(a - b) < 0.01 for a, b in zip(bsdf.inputs["Base Color"].default_value, rgb)):
            yield m, bsdf


masks = 0
for m, bsdf in flux_mat((0.08, 0.2, 0.14)):
    bsdf.inputs["Base Color"].default_value = (0.012, 0.012, 0.014, 1)
    bsdf.inputs["Alpha"].default_value = 0.88
    bsdf.inputs["Roughness"].default_value = 0.35
    if hasattr(m, "surface_render_method"):
        m.surface_render_method = "BLENDED"
    masks += 1
assert masks, "solder mask material not found"
for m, bsdf in flux_mat((0.42, 0.45, 0.29)):  # FR-4 core: dark, so only copper reads through the mask
    bsdf.inputs["Base Color"].default_value = (0.05, 0.045, 0.035, 1)
for m, bsdf in flux_mat((0.7, 0.61, 0.0)):  # copper, only ever seen through the mask (pads are their own mesh)
    bsdf.inputs["Base Color"].default_value = (0.6, 0.56, 0.5, 1)
    bsdf.inputs["Roughness"].default_value = 0.3
for m, bsdf in flux_mat((1.0, 1.0, 1.0)):  # silkscreen ink is opaque; a translucent one sorts badly against the mask
    if m.name == "mat_35":
        bsdf.inputs["Alpha"].default_value = 1.0
        if hasattr(m, "surface_render_method"):
            m.surface_render_method = "DITHERED"
assert masks, "solder mask material not found"

# Flux's part models omit metallicFactor, which glTF reads as fully metallic, and share one white material
# between the ESP32 shield can and the JST housings. Set the parts that matter to what they are on the board.
def pbr(m, rgb, metallic, roughness):
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Roughness"].default_value = roughness
    return m


nylon = pbr(bpy.data.materials["mat_7"], (0.86, 0.86, 0.84), 0.0, 0.55)  # JST housings (+ small white markings)
pbr(bpy.data.materials["mat_27"], (0.86, 0.86, 0.84), 0.0, 0.55)  # J1, J2, J4 housings (Flux had beige)
for name in ("mat_24", "mat_28"):  # JST pins (Flux had bluish), also SOT-23 leads: tin
    pbr(bpy.data.materials[name], (0.8, 0.8, 0.8), 1.0, 0.3)
# Everything Flux left "metallic" that is plastic, epoxy, ceramic or board material (mapped by part and position).
PLASTIC = {
    "mat_1": "resistor body", "mat_2": "resistor top coat", "mat_3": "MLCC ceramic", "mat_4": "C7 tantalum body",
    "mat_5": "C7 tantalum body", "mat_9": "micro-USB insulator", "mat_10": "micro-USB insulator",
    "mat_12": "black epoxy and header spacers", "mat_14": "WROOM antenna print", "mat_16": "IC packages",
    "mat_17": "DevKit PCB", "mat_18": "DevKit PCB underside", "mat_20": "DevKit SMD parts", "mat_22": "DevKit LED",
    "mat_26": "Q1/Q2 marking", "mat_29": "U3 package", "mat_31": "MPU-6050 package",
}
for name in PLASTIC:
    pbr(bpy.data.materials[name], bpy.data.materials[name].node_tree.nodes["Principled BSDF"]
        .inputs["Base Color"].default_value[:3], 0.0, 0.5)
for name in ("mat_35", "mat_36", "mat_37", "mat_38"):  # silkscreen, both masks, FR-4: dielectrics
    bpy.data.materials[name].node_tree.nodes["Principled BSDF"].inputs["Metallic"].default_value = 0.0
pbr(bpy.data.materials["mat_8"], (0.8, 0.8, 0.8), 1.0, 0.3)  # micro-USB shell: tin, not Flux's blue
can = pbr(bpy.data.materials["mat_7"].copy(), (0.78, 0.78, 0.78), 1.0, 0.32)  # ESP32-WROOM shield, tin-plated
wroom = bpy.data.objects["NAUO2"]
for slot in wroom.material_slots:
    if slot.material.name == "mat_7":
        slot.material = can

# Drop Flux's front "Balancio Board v0.1" title (the only top silk below y = -27); the label goes on the back.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from design import FLUX, SILK_AT, SILK_CAP, SILK_FONT, SILK_LABEL, SILK_PITCH  # noqa: E402

silk = next(o for o in meshes if o.data.materials and o.data.materials[0].name == "mat_35")
board = next(o for o in meshes if o.data.materials and o.data.materials[0].name == "mat_38")
bpts = [board.matrix_world @ v.co for v in board.data.vertices]
origin = Vector(((min(p.x for p in bpts) + max(p.x for p in bpts)) / 2,  # Flux (0, 0) is the board center
                 (min(p.y for p in bpts) + max(p.y for p in bpts)) / 2, 0))
mm = 1e-3  # the glTF is in meters
bm = bmesh.new()
bm.from_mesh(silk.data)
old = [f for f in bm.faces if ((silk.matrix_world @ f.calc_center_median()) - origin).y < -27 * mm]
assert old, "old silkscreen title not found"
xs = [((silk.matrix_world @ f.calc_center_median()) - origin).x / mm for f in old]
print(f"removed {len(old)} silk faces, x {min(xs):.1f}..{max(xs):.1f} mm")
bmesh.ops.delete(bm, geom=old, context="FACES")
bm.to_mesh(silk.data)
bm.free()

# Flux's mask is one sheet with no mounting-hole cutouts (it was translucent, so they showed through).
# The Gerber mask has no openings there either: the 3 mm NPTH is drilled straight through the mask.
for mask in [o for o in meshes if o.data.materials and o.data.materials[0].name in ("mat_36", "mat_37")]:
    for h in FLUX["boards"][0]["pads"]:
        bpy.ops.mesh.primitive_cylinder_add(radius=h["holeWidthMm"] / 2 * mm, depth=5 * mm,
                                            location=origin + Vector((h["center"]["x"], h["center"]["y"], 0.7)) * mm)
        drill = bpy.context.object
        cut = mask.modifiers.new("drill", "BOOLEAN")
        cut.operation, cut.object, cut.solver = "DIFFERENCE", drill, "EXACT"
        bpy.context.view_layer.objects.active = mask
        bpy.ops.object.modifier_apply(modifier=cut.name)
        bpy.data.objects.remove(drill)

font = bpy.data.fonts.load(str(Path(__file__).resolve().parent.parent / "hw/fonts" / SILK_FONT))
probe = bpy.data.objects.new("probe", bpy.data.curves.new("probe", "FONT"))  # Blender's size isn't the em: measure "H"
probe.data.body, probe.data.font = "H", font
scene.collection.objects.link(probe)
bpy.context.view_layer.update()
cap_at_size_1 = probe.dimensions.y
bpy.data.objects.remove(probe)
z = min((o.matrix_world @ Vector(c)).z for o in meshes if o.data.materials and o.data.materials[0].name == "mat_37"
        for c in o.bound_box) - 0.01 * mm  # just under the bottom mask
for i, line in enumerate(SILK_LABEL):
    cu = bpy.data.curves.new(f"label{i}", "FONT")
    cu.body, cu.font, cu.size = line, font, SILK_CAP / cap_at_size_1 * mm
    t = bpy.data.objects.new(f"label{i}", cu)
    t.location = origin + Vector((SILK_AT[0], SILK_AT[1] - SILK_CAP - i * SILK_PITCH, 0)) * mm
    t.location.z = z
    t.rotation_euler.y = math.pi  # face down, mirrored: reads left to right from below, running toward -x
    t.data.materials.append(silk.data.materials[0])
    scene.collection.objects.link(t)
bpy.context.view_layer.update()
for o in scene.objects:  # text to mesh, so the glTF export carries it
    o.select_set(o.name.startswith("label"))
bpy.context.view_layer.objects.active = next(o for o in scene.objects if o.name.startswith("label"))
bpy.ops.object.convert(target="MESH")
w = max(o.dimensions.x for o in scene.objects if o.name.startswith("label")) / mm
print(f"label block x {SILK_AT[0] - w:.2f}..{SILK_AT[0]:.2f} mm, center {SILK_AT[0] - w / 2:.2f}")
pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
lo = Vector([min(p[i] for p in pts) for i in range(3)])
hi = Vector([max(p[i] for p in pts) for i in range(3)])
center, size = (lo + hi) / 2, hi - lo
span = max(size.x, size.y)
print("model bounds", tuple(round(v, 4) for v in lo), tuple(round(v, 4) for v in hi))

engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
scene.render.engine = next(e for e in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES") if e in engines)
scene.render.resolution_x = scene.render.resolution_y = 1600
scene.render.film_transparent = False
scene.view_settings.view_transform = "Standard"
world = bpy.data.worlds.new("w")
world.use_nodes = True
# The light-gray backdrop is for the camera only; lit by it, glossy black mask reflects it and reads as gray.
nt = world.node_tree
backdrop, out = nt.nodes["Background"], nt.nodes["World Output"]
backdrop.inputs[0].default_value = (0.93, 0.93, 0.94, 1)
backdrop.inputs[1].default_value = 0.8
dim = nt.nodes.new("ShaderNodeBackground")
dim.inputs[0].default_value = (0.93, 0.93, 0.94, 1)
dim.inputs[1].default_value = 0.25
mix = nt.nodes.new("ShaderNodeMixShader")
nt.links.new(nt.nodes.new("ShaderNodeLightPath").outputs["Is Camera Ray"], mix.inputs["Fac"])
nt.links.new(dim.outputs[0], mix.inputs[1])
nt.links.new(backdrop.outputs[0], mix.inputs[2])
nt.links.new(mix.outputs[0], out.inputs["Surface"])
scene.world = world

target = bpy.data.objects.new("target", None)
target.location = center
scene.collection.objects.link(target)


def light(name, direction, energy):
    sun = bpy.data.objects.new(name, bpy.data.lights.new(name, "SUN"))
    sun.data.energy = energy
    sun.data.angle = math.radians(10)
    sun.rotation_euler = Vector(direction).to_track_quat("Z", "Y").to_euler()
    scene.collection.objects.link(sun)


light("key", (0.4, -0.5, 1.0), 3.0)  # sun direction is where it shines from
light("under", (-0.3, 0.4, -1.0), 2.0)

cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
scene.collection.objects.link(cam)
scene.camera = cam
track = cam.constraints.new("TRACK_TO")
track.target, track.track_axis, track.up_axis = target, "TRACK_NEGATIVE_Z", "UP_Y"
cam.data.clip_end = span * 100

views = {
    "top": ((0, -0.0001, 1), "ORTHO"),
    "bottom": ((0, 0.0001, -1), "ORTHO"),  # seen from below, flipped left-right
    "angle": ((0.9, -1.3, 1.1), "PERSP"),
}
for name, (direction, kind) in views.items():
    d = Vector(direction).normalized()
    cam.location = center + d * span * (3 if kind == "ORTHO" else 4.2)
    cam.data.type = kind
    cam.data.ortho_scale = span * 1.08
    cam.data.lens = 85
    scene.render.filepath = f"{outdir}/board-3d-{name}.png"
    bpy.ops.render.render(write_still=True)
    print("rendered", scene.render.filepath)

# The edited model (black mask, drilled holes, back label) for build/board-3d.html.
# No Draco: the web viewer would have to fetch the decoder from a host the artifact sandbox blocks.
bpy.ops.export_scene.gltf(filepath=f"{outdir}/board-3d.glb", export_cameras=False, export_lights=False)
print("exported", f"{outdir}/board-3d.glb")

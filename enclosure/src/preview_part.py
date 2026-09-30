"""Dev tool: render one KiCad GLB, framed, to check how it imports.
blender -b -P preview_part.py -- <part.glb> <out.png> [view] [mask #rrggbb] [strip]"""
import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_util as U  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:]
glb, out = args[0], args[1]
view = args[2] if len(args) > 2 else "top"
mask = next((a for a in args[2:] if a.startswith("#")), None)
finish = next((a for a in args[2:] if a in ("copper", "gold", "tin")), None)

U.reset()
mats = U.Mats()
coll = U.collection("Part")
o = U.import_glb(glb, "part", coll, mats, mask=mask, finish=finish)
lo, hi = U.bounds(o)
c = (lo + hi) / 2
size = (hi - lo).length
sc = bpy.context.scene
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
d = {"top": (0.35, -0.6, 1.0), "front": (0.2, -1.0, 0.45), "bottom": (0.3, -0.6, -1.0),
     "side": (1.0, -0.5, 0.5), "plan": (0.0, -0.001, 1.0), "back": (-0.3, 1.0, 0.6)}[view]
cam.location = c + Vector(d).normalized() * size * 2.2
cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
cam.data.lens = 60
cam.data.clip_start = size * 0.01
cam.data.clip_end = size * 100
sc.render.resolution_x, sc.render.resolution_y = 1400, 1000
dg = bpy.context.evaluated_depsgraph_get()
pts = [o.matrix_world @ Vector(v) for v in o.bound_box]
loc, _ = cam.camera_fit_coords(dg, [x for p in pts for x in p])
cam.location = c + (loc - c) * 1.12
for rot, en in [((0.7, 0.25, 0.9), 3.5), ((-2.2, 0.4, -0.3), 1.2)]:
    s = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    s.data.energy = en
    s.data.angle = math.radians(8)
    s.rotation_euler = rot
    sc.collection.objects.link(s)
w = bpy.data.worlds.new("w")
sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.22, 0.23, 0.25, 1)
sc.render.engine = "CYCLES"
prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type = "METAL"
prefs.get_devices()
for dv in prefs.devices:
    dv.use = dv.type == "METAL"
sc.cycles.device = "GPU"
sc.cycles.samples = 48
sc.cycles.use_denoising = True
sc.view_settings.view_transform = "AgX"
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
print("PREVIEW", out, "size mm", tuple(round(v, 2) for v in (hi - lo)), "min", tuple(round(v, 2) for v in lo))

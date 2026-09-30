"""Dev tool: plain-light views of one pedal from pedal.blend.
blender -b ../pedal.blend -P debug_view.py -- <out_dir> <open|closed> [views...]"""
import math
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
out, which = argv[0], argv[1]
views = argv[2:] or ["top"]
sc = bpy.context.scene
ped = bpy.data.objects["Pedal_Open" if which == "open" else "Pedal_Closed"]
other = bpy.data.objects["Pedal_Closed" if which == "open" else "Pedal_Open"]
other.hide_render = True
for o in bpy.data.collections["Set"].all_objects:
    o.hide_render = True
c = ped.location + Vector((0, 0, 0.02))
sun = bpy.data.objects.new("dbg_sun", bpy.data.lights.new("dbg_sun", "SUN"))
sun.data.energy = 3.0
sun.data.angle = math.radians(10)
sun.rotation_euler = (math.radians(25), math.radians(10), math.radians(30))
sc.collection.objects.link(sun)
sc.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.35, 0.35, 0.37, 1)
cam = bpy.data.objects.new("dbg_cam", bpy.data.cameras.new("dbg_cam"))
sc.collection.objects.link(cam)
sc.camera = cam
sc.cycles.samples = 32
sc.render.resolution_percentage = 100
for v in views:
    cam.data.type = "PERSP"
    cam.data.lens = 50
    cam.data.dof.use_dof = False
    if v == "top":
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = 0.205
        cam.location = c + Vector((0, 0, 0.5))
        cam.rotation_euler = (0, 0, 0)
        sc.render.resolution_x, sc.render.resolution_y = 1600, 1400
    else:
        d = {"front": (0.0, -1.0, 0.75), "left": (-1.0, -0.2, 0.8), "right": (1.0, -0.2, 0.8),
             "rear": (0.1, 1.0, 0.8), "low": (0.35, -1.0, 0.35)}[v]
        cam.location = c + Vector(d).normalized() * 0.36
        cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
        sc.render.resolution_x, sc.render.resolution_y = 1600, 1200
    sc.render.filepath = f"{out}/{which}_{v}.png"
    bpy.ops.render.render(write_still=True)
    print("RENDERED", sc.render.filepath)

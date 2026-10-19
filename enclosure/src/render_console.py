"""Renders console.blend's cameras, each in the scene it belongs to.
  blender -b console.blend -P src/render_console.py -- [--out DIR] [--samples N] [--scale PCT]
                                                       [--turntable [FIRST-LAST]] [CON_NAME ...]
With no camera names, renders every camera whose name starts with CON_, at frame 1 (the hero
still). --turntable renders the hero camera over the turntable's frames (default all 240) into
renders/console_turntable/, for the video; it is not part of the default build."""
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
out = os.path.normpath(os.path.join(HERE, "..", "renders"))
samples, scale, cams, turntable = None, 100, [], None
i = 0
while i < len(argv):
    a = argv[i]
    if a == "--out":
        out, i = argv[i + 1], i + 2
    elif a == "--samples":
        samples, i = int(argv[i + 1]), i + 2
    elif a == "--scale":
        scale, i = int(argv[i + 1]), i + 2
    elif a == "--turntable":
        nxt = argv[i + 1] if i + 1 < len(argv) else ""
        if "-" in nxt and nxt.replace("-", "").isdigit():
            turntable, i = tuple(int(x) for x in nxt.split("-")), i + 2
        else:
            turntable, i = (), i + 1
    else:
        cams.append(a)
        i += 1

prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type = "METAL"
prefs.get_devices()
for d in prefs.devices:
    d.use = d.type == "METAL"


def setup(sc):
    sc.cycles.device = "GPU"
    if samples:
        sc.cycles.samples = samples
    sc.render.resolution_percentage = scale


def scene_of(cam):
    for sc in bpy.data.scenes:
        if cam.name in sc.objects:
            return sc
    raise SystemExit(f"{cam.name} is in no scene")


os.makedirs(out, exist_ok=True)
if turntable is not None:
    sc = bpy.data.scenes["Console"]
    setup(sc)
    sc.camera = bpy.data.objects["CON_1_Hero"]
    first, last = turntable or (sc.frame_start, sc.frame_end)
    sc.frame_start, sc.frame_end = first, last
    sc.render.filepath = os.path.join(out, "console_turntable", "####")
    bpy.ops.render.render(animation=True, scene=sc.name)
    print("RENDERED", os.path.dirname(sc.render.filepath), f"frames {first}-{last}")
    raise SystemExit(0)

cams = cams or sorted(o.name for o in bpy.data.objects if o.type == "CAMERA" and o.name.startswith("CON_"))
for name in cams:
    cam = bpy.data.objects[name]
    sc = scene_of(cam)
    setup(sc)
    sc.camera = cam
    sc.frame_set(1)
    sc.render.filepath = os.path.join(out, "console_" + name.lower().replace("con_", "") + ".png")
    bpy.ops.render.render(write_still=True, scene=sc.name)
    print("RENDERED", sc.render.filepath)

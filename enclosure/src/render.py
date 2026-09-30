"""Renders cameras from pedal.blend.
  blender -b ../pedal.blend -P render.py -- [--out DIR] [--samples N] [--scale PCT] [CAM_NAME ...]
With no camera names, renders every camera whose name starts with CAM_."""
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
out = os.path.normpath(os.path.join(HERE, "..", "renders"))
samples, scale, cams, view, exposure = None, 100, [], None, None
i = 0
while i < len(argv):
    a = argv[i]
    if a == "--out":
        out, i = argv[i + 1], i + 2
    elif a == "--samples":
        samples, i = int(argv[i + 1]), i + 2
    elif a == "--scale":
        scale, i = int(argv[i + 1]), i + 2
    elif a == "--view":
        view, i = argv[i + 1], i + 2
    elif a == "--exposure":
        exposure, i = float(argv[i + 1]), i + 2
    else:
        cams.append(a)
        i += 1
sc = bpy.context.scene
prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type = "METAL"
prefs.get_devices()
for d in prefs.devices:
    d.use = d.type == "METAL"
sc.cycles.device = "GPU"
if samples:
    sc.cycles.samples = samples
sc.render.resolution_percentage = scale
if view:
    sc.view_settings.view_transform = view
    sc.view_settings.look = "None"
if exposure is not None:
    sc.view_settings.exposure = exposure
cams = cams or sorted(o.name for o in bpy.data.objects if o.type == "CAMERA" and o.name.startswith("CAM_"))
os.makedirs(out, exist_ok=True)
base_exposure = sc.view_settings.exposure
for name in cams:
    sc.camera = bpy.data.objects[name]
    if exposure is None:
        sc.view_settings.exposure = sc.camera.get("exposure", base_exposure)
    sc.render.filepath = os.path.join(out, name.lower().replace("cam_", "") + ".png")
    bpy.ops.render.render(write_still=True)
    print("RENDERED", sc.render.filepath)

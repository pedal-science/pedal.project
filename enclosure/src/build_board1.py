"""Builds stripboard/board1.blend: board 1 on its own, as built on the bench, with renders.

  blender -b --factory-startup -P src/build_board1.py [-- --no-render] [--samples N]

Needs assets/parts/board1.glb and soic_adapter.glb (src/make_parts.py board1 soic_adapter).
The board is the layout in stripboard/board1.py: parts from its hole list, its wire links,
and a short flying lead from each off-board pad. Millimetres, instanced into the scene at
0.001. Board x runs along the strips, row 0 is the far edge, the top face is at z 1.6.
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bl_util as U  # noqa: E402
from bl_wires import Wiring  # noqa: E402

REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
OUT_DIR = os.path.join(REPO, "stripboard")
BLEND = os.path.join(OUT_DIR, "board1.blend")
RENDERS = os.path.join(OUT_DIR, "renders")
PARTS = os.path.join(U.ASSETS, "parts")
P = 2.54
T = 1.6                       # board thickness
ADAPTER_Z = T + 4.1 + 2.5     # the SOIC adapter's underside, on the DIP socket (as in bl_pedal)

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SAMPLES = int(args[args.index("--samples") + 1]) if "--samples" in args else 192

meta = json.load(open(os.path.join(PARTS, "parts.json")))["board1"]
COLS, ROWS = meta["cols"], meta["rows"]
BW, BH = COLS * P, ROWS * P


def hole(c, r, z=T):
    return Vector((P / 2 + c * P, BH - P / 2 - r * P, z))


def links(W):
    """Short links are bare tinned wire; longer ones insulated orange hook-up wire."""
    bare = W.M.tin
    for (a, b) in meta["links"]:
        pa, pb = hole(*a), hole(*b)
        n = abs(a[0] - b[0]) + abs(a[1] - b[1])
        h = 0.9 if n == 1 else 1.6
        pts = [pa - Vector((0, 0, 1.4)), pa + Vector((0, 0, h - 0.6)), pa + Vector((0, 0, h)),
               pb + Vector((0, 0, h)), pb + Vector((0, 0, h - 0.6)), pb - Vector((0, 0, 1.4))]
        if n == 1:
            W.poly(f"Link_{a}_{b}", pts, 0.3, bare)
        else:
            W.poly(f"LinkCore_{a}_{b}", pts, 0.3, bare)
            W.poly(f"Link_{a}_{b}", pts[1:-1], 0.72, W.mat("orange"))


# Flying leads: which way each one leaves the board, its colour, and a sideways step (mm)
# so leads leaving the same way don't lie on top of each other.
LEADS = {
    "STAR": ("left", "black", 0), "+9V": ("right", "orange", 0), "IN": ("left", "screened", 0),
    "SW-I": ("down", "yellow", 0), "SW-L": ("down", "green", 0), "SW-C": ("down", "white", 1.6),
    "LIN1": ("up", "blue", 0), "HPL": ("down", "red", -4.0), "HPR": ("down", "purple", 0),
    "OUT-L": ("down", "red", -4.0), "OUT-R": ("down", "purple", 0),
}


def flying_leads(W):
    for label, (c, r) in meta["pads"].items():
        way, colour, step = LEADS[label]
        p = hole(c, r)
        d = {"left": Vector((-1, 0, 0)), "right": Vector((1, 0, 0)), "up": Vector((0, 1, 0)),
             "down": Vector((0, -1, 0))}[way]
        side = Vector((-d.y, d.x, 0)) * step
        # Distance to the board edge in that direction, then 18 mm beyond it.
        edge = {"left": p.x, "right": BW - p.x, "up": BH - p.y, "down": p.y}[way]
        rise = 7.0 + (r % 3) * 1.2               # clear of the parts, staggered by row
        z = Vector((0, 0, 1))
        pts = [p - z * 1.4, p + z * (rise * 0.4), p + z * rise + d * 1.5 + side,
               p + z * (rise + 0.5) + d * (edge + 6) + side, p + z * (rise + 2) + d * (edge + 18) + side]
        if colour == "screened":
            W.curve(f"Lead_{label}", pts[1:], 1.3, W.mat("sheath"))
            W.poly(f"Lead_{label}_core", pts[:2], 0.4, W.M.tin)
        else:
            W.curve(f"Lead_{label}", pts[1:], 0.72, W.mat(colour))
            W.poly(f"Lead_{label}_core", pts[:2], 0.3, W.M.tin)


def solder(coll, M):
    """A small fillet under every lead: pads, links and part leads all go through holes."""
    import bmesh
    bm = bmesh.new()
    used = set()
    for (a, b) in meta["links"]:
        used |= {tuple(a), tuple(b)}
    used |= {tuple(v) for v in meta["pads"].values()}
    sys.path.insert(0, OUT_DIR)
    import board1 as B1
    for _, _, leads in B1.PARTS.values():
        used |= {h for h, _ in leads}
    for c, r in used:
        x, y, _ = hole(c, r)
        U.cyl(bm, 0.95, -0.35, 0.0, x=x, y=y, seg=20, r2=0.45)
    me = U.mesh_from_bm(bm, "Solder")
    o = U.new_obj("Solder", me, coll, mat=M.solder)
    for p in o.data.polygons:
        p.use_smooth = True


def scene(coll):
    sc = bpy.context.scene
    e = bpy.data.objects.new("Board1", None)
    e.instance_type = "COLLECTION"
    e.instance_collection = coll
    e.scale = (0.001, 0.001, 0.001)
    e.location = (-BW / 2000, -BH / 2000, 0)
    sc.collection.objects.link(e)
    coll.hide_render = False
    # A neutral mat underneath, far enough below that the underside camera can look past it.
    bpy.ops.mesh.primitive_plane_add(size=0.6, location=(0, 0, -0.012))
    mat = bpy.context.active_object
    mat.name = "Bench"
    mat.data.materials.append(U.principled("BenchMat", U.srgb("#3b4a52")[:3], rough=0.8))
    for rot, energy in [((0.75, 0.2, 0.8), 3.2), ((-0.9, -0.5, -2.4), 1.0)]:
        s = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
        s.data.energy = energy
        s.data.angle = math.radians(6)
        s.rotation_euler = rot
        sc.collection.objects.link(s)
    w = bpy.data.worlds.new("World")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.20, 0.21, 0.23, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.8
    cams = {
        "CAM_3quarter": ((0.05, -0.16, 0.13), (0.0, 0.004, 0.0), 45),
        "CAM_plan": ((0.0, 0.0, 0.26), (0.0, 0.0, 0.0), 50),
        "CAM_low": ((-0.17, -0.12, 0.05), (0.012, 0.0, 0.004), 50),
        "CAM_copper": ((0.0, 0.0, -0.23), (0.0, 0.0, 0.0), 50),
    }
    # Light for the underside view only; switched on while that camera renders.
    s = bpy.data.objects.new("UnderLight", bpy.data.lights.new("UnderLight", "SUN"))
    s.data.energy = 3.0
    s.data.angle = math.radians(6)
    s.rotation_euler = (math.pi - 0.45, 0.25, 0)
    sc.collection.objects.link(s)
    for name, (loc, at, lens) in cams.items():
        cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
        cam.location = loc
        cam.rotation_euler = (Vector(at) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        cam.data.lens = lens
        cam.data.clip_start = 0.005
        sc.collection.objects.link(cam)
    # Straight up from below, turned so it matches board1-copper.svg: row 0 at the top,
    # column 0 on the right.
    bpy.data.objects["CAM_copper"].rotation_euler = (math.pi, 0, math.pi)
    sc.camera = bpy.data.objects["CAM_3quarter"]
    sc.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "METAL"
    prefs.get_devices()
    for dv in prefs.devices:
        dv.use = dv.type == "METAL"
    sc.cycles.device = "GPU"
    sc.cycles.samples = SAMPLES
    sc.cycles.use_denoising = True
    sc.view_settings.view_transform = "AgX"
    sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
    return cams


def under(on):
    """The underside view: hide the bench, light from below."""
    bpy.data.objects["Bench"].hide_render = on
    bpy.data.objects["UnderLight"].hide_render = not on
    for o in bpy.data.objects:
        if o.type == "LIGHT" and o.name != "UnderLight":
            o.hide_render = on


def main():
    U.reset()
    M = U.Mats()
    coll = U.collection("Board1Parts")
    board = U.import_glb(os.path.join(PARTS, "board1.glb"), "Stripboard", coll, M, finish="copper")
    board.location = (0, BH, 0)
    adapter = U.import_glb(os.path.join(PARTS, "soic_adapter.glb"), "SOICAdapter", coll, M, mask="#0F3F2A",
                           finish="gold", mask_name="adapter")
    x, y, _ = hole(18, 1)
    adapter.location = (x - 1.29, y + 1.49, ADAPTER_Z)
    W = Wiring(coll, M)
    links(W)
    flying_leads(W)
    W.finish()
    solder(coll, M)
    # The parts live in a hidden source collection, instanced into the scene.
    bpy.context.scene.collection.children.unlink(coll)
    cams = scene(coll)
    under(False)
    bpy.ops.wm.save_as_mainfile(filepath=BLEND, compress=True)
    print("SAVED", BLEND)
    if "--no-render" in args:
        return
    os.makedirs(RENDERS, exist_ok=True)
    sc = bpy.context.scene
    for name in cams:
        sc.camera = bpy.data.objects[name]
        under(name == "CAM_copper")
        sc.render.filepath = os.path.join(RENDERS, f"board1-{name[4:].replace('_', '')}.png")
        bpy.ops.render.render(write_still=True)
        print("RENDERED", sc.render.filepath)


main()

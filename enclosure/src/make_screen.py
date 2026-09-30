"""Renders the display's contents (320 x 240, at 3x) to assets/screen_ui.png.
blender -b -P make_screen.py"""
import os
import sys

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_util as U  # noqa: E402

OUT = os.path.join(U.ASSETS, "screen_ui.png")
FONT = "/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf"
FONT_C = "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf"
ORANGE = "#f2641c"

U.reset()
sc = bpy.context.scene
coll = sc.collection
font = bpy.data.fonts.load(FONT)
font_c = bpy.data.fonts.load(FONT_C)
_mat = {}


def emit(hexcol, strength=1.0):
    key = (hexcol, strength)
    if key not in _mat:
        m = bpy.data.materials.new("e" + hexcol)
        m.use_nodes = True
        nt = m.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        e = nt.nodes.new("ShaderNodeEmission")
        e.inputs[0].default_value = U.srgb(hexcol)
        e.inputs[1].default_value = strength
        o = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(e.outputs[0], o.inputs[0])
        _mat[key] = m
    return _mat[key]


z_layer = [0.0]


def rect(x, y, w, h, col, r=0.0):
    """Rectangle in screen pixels, (x, y) its top-left, y down."""
    z_layer[0] += 0.01
    bm = bmesh.new()
    pts = U.rounded_rect_pts(w, h, r, seg=6, cx=x + w / 2, cy=-(y + h / 2)) if r > 0 else \
        [(x, -y - h), (x + w, -y - h), (x + w, -y), (x, -y)]
    bm.faces.new([bm.verts.new((px, py, z_layer[0])) for px, py in pts])
    me = U.mesh_from_bm(bm, "r")
    return U.new_obj("rect", me, coll, mat=emit(col))


def text(s, x, y, size, col, align="LEFT", f=None):
    """Text whose baseline starts at (x, y), y down."""
    z_layer[0] += 0.01
    cu = bpy.data.curves.new("t", "FONT")
    cu.body = s
    cu.font = f or font
    cu.size = size
    cu.align_x = align
    o = bpy.data.objects.new("text", cu)
    coll.objects.link(o)
    o.location = (x, -y, z_layer[0])
    o.data.materials.append(emit(col))
    return o


# Background and top bar.
rect(0, 0, 320, 240, "#070709")
rect(0, 0, 320, 24, "#141418")
rect(0, 24, 320, 1.5, ORANGE)
text("RIG 07", 10, 17, 13, ORANGE)
text("BANK A", 160, 17, 11, "#8a8a92", align="CENTER")
text("48 kHz  2.7 ms", 310, 17, 11, "#8a8a92", align="RIGHT")
rect(45, 8.5, 6, 6, "#39d353", r=3)                                   # engine running

# The rig.
text("Crunch Lead", 10, 66, 34, "#f4f4f6")
text("PLEXI 1968  /  4x12 V30  /  PLATE", 11, 88, 12, "#9a9aa3", f=font_c)

# Meters: 24 segments each, green to amber to orange.
for i, (label, level) in enumerate((("IN", 15), ("OUT", 18))):
    y = 108 + i * 22
    text(label, 10, y + 11, 11, "#8a8a92")
    for k in range(24):
        col = "#2fbf5b" if k < 15 else ("#f5b82e" if k < 20 else ORANGE)
        if k >= level:
            col = "#1d1d22"
        rect(44 + k * 11, y, 9, 13, col, r=1.2)

# Footswitch assignments.
for i, (letter, name, active) in enumerate((("A", "BOOST", True), ("B", "DELAY", False), ("C", "TAP 120", False))):
    x = 8 + i * 104
    if active:
        rect(x, 170, 96, 60, ORANGE, r=6)
        tc, lc = "#0b0b0c", "#3a1a08"
    else:
        rect(x, 170, 96, 60, "#3a3a42", r=6)
        rect(x + 1.5, 171.5, 93, 57, "#101014", r=5)
        tc, lc = "#d8d8de", "#7a7a84"
    text(letter, x + 8, 188, 12, lc)
    text(name, x + 48, 216, 17, tc, align="CENTER")

cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
coll.objects.link(cam)
cam.data.type = "ORTHO"
cam.data.ortho_scale = 320
cam.location = (160, -120, 50)
sc.camera = cam
sc.render.resolution_x, sc.render.resolution_y = 960, 720
sc.render.engine = "BLENDER_EEVEE"
sc.view_settings.view_transform = "Standard"
w = bpy.data.worlds.new("w")
sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0, 0, 0, 1)
sc.render.filepath = OUT
bpy.ops.render.render(write_still=True)
print("SCREEN", OUT)

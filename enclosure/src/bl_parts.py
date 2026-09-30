"""Procedural models of the parts KiCad's library doesn't have. All in millimetres.

Each builder returns one object (several materials) in its own frame:
  panel parts (footswitch, toggle, LED): origin on the panel's top surface, +z up;
  wall parts (jacks, DIN, DC, USB-C): origin on the wall's outside surface, +z outward.
Solder points are stored on the object as custom properties, in that local frame.
"""
import math

import bmesh
import bpy
from mathutils import Matrix

import bl_util as U
import layout as L


class MB:
    """Collects bmesh pieces, each with a material, into one object."""

    def __init__(self, name):
        self.name = name
        self.bm = bmesh.new()
        self.mats = []

    def add(self, mat, build, matrix=None, smooth=True):
        t = bmesh.new()
        build(t)
        if matrix is not None:
            bmesh.ops.transform(t, matrix=matrix, verts=t.verts)
        if mat not in self.mats:
            self.mats.append(mat)
        i = self.mats.index(mat)
        for f in t.faces:
            f.material_index = i
            f.smooth = smooth
        me = U.mesh_from_bm(t, "tmp")
        self.bm.from_mesh(me)
        bpy.data.meshes.remove(me)

    def obj(self, coll, bevel=0.0, seg=2, angle=40):
        me = U.mesh_from_bm(self.bm, self.name)
        U.sharpen(me, 35)
        o = U.new_obj(self.name, me, coll, mat=self.mats)
        if bevel:
            U.bevel(o, bevel, segments=seg, limit_angle=angle)
        return o


def T(x=0, y=0, z=0):
    return Matrix.Translation((x, y, z))


def Rx(d):
    return Matrix.Rotation(math.radians(d), 4, "X")


def Ry(d):
    return Matrix.Rotation(math.radians(d), 4, "Y")


def Rz(d):
    return Matrix.Rotation(math.radians(d), 4, "Z")


def thread(r_major, z0, z1, pitch=0.75, depth=0.35, bore=None):
    """Closed lathe profile of a threaded rod (bore=None) or tube from z0 up to z1."""
    rm = r_major - depth
    pts = [(bore if bore else 0.0, z0), (rm, z0)]
    n = max(1, int((z1 - z0) / pitch))
    for i in range(n):
        z = z0 + i * pitch
        pts += [(rm, z + 0.08 * pitch), (r_major, z + 0.42 * pitch), (r_major, z + 0.58 * pitch),
                (rm, z + 0.92 * pitch)]
    pts += [(rm, z1), (bore if bore else 0.0, z1)]
    return pts


def lathe(bm, prof, seg=48, closed=None, matrix=None):
    """Lathe a profile; tubes (no point on the axis) are closed automatically."""
    if closed is None:
        closed = all(r > 1e-6 for r, _ in prof)
    U.lathe(bm, prof, seg=seg, closed=closed, matrix=matrix)


def hex_nut(bm, af, z0, z1, hole, x=0.0, y=0.0, chamfer=0.45, seg=36):
    """Hex nut, across-flats af, with the usual 30 degree chamfer on both faces."""
    rf = af / 2

    def r_hex(a):
        return rf / math.cos(((a - math.pi / 6) % (math.pi / 3)) - math.pi / 6)

    angs = [2 * math.pi * k / seg for k in range(seg)]
    r_top = [min(r_hex(a), rf * 0.97) for a in angs]
    c = min(chamfer, (z1 - z0) / 3)
    rings = [
        [(r_top[k], z0) for k in range(seg)],
        [(r_hex(a), z0 + c) for a in angs],
        [(r_hex(a), z1 - c) for a in angs],
        [(r_top[k], z1) for k in range(seg)],
        [(hole, z1)] * seg,
        [(hole, z0)] * seg,
    ]
    t = bmesh.new()
    vs = [[t.verts.new((x + r * math.cos(a), y + r * math.sin(a), z)) for (r, z), a in zip(ring, angs)]
          for ring in rings]
    n = len(vs)
    for i in range(n):
        a_ring, b_ring = vs[i], vs[(i + 1) % n]
        for k in range(seg):
            l = (k + 1) % seg
            t.faces.new((a_ring[k], a_ring[l], b_ring[l], b_ring[k]))
    bmesh.ops.recalc_face_normals(t, faces=t.faces)
    me = U.mesh_from_bm(t, "nut")
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)


def washer(bm, r_out, r_in, z0, z1, seg=48):
    lathe(bm, [(r_in, z0), (r_out, z0), (r_out, z1), (r_in, z1)], seg=seg, closed=True)


# ---- Footswitch: Multicomp Pro MC7105 (DPDT momentary, solder tags) -----------------------------

def footswitch(name, coll, M, panel=2.6):
    mb = MB(name)
    zc = -panel - 2.4                                   # top of the steel can
    # Chrome actuator with a domed top.
    mb.add(M.chrome, lambda bm: lathe(bm, [(0.0, 12.6), (2.6, 12.5), (3.8, 12.2), (4.55, 11.6), (4.8, 10.9),
                                           (4.8, 7.9), (4.35, 7.6), (4.35, 5.5), (0.0, 5.5)], seg=64))
    mb.add(M.nickel, lambda bm: lathe(bm, thread(6.0, zc, 6.2, pitch=0.8, depth=0.4, bore=4.4), seg=64))
    mb.add(M.nickel, lambda bm: washer(bm, 8.4, 6.05, 0.0, 0.55))
    mb.add(M.chrome, lambda bm: hex_nut(bm, 15.0, 0.55, 2.95, 6.05))
    mb.add(M.nickel, lambda bm: hex_nut(bm, 15.0, zc, -panel, 6.05))
    # Body: steel can, black phenolic base, six solder tags.
    mb.add(M.zinc, lambda bm: U.box(bm, -9.45, -7.2, zc - 11.0, 9.45, 7.2, zc))
    mb.add(M.black_plastic, lambda bm: U.box(bm, -9.0, -6.8, zc - 13.6, 9.0, 6.8, zc - 11.0))
    tags = []
    for ix in (-5.2, 0.0, 5.2):
        for iy in (-3.3, 3.3):
            tags.append((ix, iy, zc - 18.3))
            mb.add(M.tin, lambda bm, ix=ix, iy=iy: U.box(bm, ix - 1.4, iy - 0.25, zc - 19.3, ix + 1.4, iy + 0.25,
                                                        zc - 13.6), smooth=False)
    o = mb.obj(coll, bevel=0.25, seg=2)
    o["tags"] = tags
    return o


# ---- Neutrik NMJ6HF-S jack --------------------------------------------------------------------

def jack(name, coll, M, wall=L.ENC["wall"]):
    mb = MB(name)
    zb = -wall
    mb.add(M.black_plastic, lambda bm: lathe(bm, thread(5.5, zb, 7.0, pitch=1.0, depth=0.35, bore=3.25), seg=48))
    mb.add(M.matte_black, lambda bm: U.cyl(bm, 3.24, zb - 1.0, 3.2, seg=32))    # the throat, 4 mm down

    def nut(bm):
        pts = []
        for i in range(96):
            a = 2 * math.pi * i / 96
            r = 7.5 - (0.45 if (i // 6) % 2 else 0.0)
            pts.append((r * math.cos(a), r * math.sin(a)))
        U.extrude_poly(bm, pts, 0.6, 3.6)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        # bore through the nut is covered by the nose; nothing to cut.
    mb.add(M.black_plastic, nut, smooth=False)
    mb.add(M.dark_plastic, lambda bm: washer(bm, 7.2, 5.6, 0.0, 0.6))
    mb.add(M.black_plastic, lambda bm: U.box(bm, -7.7, -9.1, zb - 13.2, 7.7, 9.1, zb))
    tags = {"T": (-4.2, 5.4), "TS": (-4.2, 1.6), "R": (4.2, 5.4), "RS": (4.2, 1.6), "S": (0.0, -6.2)}
    for k, (x, y) in tags.items():
        mb.add(M.tin, lambda bm, x=x, y=y: U.box(bm, x - 1.2, y - 0.2, zb - 19.0, x + 1.2, y + 0.2, zb - 13.2),
               smooth=False)
    o = mb.obj(coll, bevel=0.3, seg=2)
    o["tags"] = {k: (x, y, zb - 18.2) for k, (x, y) in tags.items()}
    return o


# ---- DIN 5-pin 180 degree socket (Deltron 650-0500) -------------------------------------------

def din(name, coll, M, wall=L.ENC["wall"]):
    mb = MB(name)
    zb = -wall
    # Nickel shell: body inside the wall, threaded nose through it, lip at the mouth.
    mb.add(M.nickel, lambda bm: lathe(bm, [(6.9, 1.0), (6.9, 4.2), (7.35, 4.2), (7.85, 3.8), (7.85, zb),
                                           (9.3, zb), (9.3, zb - 12.4), (7.6, zb - 12.4), (7.6, 0.8)],
                                       seg=64, closed=True))
    mb.add(M.brass, lambda bm: hex_nut(bm, 19.0, 0.0, 2.2, 7.9))
    mb.add(M.black_plastic, lambda bm: U.cyl(bm, 6.9, zb - 12.0, 2.4, seg=48))  # insulator
    for a in (-90, -45, 0, 45, 90):
        x, y = 3.5 * math.sin(math.radians(a)), 3.5 * math.cos(math.radians(a))
        mb.add(M.matte_black, lambda bm, x=x, y=y: U.cyl(bm, 0.72, 2.36, 2.42, x=x, y=y, seg=16))
    mb.add(M.nickel, lambda bm: U.box(bm, -1.0, -7.4, 0.9, 1.0, -6.5, 3.9))     # key
    pins = {}
    for i, a in enumerate((-90, -45, 0, 45, 90)):
        x, y = 3.5 * math.sin(math.radians(a)), 3.5 * math.cos(math.radians(a))
        pins[str(i + 1)] = (x, y, zb - 16.6)
        mb.add(M.tin, lambda bm, x=x, y=y: U.box(bm, x - 0.5, y - 0.5, zb - 17.6, x + 0.5, y + 0.5, zb - 12.0),
               smooth=False)
    o = mb.obj(coll, bevel=0.2, seg=2)
    o["pins"] = pins
    return o


# ---- 2.1 mm DC socket (Cliff FC681445), insulated, panel mount --------------------------------

def dc_socket(name, coll, M, wall=L.ENC["wall"]):
    mb = MB(name)
    zb = -wall
    mb.add(M.black_plastic, lambda bm: lathe(bm, thread(5.6, zb, 5.2, pitch=0.9, depth=0.3, bore=3.1), seg=48))
    mb.add(M.matte_black, lambda bm: U.cyl(bm, 3.09, zb, 2.2, seg=32))
    mb.add(M.nickel, lambda bm: U.cyl(bm, 1.0, 2.0, 4.9, seg=20))       # centre pin
    mb.add(M.nickel, lambda bm: hex_nut(bm, 14.0, 0.0, 2.3, 5.7))
    mb.add(M.black_plastic, lambda bm: U.cyl(bm, 6.5, zb - 12.0, zb, seg=40))
    tags = {"PIN": (0.0, 3.6), "SLEEVE": (-3.4, -2.2), "SW": (3.4, -2.2)}
    for k, (x, y) in tags.items():
        mb.add(M.tin, lambda bm, x=x, y=y: U.box(bm, x - 1.1, y - 0.2, zb - 18.0, x + 1.1, y + 0.2, zb - 12.0),
               smooth=False)
    o = mb.obj(coll, bevel=0.25, seg=2)
    o["tags"] = {k: (x, y, zb - 17.2) for k, (x, y) in tags.items()}
    return o


# ---- USB-C panel socket (5 V in) ------------------------------------------------------------

def usbc_socket(name, coll, M, wall=L.ENC["wall"]):
    mb = MB(name)
    zb = -wall
    mb.add(M.steel, lambda bm: U.extrude_poly(bm, U.rounded_rect_pts(8.94, 3.26, 1.63, seg=10), zb - 7.5, -0.3))
    mb.add(M.matte_black, lambda bm: U.extrude_poly(bm, U.rounded_rect_pts(8.3, 2.62, 1.3, seg=8), -3.0, -0.28))
    mb.add(M.black_plastic, lambda bm: U.box(bm, -3.3, -0.35, -3.2, 3.3, 0.35, -0.8))       # tongue
    mb.add(M.black_plastic, lambda bm: U.extrude_poly(bm, U.rounded_rect_pts(22.0, 8.5, 1.5), zb - 2.2, zb))
    for sx in (-8.5, 8.5):
        mb.add(M.black_oxide, lambda bm, sx=sx: lathe(bm, [(0.0, 1.35), (1.6, 1.3), (2.35, 0.8), (2.4, 0.0),
                                                          (1.25, 0.0), (1.25, zb - 3.2), (0.0, zb - 3.2)], seg=32,
                                                      matrix=T(sx, 0, 0)))
        mb.add(M.steel, lambda bm, sx=sx: hex_nut(bm, 5.0, zb - 4.0, zb - 2.2, 1.25, x=sx))
    mb.add(M.mask(U.srgb("#16161a"), "usbc"), lambda bm: U.box(bm, -7.5, -4.0, zb - 3.8, 7.5, 4.0, zb - 2.2))
    for px in (-3.0, 3.0):
        mb.add(M.gold, lambda bm, px=px: U.box(bm, px - 1.6, -1.2, zb - 3.86, px + 1.6, 1.2, zb - 3.78))
    o = mb.obj(coll, bevel=0.15, seg=2)
    o["pads"] = {"VBUS": (-3.0, 0.0, zb - 3.9), "GND": (3.0, 0.0, zb - 3.9)}
    return o


# ---- Mini toggle, SPDT on-on (Multicomp Pro 1MS1T1B1M1RE) --------------------------------------

def toggle(name, coll, M, panel=2.6, flip=14.0):
    mb = MB(name)
    zb = -panel
    mb.add(M.nickel, lambda bm: lathe(bm, thread(3.1, zb - 2.0, 7.2, pitch=0.635, depth=0.25, bore=2.2), seg=40))
    mb.add(M.nickel, lambda bm: washer(bm, 5.0, 3.15, 0.0, 0.5))
    mb.add(M.nickel, lambda bm: hex_nut(bm, 9.5, 0.5, 2.5, 3.15))
    mb.add(M.nickel, lambda bm: hex_nut(bm, 9.5, zb - 2.0, zb, 3.15))
    bat = [(0.0, 0.0), (1.4, 0.0), (1.15, 6.0), (1.02, 9.0), (1.18, 10.2), (0.95, 10.9), (0.0, 11.05)]
    mb.add(M.chrome, lambda bm: lathe(bm, bat, seg=32, matrix=T(0, 0, 6.0) @ Ry(flip)))
    mb.add(M.zinc, lambda bm: U.box(bm, -6.5, -4.0, zb - 11.0, 6.5, 4.0, zb - 2.0))
    mb.add(M.black_plastic, lambda bm: U.box(bm, -6.1, -3.7, zb - 14.5, 6.1, 3.7, zb - 11.0))
    tags = {}
    for k, x in (("A", -4.7), ("C", 0.0), ("B", 4.7)):
        tags[k] = (x, 0.0, zb - 18.5)
        mb.add(M.tin, lambda bm, x=x: U.box(bm, x - 0.9, -0.2, zb - 19.5, x + 0.9, 0.2, zb - 14.5), smooth=False)
    o = mb.obj(coll, bevel=0.2, seg=2)
    o["tags"] = tags
    return o


# ---- 5 mm LED in an HLMP-0103 panel clip ---------------------------------------------------------

def led(name, coll, M, lens_mat, panel=2.6):
    mb = MB(name)
    zb = -panel
    mb.add(M.black_plastic, lambda bm: lathe(bm, [(2.9, 1.1), (4.15, 1.1), (4.15, 0.25), (3.95, 0.0), (3.2, 0.0),
                                                  (3.2, zb - 4.0), (2.9, zb - 4.0)], seg=48, closed=True))
    mb.add(M.black_plastic, lambda bm: washer(bm, 4.6, 3.2, zb - 1.4, zb))
    dome = [(0.0, 4.9)] + [(2.45 * math.sin(math.radians(a)), 2.45 + 2.45 * math.cos(math.radians(a)))
                            for a in range(10, 91, 10)] + \
           [(2.45, zb - 3.6), (2.85, zb - 3.6), (2.85, zb - 4.6), (0.0, zb - 4.6)]
    mb.add(lens_mat, lambda bm: lathe(bm, dome, seg=40))
    for x in (-1.27, 1.27):                                     # legs trimmed short
        mb.add(M.tin, lambda bm, x=x: U.box(bm, x - 0.25, -0.25, zb - 8.6, x + 0.25, 0.25, zb - 4.6), smooth=False)
    o = mb.obj(coll, bevel=0.12, seg=2)
    o["legs"] = [(-1.27, 0, zb - 8.1), (1.27, 0, zb - 8.1)]
    return o


# ---- EC11 encoder (on the display board) with its panel nut, and the knob ----------------------

def encoder(name, coll, M, body_top, panel_top):
    """Origin at the encoder's centre on the display board's top surface (z = 0)."""
    mb = MB(name)
    h = body_top
    mb.add(M.zinc, lambda bm: U.box(bm, -6.0, -5.85, 1.2, 6.0, 5.85, h))
    mb.add(M.black_plastic, lambda bm: U.box(bm, -6.2, -6.1, 0.0, 6.2, 6.1, 1.2))
    for yy in (-2.5, 0.0, 2.5):
        mb.add(M.tin, lambda bm, yy=yy: U.box(bm, -8.2, yy - 0.35, -3.2, -7.4, yy + 0.35, 0.6), smooth=False)
    mb.add(M.nickel, lambda bm: lathe(bm, thread(3.5, h, panel_top + 4.6, pitch=0.75, depth=0.3, bore=3.0), seg=40))
    mb.add(M.nickel, lambda bm: washer(bm, 5.6, 3.55, panel_top, panel_top + 0.5))
    mb.add(M.nickel, lambda bm: hex_nut(bm, 10.0, panel_top + 0.5, panel_top + 2.4, 3.55))
    mb.add(M.steel, lambda bm: U.cyl(bm, 3.0, h, panel_top + 13.5, seg=18))
    return mb.obj(coll, bevel=0.2, seg=2)


def knob(name, coll, M, accent, base_z):
    """Machined black aluminium knob with a knurled grip and a pointer line. Origin on the shaft axis."""
    mb = MB(name)
    prof = [(0.0, base_z + 14.0), (5.2, base_z + 14.0), (6.3, base_z + 13.6), (6.6, base_z + 12.8),
            (6.6, base_z + 3.2), (7.2, base_z + 2.6), (7.2, base_z + 0.4), (6.9, base_z), (3.2, base_z),
            (3.2, base_z + 11.0), (0.0, base_z + 11.0)]
    mb.add(M.knob, lambda bm: lathe(bm, prof, seg=96))
    for i in range(40):
        a = 2 * math.pi * i / 40

        def ridge(bm, a=a):
            U.box(bm, -0.2, 6.45, base_z + 3.8, 0.2, 6.78, base_z + 12.3)
            bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(a, 3, "Z"), verts=bm.verts)
        mb.add(M.knob, ridge, smooth=False)
    mb.add(accent, lambda bm: U.box(bm, -0.45, 1.3, base_z + 14.0, 0.45, 5.2, base_z + 14.05), smooth=False)
    return mb.obj(coll, bevel=0.15, seg=2)


def button_cap(name, coll, M, z0, z1):
    mb = MB(name)
    mb.add(M.black_plastic, lambda bm: lathe(bm, [(0.0, z1), (2.8, z1 - 0.1), (3.5, z1 - 0.5), (3.6, z1 - 1.0),
                                                  (3.6, z0), (0.0, z0)], seg=48))
    return mb.obj(coll, bevel=0.1, seg=2)


# ---- 2.4" TFT panel on the display board --------------------------------------------------------

def tft(name, coll, M, screen_mat, glass=(60.4, 42.7)):
    """Origin at the glass's rear-left corner on the display board's top; x right, y to the
    front is negative (the board's photo orientation)."""
    gw, gh = glass
    mb = MB(name)
    mb.add(M.black_plastic, lambda bm: U.box(bm, 0.4, -gh + 0.4, 0.0, gw - 0.4, -0.4, 0.9))     # foam tape
    mb.add(M.white_plastic, lambda bm: U.box(bm, 0.0, -gh, 0.9, gw, 0.0, 2.9))                 # backlight
    mb.add(M.steel, lambda bm: U.box(bm, 0.25, -gh + 0.25, 2.9, gw - 0.25, -0.25, 3.05))
    mb.add(M.panel_black, lambda bm: U.box(bm, 0.0, -gh, 3.05, gw - 6.0, 0.0, 3.55))           # TFT glass
    mb.add(M.panel_black, lambda bm: U.box(bm, gw - 6.0, -gh + 1.5, 3.05, gw - 0.3, -1.5, 3.35))
    ax0, ay1 = 4.6, -(gh - 36.72) / 2
    act = (ax0, ay1 - 36.72, 3.555, ax0 + 48.96, ay1, 3.565)
    mb.add(screen_mat, lambda bm: U.box(bm, *act), smooth=False)
    mb.add(M.fpc, lambda bm: U.box(bm, gw - 0.4, -gh / 2 - 7.5, 0.05, gw + 3.3, -gh / 2 + 7.5, 0.18), smooth=False)
    mb.add(M.fpc, lambda bm: U.box(bm, gw - 0.6, -gh / 2 - 7.5, 0.18, gw - 0.45, -gh / 2 + 7.5, 3.1), smooth=False)
    o = mb.obj(coll, bevel=0.1, seg=1)
    me = o.data
    uv = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        for li in poly.loop_indices:
            v = me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = ((v.x - act[0]) / (act[3] - act[0]), (v.y - act[1]) / (act[4] - act[1]))
    return o


# ---- Fixings ------------------------------------------------------------------------------------

def pan_screw(bm, d, z0, length=0.0, up=True, x=0.0, y=0.0):
    """Pan-head Phillips screw whose head sits on z0, facing +z (up) or -z."""
    r = d * 0.95
    hh = d * 0.62
    s = 1 if up else -1
    prof = [(0.0, z0 + s * hh), (r * 0.72, z0 + s * hh), (r, z0 + s * hh * 0.55), (r, z0)]
    if length:
        prof += [(d / 2, z0), (d / 2, z0 - s * length), (0.0, z0 - s * length)]
    else:
        prof += [(0.0, z0)]
    lathe(bm, prof, seg=24, matrix=T(x, y, 0))
    for rot in (0, 90):
        t = bmesh.new()
        U.box(t, -r * 0.55, -0.22, z0 + s * hh - s * 0.4, r * 0.55, 0.22, z0 + s * (hh + 0.01))
        bmesh.ops.rotate(t, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(rot), 3, "Z"), verts=t.verts)
        bmesh.ops.translate(t, vec=(x, y, 0), verts=t.verts)
        me = U.mesh_from_bm(t, "x")
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)

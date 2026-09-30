"""Wires: hook-up wire, Dupont leads, screened cable and twisted pairs, with their ends.
Millimetres, enclosure coordinates."""
import math

import bmesh
import bpy
from mathutils import Vector

import bl_util as U

COLOURS = {
    "black": "#161616", "orange": "#ff6a0d", "red": "#c9161f", "yellow": "#f3c300", "green": "#1c9a3c",
    "blue": "#1f5ad8", "purple": "#7b3fb9", "grey": "#8d8d90", "white": "#ececec", "brown": "#6a3a1d",
    "pink": "#ee6aa7", "sheath": "#5d5e62",
}
RIBBON = ["brown", "red", "orange", "yellow", "green", "blue", "purple", "grey", "white", "black", "brown", "red"]


class Wiring:
    def __init__(self, coll, mats):
        self.coll = coll
        self.M = mats
        self.bm_bits = {}      # material -> bmesh of small solid bits (ends, housings, blobs)

    def mat(self, colour):
        return self.M.wire(U.srgb(COLOURS.get(colour, colour)), colour)

    # ---- curves --------------------------------------------------------------------------

    def curve(self, name, pts, radius, mat, res=10):
        cu = bpy.data.curves.new(name, "CURVE")
        cu.dimensions = "3D"
        cu.resolution_u = res
        cu.bevel_depth = radius
        cu.bevel_resolution = 3
        cu.use_fill_caps = True
        sp = cu.splines.new("BEZIER")
        sp.bezier_points.add(len(pts) - 1)
        for bp, p in zip(sp.bezier_points, pts):
            bp.co = p
            bp.handle_left_type = bp.handle_right_type = "AUTO"
        o = bpy.data.objects.new(name, cu)
        self.coll.objects.link(o)
        o.data.materials.append(mat)
        return o

    def poly(self, name, pts, radius, mat):
        cu = bpy.data.curves.new(name, "CURVE")
        cu.dimensions = "3D"
        cu.bevel_depth = radius
        cu.bevel_resolution = 3
        cu.use_fill_caps = True
        sp = cu.splines.new("POLY")
        sp.points.add(len(pts) - 1)
        for p, v in zip(sp.points, pts):
            p.co = (*v, 1.0)
        o = bpy.data.objects.new(name, cu)
        self.coll.objects.link(o)
        o.data.materials.append(mat)
        return o

    # ---- small solid bits, batched into one object per material ---------------------------

    def bit(self, mat, build):
        bm = self.bm_bits.setdefault(mat, bmesh.new())
        t = bmesh.new()
        build(t)
        me = U.mesh_from_bm(t, "bit")
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)

    def finish(self):
        for mat, bm in self.bm_bits.items():
            me = U.mesh_from_bm(bm, "WireBits_" + mat.name)
            o = U.new_obj("WireBits_" + mat.name, me, self.coll, mat=mat)
            U.sharpen(o.data, 35)
            if mat.name in ("BlackPlastic", "HeatShrink", "CableTie"):
                U.bevel(o, 0.12, segments=1, limit_angle=50)
        self.bm_bits = {}

    def cylinder(self, mat, p0, p1, r, seg=16):
        p0, p1 = Vector(p0), Vector(p1)
        d = p1 - p0
        if d.length < 1e-6:
            return
        rot = d.to_track_quat("Z", "Y").to_matrix().to_4x4()

        def build(bm):
            U.cyl(bm, r, 0, d.length, seg=seg)
            from mathutils import Matrix
            bmesh.ops.transform(bm, matrix=Matrix.Translation(p0) @ rot, verts=bm.verts)
        self.bit(mat, build)

    def blob(self, mat, p, r, squash=1.0):
        def build(bm):
            from mathutils import Matrix
            bmesh.ops.create_uvsphere(bm, u_segments=14, v_segments=8, radius=r,
                                      matrix=Matrix.Translation(p) @ Matrix.Diagonal((1, 1, squash, 1)))
        self.bit(mat, build)

    # ---- terminations --------------------------------------------------------------------

    def into_hole(self, p, r):
        """Stripped, tinned end going down into a stripboard hole at p (on the board's top)."""
        p = Vector(p)
        self.cylinder(self.M.solder, p + Vector((0, 0, 1.4)), p - Vector((0, 0, 1.9)), min(0.33, r * 0.55))

    def on_tag(self, p, d, r, shrink=True):
        """Wire end hooked through a solder tag at p; d points from the tag towards the wire."""
        p, d = Vector(p), Vector(d).normalized()
        self.cylinder(self.M.solder, p - d * 0.6, p + d * 2.0, r * 0.55)
        self.blob(self.M.solder, p + d * 0.2, 1.0, squash=0.8)
        if shrink:
            self.cylinder(self.M.heatshrink, p - d * 1.8, p + d * 6.5, r + 0.45, seg=18)

    def dupont(self, pin_top, base_z):
        """Female Dupont housing over a header pin; returns where the wire leaves it."""
        x, y, _ = pin_top
        top = base_z + 14.0

        def build(bm):
            U.box(bm, x - 1.2, y - 1.2, base_z, x + 1.2, y + 1.2, top)
        self.bit(self.M.black_plastic, build)
        self.cylinder(self.M.tin, (x, y, top - 0.2), (x, y, top + 1.2), 0.62)
        return Vector((x, y, top + 1.2))

    # ---- routes --------------------------------------------------------------------------

    def run(self, name, colour, start, s_dir, via, end, e_dir, r=0.62, s_kind="hole", e_kind="hole",
            lead=4.0, mat=None):
        """A wire from start to end through via points. s_dir/e_dir point from each end towards
        the wire, i.e. the direction the insulation leaves the termination."""
        start, end = Vector(start), Vector(end)
        s_dir, e_dir = Vector(s_dir).normalized(), Vector(e_dir).normalized()
        gap = {"hole": 1.4, "tag": 2.0, "dupont": 0.0, "pad": 0.8, "leg": 0.0, "free": 0.0}
        a = start + s_dir * gap[s_kind]
        b = end + e_dir * gap[e_kind]
        pts = [a, a + s_dir * lead] + [Vector(v) for v in via] + [b + e_dir * lead, b]
        m = mat or self.mat(colour)
        o = self.curve(name, pts, r, m)
        for kind, p, d in ((s_kind, start, s_dir), (e_kind, end, e_dir)):
            if kind == "hole":
                self.into_hole(p, r)
            elif kind == "tag":
                self.on_tag(p, d, r)
            elif kind == "pad":
                self.cylinder(self.M.solder, p - d * 0.6, p + d * 1.0, r * 0.55)
                self.blob(self.M.solder, p - d * 0.5, 0.9, squash=0.6)
        return o

    def sample(self, pts, n_per_seg=16):
        """Catmull-Rom through pts, returned as a dense list of Vectors."""
        pts = [Vector(p) for p in pts]
        P = [pts[0] + (pts[0] - pts[1])] + pts + [pts[-1] + (pts[-1] - pts[-2])]
        out = []
        for i in range(1, len(P) - 2):
            p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
            for k in range(n_per_seg):
                t = k / n_per_seg
                t2, t3 = t * t, t * t * t
                out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
                                  (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
        out.append(P[-2])
        return out

    def twisted(self, name, colours, pts, r=0.62, pitch=9.0):
        """A twisted pair along the centre line through pts."""
        c = self.sample(pts, 24)
        s = 0.0
        prev_n = None
        a_pts, b_pts = [], []
        for i, p in enumerate(c):
            t = (c[min(i + 1, len(c) - 1)] - c[max(i - 1, 0)]).normalized()
            if i:
                s += (p - c[i - 1]).length
            if prev_n is None:
                ref = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))
                prev_n = (ref - t * ref.dot(t)).normalized()
            n = (prev_n - t * prev_n.dot(t)).normalized()
            prev_n = n
            bvec = t.cross(n)
            th = 2 * math.pi * s / pitch
            off = (n * math.cos(th) + bvec * math.sin(th)) * r * 1.02
            a_pts.append(p + off)
            b_pts.append(p - off)
        self.poly(name + "_a", a_pts, r, self.mat(colours[0]))
        self.poly(name + "_b", b_pts, r, self.mat(colours[1]))
        return c

    def tie(self, p, d, r_bundle, w=2.4):
        """Nylon cable tie around a bundle at p, with the bundle running along d."""
        p, d = Vector(p), Vector(d).normalized()
        from mathutils import Matrix
        rot = d.to_track_quat("Z", "Y").to_matrix().to_4x4()

        def build(bm):
            U.lathe(bm, [(r_bundle, -w / 2), (r_bundle + 0.9, -w / 2), (r_bundle + 0.9, w / 2), (r_bundle, w / 2)],
                    seg=28, closed=True)
            U.box(bm, r_bundle + 0.4, -2.2, -w / 2 - 0.4, r_bundle + 3.6, 2.2, w / 2 + 0.4)
            bmesh.ops.transform(bm, matrix=Matrix.Translation(p) @ rot, verts=bm.verts)
        self.bit(self.M.tie, build)

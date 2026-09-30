"""Blender helpers shared by the scene build: materials, KiCad GLB import, mesh building.

Everything inside the pedal is modelled in millimetres around the enclosure's own origin
(see layout.py). The pedal collections are then instanced into the metre-scale scene with
a 0.001 scale, so modifiers and bevel widths here are all in mm.
"""
import math
import os

import bmesh
import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.normpath(os.path.join(HERE, "..", "assets"))


# ---- Scene plumbing -----------------------------------------------------------------------

def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)


def collection(name, parent=None):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(c)
    return c


def link(obj, coll):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)
    return obj


def new_obj(name, mesh, coll, mat=None, loc=(0, 0, 0)):
    o = bpy.data.objects.new(name, mesh)
    coll.objects.link(o)
    o.location = loc
    if mat is not None:
        if isinstance(mat, (list, tuple)):
            for m in mat:
                o.data.materials.append(m)
        else:
            o.data.materials.append(mat)
    return o


def sharpen(me, angle_deg=35.0):
    """Smooth-shade a mesh but keep edges sharper than angle_deg (Blender 5 has no
    auto-smooth: sharp edges are stored on the mesh)."""
    bm = bmesh.new()
    bm.from_mesh(me)
    thr = math.radians(angle_deg)
    for f in bm.faces:
        f.smooth = True
    for e in bm.edges:
        if len(e.link_faces) == 2:
            a = e.calc_face_angle(None)
            e.smooth = not (a is not None and a > thr)
        else:
            e.smooth = False
    bm.to_mesh(me)
    bm.free()


def weighted_normals(o):
    m = o.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")
    m.mode = "FACE_AREA"
    m.weight = 100
    m.keep_sharp = True
    return m


def bevel(o, width, segments=3, limit_angle=30, clamp=True, harden=True):
    m = o.modifiers.new("Bevel", "BEVEL")
    m.width = width
    m.segments = segments
    m.limit_method = "ANGLE"
    m.angle_limit = math.radians(limit_angle)
    m.use_clamp_overlap = clamp
    m.harden_normals = harden
    return m


def apply_modifiers(o):
    dg = bpy.context.evaluated_depsgraph_get()
    oe = o.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(oe)
    o.modifiers.clear()
    old = o.data
    o.data = me
    if old.users == 0:
        bpy.data.meshes.remove(old)


# ---- Materials ----------------------------------------------------------------------------

def srgb(h):
    """'#rrggbb' or (r, g, b) 0-255 sRGB to linear RGBA."""
    if isinstance(h, str):
        h = h.lstrip("#")
        h = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    out = []
    for c in h[:3]:
        c = c / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (*out, 1.0)


_mats = {}


def principled(name, color, metallic=0.0, rough=0.5, coat=0.0, coat_rough=0.05, spec=0.5,
               transmission=0.0, ior=1.45, emission=None, emission_strength=0.0, alpha=1.0,
               subsurface=0.0, aniso=0.0):
    if name in _mats:
        return _mats[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = color if len(color) == 4 else (*color, 1)
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Roughness"].default_value = rough
    b.inputs["Coat Weight"].default_value = coat
    b.inputs["Coat Roughness"].default_value = coat_rough
    b.inputs["Specular IOR Level"].default_value = spec
    b.inputs["Transmission Weight"].default_value = transmission
    b.inputs["IOR"].default_value = ior
    b.inputs["Anisotropic"].default_value = aniso
    if subsurface:
        b.inputs["Subsurface Weight"].default_value = subsurface
    if emission is not None:
        b.inputs["Emission Color"].default_value = emission if len(emission) == 4 else (*emission, 1)
        b.inputs["Emission Strength"].default_value = emission_strength
    if alpha < 1:
        b.inputs["Alpha"].default_value = alpha
    _mats[name] = m
    return m


def node(nt, kind, loc=(0, 0), **inputs):
    n = nt.nodes.new(kind)
    n.location = loc
    for k, v in inputs.items():
        if k in n.inputs:
            n.inputs[k].default_value = v
        else:
            setattr(n, k, v)
    return n


class Mats:
    """The shared material library."""

    def __init__(self):
        P = principled
        self.chrome = P("Chrome", (0.95, 0.95, 0.96), metallic=1, rough=0.07)
        self.nickel = P("Nickel", (0.80, 0.78, 0.74), metallic=1, rough=0.22)
        self.steel = P("Steel", (0.62, 0.62, 0.64), metallic=1, rough=0.32)
        self.zinc = P("ZincScrew", (0.78, 0.79, 0.82), metallic=1, rough=0.28)
        self.black_oxide = P("BlackOxide", (0.035, 0.035, 0.04), metallic=1, rough=0.35)
        self.brass = P("Brass", (0.90, 0.72, 0.38), metallic=1, rough=0.28)
        self.gold = P("Gold", (1.0, 0.76, 0.33), metallic=1, rough=0.22)
        self.copper = P("Copper", (0.95, 0.56, 0.40), metallic=1, rough=0.30)
        self.tin = P("Tin", (0.80, 0.80, 0.82), metallic=1, rough=0.18)
        self.solder = P("Solder", (0.82, 0.82, 0.84), metallic=1, rough=0.12)
        self.alu = self._alu()
        self.black_plastic = P("BlackPlastic", (0.018, 0.018, 0.02), rough=0.45)
        self.dark_plastic = P("DarkPlastic", (0.045, 0.045, 0.05), rough=0.5)
        self.matte_black = P("MatteBlack", (0.012, 0.012, 0.013), rough=0.75)
        self.white_plastic = P("WhitePlastic", (0.85, 0.85, 0.82), rough=0.45)
        self.nylon = P("Nylon", (0.86, 0.84, 0.78), rough=0.4, subsurface=0.2)
        self.rubber = P("Rubber", (0.02, 0.02, 0.022), rough=0.85)
        self.silk = P("Silkscreen", (0.90, 0.90, 0.88), rough=0.55)
        self.glass = P("Glass", (1, 1, 1), rough=0.0, transmission=1.0, ior=1.49)
        self.acrylic = P("Acrylic", (1, 1, 1), rough=0.02, transmission=1.0, ior=1.49)
        self.fr4 = self._fr4()
        self.knob = P("AnodisedBlack", (0.03, 0.03, 0.032), metallic=1, rough=0.28)
        self.panel_black = P("PanelGlassBlack", (0.004, 0.004, 0.005), rough=0.04, coat=1.0, coat_rough=0.02)
        self.fpc = P("Polyimide", (0.62, 0.30, 0.02), rough=0.3, coat=0.4, subsurface=0.3)
        self.heatshrink = P("HeatShrink", (0.02, 0.02, 0.022), rough=0.42, coat=0.15)
        self.tie = P("CableTie", (0.025, 0.025, 0.027), rough=0.38)
        self.disc_cap = P("DiscCap", srgb("#2f63c9")[:3], rough=0.35, coat=0.3)
        self.braid = P("Braid", (0.78, 0.76, 0.72), metallic=1, rough=0.45)
        self._by_key = {}

    def _alu(self):
        m = principled("CastAluminium", (0.72, 0.72, 0.73), metallic=1, rough=0.55)
        nt = m.node_tree
        b = nt.nodes["Principled BSDF"]
        tc = node(nt, "ShaderNodeTexCoord", (-900, 0))
        nz = node(nt, "ShaderNodeTexNoise", (-700, 0), Scale=0.35, Detail=8.0, Roughness=0.6)
        nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
        ramp = node(nt, "ShaderNodeMapRange", (-500, 0))
        ramp.inputs["To Min"].default_value = 0.5
        ramp.inputs["To Max"].default_value = 0.68
        nt.links.new(nz.outputs["Fac"], ramp.inputs["Value"])
        nt.links.new(ramp.outputs["Result"], b.inputs["Roughness"])
        bump = node(nt, "ShaderNodeBump", (-300, -200), Strength=0.25, Distance=0.02)
        n2 = node(nt, "ShaderNodeTexNoise", (-700, -250), Scale=4.0, Detail=4.0)
        nt.links.new(tc.outputs["Object"], n2.inputs["Vector"])
        nt.links.new(n2.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
        return m

    def _fr4(self):
        """Kemo E005 stripboard: pale, slightly translucent glass-fibre board."""
        m = principled("FR4", srgb("#b9b27a")[:3], rough=0.55, subsurface=0.15)
        nt = m.node_tree
        b = nt.nodes["Principled BSDF"]
        b.inputs["Subsurface Radius"].default_value = (0.6, 0.6, 0.3)
        b.inputs["Subsurface Scale"].default_value = 1.0
        tc = node(nt, "ShaderNodeTexCoord", (-900, 0))
        wave = node(nt, "ShaderNodeTexWave", (-700, 0), Scale=0.9, Distortion=1.5, Detail=2.0)
        nt.links.new(tc.outputs["Object"], wave.inputs["Vector"])
        mix = node(nt, "ShaderNodeMix", (-400, 0), data_type="RGBA")
        mix.inputs[0].default_value = 0.08
        mix.inputs[6].default_value = srgb("#b9b27a")
        mix.inputs[7].default_value = srgb("#a39b5f")
        nt.links.new(wave.outputs["Fac"], mix.inputs[0])
        nt.links.new(mix.outputs[2], b.inputs["Base Color"])
        return m

    def plastic(self, rgb, rough=0.45, name=None):
        key = ("plastic", tuple(round(c, 2) for c in rgb[:3]), rough)
        if key not in self._by_key:
            self._by_key[key] = principled(name or "Plastic_%02x%02x%02x" % tuple(int(min(1, c) * 255) for c in rgb[:3]),
                                           rgb[:3], rough=rough)
        return self._by_key[key]

    def mask(self, rgb, name):
        return principled("Mask_" + name, rgb[:3], rough=0.32, coat=0.35, coat_rough=0.12)

    def wire(self, rgb, name):
        return principled("Wire_" + name, rgb[:3], rough=0.32, coat=0.2, coat_rough=0.15)


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def classify(color, mask_hex=None, finish=None):
    """Map a KiCad-exported base colour to one of our materials. KiCad writes the
    soldermask as 0.8 x its sRGB value, and bare copper/pads as flat 0.5 grey."""
    r, g, b = color[:3]
    mx, mn = max(r, g, b), min(r, g, b)
    strip = finish == "copper"
    if mask_hex is not None:
        mr, mg, mb = (0.8 * c / 255 for c in hex_rgb(mask_hex))
        if abs(r - mr) + abs(g - mg) + abs(b - mb) < 0.05:
            return "mask"
    if finish and abs(r - 0.5) < 0.01 and abs(g - 0.5) < 0.01 and abs(b - 0.5) < 0.01:
        return finish
    if abs(r - 0.427) < 0.01 and abs(g - 0.455) < 0.01 and abs(b - 0.294) < 0.02:
        return "fr4"
    if strip and abs(r - 0.063) < 0.01 and abs(g - 0.160) < 0.01:
        return "fr4"
    if mn > 0.9:
        return "silk"
    if r > 0.6 and 0.35 < g < 0.9 and b < 0.35 and r - b > 0.45:
        return "gold"
    if g > 1.6 * r and g > 1.2 * b and g > 0.12 and mx < 0.5:
        return "pcbgreen"
    if mx - mn < 0.09 and 0.28 < mx <= 0.9:
        return "metal"
    if mx < 0.09:
        return "black"
    return "plastic"


def import_glb(path, name, coll, mats, mask=None, finish=None, mask_name="pcb"):
    """Import a KiCad GLB, remap its materials, join it into one mm-scale object.
    mask: the soldermask '#rrggbb' it was exported with; finish: copper, gold or tin."""
    before = set(bpy.data.objects)
    before_mats = set(bpy.data.materials)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    mask_mat = mats.mask(srgb(mask), mask_name) if mask is not None else None
    cache = {}
    for o in meshes:
        for slot in o.material_slots:
            src = slot.material
            if src is None:
                continue
            if src.name not in cache:
                bsdf = src.node_tree.nodes.get("Principled BSDF") if src.use_nodes else None
                col = tuple(bsdf.inputs["Base Color"].default_value) if bsdf else (0.5, 0.5, 0.5, 1)
                kind = classify(col, mask, finish)
                cache[src.name] = {
                    "mask": mask_mat, "copper": mats.copper, "fr4": mats.fr4, "silk": mats.silk,
                    "gold": mats.gold, "tin": mats.tin, "metal": mats.tin, "black": mats.black_plastic,
                    "pcbgreen": mats.mask(srgb("#1f6b37"), "pi_green"),
                }.get(kind) or mats.plastic(col)
            slot.material = cache[src.name]
    # Join everything into one object in mm.
    for o in meshes:
        o.data = o.data.copy() if o.data.users > 1 else o.data
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        mw = o.matrix_world.copy()
        o.parent = None
        o.matrix_world = mw
    for o in meshes:
        o.data.transform(Matrix.Scale(1000.0, 4) @ o.matrix_world)
        o.matrix_world = Matrix.Identity(4)
    target = meshes[0]
    empties = [o.name for o in new if o.type != "MESH"]
    with bpy.context.temp_override(active_object=target, selected_editable_objects=meshes,
                                   selected_objects=meshes):
        bpy.ops.object.join()
    target.name = name
    target.data.name = name
    for n in empties:
        if n in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[n], do_unlink=True)
    link(target, coll)
    # Merge duplicate material slots.
    me = target.data
    uniq = []
    remap = []
    for m in me.materials:
        if m not in uniq:
            uniq.append(m)
        remap.append(uniq.index(m))
    idx = [remap[p.material_index] for p in me.polygons]
    me.materials.clear()
    for m in uniq:
        me.materials.append(m)
    for p, i in zip(me.polygons, idx):
        p.material_index = i
    for p in me.polygons:
        p.use_smooth = True
    for m in list(bpy.data.materials):
        if m not in before_mats and m.users == 0:
            bpy.data.materials.remove(m)
    return target


def bounds(o):
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return (Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))),
            Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))))


# ---- Mesh building ------------------------------------------------------------------------

def mesh_from_bm(bm, name):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me


def box(bm, x0, y0, z0, x1, y1, z1):
    mat = Matrix.Translation(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)) @ \
        Matrix.Diagonal((abs(x1 - x0), abs(y1 - y0), abs(z1 - z0), 1))
    bmesh.ops.create_cube(bm, size=1.0, matrix=mat)


def cyl(bm, r, z0, z1, x=0, y=0, seg=32, r2=None, matrix=None, cap=True):
    r2 = r if r2 is None else r2
    h = z1 - z0
    m = Matrix.Translation((x, y, (z0 + z1) / 2))
    if matrix is not None:
        m = matrix @ m
    bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=seg, radius1=r, radius2=r2,
                          depth=h, matrix=m)


def prism(bm, r, z0, z1, sides=6, x=0, y=0, rot=0.0, matrix=None):
    m = Matrix.Translation((x, y, (z0 + z1) / 2)) @ Matrix.Rotation(rot, 4, "Z")
    if matrix is not None:
        m = matrix @ m
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=sides, radius1=r, radius2=r,
                          depth=z1 - z0, matrix=m)


def lathe(bm, profile, seg=48, matrix=None, closed=False):
    """Revolve a list of (radius, z) points around Z. Points on the axis (r = 0) close the
    surface there; closed=True also joins the last point back to the first."""
    t = bmesh.new()
    verts = [t.verts.new((r, 0.0, z)) for r, z in profile]
    edges = [t.edges.new((verts[i], verts[i + 1])) for i in range(len(verts) - 1)]
    if closed:
        edges.append(t.edges.new((verts[-1], verts[0])))
    bmesh.ops.spin(t, geom=verts + edges, cent=(0, 0, 0), axis=(0, 0, 1),
                   angle=2 * math.pi, steps=seg, use_merge=True)
    bmesh.ops.remove_doubles(t, verts=t.verts, dist=1e-4)
    bmesh.ops.recalc_face_normals(t, faces=t.faces)
    if matrix is not None:
        bmesh.ops.transform(t, matrix=matrix, verts=t.verts)
    me = mesh_from_bm(t, "lathe_tmp")
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)


def rounded_rect_pts(w, h, r, seg=8, cx=0.0, cy=0.0):
    pts = []
    r = min(r, w / 2, h / 2)
    for (qx, qy, a0) in [(w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90),
                         (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)]:
        for i in range(seg + 1):
            a = math.radians(a0 + 90 * i / seg)
            pts.append((cx + qx + r * math.cos(a), cy + qy + r * math.sin(a)))
    return pts


def extrude_poly(bm, pts, z0, z1):
    """A closed polygon (list of x, y) extruded between z0 and z1."""
    bot = [bm.verts.new((x, y, z0)) for x, y in pts]
    top = [bm.verts.new((x, y, z1)) for x, y in pts]
    n = len(pts)
    bm.faces.new(list(reversed(bot)))
    bm.faces.new(top)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((bot[i], bot[j], top[j], top[i]))


def boolean(o, cutter, op="DIFFERENCE", solver="EXACT", apply=True):
    m = o.modifiers.new("Bool", "BOOLEAN")
    m.operation = op
    m.object = cutter
    m.solver = solver
    if apply:
        apply_modifiers(o)
    return m


def cutter_object(name, bm):
    me = mesh_from_bm(bm, name)
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    return o


def remove(o):
    me = o.data
    bpy.data.objects.remove(o, do_unlink=True)
    if me is not None and me.users == 0:
        bpy.data.meshes.remove(me)

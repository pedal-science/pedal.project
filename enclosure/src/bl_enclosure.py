"""The 1590DD-size body and lid, drilled for this pedal, with its paint. Millimetres,
enclosure coordinates from layout.py."""
import math

import bmesh
import bpy
from mathutils import Matrix, Vector

import bl_util as U
import layout as L
from bl_parts import MB, T, Rx, Ry, lathe

E = L.ENC
W, D, H = E["W"], E["D"], E["H"]
R = E["r_corner"]
Z0 = E["lid"]                       # rim of the body
CORNER_SEG = 14


def inset_at(z):
    """How far the outside of the wall has moved in at height z (casting draft)."""
    return E["draft"] * max(0.0, min(1.0, (z - Z0) / (H - Z0)))


def rr_loop(inset, z, r=R, seg=CORNER_SEG):
    """Rounded-rectangle ring of the enclosure outline, offset inwards by inset."""
    pts = U.rounded_rect_pts(W - 2 * inset, D - 2 * inset, max(0.3, r - inset), seg=seg, cx=L.CX, cy=L.CY)
    return [(x, y, z) for x, y in pts]


def loft(bm, rings, cap_bottom=True, cap_top=True):
    vs = [[bm.verts.new(p) for p in ring] for ring in rings]
    n = len(rings[0])
    for a, b in zip(vs, vs[1:]):
        for k in range(n):
            l = (k + 1) % n
            bm.faces.new((a[k], a[l], b[l], b[k]))
    if cap_bottom:
        bm.faces.new(list(reversed(vs[0])))
    if cap_top:
        bm.faces.new(vs[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)


def paint_material():
    """Black textured powder coat with the orange band across the top and down the sides."""
    m = bpy.data.materials.get("PowderCoat")
    if m:
        return m
    m = bpy.data.materials.new("PowderCoat")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    n = U.node
    tc = n(nt, "ShaderNodeTexCoord", (-1400, 0))
    sep = n(nt, "ShaderNodeSeparateXYZ", (-1200, 200))
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    lo = n(nt, "ShaderNodeMath", (-1000, 300), operation="GREATER_THAN")
    lo.inputs[1].default_value = L.STRIPE_Y[0]
    hi = n(nt, "ShaderNodeMath", (-1000, 150), operation="LESS_THAN")
    hi.inputs[1].default_value = L.STRIPE_Y[1]
    nt.links.new(sep.outputs["Y"], lo.inputs[0])
    nt.links.new(sep.outputs["Y"], hi.inputs[0])
    band = n(nt, "ShaderNodeMath", (-800, 250), operation="MULTIPLY")
    nt.links.new(lo.outputs[0], band.inputs[0])
    nt.links.new(hi.outputs[0], band.inputs[1])
    # Only on the top face and the two side walls: the front and rear walls stay black.
    front_rear = n(nt, "ShaderNodeVectorMath", (-1000, -50), operation="ABSOLUTE")
    geo = n(nt, "ShaderNodeNewGeometry", (-1400, -200))
    nw = n(nt, "ShaderNodeVectorTransform", (-1200, -200), vector_type="NORMAL", convert_from="WORLD",
           convert_to="OBJECT")
    nt.links.new(geo.outputs["Normal"], nw.inputs[0])
    nt.links.new(nw.outputs[0], front_rear.inputs[0])
    sep_n = n(nt, "ShaderNodeSeparateXYZ", (-800, -50))
    nt.links.new(front_rear.outputs[0], sep_n.inputs[0])
    not_fr = n(nt, "ShaderNodeMath", (-600, -50), operation="LESS_THAN")
    not_fr.inputs[1].default_value = 0.7
    nt.links.new(sep_n.outputs["Y"], not_fr.inputs[0])
    mask = n(nt, "ShaderNodeMath", (-600, 200), operation="MULTIPLY")
    nt.links.new(band.outputs[0], mask.inputs[0])
    nt.links.new(not_fr.outputs[0], mask.inputs[1])
    col = n(nt, "ShaderNodeMix", (-300, 250), data_type="RGBA")
    col.inputs[6].default_value = U.srgb("#0b0b0c")
    col.inputs[7].default_value = U.srgb("#f2641c")
    nt.links.new(mask.outputs[0], col.inputs[0])
    nt.links.new(col.outputs[2], b.inputs["Base Color"])
    rough = n(nt, "ShaderNodeMapRange", (-300, 0))
    rough.inputs["To Min"].default_value = 0.76
    rough.inputs["To Max"].default_value = 0.78
    nt.links.new(mask.outputs[0], rough.inputs["Value"])
    nt.links.new(rough.outputs["Result"], b.inputs["Roughness"])
    b.inputs["Specular IOR Level"].default_value = 0.28
    # Fine orange-peel texture.
    nz = n(nt, "ShaderNodeTexNoise", (-800, -350), Scale=3.2, Detail=6.0, Roughness=0.55)
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    bump = n(nt, "ShaderNodeBump", (-300, -300), Strength=0.22, Distance=0.015)
    nt.links.new(nz.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def cutter_cyl(name, r, p0, p1, seg=64):
    """A cylinder from point p0 to p1 (enclosure coords) for drilling."""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    bm = bmesh.new()
    U.cyl(bm, r, 0, d.length, seg=seg)
    rot = d.to_track_quat("Z", "Y").to_matrix().to_4x4()
    bmesh.ops.transform(bm, matrix=Matrix.Translation(p0) @ rot, verts=bm.verts)
    return U.cutter_object(name, bm)


def wall_frame(wall, s, z):
    """Matrix placing a wall part: origin on the wall's outside at (s along the wall, z),
    local +z pointing outwards."""
    ins = inset_at(z)
    if wall == "left":
        return Matrix.Translation((ins, s, z)) @ Ry(-90)
    if wall == "right":
        return Matrix.Translation((W - ins, s, z)) @ Ry(90)
    if wall == "rear":
        return Matrix.Translation((s, D - ins, z)) @ Rx(-90)
    if wall == "front":
        return Matrix.Translation((s, ins, z)) @ Rx(90)
    raise ValueError(wall)


def body(coll, mats, open_top=False):
    paint = paint_material()
    alu = mats.alu
    # Outer solid: straight drafted walls, then a fillet into the top face.
    rt = E["r_top"]
    zf = H - rt
    rings = [rr_loop(0.0, Z0), rr_loop(inset_at(zf), zf)]
    for i in range(1, 9):
        a = math.radians(90 * i / 8)
        rings.append(rr_loop(inset_at(zf) + rt * (1 - math.cos(a)), zf + rt * math.sin(a)))
    bm = bmesh.new()
    loft(bm, rings)
    o = U.new_obj("Body_Open" if open_top else "Body_Closed", U.mesh_from_bm(bm, "body"), coll, mat=[paint, alu])
    # Cavity.
    w = E["wall"]
    ztop = L.Z_TOP_IN
    ri = 1.0
    crings = [rr_loop(w, Z0 - 2.0), rr_loop(w + inset_at(ztop - ri), ztop - ri)]
    for i in range(1, 6):
        a = math.radians(90 * i / 5)
        crings.append(rr_loop(w + inset_at(ztop - ri) + ri * (1 - math.cos(a)), ztop - ri + ri * math.sin(a)))
    bm = bmesh.new()
    loft(bm, crings)
    for f in bm.faces:
        f.material_index = 0
    cav = U.cutter_object("cavity", bm)
    cav.data.materials.append(alu)
    _bool(o, cav, "DIFFERENCE")
    # Lid-screw bosses in the inside corners, tapped 6-32.
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = L.CX + sx * E["screw_dx"] / 2, L.CY + sy * E["screw_dy"] / 2
            bm = bmesh.new()
            U.cyl(bm, E["boss_d"] / 2, Z0, ztop - 0.2, x=x, y=y, seg=32)
            c = U.cutter_object("boss", bm)
            c.data.materials.append(alu)
            _bool(o, c, "UNION")
            c = cutter_cyl("tap", 1.4, (x, y, Z0 - 1), (x, y, Z0 + 11), seg=20)
            c.data.materials.append(alu)
            _bool(o, c, "DIFFERENCE")
    # Top-face holes.
    cuts = []
    zt0, zt1 = ztop - 1.5, H + 1.0
    for x in L.FS_X:
        cuts.append(("fs", 6.15, (x, L.FS_Y, zt0), (x, L.FS_Y, zt1)))
        cuts.append(("led", 3.25, (x, L.LED_Y, zt0), (x, L.LED_Y, zt1)))
    cuts.append(("led", 3.25, (*L.LED_READY, zt0), (*L.LED_READY, zt1)))
    cuts.append(("enc", 3.65, (*L.ENCODER, zt0), (*L.ENCODER, zt1)))
    cuts.append(("btn", 4.1, (*L.BUTTON, zt0), (*L.BUTTON, zt1)))
    cuts.append(("tog", 3.3, (*L.TOGGLE, zt0), (*L.TOGGLE, zt1)))
    # Wall holes.
    for name, (wall, s, z) in L.JACKS.items():
        m = wall_frame(wall, s, z)
        cuts.append(("jack", 5.65, m @ Vector((0, 0, -6)), m @ Vector((0, 0, 3))))
    for name, r, (x, z) in (("din", 7.9, L.MIDI), ("dc", 5.75, L.DC9V)):
        m = wall_frame("rear", x, z)
        cuts.append((name, r, m @ Vector((0, 0, -6)), m @ Vector((0, 0, 3))))
    for sx in (-8.5, 8.5):
        m = wall_frame("rear", L.USBC[0] + sx, L.USBC[1])
        cuts.append(("usbscrew", 1.3, m @ Vector((0, 0, -6)), m @ Vector((0, 0, 3))))
    for i, (kind, r, p0, p1) in enumerate(cuts):
        c = cutter_cyl(f"cut_{kind}_{i}", r, p0, p1)
        c.data.materials.append(alu)
        _bool(o, c, "DIFFERENCE")
    # Window for the display, and the USB-C slot.
    bm = bmesh.new()
    wx, wy = L.WINDOW_C
    U.extrude_poly(bm, U.rounded_rect_pts(L.WINDOW[0], L.WINDOW[1], 1.5, cx=wx, cy=wy), zt0, zt1)
    c = U.cutter_object("window", bm)
    c.data.materials.append(mats.matte_black)       # the cut edge is painted black, like a bezel
    _bool(o, c, "DIFFERENCE")
    bm = bmesh.new()
    U.extrude_poly(bm, U.rounded_rect_pts(9.4, 3.8, 1.85), -6, 3)
    bmesh.ops.transform(bm, matrix=wall_frame("rear", *L.USBC), verts=bm.verts)
    c = U.cutter_object("usbslot", bm)
    c.data.materials.append(alu)
    _bool(o, c, "DIFFERENCE")
    # DIN anti-rotation notch.
    bm = bmesh.new()
    U.box(bm, -1.1, 7.2, -6, 1.1, 8.6, 3)
    bmesh.ops.transform(bm, matrix=wall_frame("rear", *L.MIDI), verts=bm.verts)
    c = U.cutter_object("dinkey", bm)
    c.data.materials.append(alu)
    _bool(o, c, "DIFFERENCE")
    if open_top:
        bm = bmesh.new()
        U.box(bm, -10, -10, ztop, W + 10, D + 10, H + 10)
        c = U.cutter_object("lid_cut", bm)
        c.data.materials.append(alu)
        _bool(o, c, "DIFFERENCE")
    U.sharpen(o.data, 30)
    U.weighted_normals(o)
    return o


def _bool(o, cutter, op):
    m = o.modifiers.new("Bool", "BOOLEAN")
    m.operation = op
    m.object = cutter
    m.solver = "EXACT"
    m.material_mode = "TRANSFER"
    U.apply_modifiers(o)
    U.remove(cutter)


def lid(coll, mats):
    """Base plate with its lip, screws and rubber feet. The inside face is bare metal."""
    paint = paint_material()
    mb = MB("Lid")
    pts = U.rounded_rect_pts(W, D, R, seg=CORNER_SEG, cx=L.CX, cy=L.CY)

    def plate(bm):
        U.extrude_poly(bm, pts, 0.0, E["lid"] - 0.02)
    mb.add(paint, plate, smooth=False)
    mb.add(mats.alu, lambda bm: U.extrude_poly(bm, U.rounded_rect_pts(W - 2.2, D - 2.2, R - 1.1, seg=CORNER_SEG,
                                                                       cx=L.CX, cy=L.CY), E["lid"] - 0.02, E["lid"]),
           smooth=False)
    # Lip: a band just inside the walls.
    o_in = E["wall"] + 0.25

    def lip(bm):
        outer = U.rounded_rect_pts(W - 2 * o_in, D - 2 * o_in, R - o_in, seg=CORNER_SEG, cx=L.CX, cy=L.CY)
        inner = U.rounded_rect_pts(W - 2 * (o_in + E["lip_w"]), D - 2 * (o_in + E["lip_w"]),
                                   R - o_in - E["lip_w"], seg=CORNER_SEG, cx=L.CX, cy=L.CY)
        z0, z1 = E["lid"], E["lid"] + E["lid_lip"]
        ob = [bm.verts.new((x, y, z0)) for x, y in outer]
        ot = [bm.verts.new((x, y, z1)) for x, y in outer]
        ib = [bm.verts.new((x, y, z0)) for x, y in inner]
        it = [bm.verts.new((x, y, z1)) for x, y in inner]
        n = len(outer)
        for k in range(n):
            l = (k + 1) % n
            bm.faces.new((ob[k], ob[l], ot[l], ot[k]))
            bm.faces.new((it[k], it[l], ib[l], ib[k]))
            bm.faces.new((ot[k], ot[l], it[l], it[k]))
            bm.faces.new((ib[k], ib[l], ob[l], ob[k]))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mb.add(mats.alu, lip, smooth=False)
    # Countersunk 6-32 screws into the bosses, and four rubber feet.
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = L.CX + sx * E["screw_dx"] / 2, L.CY + sy * E["screw_dy"] / 2
            mb.add(mats.black_oxide, lambda bm, x=x, y=y: lathe(bm, [(0.0, -0.02), (2.7, -0.02), (1.4, 1.4), (1.4, 12.0),
                                                                    (0.0, 12.0)], seg=24, matrix=T(x, y, 0)))
            fx, fy = L.CX + sx * (W / 2 - 14), L.CY + sy * (D / 2 - 14)
            mb.add(mats.rubber, lambda bm, fx=fx, fy=fy: lathe(bm, [(0.0, -3.2), (4.2, -3.2), (5.6, -2.6), (6.0, -1.4),
                                                                    (6.0, 0.0), (0.0, 0.0)], seg=40,
                                                               matrix=T(fx, fy, 0)))
    return mb.obj(coll, bevel=0.3, seg=2, angle=50)

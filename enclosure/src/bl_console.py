"""The console model's parts: the Hammond 1456RH3 case and cover, the Prechen bar screen, the
panel and rear-wall parts, and what is inside. Millimetres, in console.py's frame.

Each builder links its objects into the collection it is given and returns them. Parts that the
old 1590DD model already had (footswitch, jack, DIN, DC and USB-C sockets, knob) come from
bl_parts.py unchanged; the rest are here.
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

import bl_parts as BP
import bl_util as U
import console as C
from bl_parts import MB, Rx, Rz, T, lathe

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.normpath(os.path.join(HERE, "..", ".."))
WORKSPACE = os.path.normpath(os.path.join(PROJECT, ".."))
PARTS = os.path.join(U.ASSETS, "parts")
RIGPA_SHOT = os.path.join(WORKSPACE, "rigpa", "docs", "screenshots", "two-rigs.png")


# ---- Frames --------------------------------------------------------------------------------------

def slope_frame(x, s):
    """Origin on the slope's outside surface at (x, s); x across, y up the face, z out of it."""
    return T(*C.slope_point(x, s)) @ Rx(C.SLOPE)


def rear_frame(x, z):
    """Origin on the rear wall's outside surface; x reads left to right seen from behind, y up,
    z out of the wall (+y in the case's frame)."""
    return T(x, C.D, z) @ Rx(-90) @ Rz(180)


def place(o, m):
    o.matrix_world = m
    return o


# ---- Materials -----------------------------------------------------------------------------------

def materials(M):
    """The console's own materials, added to the shared library."""
    m = U.principled("PowderCoatBlack", (0.014, 0.014, 0.015), rough=0.58, spec=0.45)
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    tc = U.node(nt, "ShaderNodeTexCoord", (-900, 0))
    nz = U.node(nt, "ShaderNodeTexNoise", (-700, 0), Scale=1.6, Detail=3.0, Roughness=0.55)
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    bump = U.node(nt, "ShaderNodeBump", (-300, -200), Strength=0.22, Distance=0.05)
    nt.links.new(nz.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    rr = U.node(nt, "ShaderNodeMapRange", (-450, 100))
    rr.inputs["To Min"].default_value = 0.5
    rr.inputs["To Max"].default_value = 0.66
    nt.links.new(nz.outputs["Fac"], rr.inputs["Value"])
    nt.links.new(rr.outputs["Result"], b.inputs["Roughness"])
    M.powder = m
    M.screen_case = U.principled("ScreenCase", (0.05, 0.05, 0.055), metallic=1, rough=0.4)
    M.accent = U.principled("AccentOrange", U.srgb("#f2641c")[:3], rough=0.35)
    M.rf_plastic = U.principled("RFWindow", (0.025, 0.025, 0.028), rough=0.75)
    M.stripboard = stripboard_material()
    M.resistor = U.principled("ResistorBlue", U.srgb("#5b86c4")[:3], rough=0.4, coat=0.3)
    M.film = U.principled("FilmCapRed", U.srgb("#b5242a")[:3], rough=0.35, coat=0.2)
    M.elec = U.principled("ElectrolyticSleeve", U.srgb("#1d2a52")[:3], rough=0.35, coat=0.3)
    M.xh = U.principled("JSTCream", U.srgb("#efe9d8")[:3], rough=0.45)
    M.pico_green = M.mask(U.srgb("#1f7a3d"), "pico")
    M.screen = screen_material()
    return M


def stripboard_material():
    """Kemo stripboard from above: pale FR4 with a hole every 2.54 mm. The holes are drawn by
    the shader in object space, so a board's origin must sit on its grid's corner."""
    m = U.principled("StripboardTop", U.srgb("#c9bf86")[:3], rough=0.6, subsurface=0.1)
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    n = U.node
    tc = n(nt, "ShaderNodeTexCoord", (-1200, 0))
    sep = n(nt, "ShaderNodeSeparateXYZ", (-1000, 0))
    nt.links.new(tc.outputs["Object"], sep.inputs[0])

    def frac_centered(sock, loc):
        d = n(nt, "ShaderNodeMath", (loc[0], loc[1]), operation="DIVIDE")
        d.inputs[1].default_value = C.P
        nt.links.new(sock, d.inputs[0])
        f = n(nt, "ShaderNodeMath", (loc[0] + 150, loc[1]), operation="FRACT")
        nt.links.new(d.outputs[0], f.inputs[0])
        s = n(nt, "ShaderNodeMath", (loc[0] + 300, loc[1]), operation="SUBTRACT")
        s.inputs[1].default_value = 0.5
        nt.links.new(f.outputs[0], s.inputs[0])
        return s.outputs[0]
    fx = frac_centered(sep.outputs["X"], (-850, 100))
    fy = frac_centered(sep.outputs["Y"], (-850, -100))
    cx = n(nt, "ShaderNodeCombineXYZ", (-400, 0))
    nt.links.new(fx, cx.inputs[0])
    nt.links.new(fy, cx.inputs[1])
    ln = n(nt, "ShaderNodeVectorMath", (-250, 0), operation="LENGTH")
    nt.links.new(cx.outputs[0], ln.inputs[0])
    hole = n(nt, "ShaderNodeMath", (-100, 0), operation="LESS_THAN")
    hole.inputs[1].default_value = 0.2
    nt.links.new(ln.outputs["Value"], hole.inputs[0])
    mix = n(nt, "ShaderNodeMix", (100, 150), data_type="RGBA")
    mix.inputs[6].default_value = U.srgb("#c9bf86")
    mix.inputs[7].default_value = (0.02, 0.016, 0.01, 1)
    nt.links.new(hole.outputs[0], mix.inputs[0])
    nt.links.new(mix.outputs[2], b.inputs["Base Color"])
    return m


def screen_material():
    """The bar's active area: rigpa's own screenshot (1920 x 480 at 4:1), lit, under glass."""
    m = U.principled("BarScreen", (0.0, 0.0, 0.0), rough=0.08, coat=1.0, coat_rough=0.02)
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    if os.path.exists(RIGPA_SHOT):
        tex = U.node(nt, "ShaderNodeTexImage", (-500, 0))
        tex.image = bpy.data.images.load(RIGPA_SHOT, check_existing=True)
        tex.interpolation = "Cubic"
        nt.links.new(tex.outputs["Color"], b.inputs["Emission Color"])
    else:
        print("WARNING: no rigpa screenshot at", RIGPA_SHOT, "- the screen is lit plain")
        b.inputs["Emission Color"].default_value = (0.05, 0.05, 0.06, 1)
    b.inputs["Emission Strength"].default_value = 2.2
    return m


# ---- Sheet-metal profiles --------------------------------------------------------------------------

def _fillet(pts, radii, seg):
    """An open (y, z) polyline with each interior corner rounded to radii[i]."""
    out = [Vector(pts[0])]
    for i in range(1, len(pts) - 1):
        p, r = Vector(pts[i]), radii[i]
        d1 = (p - Vector(pts[i - 1])).normalized()
        d2 = (Vector(pts[i + 1]) - p).normalized()
        turn = math.acos(max(-1.0, min(1.0, d1.dot(d2))))
        if r <= 0 or turn < 1e-6:
            out.append(p)
            continue
        t = r * math.tan(turn / 2)
        a, b = p - d1 * t, p + d2 * t
        cross = d1.x * d2.y - d1.y * d2.x
        nrm = Vector((-d1.y, d1.x)) if cross > 0 else Vector((d1.y, -d1.x))
        c = a + nrm * r
        a0 = math.atan2(a.y - c.y, a.x - c.x)
        a1 = math.atan2(b.y - c.y, b.x - c.x)
        da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        for k in range(seg + 1):
            ang = a0 + da * k / seg
            out.append(c + Vector((math.cos(ang), math.sin(ang))) * r)
    out.append(Vector(pts[-1]))
    return out


def _offset(pts, d):
    """The polyline moved d to the right of its direction of travel (into the case)."""
    lines = []
    for i in range(len(pts) - 1):
        a, b = Vector(pts[i]), Vector(pts[i + 1])
        t = (b - a).normalized()
        n = Vector((t.y, -t.x))
        lines.append((a + n * d, t))
    out = [lines[0][0]]
    for (p1, t1), (p2, t2) in zip(lines, lines[1:]):
        den = t1.x * t2.y - t1.y * t2.x
        if abs(den) < 1e-9:
            out.append(p2)
            continue
        k = ((p2.x - p1.x) * t2.y - (p2.y - p1.y) * t2.x) / den
        out.append(p1 + t1 * k)
    a, b = Vector(pts[-2]), Vector(pts[-1])
    t = (b - a).normalized()
    out.append(b + Vector((t.y, -t.x)) * d)
    return out


CORNERS = [(0.0, C.H_FRONT), (C.Y_TOP, C.H), (C.D, C.H)]
RADII = [C.R_BEND, 10.0, C.R_BEND]
SEG = 8


def _extrude_yz(bm, loop, x0, x1):
    """A closed (y, z) polygon extruded along x."""
    a = [bm.verts.new((x0, p.x, p.y)) for p in loop]
    b = [bm.verts.new((x1, p.x, p.y)) for p in loop]
    bm.faces.new(list(reversed(a)))
    bm.faces.new(b)
    n = len(loop)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((a[i], a[j], b[j], b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)


def cover_shell(bm, x0, x1):
    """The cover's wrap: front wall, slope, flat top and rear wall, standing on the base."""
    path = [(0.0, C.T)] + CORNERS + [(C.D, C.T)]
    outer = _fillet(path, [0] + RADII + [0], SEG)
    inner = _fillet(_offset(path, C.T), [0] + [r - C.T for r in RADII] + [0], SEG)
    _extrude_yz(bm, outer + list(reversed(inner)), x0, x1)


def end_outline():
    path = [(0.0, 0.0)] + CORNERS + [(C.D, 0.0)]
    return _fillet(path, [0] + RADII + [0], SEG)


def stadium(bm, cx, cy, w, l, z0, z1, along_y=True, seg=10):
    """A slot w wide and l long with round ends, as a prism from z0 to z1."""
    r = w / 2
    pts = []
    h = l / 2 - r
    for k in range(seg + 1):
        a = math.pi * k / seg
        pts.append((r * math.cos(a), h + r * math.sin(a)))
    for k in range(seg + 1):
        a = math.pi + math.pi * k / seg
        pts.append((r * math.cos(a), -h + r * math.sin(a)))
    if not along_y:
        pts = [(y, -x) for x, y in pts]
    U.extrude_poly(bm, [(cx + x, cy + y) for x, y in pts], z0, z1)


def _cutter(name, pieces):
    """One cutter object from (build(bm), matrix) pieces."""
    bm = bmesh.new()
    for build, m in pieces:
        t = bmesh.new()
        build(t)
        bmesh.ops.transform(t, matrix=m, verts=t.verts)
        me = U.mesh_from_bm(t, "tmp")
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return U.cutter_object(name, bm)


# ---- The case and the cover ------------------------------------------------------------------------

def case(coll, M):
    """The base and the two end panels (one U-shaped piece), the feet and the cover screws."""
    bm = bmesh.new()
    U.box(bm, C.T, 0.0, 0.0, C.W - C.T, C.D, C.T)
    me = U.mesh_from_bm(bm, "Case")
    o = U.new_obj("Case", me, coll, mat=M.powder)
    pieces = []
    s = C.BASE_SLOTS
    for gx0, gx1 in s["groups"]:
        n = int((gx1 - gx0) / s["pitch"]) + 1
        for k in range(n):
            x = gx0 + k * s["pitch"]
            pieces.append((lambda bm, x=x: stadium(bm, x, s["y0"] + C.SLOT_L / 2, C.SLOT_W, C.SLOT_L, -1, 3),
                           Matrix.Identity(4)))
    for x, y in C.SCREWS:
        pieces.append((lambda bm, x=x, y=y: U.cyl(bm, C.SCREW_D / 2, -1, 3, x=x, y=y, seg=24), Matrix.Identity(4)))
    cut = _cutter("CaseCut", pieces)
    U.boolean(o, cut)
    U.remove(cut)
    # The end panels join the base after its holes are cut: they only touch it, and the exact
    # solver drops pieces that merely touch.
    bm = bmesh.new()
    bm.from_mesh(o.data)
    for x0 in (0.0, C.W - C.T):
        t = bmesh.new()
        _extrude_yz(t, end_outline(), x0, x0 + C.T)
        tm = U.mesh_from_bm(t, "tmp")
        bm.from_mesh(tm)
        bpy.data.meshes.remove(tm)
    bm.to_mesh(o.data)
    bm.free()
    U.sharpen(o.data, 40)
    U.bevel(o, 0.35, segments=2, limit_angle=50)
    U.weighted_normals(o)

    fx = MB("CaseFixings")
    for x, y in C.FEET:
        fx.add(M.rubber, lambda bm, x=x, y=y: lathe(bm, [(0.0, -C.FOOT_H), (C.FOOT_D * 0.36, -C.FOOT_H),
                                                         (C.FOOT_D * 0.47, -C.FOOT_H * 0.6), (C.FOOT_D / 2, -0.4),
                                                         (C.FOOT_D / 2, 0.0), (0.0, 0.0)], seg=40,
                                                     matrix=T(x, y, 0)))
    for x, y in C.SCREWS:
        fx.add(M.black_oxide, lambda bm, x=x, y=y: BP.pan_screw(bm, 3.5, 0.0, length=6.0, up=False, x=x, y=y))
    fo = fx.obj(coll, bevel=0.1, seg=1)
    return [o, fo]


def cover(coll, M):
    """The wrap the panel parts mount on, with the screen's window, the rear vents and the
    USB-C opening cut through it, and the two foot flanges the cover screws go into."""
    bm = bmesh.new()
    gap = (C.W - C.COVER_W) / 2
    cover_shell(bm, gap, C.W - gap)
    fl0 = (C.W - C.FLANGE_W) / 2
    U.box(bm, fl0, C.T, C.T, C.W - fl0, C.T + C.FLANGE_D, 2 * C.T)
    U.box(bm, fl0, C.D - C.T - C.FLANGE_D, C.T, C.W - fl0, C.D - C.T, 2 * C.T)
    me = U.mesh_from_bm(bm, "Cover")
    o = U.new_obj("Cover", me, coll, mat=M.powder)

    ww, wh, wr = C.SCREEN["window"]
    pieces = [(lambda bm: U.extrude_poly(bm, U.rounded_rect_pts(ww, wh, wr, seg=6), -6.0, 3.0),
               slope_frame(C.CX, C.SCREEN_S))]
    rs = C.REAR_SLOTS
    x_first = C.W / 2 - (rs["n"] - 1) * rs["pitch"] / 2
    for k in range(rs["n"]):
        x = x_first + k * rs["pitch"]
        z = rs["z0"] + C.SLOT_L / 2
        pieces.append((lambda bm, x=x, z=z: stadium(bm, 0.0, 0.0, C.SLOT_W, C.SLOT_L, -4, 4), rear_frame(x, z)))
    usb = next(r for r in C.REAR if r[1] == "usbc")
    pieces.append((lambda bm: U.extrude_poly(bm, U.rounded_rect_pts(9.6, 3.9, 1.9, seg=6), -4, 4),
                   rear_frame(usb[2], C.REAR_Z)))
    for x, y in C.SCREWS:
        yy = C.T + C.FLANGE_D / 2 if y < C.D / 2 else C.D - C.T - C.FLANGE_D / 2
        pieces.append((lambda bm, x=x, yy=yy: U.cyl(bm, 1.4, 1.0, 5.0, x=x, y=yy, seg=16), Matrix.Identity(4)))
    cut = _cutter("CoverCut", pieces)
    U.boolean(o, cut)
    U.remove(cut)
    U.sharpen(o.data, 40)
    U.bevel(o, 0.3, segments=2, limit_angle=50)
    U.weighted_normals(o)
    return [o]


# ---- The screen ------------------------------------------------------------------------------------

def screen(coll, M):
    """The Prechen bar in its own case, pressed against the inside of the slope behind its
    window. Its local frame is the slope's at the window's centre."""
    S = C.SCREEN
    w, h, d = S["w"], S["h"], S["d"]
    zf = -C.T - 0.05                    # its front face, just behind the panel
    mb = MB("Screen")
    mb.add(M.screen_case, lambda bm: U.extrude_poly(bm, U.rounded_rect_pts(w, h, 3.0, seg=6), zf - d, zf - 0.6))
    mb.add(M.panel_black, lambda bm: U.extrude_poly(bm, U.rounded_rect_pts(w - 0.8, h - 0.8, 2.6, seg=6),
                                                    zf - 0.6, zf))
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * S["mounts"][0] / 2, sy * S["mounts"][1] / 2
            mb.add(M.steel, lambda bm, x=x, y=y: U.cyl(bm, 3.2, zf - d - 1.2, zf - d + 0.1, x=x, y=y, seg=20))
            mb.add(M.black_oxide, lambda bm, x=x, y=y: U.cyl(bm, 1.7, zf - d - 1.25, zf - d - 1.15, x=x, y=y, seg=16))
    # Ports on the right-hand end: mini-HDMI and USB-C.
    for yy, pw in ((-12.0, 11.2), (10.0, 9.0)):
        mb.add(M.matte_black, lambda bm, yy=yy, pw=pw: U.box(bm, w / 2 - 0.4, yy - pw / 2, zf - d / 2 - 1.8,
                                                             w / 2 + 0.05, yy + pw / 2, zf - d / 2 + 1.8),
               smooth=False)
    o = mb.obj(coll, bevel=0.25, seg=2)

    aw, ah = S["active"]
    bm = bmesh.new()
    vs = [bm.verts.new((x, y, zf + 0.02)) for x, y in ((-aw / 2, -ah / 2), (aw / 2, -ah / 2), (aw / 2, ah / 2),
                                                       (-aw / 2, ah / 2))]
    bm.faces.new(vs)
    me = U.mesh_from_bm(bm, "ScreenActive")
    uv = me.uv_layers.new(name="UVMap")
    for li, lp in enumerate(me.loops):
        v = me.vertices[lp.vertex_index].co
        uv.data[li].uv = ((v.x + aw / 2) / aw, (v.y + ah / 2) / ah)
    a = U.new_obj("ScreenActive", me, coll, mat=M.screen)
    m = slope_frame(C.CX, C.SCREEN_S)
    return [place(o, m), place(a, m)]


# ---- The sloped face's parts -----------------------------------------------------------------------

def pot(name, coll, M, knob_scale=1.0, bushing=3.5, body_r=12.0):
    """A panel pot or encoder: threaded bushing, washer and nut above the panel, its can below,
    and a knob (bl_parts' knob, scaled)."""
    mb = MB(name)
    zb = -C.T
    mb.add(M.nickel, lambda bm: lathe(bm, BP.thread(bushing, zb - 1.0, 6.5, pitch=0.75, depth=0.3,
                                                    bore=bushing - 0.5), seg=40))
    mb.add(M.nickel, lambda bm: BP.washer(bm, bushing + 2.4, bushing + 0.05, 0.0, 0.5))
    mb.add(M.nickel, lambda bm: BP.hex_nut(bm, bushing * 2 + 3.2, 0.5, 2.6, bushing + 0.05))
    mb.add(M.zinc, lambda bm: U.cyl(bm, body_r, zb - 10.0, zb - 1.0, seg=40))
    mb.add(M.tin, lambda bm: U.box(bm, -6.0, -body_r - 4.5, zb - 9.0, 6.0, -body_r + 1.0, zb - 8.4), smooth=False)
    o = mb.obj(coll, bevel=0.2, seg=2)
    k = BP.knob(name + "_Knob", coll, M, M.accent, 2.8)
    k.matrix_basis = Matrix.Diagonal((knob_scale, knob_scale, 0.85 + 0.25 * knob_scale, 1.0))
    return o, k


def push_button(name, coll, M):
    """A small panel push button: nickel bezel and a black cap."""
    mb = MB(name)
    zb = -C.T
    mb.add(M.nickel, lambda bm: lathe(bm, [(3.9, 0.0), (5.6, 0.0), (5.6, 1.6), (5.2, 2.2), (3.9, 2.2)], seg=48,
                                       closed=True))
    mb.add(M.black_plastic, lambda bm: lathe(bm, [(0.0, 3.6), (2.6, 3.5), (3.5, 3.0), (3.6, 1.0), (3.6, zb - 2.0),
                                                  (0.0, zb - 2.0)], seg=40))
    mb.add(M.black_plastic, lambda bm: U.box(bm, -5.0, -5.0, zb - 12.0, 5.0, 5.0, zb - 2.0))
    return mb.obj(coll, bevel=0.12, seg=2)


def panel(coll, M):
    """Six footswitches, the volume pot, the encoder and its two buttons, on the slope."""
    out = []
    for x, s, n in C.FOOTSWITCHES:
        out.append(place(BP.footswitch(f"Footswitch_{n}", coll, M, panel=C.T), slope_frame(x, s)))
    out.append(place(BP.footswitch("Footswitch_Tuner", coll, M, panel=C.T), slope_frame(*C.TUNER)))
    for name, at, scale, bush in (("Volume", C.VOLUME, 1.6, 4.75), ("Encoder", C.ENCODER, 1.0, 3.5)):
        o, k = pot(name, coll, M, knob_scale=scale, bushing=bush, body_r=12.0 if name == "Volume" else 6.5)
        m = slope_frame(*at)
        place(o, m)
        k.matrix_world = m @ k.matrix_basis
        out += [o, k]
    out.append(place(push_button("Button_Apply", coll, M), slope_frame(*C.APPLY)))
    out.append(place(push_button("Button_Back", coll, M), slope_frame(*C.BACK)))
    return out


# ---- The rear wall's parts --------------------------------------------------------------------------

def combo(name, coll, M):
    """Neutrik NCJ6FA-H-style combo socket: XLR with a 6.35 mm jack in its middle."""
    mb = MB(name)
    zb = -C.T
    mb.add(M.black_plastic, lambda bm: U.extrude_poly(bm, U.rounded_rect_pts(26.0, 31.0, 3.0, seg=6), 0.0, 2.4))
    mb.add(M.matte_black, lambda bm: U.cyl(bm, 10.6, 2.4, 2.45, seg=64))
    mb.add(M.nickel, lambda bm: lathe(bm, [(10.6, 2.4), (11.3, 2.4), (11.3, 2.7), (10.6, 2.7)], seg=64, closed=True))
    mb.add(M.dark_plastic, lambda bm: U.cyl(bm, 5.3, 2.45, 2.6, seg=40))
    mb.add(M.matte_black, lambda bm: U.cyl(bm, 3.3, 2.6, 2.65, seg=32))
    for a in (90, 210, 330):
        x, y = 7.9 * math.cos(math.radians(a)), 7.9 * math.sin(math.radians(a))
        mb.add(M.matte_black, lambda bm, x=x, y=y: U.cyl(bm, 1.25, 2.45, 2.5, x=x, y=y, seg=16))
    mb.add(M.nickel, lambda bm: U.box(bm, -2.5, 11.6, 2.4, 2.5, 13.8, 3.3))          # latch
    for sx, sy in ((-9.5, -12.0), (9.5, 12.0)):
        mb.add(M.black_oxide, lambda bm, sx=sx, sy=sy: BP.pan_screw(bm, 2.5, 2.4, x=sx, y=sy))
    mb.add(M.black_plastic, lambda bm: U.cyl(bm, 12.0, zb - 30.0, zb, seg=40))
    return mb.obj(coll, bevel=0.15, seg=2)


def rocker(name, coll, M):
    mb = MB(name)
    zb = -C.T
    mb.add(M.black_plastic, lambda bm: U.extrude_poly(bm, U.rounded_rect_pts(15.0, 21.0, 1.5, seg=4), 0.0, 2.2))
    mb.add(M.matte_black, lambda bm: U.box(bm, -6.0, -9.0, 2.2, 6.0, 9.0, 2.25))

    def rock(bm):
        U.box(bm, -5.6, -8.6, 0.0, 5.6, 8.6, 2.6)
        bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(9), 3, "X"), verts=bm.verts)
        bmesh.ops.translate(bm, vec=(0, 0, 2.0), verts=bm.verts)
    mb.add(M.panel_black, rock)
    mb.add(M.silk, lambda bm: U.box(bm, -0.5, 3.0, 4.8, 0.5, 6.4, 5.4), smooth=False)
    mb.add(M.black_plastic, lambda bm: U.box(bm, -6.5, -9.5, zb - 20.0, 6.5, 9.5, zb))
    return mb.obj(coll, bevel=0.2, seg=2)


def battery_door(name, coll, M):
    """A panel-mount PP3 holder: flange, a sliding door with grip ridges, its box inside."""
    mb = MB(name)
    zb = -C.T
    mb.add(M.black_plastic, lambda bm: U.extrude_poly(bm, U.rounded_rect_pts(46.0, 25.0, 2.5, seg=5), 0.0, 1.8))
    mb.add(M.dark_plastic, lambda bm: U.extrude_poly(bm, U.rounded_rect_pts(40.0, 19.0, 1.5, seg=4), 1.8, 2.5))
    for k in range(6):
        x = 9.0 + k * 1.8
        mb.add(M.dark_plastic, lambda bm, x=x: U.box(bm, x - 0.4, -6.5, 2.5, x + 0.4, 6.5, 3.0))
    mb.add(M.black_plastic, lambda bm: U.box(bm, -26.0, -14.0, zb - 20.0, 26.0, 14.0, zb))
    return mb.obj(coll, bevel=0.15, seg=2)


def rf_window(name, coll, M):
    """A plastic window in the aluminium for the Pi's Wi-Fi and Bluetooth."""
    mb = MB(name)
    mb.add(M.rf_plastic, lambda bm: U.extrude_poly(bm, U.rounded_rect_pts(30.0, 18.0, 3.0, seg=6), 0.0, 1.6))
    for sx in (-11.5, 11.5):
        mb.add(M.black_oxide, lambda bm, sx=sx: BP.pan_screw(bm, 2.0, 1.6, x=sx))
    return mb.obj(coll, bevel=0.2, seg=2)


def rear(coll, M):
    build = {"jack": BP.jack, "din": BP.din, "dc": BP.dc_socket, "usbc": BP.usbc_socket}
    out = []
    for key, kind, x, _ in C.REAR:
        if kind in build:
            o = build[kind]("Rear_" + key, coll, M, wall=C.T)
        else:
            o = {"combo": combo, "rocker": rocker, "battery": battery_door, "rfwindow": rf_window}[kind](
                "Rear_" + key, coll, M)
        out.append(place(o, rear_frame(x, C.REAR_Z)))
    return out


# ---- Inside ----------------------------------------------------------------------------------------

def standoff(mb, M, x, y, z0, z1):
    mb.add(M.nylon, lambda bm: BP.hex_nut(bm, 5.0, z0, z1, 1.3, x=x, y=y, chamfer=0.2))


def stripboards(coll, M):
    """The input, output and power boards, from stripboard/module_boards.py's own layouts:
    their size in holes, every part in its holes, the JST headers, the wire links and the
    standoff holes. The parts are simple shapes of the right size, not models of each part."""
    sys.path.insert(0, os.path.join(PROJECT, "stripboard"))
    import module_boards  # noqa: E402
    boards = {b.key: b for b in module_boards.boards()}
    out = []
    zb = C.T + C.STANDOFF
    for key, (x0, y0, rot) in C.BOARDS.items():
        b = boards[key]
        w, h = b.W * C.P, b.H * C.P
        o = stripboard(key, coll, M, b)
        o.matrix_world = T(x0, y0 + h, zb) @ Rz(rot)
        fx = MB(key + "_standoffs")
        for i, j in b.mounts:
            p = o.matrix_world @ Vector(((i + 0.5) * C.P, -(j + 0.5) * C.P, 0))
            standoff(fx, M, p.x, p.y, C.T, zb)
            fx.add(M.nylon, lambda bm, p=p: BP.hex_nut(bm, 5.0, zb + 1.6, zb + 3.6, 1.3, x=p.x, y=p.y, chamfer=0.2))
        out += [o, fx.obj(coll, bevel=0.1, seg=1)]
    return out


def stripboard(key, coll, M, b):
    """One stripboard. Origin on its grid's top-left corner, x along the strips, y down the
    rows (negative), z = 0 its underside."""
    P = C.P
    w, h = b.W * P, b.H * P

    def at(hole, z=1.6):
        return Vector(((hole[0] + 0.5) * P, -(hole[1] + 0.5) * P, z))

    mb = MB("Board_" + key)
    mb.add(M.stripboard, lambda bm: U.box(bm, 0, -h, 0, w, 0, 1.6), smooth=False)
    for j in range(b.H):
        mb.add(M.copper, lambda bm, j=j: U.box(bm, 0.1, -(j + 0.5) * P - 1.0, -0.04, w - 0.1, -(j + 0.5) * P + 1.0,
                                               0.0), smooth=False)

    def lead_wire(a, b_, lift=0.0):
        """A tinned lead lying from hole a to hole b_, down into both holes."""
        pa, pb = at(a), at(b_)
        mb.add(M.tin, lambda bm: _rod(bm, pa + Vector((0, 0, 0.4 + lift)), pb + Vector((0, 0, 0.4 + lift)), 0.3))
        for p in (pa, pb):
            mb.add(M.tin, lambda bm, p=p: _rod(bm, p - Vector((0, 0, 1.0)), p + Vector((0, 0, 0.4 + lift)), 0.3))

    for ref, (kind, value, holes) in b.parts_at.items():
        if kind in ("r", "d", "film") or kind in ("cer", "rs", "ds") or kind.startswith("el"):
            a, c = holes[0], holes[1]
            pa, pc = at(a), at(c)
            mid = (pa + pc) / 2
            axis = (pc - pa).normalized()
            if kind in ("r", "d"):
                lead_wire(a, c, lift=0.9)
                L, r = (6.3, 1.2) if kind == "r" else (4.2, 1.35)
                mat = M.resistor if kind == "r" else M.black_plastic
                mb.add(mat, lambda bm, mid=mid, axis=axis, L=L, r=r: _rod(bm, mid - axis * L / 2 + Vector((0, 0, 1.3)),
                                                                           mid + axis * L / 2 + Vector((0, 0, 1.3)),
                                                                           r, seg=20))
                if kind == "d":
                    mb.add(M.silk, lambda bm, mid=mid, axis=axis: _rod(bm, mid + axis * 1.2 + Vector((0, 0, 1.3)),
                                                                       mid + axis * 1.7 + Vector((0, 0, 1.3)), 1.37,
                                                                       seg=20))
            elif kind == "film":
                lead_wire(a, c)
                sx, sy = (abs(pc.x - pa.x) + 2.5, 4.5) if abs(axis.x) > 0.5 else (4.5, abs(pc.y - pa.y) + 2.5)
                mb.add(M.film, lambda bm, mid=mid, sx=sx, sy=sy: U.box(bm, mid.x - sx / 2, mid.y - sy / 2, 1.6,
                                                                       mid.x + sx / 2, mid.y + sy / 2, 11.0))
            elif kind == "cer":
                lead_wire(a, c)
                mb.add(M.disc_cap, lambda bm, mid=mid: _rod(bm, mid + Vector((0, -1.1, 5.0)), mid + Vector((0, 1.1, 5.0)),
                                                            2.5, seg=24))
            elif kind in ("rs", "ds"):
                lead_wire(a, c, lift=8.0)
                mat = M.resistor if kind == "rs" else M.black_plastic
                mb.add(mat, lambda bm, pa=pa, mat=mat: U.cyl(bm, 1.2 if kind == "rs" else 1.35, 2.3, 8.3, x=pa.x,
                                                             y=pa.y, seg=20))
            else:
                dia = float(kind[2:])
                ht = {6.3: 11.0, 5.2: 11.0, 10.0: 16.0}.get(dia, 11.0)
                lead_wire(a, c)
                mb.add(M.elec, lambda bm, mid=mid, dia=dia, ht=ht: U.cyl(bm, dia / 2, 1.9, 1.9 + ht, x=mid.x, y=mid.y,
                                                                         seg=32))
                mb.add(M.alu, lambda bm, mid=mid, dia=dia, ht=ht: U.cyl(bm, dia / 2 - 0.2, 1.9 + ht, 2.0 + ht, x=mid.x,
                                                                        y=mid.y, seg=32))
        elif kind in ("dip6", "dip8", "relay"):
            n = {"dip6": 6, "dip8": 8, "relay": 10}[kind]
            p0 = at(holes[0])
            x0, x1 = p0.x - 1.3, p0.x + 3 * P + 1.3
            y1, y0 = p0.y + 1.4, p0.y - (n // 2 - 1) * P - 1.4
            mb.add(M.black_plastic, lambda bm, x0=x0, x1=x1, y0=y0, y1=y1: U.box(bm, x0, y0, 1.6, x1, y1, 4.6))
            mb.add(M.panel_black, lambda bm, x0=x0, x1=x1, y0=y0, y1=y1: U.box(bm, x0 + 0.6, y0 + 0.3, 4.6, x1 - 0.6,
                                                                              y1 - 0.3, 8.0))
        elif kind == "to92":
            mid = at(holes[1])
            mb.add(M.black_plastic, lambda bm, mid=mid: U.box(bm, mid.x - 2.4, mid.y - 1.0, 4.0, mid.x + 2.4, mid.y + 1.4,
                                                              9.0))
    for hd in b.headers:
        hs = [at(hh) for hh in hd.holes()]
        xs, ys = [p.x for p in hs], [p.y for p in hs]
        x0, x1 = min(xs) - 2.9, max(xs) + 2.9
        y0, y1 = min(ys) - 2.45, max(ys) + 2.45
        mb.add(M.xh, lambda bm, x0=x0, x1=x1, y0=y0, y1=y1: U.box(bm, x0, y0, 1.6, x1, y1, 8.6))
        for p in hs:
            mb.add(M.tin, lambda bm, p=p: U.box(bm, p.x - 0.32, p.y - 0.32, 2.0, p.x + 0.32, p.y + 0.32, 8.0),
                   smooth=False)
    for a, c, _ in b.links:
        lead_wire(a, c, lift=0.0)
    return mb.obj(coll, bevel=0.0)


def _rod(bm, a, b, r, seg=10):
    v = b - a
    if v.length < 1e-6:
        return
    m = Matrix.Translation(a) @ v.to_track_quat("Z", "Y").to_matrix().to_4x4()
    U.cyl(bm, r, 0.0, v.length, seg=seg, matrix=m)


def pico(coll, M):
    """Raspberry Pi Pico 2 (51 x 21 mm), on four nylon standoffs, USB end towards the rear."""
    x0, y0 = C.PICO
    zb = C.T + C.STANDOFF
    mb = MB("Pico2")
    L_, W_ = 51.0, 21.0
    # Built along +x, then turned so its USB end faces the rear wall.
    mb.add(M.pico_green, lambda bm: U.box(bm, 0, -W_ / 2, 0, L_, W_ / 2, 1.0), smooth=False)
    for k in range(20):
        x = 1.61 + k * 2.54
        for y in (-W_ / 2, W_ / 2):
            mb.add(M.gold, lambda bm, x=x, y=y: U.cyl(bm, 0.85, -0.01, 1.01, x=x, y=y, seg=16))
    mb.add(M.black_plastic, lambda bm: U.box(bm, 22.0, -3.5, 1.0, 29.0, 3.5, 1.9))          # RP2350
    mb.add(M.black_plastic, lambda bm: U.box(bm, 33.0, -3.0, 1.0, 38.0, 3.0, 2.2))          # flash
    mb.add(M.tin, lambda bm: U.box(bm, 13.0, -6.5, 1.0, 16.2, -4.0, 1.8))                    # crystal
    mb.add(M.steel, lambda bm: U.box(bm, -1.3, -3.9, 1.0, 4.4, 3.9, 3.9))                  # micro-USB
    mb.add(M.white_plastic, lambda bm: U.box(bm, 8.0, 3.0, 1.0, 11.0, 6.5, 2.6))            # BOOTSEL
    mb.add(M.silk, lambda bm: U.box(bm, 8.4, 3.4, 2.6, 10.6, 6.1, 3.2))
    for x in (2.0, 49.0):
        for y in (-5.7, 5.7):
            mb.add(M.matte_black, lambda bm, x=x, y=y: U.cyl(bm, 1.05, -0.01, 1.02, x=x, y=y, seg=16))
    o = mb.obj(coll, bevel=0.1, seg=1)
    o.matrix_world = T(x0 + W_ / 2, y0, zb) @ Rz(90)
    fx = MB("Pico2_standoffs")
    for x in (2.0, 49.0):
        for y in (-5.7, 5.7):
            p = o.matrix_world @ Vector((x, y, 0))
            standoff(fx, M, p.x, p.y, C.T, zb)
    return [o, fx.obj(coll, bevel=0.1, seg=1)]


def kicad_boards(coll, M):
    """The Pi 5 and the SparkFun WM8960, from the GLBs src/make_parts.py builds; plain boards
    of the right size when they have not been built."""
    out = []
    zb = C.T + C.STANDOFF
    fx = MB("Inside_standoffs")
    # Raspberry Pi 5: the GLB's origin is the PCB's corner, the PCB 1.62 mm up from it. Turned
    # half round so its USB-C and HDMI edge faces the rear wall.
    px, py = C.PI5
    m = T(px + 85.0, py + 56.0, zb - 1.62) @ Rz(180)
    path = os.path.join(PARTS, "rpi5.glb")
    if os.path.exists(path):
        o = U.import_glb(path, "RaspberryPi5", coll, M)
    else:
        print("WARNING: no", path, "- a plain board stands in for the Pi 5")
        mb = MB("RaspberryPi5")
        mb.add(M.mask(U.srgb("#1f6b37"), "pi_green"), lambda bm: U.box(bm, 0, 0, 1.62, 85, 56, 3.0))
        o = mb.obj(coll)
    out.append(place(o, m))
    for hx, hy in ((3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)):
        p = m @ Vector((hx, hy, 1.62))
        standoff(fx, M, p.x, p.y, C.T, zb)
    # SparkFun WM8960 breakout, 25.4 x 40.64 mm: origin top-left, underside at z = 0.
    cx, cy = C.CODEC
    path = os.path.join(PARTS, "codec.glb")
    if os.path.exists(path):
        o = U.import_glb(path, "WM8960", coll, M, mask="#C8102E", finish="gold", mask_name="sparkfun")
    else:
        print("WARNING: no", path, "- a plain board stands in for the WM8960")
        mb = MB("WM8960")
        mb.add(M.mask(U.srgb("#C8102E"), "sparkfun"), lambda bm: U.box(bm, 0, -40.64, 0, 25.4, 0, 1.6))
        o = mb.obj(coll)
    out.append(place(o, T(cx, cy + 40.64, zb)))
    for hx, hy in ((2.6, 2.6), (22.8, 2.6), (2.6, 38.0), (22.8, 38.0)):
        standoff(fx, M, cx + hx, cy + hy, C.T, zb)
    out.append(fx.obj(coll, bevel=0.1, seg=1))
    return out

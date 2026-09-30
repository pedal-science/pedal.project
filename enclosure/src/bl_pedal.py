"""Assembles the pedal: enclosure, boards, panel and wall parts, fixings, labels and wiring.
Everything is in millimetres around the enclosure origin (layout.py). Returns the three
source collections the scene instances: common parts, closed-only and open-only."""
import json
import math
import os

import bmesh
import bpy
from mathutils import Matrix, Vector

import bl_enclosure as BE
import bl_parts as BP
import bl_util as U
import layout as L
from bl_parts import MB, Rz
from bl_wires import RIBBON, Wiring

PARTS = os.path.join(U.ASSETS, "parts")
H = L.ENC["H"]
PANEL = L.ENC["top"]
FONT = "/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf"

# Heights (enclosure z) that follow from the parts.
PI_Z = L.Z_LID_TOP + L.PI5_STANDOFF - 1.62          # GLB origin of the Pi: its PCB underside is 1.62 up
PI_PCB_TOP = PI_Z + 2.90
PI_PIN_BASE = PI_PCB_TOP + 2.5                     # top of the GPIO header's plastic
CODEC_Z = L.BOARD_TOP + L.SOCKET_H + L.HEADER_BASE  # codec PCB underside, on its sockets
ADAPTER_Z = L.BOARD_TOP + 4.1 + L.HEADER_BASE       # SOIC adapter PCB underside, on the DIP socket
DISP_Z = L.DISP_PCB_TOP - L.PCB_T                   # display board underside


def pi_pin(n):
    """Top of Pi GPIO header pin n (enclosure coords)."""
    col = (n - 1) // 2
    x = L.PI5_ORIGIN[0] + 8.38 + 2.54 * col
    y = L.PI5_ORIGIN[1] + (51.22 if n % 2 else 53.76)
    return Vector((x, y, PI_Z + 11.47))


class Holes:
    """Free-hole bookkeeping for wires landing on the stripboards."""

    def __init__(self):
        meta = json.load(open(os.path.join(PARTS, "parts.json")))
        self.meta = {"a": meta["board_a"], "b": meta["board_b"]}
        self.used = {k: {tuple(h) for h in v["blocked"]} for k, v in self.meta.items()}
        self.used["b"] |= {(c, r) for c in range(9, 15) for r in range(20)}   # under the Pico

    def take(self, board, c, r):
        bd = self.meta[board]
        best = None
        for cc in range(bd["cols"]):
            for rr in range(bd["rows"]):
                if (cc, rr) in self.used[board]:
                    continue
                d = (cc - c) ** 2 + 1.3 * (rr - r) ** 2
                if best is None or d < best[0]:
                    best = (d, cc, rr)
        _, cc, rr = best
        self.used[board].add((cc, rr))
        x, y = L.hole(bd, cc, rr)
        return Vector((x, y, L.BOARD_TOP))


def place(o, loc=(0, 0, 0), rot_z=0.0, matrix=None):
    o.matrix_world = matrix if matrix is not None else Matrix.Translation(loc) @ Rz(rot_z)
    return o


def world(o, local):
    return o.matrix_world @ Vector(local)


def label(coll, mat, s, matrix, size=3.0, align="CENTER"):
    """Flat printed text; matrix places its origin, x reading direction, y up, z out."""
    cu = bpy.data.curves.new("label", "FONT")
    cu.body = s
    cu.font = bpy.data.fonts.load(FONT, check_existing=True)
    cu.size = size
    cu.align_x = align
    cu.align_y = "CENTER"
    cu.extrude = 0.015
    o = bpy.data.objects.new("Label_" + s, cu)
    coll.objects.link(o)
    o.data.materials.append(mat)
    o.matrix_world = matrix @ Matrix.Translation((0, 0, 0.03))
    return o


def wall_basis(wall, s, z):
    """Matrix for text on a wall: x reads left to right as seen from outside, y up."""
    ins = BE.inset_at(z)
    n = {"left": Vector((-1, 0, 0)), "right": Vector((1, 0, 0)), "rear": Vector((0, 1, 0)),
         "front": Vector((0, -1, 0))}[wall]
    up = Vector((0, 0, 1))
    right = up.cross(n)
    pos = {"left": (ins, s, z), "right": (L.ENC["W"] - ins, s, z), "rear": (s, L.ENC["D"] - ins, z),
           "front": (s, ins, z)}[wall]
    m = Matrix.Identity(4)
    m.col[0][:3] = right
    m.col[1][:3] = up
    m.col[2][:3] = n
    m.col[3][:3] = pos
    return m


def build(M):
    src = U.collection("PedalSource")
    common = U.collection("Pedal_Common", src)
    closed_only = U.collection("Pedal_ClosedOnly", src)
    open_only = U.collection("Pedal_OpenOnly", src)
    screen = screen_material()
    ink_white = U.principled("InkWhite", (0.85, 0.85, 0.83), rough=0.5)
    ink_black = U.principled("InkBlack", (0.01, 0.01, 0.011), rough=0.45)
    led_on = {c: U.principled(f"LED_{c}_on", U.srgb(h)[:3], rough=0.15, transmission=0.3, emission=U.srgb(h)[:3],
                              emission_strength=s)
              for c, h, s in (("red", "#ff2a1a", 60.0), ("green", "#2bff5a", 45.0))}
    led_off = {c: U.principled(f"LED_{c}_off", U.srgb(h)[:3], rough=0.12, transmission=0.6, subsurface=0.4)
               for c, h in (("red", "#8c0d08"), ("green", "#0d6b22"))}

    # ---- Enclosure --------------------------------------------------------------------
    BE.body(closed_only, M, open_top=False)
    BE.body(open_only, M, open_top=True)
    BE.lid(common, M)
    wx, wy = L.WINDOW_C
    mb = MB("WindowAcrylic")
    mb.add(M.acrylic, lambda bm: U.extrude_poly(bm, U.rounded_rect_pts(L.WINDOW[0] + 7, L.WINDOW[1] + 7, 2, cx=wx,
                                                                       cy=wy), L.Z_TOP_IN - 1.0, L.Z_TOP_IN - 0.02),
           smooth=False)
    mb.obj(closed_only, bevel=0.2, seg=2)

    # ---- KiCad-built boards ------------------------------------------------------------
    parts = {}
    parts["pi"] = place(U.import_glb(os.path.join(PARTS, "rpi5.glb"), "RaspberryPi5", common, M),
                        (L.PI5_ORIGIN[0], L.PI5_ORIGIN[1], PI_Z))
    for key, bd in (("board_b", L.BOARD_B), ("board_a", L.BOARD_A)):
        o = U.import_glb(os.path.join(PARTS, key + ".glb"), key, common, M, finish="copper")
        place(o, (bd["x0"], bd["y0"] + bd["rows"] * L.P, L.BOARD_Z))
    hx, hy = L.hole(L.BOARD_A, 1, 2)
    place(U.import_glb(os.path.join(PARTS, "codec.glb"), "WM8960", common, M, mask="#C8102E", finish="gold",
                       mask_name="sparkfun"), (hx - 1.27, hy + 1.27, CODEC_Z))
    hx, hy = L.hole(L.BOARD_A, 13, 4)
    place(U.import_glb(os.path.join(PARTS, "soic_adapter.glb"), "SOICAdapter", common, M, mask="#0F3F2A",
                       finish="gold", mask_name="adapter"), (hx - 1.29, hy + 1.49, ADAPTER_Z))
    place(U.import_glb(os.path.join(PARTS, "display.glb"), "DisplayBoard", common, M, mask="#1D5BB8",
                       finish="tin", mask_name="display"), (L.DISP_X0, L.DISP_YTOP, DISP_Z))

    # ---- Display module parts ----------------------------------------------------------
    gx0 = L.DISP_X0 + L.DISP["glass_x0"]
    place(BP.tft("TFT", common, M, screen), (gx0, L.DISP_YTOP - 0.25, L.DISP_PCB_TOP))
    ex, ey = L.ENCODER
    panel_rel = H - L.DISP_PCB_TOP
    place(BP.encoder("EC11", common, M, 6.5, panel_rel), (ex, ey, L.DISP_PCB_TOP))
    place(BP.knob("Knob", common, M, U.principled("KnobLine", U.srgb("#f2641c")[:3], rough=0.35),
                  panel_rel + 2.4 + 0.9), (ex, ey, L.DISP_PCB_TOP), rot_z=math.radians(-35))
    bx, by = L.BUTTON
    place(BP.button_cap("ButtonCap", common, M, L.DISP_PCB_TOP + 8.45, H + 3.0), (bx, by, 0))

    # ---- Panel parts -------------------------------------------------------------------
    fsw = []
    for i, x in enumerate(L.FS_X):
        fsw.append(place(BP.footswitch(f"Footswitch_{'ABC'[i]}", common, M), (x, L.FS_Y, H), rot_z=math.radians(90)))
    leds = []
    states = [led_on["red"], led_off["green"], led_off["green"], led_on["green"]]
    spots = [(x, L.LED_Y) for x in L.FS_X] + [L.LED_READY]
    for i, ((x, y), lm) in enumerate(zip(spots, states)):
        leds.append(place(BP.led(f"LED_{i + 1}", common, M, lm), (x, y, H)))
    tog = place(BP.toggle("InstLine", common, M, flip=-16.0), (*L.TOGGLE, H), rot_z=math.radians(0))

    # ---- Wall parts --------------------------------------------------------------------
    jacks = {}
    for name, (wall, s, z) in L.JACKS.items():
        jacks[name] = place(BP.jack(f"Jack_{name}", common, M), matrix=BE.wall_frame(wall, s, z))
    din = place(BP.din("MIDI_In", common, M), matrix=BE.wall_frame("rear", *L.MIDI))
    dc = place(BP.dc_socket("DC_9V", common, M), matrix=BE.wall_frame("rear", *L.DC9V))
    usb = place(BP.usbc_socket("USBC_5V", common, M), matrix=BE.wall_frame("rear", *L.USBC))

    # ---- Standoffs and screws ----------------------------------------------------------
    fix = MB("Fixings")
    ox, oy = L.PI5_ORIGIN
    for hx_, hy_ in ((3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)):
        x, y = ox + hx_, oy + hy_
        fix.add(M.brass, lambda bm, x=x, y=y: BP.hex_nut(bm, 5.0, L.Z_LID_TOP, L.Z_LID_TOP + L.PI5_STANDOFF, 1.25,
                                                         x=x, y=y, chamfer=0.25))
        fix.add(M.zinc, lambda bm, x=x, y=y: BP.pan_screw(bm, 2.5, PI_PCB_TOP, x=x, y=y))
    for key, bd in (("b", L.BOARD_B), ("a", L.BOARD_A)):
        meta = json.load(open(os.path.join(PARTS, "parts.json")))["board_" + key]
        for c, r in meta["standoffs"]:
            x, y = L.hole(bd, c, r)
            fix.add(M.brass, lambda bm, x=x, y=y: BP.hex_nut(bm, 5.5, L.Z_LID_TOP, L.BOARD_Z, 1.5, x=x, y=y,
                                                             chamfer=0.25))
            fix.add(M.zinc, lambda bm, x=x, y=y: BP.pan_screw(bm, 3.0, L.BOARD_TOP + (0.9 if (key, c, r) == ("a", 0, 19)
                                                                                     else 0.0), x=x, y=y))
    # Star ground: two solder tags under the screw at board A's front-left corner.
    sx, sy = L.hole(L.BOARD_A, 0, 19)
    star = Vector((sx, sy, L.BOARD_TOP))
    for k, ang in enumerate((200.0, 250.0)):
        def tag(bm, ang=ang, k=k):
            z0 = L.BOARD_TOP + k * 0.45
            BP.washer(bm, 3.2, 1.6, z0, z0 + 0.4)
            U.box(bm, 2.6, -1.3, z0, 8.0, 1.3, z0 + 0.4)
            bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(ang), 3, "Z"), verts=bm.verts)
            bmesh.ops.translate(bm, vec=(sx, sy, 0), verts=bm.verts)
        fix.add(M.tin, tag, smooth=False)
    fix.obj(common, bevel=0.1, seg=1)
    star_tags = [star + Vector((math.cos(math.radians(a)), math.sin(math.radians(a)), 0)) * 6.8 +
                 Vector((0, 0, 0.2 + k * 0.45)) for k, a in enumerate((200.0, 250.0))]

    # ---- Printed labels ---------------------------------------------------------------
    for name, (wall, s, z) in L.JACKS.items():
        text = {"OUT_L": "OUT L", "OUT_R": "OUT R", "IN": "IN", "EXP": "EXP"}[name]
        label(common, ink_black, text, wall_basis(wall, s, z + 11.5), size=3.4)
    label(common, ink_white, "5V", wall_basis("rear", L.USBC[0], L.USBC[1] - 7.5), size=3.2)
    label(common, ink_white, "9V", wall_basis("rear", L.DC9V[0], L.DC9V[1] - 10.5), size=3.2)
    label(common, ink_white, "MIDI", wall_basis("rear", L.MIDI[0], L.MIDI[1] - 13.5), size=3.2)
    top = Matrix.Translation((0, 0, H))
    tx, ty = L.TOGGLE
    label(closed_only, ink_black, "INST", top @ Matrix.Translation((tx - 7.5, ty + 11.0, 0)), size=2.6)
    label(closed_only, ink_black, "LINE", top @ Matrix.Translation((tx + 7.5, ty + 11.0, 0)), size=2.6)
    for i, x in enumerate(L.FS_X):
        label(closed_only, ink_white, "ABC"[i], top @ Matrix.Translation((x, L.FS_Y - 13.5, 0)), size=3.6)

    wiring(M, common, fsw, leds, tog, jacks, din, dc, usb, star_tags)
    return common, closed_only, open_only


def screen_material():
    m = bpy.data.materials.new("ScreenUI")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    img = nt.nodes.new("ShaderNodeTexImage")
    img.image = bpy.data.images.load(os.path.join(U.ASSETS, "screen_ui.png"))
    img.interpolation = "Cubic"
    img.location = (-500, 0)
    nt.links.new(img.outputs["Color"], b.inputs["Emission Color"])
    b.inputs["Emission Strength"].default_value = 3.2
    b.inputs["Base Color"].default_value = (0.0, 0.0, 0.0, 1)
    b.inputs["Roughness"].default_value = 0.05
    b.inputs["Coat Weight"].default_value = 1.0
    b.inputs["Coat Roughness"].default_value = 0.02
    return m


# ---- Wiring ------------------------------------------------------------------------------------

def wiring(M, coll, fsw, leds, tog, jacks, din, dc, usb, star_tags):
    W = Wiring(U.collection("Pedal_Wiring", coll), M)
    holes = Holes()
    up, down = Vector((0, 0, 1)), Vector((0, 0, -1))
    inward = {"left": Vector((1, 0, 0)), "right": Vector((-1, 0, 0)), "rear": Vector((0, -1, 0))}

    # Dupont housings on the Pi header, and the leads from them.
    def dup(n):
        return W.dupont(pi_pin(n), PI_PIN_BASE)

    # 5 V in: USB-C pads to header pins 2 (5 V) and 6 (GND), 20 AWG.
    for pad, pin, col, dx in (("VBUS", 2, "red", 0.0), ("GND", 6, "black", 1.8)):
        p = world(usb, usb["pads"][pad])
        top = dup(pin)
        W.run(f"W_usb_{pad}", col, p, (0, -0.35, -1), [
            (p.x + dx, p.y - 7, 26.6), (38.5 + dx, 98, 26.6), (35.5 + dx, 76, 26.6), (33.5 + dx, 64.5, 26.3),
            (top.x, top.y + 1.5, top.z + 3.5)], top, up, r=0.78, s_kind="pad", e_kind="dupont", lead=2.0)

    # Pi 5 V (pin 4) to the Pico's VSYS diode; UART and ground to the Pico's socket strip.
    for pin, target, col in ((4, (0, 18), "red"), (8, (7, 19), "yellow"), (10, (7, 18), "green"),
                             (14, (6, 18), "black")):
        top = dup(pin)
        h = holes.take("b", *target)
        mid = (top + h) / 2
        W.run(f"W_pi{pin}", col, top, up, [(top.x, top.y + 1.0, top.z + 3.2), (mid.x, mid.y + 1.5, top.z + 2.2),
                                           (h.x, h.y - 0.5, h.z + 9.0)], h, up, s_kind="dupont", lead=1.5)

    # Pi to codec: I2S, I2C, 3V3 and ground, down beside the codec to its left strips.
    leads = [(1, 10, "orange"), (3, 9, "blue"), (5, 8, "purple"), (12, 3, "white"), (35, 4, "grey"),
             (38, 7, "brown"), (40, 5, "pink"), (39, 11, "black")]
    for k, (pin, row, col) in enumerate(leads):
        top = dup(pin)
        h = holes.take("a", 0, row)
        if top.x < 60:
            via = [(top.x, top.y + 1.0, top.z + 2.4), (top.x + 8, 68 + k * 0.9, 25.6 + 0.35 * (k % 3)),
                   (62 + k * 0.4, h.y - 7, 25.7), (71.2 - 0.3 * k, h.y - 3, 20.5)]
        else:
            via = [(top.x, top.y + 1.2, top.z + 2.2), (73.2 - 0.5 * (k - 4), 66.0, 24.0), (72.4, h.y - 5, 17.5)]
        W.run(f"W_codec_{pin}", col, top, up, via + [(h.x, h.y, h.z + 6.5)], h, up, s_kind="dupont", lead=1.2)

    # Display leads: a split rainbow ribbon from the module's pads straight down to board B.
    for i in range(12):
        pu, pv = L.DISP["pads_x"], L.DISP["pads_y0"] + i * L.P
        pad = Vector((*L.disp_to_enc(pu, pv), DISP_Z))
        h = holes.take("b", 1, 8 + i)
        jit = ((i * 37) % 7 - 3) * 0.12
        W.run(f"W_disp_{i}", RIBBON[i], pad, down, [(pad.x + 0.8, pad.y + jit, pad.z - 7.5),
                                                  (h.x - 0.6, h.y + jit, h.z + 8.5)], h, up,
              r=0.5, s_kind="pad", lead=2.5)

    # Footswitches: common and normally-open tags to board B, 100 nF across each.
    for i, sw in enumerate(fsw):
        com = world(sw, (0.0, 3.3, sw["tags"][0][2]))
        no = world(sw, (5.2, 3.3, sw["tags"][0][2]))
        cap_c = (com + no) / 2 + Vector((-2.2, 0, -1.0))
        W.cylinder(M.disc_cap, cap_c + Vector((-0.8, 0, 0)), cap_c + Vector((0.8, 0, 0)), 2.1, seg=24)
        for t in (com, no):
            W.cylinder(M.tin, cap_c, t + Vector((0, 0, 0.8)), 0.22, seg=8)
        for tag, col, j in ((no, "orange", 0), (com, "black", 1)):
            h = holes.take("b", 0, 15 + 2 * i + j - 4 * (i == 2))
            name = f"W_fs{i}_{j}"
            if i == 0:
                via = [(tag.x - 1.5, tag.y + 8, 9.0 + j), (19.5 + j, 42, 7.0 + j), (21.0 + j, 60, 7.0 + j),
                       (24.2, h.y - 2, 9.5 + j * 0.8)]
            else:
                x0 = tag.x - 2.0
                via = [(x0, tag.y + 9, 11.0 + j), (x0 - 0.5, 52, 10.5 + j), (x0 - 1.5, 62.4, 10.4 + j * 0.9),
                       (x0 - 6, 63.3 + j * 0.3, 10.4 + j * 0.9)]
                via += [(49.0 - 0.6 * i - j * 0.5, 63.4 + j * 0.3, 10.8 + j * 0.9), (40.0, 63.2, 11.5),
                        (27.5, 63.2 + 0.4 * j, 12.0), (26.0, h.y - 2, 10.5)]
            W.run(name, col, tag, (0, 0.3, -1), via, h, up, s_kind="tag", lead=2.0)

    # LEDs: legs spliced to wires under heat shrink, then to board B.
    for i, led in enumerate(leds):
        for j, (leg, col) in enumerate(zip(led["legs"], ("orange", "black"))):
            p = world(led, leg)
            W.cylinder(M.heatshrink, p + Vector((0, 0, 3.2)), p - Vector((0, 0, 4.0)), 0.95, seg=16)
            h = holes.take("b", 0, [6, 8, 10, 13][i] + j)
            if i == 3:
                via = [(p.x, p.y, p.z - 6), (p.x + 6, p.y + 0.5, 19.5), (24.0, h.y, 16.0)]
            elif i == 0:
                via = [(p.x, p.y, p.z - 7), (p.x - 0.5, p.y + 6, 11.0), (21.5 + j, 60, 7.5 + j), (24.8, h.y - 2, 10.0)]
            else:
                x0 = p.x - 2.5
                via = [(p.x, p.y, p.z - 6), (x0, 55, 12.0 + j * 0.6), (x0 - 2, 62.6, 11.2 + j * 0.9),
                       (x0 - 8, 63.0, 11.2 + j * 0.9), (40.0, 62.9, 12.2 + j * 0.5), (27.5, 62.9, 12.6),
                       (26.0, h.y - 2, 11.0)]
            W.run(f"W_led{i}_{j}", col, p - Vector((0, 0, 3.5)), down, via, h, up, s_kind="free", lead=2.5)

    # Expression jack: tip, ring and sleeve to board B along the front loom.
    ej = jacks["EXP"]
    for k, (tag, col) in enumerate((("T", "orange"), ("R", "white"), ("S", "black"))):
        p = world(ej, ej["tags"][tag])
        h = holes.take("b", 7, 15 + k)
        via = [(118.5, p.y - 3, 13.5 + k * 0.7), (116.0, 63.6, 12.6 + 0.7 * k), (80.0, 63.7, 12.9 + 0.7 * k),
               (52.0, 63.5, 13.2 + 0.6 * k), (47.2, h.y - 3, 12.0)]
        W.run(f"W_exp_{tag}", col, p, inward["right"], via, h, up, s_kind="tag", lead=2.5)

    # Input: screened cable from the tip to the buffer; sleeve to the star ground; tip switch
    # linked to the sleeve.
    ij = jacks["IN"]
    t = world(ij, ij["tags"]["T"])
    h = holes.take("a", 17, 2)
    W.run("W_in_screened", "sheath", t, inward["right"], [(119.5, t.y + 1.5, 17.5), (h.x + 0.5, h.y - 1, h.z + 7)],
          h, up, r=1.35, s_kind="tag", lead=2.5)
    W.cylinder(M.braid, h + Vector((0, 0, 2.2)), h + Vector((0, 0, 3.4)), 1.25, seg=20)
    ts, sl = world(ij, ij["tags"]["TS"]), world(ij, ij["tags"]["S"])
    W.run("W_in_link", "black", ts, inward["right"], [(ts.x - 3, (ts.y + sl.y) / 2, (ts.z + sl.z) / 2)], sl,
          inward["right"], r=0.5, s_kind="tag", e_kind="tag", lead=1.5)

    # Inst / Line toggle to the buffer's pad taps.
    for k, key in enumerate(("A", "C", "B")):
        p = world(tog, tog["tags"][key])
        h = holes.take("a", 17, 6 + k)
        W.run(f"W_tog_{key}", "orange", p, (0, 0, -1),
              [(p.x - 2, p.y + 3 + k, 13.0 + k * 0.5), (120.5, h.y - 1, 12.5 + k * 0.5)], h, up, s_kind="tag", lead=2.0)

    # 9 V: centre pin to the reverse-polarity diode, sleeve to the star ground.
    p = world(dc, dc["tags"]["PIN"])
    h = holes.take("a", 1, 0)
    W.run("W_dc_pin", "red", p, inward["rear"], [(p.x - 1.5, p.y - 3, p.z - 4), (h.x + 0.5, h.y + 1, h.z + 7)], h, up,
          s_kind="tag", lead=2.0)
    p = world(dc, dc["tags"]["SLEEVE"])
    W.run("W_dc_gnd", "black", p, inward["rear"], [(p.x - 3.5, p.y - 4, 22.0), (70.4, 95.0, 18.5), (70.3, 75.0, 14.0),
                                                   (star_tags[0] + Vector((0.5, 3.0, 5.0)))], star_tags[0], up,
          s_kind="tag", e_kind="tag", lead=2.0)

    # MIDI in: DIN pins 4 and 5 as a twisted pair over the boards to the opto on board B.
    p4, p5 = world(din, din["pins"]["2"]), world(din, din["pins"]["4"])
    h4, h5 = holes.take("b", 0, 1), holes.take("b", 0, 2)
    mid = (p4 + p5) / 2
    cl = W.twisted("W_midi", ("orange", "black"), [mid, mid + Vector((0, -4, 0.5)), (100, 96, 24.4), (75, 96.5, 24.4),
                                                   (50, 98.5, 24.4), (33, 103.5, 23.0), (28.8, 108.5, 16.5),
                                                   ((h4 + h5) / 2 + Vector((0, 0, 7)))], r=0.55)
    for pin_p, h in ((p4, h4), (p5, h5)):
        W.run("W_midi_end", "orange" if pin_p is p4 else "black", cl[-1], down, [((cl[-1] + h) / 2 + Vector((0, 0, 1.5)))],
              h, up, r=0.55, s_kind="free", lead=0.8)
        W.run("W_midi_start", "orange" if pin_p is p4 else "black", pin_p, inward["rear"], [], cl[0], -inward["rear"],
              r=0.55, s_kind="tag", e_kind="free", lead=1.0)

    # Outputs: twisted pairs from the output resistors, along the front loom, to the left-wall jacks.
    for k, (name, row) in enumerate((("OUT_L", 17), ("OUT_R", 18))):
        jk = jacks[name]
        t, s = world(jk, jk["tags"]["T"]), world(jk, jk["tags"]["S"])
        h = holes.take("a", 16, row)
        z = 15.5 + 1.4 * k
        start = h + Vector((0, 0, 5.5))
        cl = W.twisted(f"W_{name}", ("orange", "black"), [start, (h.x, 64.4, z - 2), (95.0, 63.9, z - 2.5),
                                                        (60.0, 63.9, z - 2), (30.0, 63.8, z - 1),
                                                        (24.2, 66.0 + 4 * k, z), (24.0, (t.y + s.y) / 2, z + 0.5)],
                       r=0.58, pitch=10.0)
        W.run(f"W_{name}_hole", "orange", start, down, [], h, up, r=0.58, s_kind="free", lead=1.0)
        W.run(f"W_{name}_T", "orange", t, inward["left"], [(t.x + 2.5, t.y, t.z)], cl[-1], (0, 0, 1), r=0.58,
              s_kind="tag", e_kind="free", lead=1.5)
        W.run(f"W_{name}_S", "black", s, inward["left"], [(s.x + 2.5, s.y, s.z)], cl[-1], (0, 0, 1), r=0.58,
              s_kind="tag", e_kind="free", lead=1.5)
        # Sleeve returns to the star ground.
        W.run(f"W_{name}_gnd", "black", s + Vector((0.8, 0, -1.2)), (1, 0, 0),
              [(26.5, 63.0, 9.5 + k), (60.0, 63.0, 9.5 + k), (70.0, 63.8, 9.8), (star_tags[1] + Vector((-1.5, -2.5, 5)))],
              star_tags[1], up, r=0.55, s_kind="free", e_kind="tag", lead=2.0)

    # Cable ties on the front loom.
    for x in (36.0, 58.0, 88.0, 110.0):
        W.tie((x, 63.5, 11.8), (1, 0, 0), 2.1)
    W.finish()

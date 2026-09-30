"""Builds the pedal's circuit boards in KiCad and exports each one as GLB for Blender.

Run with KiCad's own Python (it provides the pcbnew module):
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 make_parts.py

Boards are drawn with their top-left corner at KiCad (0, 0), y down. In the GLB that
becomes X = x, Y = -y, with the board's underside at Z = 0 and its top at Z = 1.6 mm.
Component models come from KiCad's bundled 3D library; the parts that library lacks
(TFT panel, EC11 encoder, jacks, footswitches) are modelled in build_scene.py.
"""
import json
import os
import subprocess
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(__file__))
from layout import BOARD_A, BOARD_B, P, DISP  # noqa: E402

KICAD = "/Applications/KiCad/KiCad.app/Contents"
FPDIR = KICAD + "/SharedSupport/footprints"
CLI = KICAD + "/MacOS/kicad-cli"
HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "..", "assets")
OUT = os.path.join(ASSETS, "parts")
KDIR = os.path.join(ASSETS, "kicad")
PI5_STEP = os.path.join(ASSETS, "rpi5", "rpi-5b_with_graphics.step")

meta = {}


def mm(x, y):
    return pcbnew.VECTOR2I_MM(float(x), float(y))


def new_board(w, h, radius=0.0):
    b = pcbnew.BOARD()
    pts = [(0, 0), (w, 0), (w, h), (0, h)]
    if radius <= 0:
        for i in range(4):
            s = pcbnew.PCB_SHAPE(b)
            s.SetShape(pcbnew.SHAPE_T_SEGMENT)
            s.SetStart(mm(*pts[i]))
            s.SetEnd(mm(*pts[(i + 1) % 4]))
            s.SetLayer(pcbnew.Edge_Cuts)
            s.SetWidth(pcbnew.FromMM(0.05))
            b.Add(s)
    else:
        r = radius
        segs = [((r, 0), (w - r, 0)), ((w, r), (w, h - r)), ((w - r, h), (r, h)), ((0, h - r), (0, r))]
        for a, c in segs:
            s = pcbnew.PCB_SHAPE(b)
            s.SetShape(pcbnew.SHAPE_T_SEGMENT)
            s.SetStart(mm(*a))
            s.SetEnd(mm(*c))
            s.SetLayer(pcbnew.Edge_Cuts)
            s.SetWidth(pcbnew.FromMM(0.05))
            b.Add(s)
        for cx, cy, sx, sy in [(r, r, 0, r), (w - r, r, w - r, 0), (w - r, h - r, w, h - r), (r, h - r, r, h)]:
            s = pcbnew.PCB_SHAPE(b)
            s.SetShape(pcbnew.SHAPE_T_ARC)
            s.SetCenter(mm(cx, cy))
            s.SetStart(mm(sx, sy))
            s.SetArcAngleAndEnd(pcbnew.EDA_ANGLE(90, pcbnew.DEGREES_T))
            s.SetLayer(pcbnew.Edge_Cuts)
            s.SetWidth(pcbnew.FromMM(0.05))
            b.Add(s)
    return b


def fp(b, lib, name, x, y, rot=0, back=False, show=None, offset=None, scale=None,
       rotate=None, extra_models=()):
    """Place a library footprint. show(filename) picks which of its 3D models to keep."""
    f = pcbnew.FootprintLoad(f"{FPDIR}/{lib}.pretty", name)
    if f is None:
        raise SystemExit(f"missing footprint {lib}:{name}")
    kept = []
    for m in list(f.Models()):
        if show is not None and not show(m.m_Filename):
            continue
        n = pcbnew.FP_3DMODEL()
        n.m_Filename = m.m_Filename
        n.m_Show = True
        dx, dy, dz = offset or (0, 0, 0)  # added to the library's own offset
        n.m_Offset = pcbnew.VECTOR3D(m.m_Offset.x + dx, m.m_Offset.y + dy, m.m_Offset.z + dz)
        n.m_Scale = pcbnew.VECTOR3D(*(scale or (m.m_Scale.x, m.m_Scale.y, m.m_Scale.z)))
        n.m_Rotation = pcbnew.VECTOR3D(*(rotate or (m.m_Rotation.x, m.m_Rotation.y, m.m_Rotation.z)))
        kept.append(n)
    f.Models().clear()
    for n in kept:
        f.Add3DModel(n)
    for fn, off, sc, rt in extra_models:
        n = pcbnew.FP_3DMODEL()
        n.m_Filename = fn
        n.m_Show = True
        n.m_Offset = pcbnew.VECTOR3D(*off)
        n.m_Scale = pcbnew.VECTOR3D(*sc)
        n.m_Rotation = pcbnew.VECTOR3D(*rt)
        f.Add3DModel(n)
    f.Reference().SetVisible(False)
    f.Value().SetVisible(False)
    b.Add(f)  # before Flip: flipping a footprint that has no board segfaults
    f.SetPosition(mm(x, y))
    if back:
        f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)
    f.SetOrientationDegrees(rot)
    return f


def text(b, s, x, y, size=1.0, rot=0, layer=pcbnew.F_SilkS, bold=True, justify=None):
    t = pcbnew.PCB_TEXT(b)
    t.SetText(s)
    t.SetPosition(mm(x, y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I_MM(size, size))
    t.SetTextThickness(pcbnew.FromMM(size * (0.18 if bold else 0.12)))
    t.SetTextAngleDegrees(rot)
    if justify == "left":
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
    elif justify == "right":
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_RIGHT)
    if layer == pcbnew.B_SilkS:
        t.SetMirrored(True)
    b.Add(t)
    return t


def custom_pad(owner, x, y, size, drill=None, shape="circle", layers=("F.Cu", "B.Cu", "F.Mask", "B.Mask"),
               npth=False):
    pad = pcbnew.PAD(owner)
    if drill is None:
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    else:
        pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH if npth else pcbnew.PAD_ATTRIB_PTH)
        pad.SetDrillSize(mm(drill, drill))
    sh = {"circle": pcbnew.PAD_SHAPE_CIRCLE, "rect": pcbnew.PAD_SHAPE_RECT,
          "oval": pcbnew.PAD_SHAPE_OVAL}[shape]
    pad.SetShape(pcbnew.PADSTACK.ALL_LAYERS, sh)
    sz = size if isinstance(size, tuple) else (size, size)
    pad.SetSize(pcbnew.PADSTACK.ALL_LAYERS, mm(*sz))
    ls = pcbnew.LSET()
    ids = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu, "F.Mask": pcbnew.F_Mask, "B.Mask": pcbnew.B_Mask,
           "F.Paste": pcbnew.F_Paste}
    for l in layers:
        ls.AddLayer(ids[l])
    pad.SetLayerSet(ls)
    pad.SetPosition(mm(x, y))
    owner.Add(pad)
    return pad


def holder(b, ref):
    f = pcbnew.FOOTPRINT(b)
    f.SetReference(ref)
    f.Reference().SetVisible(False)
    f.Value().SetVisible(False)
    b.Add(f)
    return f


STACKUP = """\t\t(stackup
\t\t\t(layer "F.SilkS" (type "Top Silk Screen") (color "{silk}"))
\t\t\t(layer "F.Paste" (type "Top Solder Paste"))
\t\t\t(layer "F.Mask" (type "Top Solder Mask") (color "{mask}") (thickness 0.01))
\t\t\t(layer "F.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "dielectric 1" (type "core") (color "{core}") (thickness 1.51) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
\t\t\t(layer "B.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "B.Mask" (type "Bottom Solder Mask") (color "{mask}") (thickness 0.01))
\t\t\t(layer "B.Paste" (type "Bottom Solder Paste"))
\t\t\t(layer "B.SilkS" (type "Bottom Silk Screen") (color "{silk}"))
\t\t\t(copper_finish "{finish}")
\t\t\t(dielectric_constraints no)
\t\t)
"""


def save_export(b, name, mask="Green", silk="White", finish="ENIG", core="FR4 natural",
                soldermask=True, silkscreen=True, board_body=True, components=True):
    os.makedirs(KDIR, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(KDIR, name + ".kicad_pcb")
    b.Save(path)
    src = open(path).read()
    stack = STACKUP.format(mask=mask, silk=silk, finish=finish, core=core)
    src = src.replace("\t(setup\n", "\t(setup\n" + stack, 1)
    open(path, "w").write(src)
    glb = os.path.join(OUT, name + ".glb")
    cmd = [CLI, "pcb", "export", "glb", "-f", "-o", glb, "--include-pads", "--include-tracks"]
    if soldermask:
        cmd.append("--include-soldermask")
    if silkscreen:
        cmd.append("--include-silkscreen")
    if not board_body:
        cmd.append("--no-board-body")
    if not components:
        cmd.append("--no-components")
    cmd.append(path)
    r = subprocess.run(cmd, capture_output=True, text=True)
    ok = os.path.exists(glb) and "created" in (r.stdout + r.stderr)
    print(f"{name}: {'ok' if ok else 'FAILED'} {os.path.getsize(glb) if ok else ''}")
    if not ok:
        print(r.stdout, r.stderr)
    return glb


# ---- Stripboards -----------------------------------------------------------------------------

def stripboard(bd, cuts=()):
    """Kemo E005: 1.0 mm holes on 2.54 mm, copper strips underneath running along x.
    cuts: (col, row) holes where the strip is cut."""
    W, H = bd["cols"], bd["rows"]
    b = new_board(W * P, H * P)
    grid = holder(b, "GRID")
    cut = set(cuts)
    for r in range(H):
        for c in range(W):
            x, y = P / 2 + c * P, P / 2 + r * P
            if (c, r) in cut:
                custom_pad(grid, x, y, 1.0, drill=1.0, npth=True, layers=("B.Cu",))
            else:
                custom_pad(grid, x, y, (P + 0.02, 2.0), drill=1.0, npth=True, shape="rect", layers=("B.Cu",))
    return b


def g(c, r):
    """KiCad position of stripboard hole (col, row)."""
    return P / 2 + c * P, P / 2 + r * P


class Strip:
    """A stripboard that refuses overlapping parts and records which holes are taken."""

    def __init__(self, bd, cuts=()):
        self.bd = bd
        self.b = stripboard(bd, cuts)
        self.blocked = {}
        self.standoffs = []

    def block(self, holes, label):
        for h in holes:
            if h in self.blocked:
                raise SystemExit(f"{self.bd['name']}: {label} overlaps {self.blocked[h]} at {h}")
            self.blocked[h] = label

    def place(self, label, lib, name, c, r, rot=0, **kw):
        f = fp(self.b, lib, name, *g(c, r), rot=rot, **kw)
        bb = f.GetBoundingBox(False)
        x0, y0 = pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY())
        x1, y1 = x0 + pcbnew.ToMM(bb.GetWidth()), y0 + pcbnew.ToMM(bb.GetHeight())
        holes = set()
        for cc in range(self.bd["cols"]):
            for rr in range(self.bd["rows"]):
                hx, hy = g(cc, rr)
                if x0 + 0.5 < hx < x1 - 0.5 and y0 + 0.5 < hy < y1 - 0.5:
                    holes.add((cc, rr))
        for pad in f.Pads():
            px, py = pcbnew.ToMM(pad.GetPosition().x), pcbnew.ToMM(pad.GetPosition().y)
            holes.add((round((px - P / 2) / P), round((py - P / 2) / P)))
        self.block(holes, label)
        return f

    def R(self, label, c, r, span=4, rot=0):
        name = {4: "R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal",
                3: "R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal"}[span]
        return self.place(label, "Resistor_THT", name, c, r, rot=rot)

    def standoff(self, c, r):
        self.block([(c, r)], "standoff")
        self.standoffs.append((c, r))

    def save(self, name):
        save_export(self.b, name, soldermask=False, silkscreen=False, finish="None")
        meta[name] = dict(self.bd, blocked=sorted(self.blocked), standoffs=self.standoffs)


def board_b():
    """Control board: Pico 2 WH in socket strips, MIDI in, the bypass relay and its driver.
    Row 0 is the rear edge; the Pico's USB end faces the rear."""
    bd = BOARD_B
    cuts = [(c, r) for r in range(bd["rows"]) for c in (11, 12)]      # between the Pico's rows
    cuts += [(c, r) for r in range(0, 3) for c in (4, 5)]             # under the H11L1M
    cuts += [(c, r) for r in range(7, 12) for c in (3, 4)]            # under the relay
    s = Strip(bd, cuts)
    for h in [(1, 0), (1, 19), (12, 0), (12, 19)]:              # col 0 would sit on the lid's lip
        s.standoff(*h)
    # Pico 2 WH (KiCad's Pico WH model, same outline) seated in two 1x20 socket strips.
    s.place("pico_l", "Connector_PinSocket_2.54mm", "PinSocket_1x20_P2.54mm_Vertical", 8, 0)
    s.place("pico_r", "Connector_PinSocket_2.54mm", "PinSocket_1x20_P2.54mm_Vertical", 15, 0)
    fp(s.b, "Module", "RaspberryPi_Pico_Common_THT", *g(8, 0),
       show=lambda f: f.endswith("RaspberryPi_Pico_WH.step"), offset=(0, 0, 8.5))
    s.block([(1, r) for r in range(6, 18)], "ribbon")                  # display leads land here
    # MIDI in: H11L1M in a DIP-6 socket, 220R, 1N4148, 1k pull-up, 100n.
    ic = "${KICAD10_3DMODEL_DIR}/Package_DIP.3dshapes/DIP-6_W7.62mm.step"
    s.place("h11l1", "Package_DIP", "DIP-6_W7.62mm_Socket", 3, 0, extra_models=[(ic, (0, 0, 3.0), (1, 1, 1), (0, 0, 0))])
    s.place("c100n", "Capacitor_THT", "C_Disc_D3.0mm_W1.6mm_P2.50mm", 1, 3)
    s.R("r220", 1, 4, span=3)
    s.place("d4148", "Diode_THT", "D_DO-35_SOD27_P7.62mm_Horizontal", 1, 5)
    s.R("r1k_pu", 4, 6, span=3)
    # Bypass relay (TQ2-5V stand-in: a DIP-10 body, 5 mm tall), BC337, 1k, 100k, flyback diode.
    s.place("relay", "Package_DIP", "DIP-10_W7.62mm", 2, 8, offset=(0, 0, 0.3), scale=(1.12, 1.0, 1.45))
    s.place("d_fly", "Diode_THT", "D_DO-35_SOD27_P7.62mm_Horizontal", 2, 13)
    s.place("bc337", "Package_TO_SOT_THT", "TO-92_Inline_Wide", 3, 15)
    s.R("r1k_b", 2, 17, span=3)
    s.R("r100k", 2, 18, span=3)
    # 1N5817 into VSYS; the LED resistors; the expression filter.
    s.place("d5817", "Diode_THT", "D_DO-41_SOD81_P10.16mm_Horizontal", 2, 19)
    s.R("r_led1", 6, 10, span=3, rot=90)
    s.R("r_led2", 7, 10, span=3, rot=90)
    s.R("r_led3", 6, 14, span=3, rot=90)
    s.R("r_led4", 7, 14, span=3, rot=90)
    s.place("c_exp", "Capacitor_THT", "C_Disc_D3.0mm_W1.6mm_P2.50mm", 6, 17)
    s.save("board_b")


def board_a():
    """Analogue board: OPA2197 buffer on a SOIC adapter, bias, power, output stage, and the
    SparkFun codec board in two 16-way socket strips."""
    bd = BOARD_A
    cuts = [(c, r) for r in range(2, 18) for c in (5, 6)]             # between the codec's rows
    cuts += [(c, r) for r in range(4, 8) for c in (14, 15)]           # under the op-amp
    s = Strip(bd, cuts)
    for h in [(0, 0), (16, 0), (0, 19), (16, 19)]:              # col 17 would sit on the lid's lip
        s.standoff(*h)
    # Codec seat: rows 2..17 in columns 1 and 10 (22.86 mm apart). The board itself hides
    # the holes between.
    s.place("codec_l", "Connector_PinSocket_2.54mm", "PinSocket_1x16_P2.54mm_Vertical", 1, 2)
    s.place("codec_r", "Connector_PinSocket_2.54mm", "PinSocket_1x16_P2.54mm_Vertical", 10, 2)
    s.block([(c, r) for c in range(2, 10) for r in range(2, 18)], "under_codec")
    # Buffer: DIP-8 socket (the SOIC adapter sits in it), input film cap, pad and bias.
    s.place("dip8", "Package_DIP", "DIP-8_W7.62mm_Socket", 13, 4)
    s.place("c_in", "Capacitor_THT", "C_Rect_L7.2mm_W2.5mm_P5.00mm_FKS2_FKP2_MKS2_MKP2", 13, 1)
    s.place("c_dec", "Capacitor_THT", "C_Disc_D3.0mm_W1.6mm_P2.50mm", 12, 8)
    s.R("r680k", 12, 9, span=4)
    s.R("r330k", 12, 10, span=4)
    s.R("r10k_1", 12, 11, span=4)
    s.R("r10k_2", 12, 12, span=4)
    s.R("r10k_3", 12, 13, span=4)
    s.R("r1m_r", 17, 13, span=3, rot=90)
    # Bias 10u between the two output caps; 100R and 1M bleed on each channel.
    s.place("c_outl", "Capacitor_THT", "CP_Radial_D5.0mm_P2.00mm", 11, 15)
    s.place("c_bias", "Capacitor_THT", "CP_Radial_D5.0mm_P2.00mm", 13, 15)
    s.place("c_outr", "Capacitor_THT", "CP_Radial_D5.0mm_P2.00mm", 15, 15)
    s.R("r100_l", 12, 17, span=3)
    s.R("r100_r", 12, 18, span=3)
    s.R("r1m_l", 12, 19, span=3)
    # Power along the rear edge: 1N5817, 100R, 100u; the 78L33 and its 10u caps at the front.
    s.place("d5817", "Diode_THT", "D_DO-41_SOD81_P10.16mm_Horizontal", 2, 0)
    s.R("r100_ps", 2, 1, span=3)
    s.place("c100u", "Capacitor_THT", "CP_Radial_D6.3mm_P2.50mm", 8, 0)
    s.place("u78l33", "Package_TO_SOT_THT", "TO-92_Inline_Wide", 2, 19)
    s.place("c10u_a", "Capacitor_THT", "CP_Radial_D5.0mm_P2.00mm", 6, 19)
    s.place("c10u_b", "Capacitor_THT", "CP_Radial_D5.0mm_P2.00mm", 8, 19)
    s.save("board_a")


def board1():
    """Board 1 as laid out in stripboard/board1.py (the bench build): the 9 V supply, the
    buffer and the output stage. Parts are placed from that file's hole list, so this model
    follows the layout it checks."""
    sys.path.insert(0, os.path.join(HERE, "..", "..", "stripboard"))
    import board1 as B1
    errs = B1.check()
    if errs:
        raise SystemExit("board1 layout: " + "; ".join(errs))
    bd = dict(name="board1", cols=B1.W, rows=B1.H)
    b = stripboard(bd, B1.CUTS)
    models = {
        "r": ("Resistor_THT", "R_Axial_DIN0207_L6.3mm_D2.5mm_P{}_Horizontal"),
        "d": ("Diode_THT", "D_DO-41_SOD81_P{}_Horizontal"),
        "film": ("Capacitor_THT", "C_Rect_L7.2mm_W2.5mm_P5.00mm_FKS2_FKP2_MKS2_MKP2"),
        "cer": ("Capacitor_THT", "C_Disc_D3.0mm_W1.6mm_P2.50mm"),
        "el6.3": ("Capacitor_THT", "CP_Radial_D6.3mm_P2.50mm"),
        "el5": ("Capacitor_THT", "CP_Radial_D5.0mm_P2.50mm"),
        "bipolar": ("Capacitor_THT", "C_Radial_D6.3mm_H11.0mm_P2.50mm"),
        "dip8": ("Package_DIP", "DIP-8_W7.62mm_Socket"),
    }
    pitch = {4: "10.16mm", 5: "12.70mm"}
    for ref, (kind, val, leads) in B1.PARTS.items():
        holes = [h for h, _ in leads]
        if kind == "d":
            holes = holes[::-1]                    # KiCad's pad 1 is the cathode
        if "bipolar" in val:
            kind = "bipolar"
        lib, name = models[kind]
        if "{}" in name:
            (x1, y1), (x2, y2) = holes[:2]
            name = name.format(pitch[abs(x2 - x1) + abs(y2 - y1)])
        # Pad 1 sits on the footprint's origin: put it on the first hole, then turn the part
        # until pad 2 (or, for the socket, pin 8) lands on its hole.
        target = holes[-1] if kind == "dip8" else holes[1]
        f = fp(b, lib, name, *g(*holes[0]))
        want = g(*target)
        for rot in (0, 90, 180, 270):
            f.SetOrientationDegrees(rot)
            pad = next(p for p in f.Pads() if p.GetNumber() == ("8" if kind == "dip8" else "2"))
            px, py = pcbnew.ToMM(pad.GetPosition().x), pcbnew.ToMM(pad.GetPosition().y)
            if abs(px - want[0]) < 0.6 and abs(py - want[1]) < 0.6:
                break
        else:
            raise SystemExit(f"board1: {ref} ({name}) doesn't fit holes {holes}")
    save_export(b, "board1", soldermask=False, silkscreen=False, finish="None")
    meta["board1"] = dict(bd, links=B1.LINKS, pads={k: v[0] for k, v in B1.PADS.items()})


# ---- SparkFun WM8960 breakout -------------------------------------------------------------

CODEC_W, CODEC_H = 25.4, 40.64
CODEC_LEFT = ["GND", "BCLK", "DLRC", "DDAT", "ALRC", "ADAT", "SCL", "SDA", "3V3", "GND", "GND",
              "SPKVDD", "VIN", "EN", "GND", "GND"]
CODEC_RIGHT = ["GND", "RIN3", "RIN2", "RIN1", "LIN1", "LIN2", "LIN3", "MICB", "HPL", "OUT3", "HPR",
               "AVDD", "SL+", "SL-", "SR+", "SR-"]


def codec():
    b = new_board(CODEC_W, CODEC_H, radius=0.6)
    pads = holder(b, "J")
    for i in range(16):
        y = 1.27 + i * P
        custom_pad(pads, 1.27, y, 1.8, drill=1.0)
        custom_pad(pads, CODEC_W - 1.27, y, 1.8, drill=1.0)
        text(b, CODEC_LEFT[i], 2.6, y, size=1.05, justify="left")
        text(b, CODEC_RIGHT[i], CODEC_W - 2.6, y, size=1.05, justify="right")
    # Male headers soldered underneath, pins down into the sockets on board A. Flipping
    # mirrors a footprint in y, so each strip is anchored at its last pad.
    fp(b, "Connector_PinHeader_2.54mm", "PinHeader_1x16_P2.54mm_Vertical", 1.27, 1.27 + 15 * P, back=True)
    fp(b, "Connector_PinHeader_2.54mm", "PinHeader_1x16_P2.54mm_Vertical", CODEC_W - 1.27, 1.27 + 15 * P,
       back=True)
    text(b, "Audio", 12.4, 2.4, size=1.25)
    text(b, "Codec", 12.4, 4.0, size=1.25)
    text(b, "WM8960", 12.4, 5.6, size=1.25)
    fp(b, "Package_DFN_QFN", "QFN-32-1EP_5x5mm_P0.5mm_EP3.45x3.45mm", 12.4, 19.0, rot=0)
    fp(b, "Oscillator", "Oscillator_SMD_Abracon_ASE-4Pin_3.2x2.5mm", 6.1, 17.4)
    # The input network: caps, resistors, caps, six of each, in three rows.
    for i in range(6):
        x = 8.8 + i * 1.6
        fp(b, "Capacitor_SMD", "C_0603_1608Metric", x, 8.6, rot=90)
        fp(b, "Resistor_SMD", "R_0603_1608Metric", x, 10.7, rot=90)
        fp(b, "Capacitor_SMD", "C_0603_1608Metric", x + 0.4, 12.8, rot=90)
    for i in range(5):  # ferrites on the speaker lines
        fp(b, "Resistor_SMD", "R_1206_3216Metric", 11.4 + i * 1.9, 26.4, rot=90)
    for (x, y, r) in [(9.9, 15.2, 45), (15.6, 15.9, 0), (18.2, 16.6, 0), (17.7, 21.4, 0), (5.3, 14.8, 0),
                      (7.8, 19.3, 90), (9.2, 20.6, 45), (15.0, 29.8, 0), (13.0, 29.8, 0), (17.3, 29.8, 0),
                      (19.6, 30.6, 0), (7.4, 34.7, 0), (13.6, 34.7, 90), (15.4, 34.7, 90), (7.4, 37.0, 0)]:
        fp(b, "Capacitor_SMD", "C_0603_1608Metric", x, y, rot=r)
    fp(b, "Capacitor_SMD", "C_1206_3216Metric", 18.6, 23.4, rot=0)
    for i in range(5):
        fp(b, "Resistor_SMD", "R_0603_1608Metric", 7.2, 22.5 + i * 1.05, rot=0)
    fp(b, "Package_TO_SOT_SMD", "SOT-23-5", 11.2, 35.0, rot=90)
    fp(b, "Connector_JST", "JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal", 12.4, 40.0, rot=180)
    fp(b, "LED_SMD", "LED_0603_1608Metric", 16.6, 38.6, rot=90)
    text(b, "qwiic", 8.2, 38.2, size=0.9, rot=90, bold=False)
    text(b, "PWR", 18.4, 38.4, size=0.8, rot=90)
    save_export(b, "codec", mask="#C8102EFF", finish="ENIG")
    meta["codec"] = dict(w=CODEC_W, h=CODEC_H)


# ---- Display module (2.4" ST7789 + EC11 + tact switch, board V1.2) -----------------------------

DISP_PINS = ["GND", "VCC", "SCL", "SDA", "RES", "DC", "CS", "BLK", "A", "B", "PUSH", "K0"]


def display():
    w, h = DISP["w"], DISP["h"]
    b = new_board(w, h, radius=1.0)
    for (x, y) in DISP["holes"]:
        fp(b, "MountingHole", "MountingHole_3.2mm_M3_Pad", x, y)
    pads = holder(b, "J1")
    for i in range(12):
        y = DISP["pads_y0"] + i * P
        custom_pad(pads, DISP["pads_x"], y, 1.7, drill=1.0, shape="rect" if i == 0 else "circle")
        text(b, DISP_PINS[i], DISP["pads_x"] + 1.9, y, size=0.75, rot=90, bold=False)
    # Passives in a column between the glass and the controls, as on the real board.
    parts = [("C", 1.6), ("R", 3.2), ("R", 4.7), ("C", 6.4), ("R", 13.6), ("C", 15.0), ("R", 16.5),
             ("C", 18.0), ("R", 21.6), ("R", 23.1), ("R", 24.6), ("R", 27.3), ("C", 34.9), ("R", 36.4),
             ("C", 38.2), ("R", 39.8)]
    for kind, y in parts:
        lib, name = ("Capacitor_SMD", "C_0603_1608Metric") if kind == "C" else ("Resistor_SMD", "R_0603_1608Metric")
        fp(b, lib, name, 69.3, y, rot=0)
        text(b, kind + str(int(y) % 9 + 1), 71.6, y, size=0.7, bold=False, justify="left")
    fp(b, "Package_TO_SOT_SMD", "SOT-23", 69.8, 31.5, rot=90)
    # EC11 footprint pads (the encoder body is modelled in Blender) and the 12 mm tact switch.
    ex, ey = DISP["enc"]
    enc = holder(b, "SW1")
    for dy in (-2.5, 0, 2.5):
        custom_pad(enc, ex - 7.5, ey + dy, 1.6, drill=1.0)
    custom_pad(enc, ex, ey - 5.6, (2.4, 1.6), drill=1.0, shape="oval")
    custom_pad(enc, ex, ey + 5.6, (2.4, 1.6), drill=1.0, shape="oval")
    bx, by = DISP["btn"]
    fp(b, "Button_Switch_THT", "SW_PUSH-12mm_Wuerth-430476085716", bx - 6.25, by - 2.5)
    # Glass outline pads for the TFT's FPC (the panel itself is modelled in Blender).
    fpc = holder(b, "LCD")
    for i in range(14):
        custom_pad(fpc, 64.8, 9.8 + i * 1.0, (1.6, 0.5), shape="rect", layers=("F.Cu", "F.Mask"))
    text(b, "V1.2", 80.0, 41.4, size=0.8, bold=False, layer=pcbnew.F_SilkS)
    # The back carries the module's spec block, as on the real board.
    for i, s in enumerate(["2.4 TFT + EC11", "2.4 TFT :320*240 RGB", "TFT Drive IC : ST7789",
                           "TFT Interface : 4 - SPI", "EC11 interface : A, B ,PUSH", "START KEY : K0",
                           "VCC: 3.3V/5V"]):
        text(b, s, 45.0, 15.0 + i * 2.6, size=1.0, layer=pcbnew.B_SilkS, bold=False, justify="right")
    save_export(b, "display", mask="#1D5BB8FF", finish="HAL SnPb")
    meta["display"] = dict(w=w, h=h)


def soic_adapter():
    """Aries LCQT-SOIC8-8: OPA2197 on a small board with DIP-8 pins underneath."""
    w, h = 10.2, 10.6
    b = new_board(w, h, radius=0.4)
    x0, y0 = (w - 7.62) / 2, (h - 7.62) / 2
    fp(b, "Package_SO", "SOIC-8_3.9x4.9mm_P1.27mm", w / 2, h / 2, rot=90)
    for col in (0, 1):
        fp(b, "Connector_PinHeader_2.54mm", "PinHeader_1x04_P2.54mm_Vertical", x0 + col * 7.62, y0 + 3 * P,
           back=True)
    text(b, "OPA2197", w / 2, 1.2, size=0.7, bold=False)
    save_export(b, "soic_adapter", mask="#0F3F2AFF", finish="ENIG")
    meta["soic_adapter"] = dict(w=w, h=h, pin1=(x0, y0))


def pi5():
    """Wraps Raspberry Pi's official STEP so KiCad converts it to GLB."""
    glb = os.path.join(OUT, "rpi5.glb")
    if os.path.exists(glb):
        print("rpi5: exists")
        return
    b = new_board(200, 200)
    f = pcbnew.FOOTPRINT(b)
    m = pcbnew.FP_3DMODEL()
    m.m_Filename = PI5_STEP
    m.m_Show = True
    f.Add3DModel(m)
    f.SetPosition(mm(0, 0))
    b.Add(f)
    save_export(b, "rpi5", soldermask=False, silkscreen=False, board_body=False)


if __name__ == "__main__":
    which = sys.argv[1:] or ["board_b", "board_a", "codec", "display", "soic_adapter", "pi5"]
    for name in which:
        globals()[name]()
    mpath = os.path.join(OUT, "parts.json")
    old = json.load(open(mpath)) if os.path.exists(mpath) else {}
    old.update(meta)
    json.dump(old, open(mpath, "w"), indent=1)

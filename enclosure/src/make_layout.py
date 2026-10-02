"""Builds one editable 2D layout board for playing with the pedal's physical arrangement.

The output is `enclosure/layout.kicad_pcb`: the whole inside of the box seen from above, at
1:1 in millimetres, as footprints you can drag around in KiCad's PCB editor. It is a layout
sandbox, not a schematic and not something to fabricate: there are no nets and no tracks.
Panel parts sit at their panel position; rear-wall parts sit on the rear edge line, because
in a 2D view a wall connector is a position along a wall plus a height (z), and the height is
not on this drawing.

It lives outside `assets/` on purpose: `assets/` is generated and gitignored, and this file is
meant to be opened, edited and committed. The script will not overwrite a layout that KiCad has
saved unless it is run with --force (see the guard at the bottom).

Run with KiCad's own Python (it provides the pcbnew module):
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 \
      enclosure/src/make_layout.py

Coordinates. `layout.py` is in enclosure coordinates: origin at the outside bottom-left-front
corner, x left to right, y from the player's edge (front) to the jack edge (rear). This drawing
keeps x as-is and turns y round (`119 - y`), so a point's distance from the top of the drawing is
its distance from the rear wall. The board outline is the enclosure's *outside* 188 x 119 mm, so
noting where things fall inside it is enough to see what a change would cost. Enclosure z is
dropped, which is the one thing a 2D drawing cannot carry.

There are no "rear" and "front" captions in the drawing: they ended up competing with the very
parts that already say which way round it is, and the notes belong in the README instead.
"""
import math
import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout as L  # noqa: E402

KICAD = "/Applications/KiCad/KiCad.app/Contents"
FPDIR = KICAD + "/SharedSupport/footprints"
HERE = os.path.dirname(os.path.abspath(__file__))
KDIR = os.path.normpath(os.path.join(HERE, "..", "assets", "kicad"))
OUT = os.path.normpath(os.path.join(HERE, "..", "layout.kicad_pcb"))

D = L.ENC["D"]              # 119.0
W = L.ENC["W"]              # 188.0

# Which source board each module came from, and where that board is drawn in layout.py.
# (x0, y0) is the board's rear-left corner in enclosure coordinates; the generator finds the
# board's own footprint-frame origin from its outline, so only the placement is given here.
BOARDS = (
    ("board_b", L.BOARD_B, "BOARD_B", "B  Pico, MIDI in, bypass relay"),
    ("board_a", L.BOARD_A, "BOARD_A", "A  buffer, power, output stage"),
)
# Modules that sit on board A, with the hole they are seated on (see bl_pedal.py).
ON_BOARD_A = (
    ("codec", "CODEC", (1, 2), (-1.27, 1.27), "SparkFun WM8960 breakout on socket strips"),
    ("soic_adapter", "SOIC_ADAPTER", (13, 4), (-1.29, 1.49), "OPA2197 SOIC adapter in DIP-8"),
)

# The references worth showing: a module, its fixings, and the handful of source footprints
# that carry a real name (J is the codec's lead connector, J1 the display's). Everything else
# the source boards left as REF** and is hidden.
NAMED = {"J", "J1", "LCD", "SW1", "GRID"}


def mm(x, y):
    return pcbnew.VECTOR2I_MM(float(x), float(y))


def canvas(xe, ye):
    """Enclosure (x, y) to this drawing's (x, y)."""
    return xe, D - ye


def rot(deg):
    """An enclosure-frame angle as a KiCad footprint angle.

    This drawing's x runs the same way as layout.py's and its y runs the same way round
    relative to the view, so angles carry over unchanged."""
    return deg


# ---- primitives, following make_parts.py -------------------------------------------------

def custom_pad(owner, x, y, size, drill=None, shape="circle",
               layers=("F.Cu", "B.Cu", "F.Mask", "B.Mask"), npth=False):
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
    ids = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu, "F.Mask": pcbnew.F_Mask,
           "B.Mask": pcbnew.B_Mask, "F.Paste": pcbnew.F_Paste, "Dwgs.User": pcbnew.Dwgs_User,
           "Edge.Cuts": pcbnew.Edge_Cuts, "User.1": pcbnew.User_1}
    for l in layers:
        ls.AddLayer(ids[l])
    pad.SetLayerSet(ls)
    pad.SetPosition(mm(x, y))
    owner.Add(pad)
    return pad


def holder(b, ref, name=None):
    f = pcbnew.FOOTPRINT(b)
    f.SetReference(ref)
    f.Reference().SetVisible(True)
    f.Value().SetText(name or ref)
    f.Value().SetVisible(False)
    b.Add(f)
    return f


def locate(f, x, y, rot_deg=0.0, back=False):
    if back:
        f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)
    f.SetOrientationDegrees(rot_deg)
    f.SetPosition(mm(x, y))
    return f


def fp(b, lib, name, xe, ye, rot_deg=0.0, ref=None, value=None, back=False):
    """A footprint from KiCad's library, placed at an enclosure position."""
    x, y = canvas(xe, ye)
    f = pcbnew.FootprintLoad(os.path.join(FPDIR, lib + ".pretty"), name)
    if f is None:
        raise SystemExit(f"no footprint {lib}:{name}")
    b.Add(f)
    locate(f, x, y, rot(rot_deg), back)
    if ref:
        f.SetReference(ref)
    if value:
        f.SetValue(value)
    f.Reference().SetVisible(True)
    f.Value().SetVisible(False)
    return f


def rect(owner, x, y, w, h, layer=pcbnew.Dwgs_User, width=0.15):
    """A closed rectangle of four lines, in drawing coordinates."""
    pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    for i in range(4):
        s = pcbnew.PCB_SHAPE(owner)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(mm(*pts[i]))
        s.SetEnd(mm(*pts[(i + 1) % 4]))
        s.SetLayer(layer)
        s.SetWidth(pcbnew.FromMM(width))
        owner.Add(s)


def label(b, s, x, y, size=1.6, layer=pcbnew.F_SilkS, rot_deg=0.0, justify="left"):
    """An annotation. Left-justified by default: KiCad centres text on its position, which
    makes a long note at the board's edge run off the drawing."""
    t = pcbnew.PCB_TEXT(b)
    t.SetText(s)
    t.SetPosition(mm(x, y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I_MM(size, size))
    t.SetTextThickness(pcbnew.FromMM(size * 0.16))
    t.SetTextAngleDegrees(rot_deg)
    if justify == "left":
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
    elif justify == "right":
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_RIGHT)
    if layer == pcbnew.B_SilkS:
        t.SetMirrored(True)
    b.Add(t)
    return t


# ---- panel hardware ----------------------------------------------------------------------
# A panel toggle, a DIN-5 socket and a panel USB-C socket are panel parts, not board parts,
# so KiCad's libraries have no footprint for them. These are the smallest footprints that
# still show the right pins and the right body: enough to place and to measure, no more.

def panel_footprint(master, ref, value, xe, ye, pads, body, rot_deg=0.0):
    """pads: (x, y, drill, dia) in enclosure mm; `body`: a (w, h) outline around the position."""
    cx, cy = canvas(xe, ye)
    f = holder(master, ref, value)
    locate(f, cx, cy, rot(rot_deg))
    for px, py, drill, dia in pads:
        dx, dy = canvas(px, py)
        custom_pad(f, dx, dy, dia, drill=drill)
    w, h = body
    pts = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    for i in range(4):
        s = pcbnew.PCB_SHAPE(f)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(mm(cx + pts[i][0], cy + pts[i][1]))
        s.SetEnd(mm(cx + pts[(i + 1) % 4][0], cy + pts[(i + 1) % 4][1]))
        s.SetLayer(pcbnew.F_SilkS)
        s.SetWidth(pcbnew.FromMM(0.2))
        f.Add(s)
    return f


def spdt_toggle(master, xe, ye, ref="SW_INSTLINE"):
    """The Inst / Line panel toggle: three lugs in a row on 2.54 mm, bushing above them."""
    pads = [(xe - 2.54, ye, 1.0, 1.8), (xe, ye, 1.0, 1.8), (xe + 2.54, ye, 1.0, 1.8)]
    return panel_footprint(master, ref, "SPDT on-on, panel", xe, ye, pads, (10.0, 13.0))


def din5(master, xe, ye, ref="J_MIDI"):
    """MIDI in: a 5-pin 180-degree DIN socket. Pins on a 3 mm arc, 60 degrees apart."""
    order = (210.0, 270.0, 330.0, 150.0, 30.0)      # DIN pins 1, 4, 2, 5, 3
    pads = [(xe + 3.0 * math.cos(math.radians(a)), ye + 3.0 * math.sin(math.radians(a)), 1.2, 2.0)
            for a in order]
    return panel_footprint(master, ref, "MIDI in, DIN-5", xe, ye, pads, (15.0, 15.0))


def usbc_panel(master, xe, ye, ref="J_USB5V"):
    """The 5 V input: a panel USB-C extension, flange and its four fixing holes."""
    pads = [(xe + dx, ye + dy, 2.2, 4.0) for dx in (-5.0, 5.0) for dy in (-3.2, 3.2)]
    return panel_footprint(master, ref, "USB-C 5 V, panel extension", xe, ye, pads, (16.0, 10.0))


# ---- the boards themselves ---------------------------------------------------------------

def board_outline(b):
    """The board's own outline bounding box, in footprint-frame millimetres."""
    bb = b.GetBoardEdgesBoundingBox()
    return (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
            pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight()))


def place_board(master, name, ox, oy, ref, note, keep=()):
    """Copy one generated board into the drawing, keeping the generated arrangement.

    A generated board is drawn top-left at (0, 0) with y down. layout.py's (ox, oy) is where
    that top-left corner goes in enclosure coordinates (its rear-left corner). This drawing
    turns the enclosure's y round, so a board-local point (fx, fy) lands at
    (ox + fx, (D - oy) + fy): no flip, and no change to the footprints' angles. Verified
    against board B's recorded standoff holes and board A's DIP-8 socket, both of which
    bl_pedal places through layout.hole().

    The board's outline is not copied: the parts and the stripboard's holes carry the
    arrangement. `keep` names source footprints to leave out."""
    path = os.path.join(KDIR, name + ".kicad_pcb")
    if not os.path.exists(path):
        raise SystemExit(f"{path} is missing: run enclosure/src/build first")
    src = pcbnew.LoadBoard(path)
    left, top, w, h = board_outline(src)
    named = False
    for f in list(src.GetFootprints()):
        fx, fy = pcbnew.ToMM(f.GetPosition().x), pcbnew.ToMM(f.GetPosition().y)
        if f.GetReference() in keep:
            continue
        cx = ox + (fx - left)
        cy = (D - oy) + (fy - top)
        f.SetParent(master)
        master.Add(f)
        f.SetPosition(mm(cx, cy))
        # The source boards leave every reference as REF** (they are only ever rendered), so
        # those texts are noise here. Hide them all, and name one holder per module so the
        # parts panel reads BOARD_A rather than a row of REF**.
        if f.GetReference().startswith("REF"):
            if not named:
                f.SetReference(ref)
                f.SetValue(note)
                f.Reference().SetPosition(mm(cx + 3.0, cy + 4.0))
                named = True
            else:
                f.Reference().SetVisible(False)
        elif f.GetReference() not in NAMED:
            f.Reference().SetVisible(False)
    module = not ref.startswith("BOARD_")
    label(master, note,
          *canvas(ox + 3.0, oy + (3.0 if module else 4.0)),
          size=1.2 if module else 1.4,
          layer=pcbnew.Dwgs_User if module else pcbnew.F_SilkS)
    return w, h


def standoffs(master, name, holes, ref):
    """The stripboard's fixing holes, as one footprint you can see and move."""
    f = holder(master, ref, "M3 standoffs")
    left, top, _w, _h = board_outline(pcbnew.LoadBoard(os.path.join(KDIR, name + ".kicad_pcb")))
    ox, oy = BOARDS_X0[name]
    for c, r in holes:
        cx = ox + (L.P / 2 + c * L.P) - left
        cy = (D - oy) + (L.P / 2 + r * L.P) - top
        custom_pad(f, cx, cy, 3.2, drill=3.2, npth=True, layers=())
    return f


BOARDS_X0 = {}


def main():
    master = pcbnew.BOARD()

    # The box, on Edge.Cuts, so the editor shows the working area. Outside dimensions.
    rect(master, 0.0, 0.0, W, D, layer=pcbnew.Edge_Cuts, width=0.15)
    # Lid-screw bosses and the lid lip, as a guide: 3 mm FR4 plate and clearance live inside.
    for sx in (-1, 1):
        for sy in (-1, 1):
            cx = W / 2 + sx * L.ENC["screw_dx"] / 2
            cy = D / 2 + sy * L.ENC["screw_dy"] / 2
            c = pcbnew.PCB_SHAPE(master)
            c.SetShape(pcbnew.SHAPE_T_CIRCLE)
            c.SetCenter(mm(cx, cy))
            c.SetEnd(mm(cx + L.ENC["boss_d"] / 2, cy))
            c.SetLayer(pcbnew.Dwgs_User)
            c.SetWidth(pcbnew.FromMM(0.15))
            master.Add(c)

    # No "REAR"/"FRONT" captions: the rear-wall parts, the footswitches and the display
    # already say which way round this is, and a note competing with them just adds clutter.

    # ---- stripboards and what sits on them ----
    for name, bd, ref, note in BOARDS:
        ox, oy = bd["x0"], bd["y0"] + bd["rows"] * L.P
        BOARDS_X0[name] = (ox, oy)
        place_board(master, name, ox, oy, ref, note)
        standoffs(master, name, [tuple(s) for s in LAYOUT_STANDOFFS[name]], ref + "_FIX")

    # Modules seated on board A.
    for name, ref, (c, r), (dx, dy), note in ON_BOARD_A:
        hx, hy = L.hole(L.BOARD_A, c, r)
        place_board(master, name, hx + dx, hy + dy, ref, note)

    # ---- the display module and its controls ----
    place_board(master, "display", L.DISP_X0, L.DISP_YTOP, "DISPLAY",
                "ST7789 + EC11, 90 x 43.2 mm, no onboard LDO: run it at 3.3 V")

    # ---- top panel: what pokes through the top face ----
    for i, x in enumerate(L.FS_X):
        fp(master, "Button_Switch_THT", "SW_PUSH_6mm", x, L.FS_Y, 90.0,
           ref=f"FS_{'ABC'[i]}", value="Footswitch")
    for i, (x, y) in enumerate([(x, L.LED_Y) for x in L.FS_X] + [L.LED_READY]):
        fp(master, "LED_THT", "LED_D5.0mm", x, y, 0.0, ref=f"LED_{i + 1}", value="LED 5 mm")
    spdt_toggle(master, *L.TOGGLE)
    lab = pcbnew.PCB_SHAPE(master)   # the display window, as a guide on the top face
    lab.SetShape(pcbnew.SHAPE_T_RECT)
    lab.SetStart(mm(*canvas(L.WINDOW_C[0] - L.WINDOW[0] / 2, L.WINDOW_C[1] + L.WINDOW[1] / 2)))
    lab.SetEnd(mm(*canvas(L.WINDOW_C[0] + L.WINDOW[0] / 2, L.WINDOW_C[1] - L.WINDOW[1] / 2)))
    lab.SetLayer(pcbnew.Dwgs_User)
    lab.SetWidth(pcbnew.FromMM(0.2))
    master.Add(lab)
    label(master, "WINDOW", *canvas(L.WINDOW_C[0], L.WINDOW_C[1]), size=2.0, layer=pcbnew.Dwgs_User)
    label(master, f"STRIPE from y {L.STRIPE_Y[0]:.0f} to {L.STRIPE_Y[1]:.0f}",
          *canvas(W / 2, 60.0), size=1.6, layer=pcbnew.Dwgs_User)

    # ---- rear wall: position along the wall, on the rear edge line ----
    # In a 2D view a wall connector is a position along a wall plus a height; the height (z 16
    # for all of these) is not on this drawing. They are drawn on the rear edge, facing out.
    for name, (_wall, s, _z) in L.JACKS.items():
        fp(master, "Connector_Audio", "Jack_6.35mm_Neutrik_NMJ6HCD2_Horizontal",
           s, D - 1.0, 180.0, ref=f"J_{name}", value="6.35 mm jack")
    fp(master, "Connector_BarrelJack", "BarrelJack_CLIFF_FC681465S_SMT_Horizontal",
       L.DC9V[0], D - 1.0, 180.0, ref="J_9V", value="9 V DC, switched")
    usbc_panel(master, *L.USBC)
    din5(master, *L.MIDI)

    # ---- the Pi ----
    pi = holder(master, "PI5", "Raspberry Pi 5")
    ox, oy = L.PI5_ORIGIN
    # Dwgs.User, not User.1: this board's layer table enables User.1..User.4, but only the
    # layers actually plotted appear in the export, and User.1 does not. Dwgs.User does, and
    # is what the rest of the guides use.
    rect(pi, *canvas(ox, oy + 56.0), 85.0, 56.0, layer=pcbnew.Dwgs_User, width=0.2)

    # Names on the canvas. The modules that came from the source boards are mechanical holders
    # whose reference field the source boards left hidden, so a module could otherwise only be
    # found in KiCad's parts list and never by looking at the drawing. Showing each holder's own
    # reference is the same mechanism KiCad-created parts use ("J_USB5V" and friends), and the
    # text belongs to the footprint, so it travels with the part when it is dragged.
    #
    # Positions are canvas coordinates, so a board's y in layout.py is NOT its y here: a point
    # at layout.py y has canvas y = 119 - y. Board A and board B run from canvas y 26 to 77,
    # the Pi from 5 to 61, and the display from 68.5 to 112.
    names = {
        "PI5": ((ox + 40.0, oy + 28.0), 2.6),                       # the middle of the Pi
        "BOARD_B": ((L.BOARD_B["x0"] + 9.0, 36.0), 2.0),
        "BOARD_A": ((L.BOARD_A["x0"] + 2.5, 58.0), 2.0),
        "CODEC": ((L.BOARD_A["x0"] + 3.0, 40.0), 1.8),
        "SOIC_ADAPTER": ((L.BOARD_A["x0"] + 22.0, 40.0), 1.8),
        "DISPLAY": ((L.DISP_X0 + 30.0, 116.0), 2.0),
    }
    for f in master.GetFootprints():
        if f.GetReference() in names:
            (nx, ny), size = names[f.GetReference()]
            r = f.Reference()
            r.SetVisible(True)
            r.SetTextSize(pcbnew.VECTOR2I_MM(size, size))
            r.SetPosition(mm(nx, ny))       # pcbnew converts this to the footprint's frame
    label(master, "PI 5 85 x 56, HDMI edge to the front", *canvas(ox + 14.0, oy + 60.0),
          size=1.4, layer=pcbnew.Dwgs_User)

    # ---- annotate and write ----
    master.BuildListOfNets()
    pcbnew.SaveBoard(OUT, master)
    # SaveBoard writes its own generator, so stamp the marker the guard looks for into the
    # text instead (make_parts.py patches the file this way for the stackup).
    text = open(OUT, encoding="utf-8").read()
    text = text.replace('\t(generator "pcbnew")\n\t(generator_version "10.0")',
                        '\t(generator "make_layout")\n\t(generator_version "0.1")', 1)
    open(OUT, "w", encoding="utf-8").write(text)
    names = sorted({f.GetReference() for f in master.GetFootprints()})
    print(f"wrote {OUT}")
    print(f"  {len(master.GetFootprints())} footprints; named: {', '.join(names)}")


LAYOUT_STANDOFFS = {}


if __name__ == "__main__":
    import json
    # This file is meant to be edited by hand in KiCad. Refuse to overwrite a layout that has
    # been saved by the editor since it was generated, unless asked to: `--force` regenerates.
    force = "--force" in sys.argv[1:]
    if os.path.exists(OUT) and not force:
        stamp = open(OUT, encoding="utf-8", errors="replace").read(4000)
        if '(generator "make_layout")' not in stamp:
            raise SystemExit(
                f"{OUT} was saved by KiCad, not by this script. Refusing to overwrite it.\n"
                f"  Move it aside, or run with --force to regenerate from layout.py.")
    meta = json.load(open(os.path.join(HERE, "..", "assets", "parts", "parts.json")))
    LAYOUT_STANDOFFS = {k: meta[k]["standoffs"] for k in ("board_a", "board_b")}
    main()

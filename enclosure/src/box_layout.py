#!/usr/bin/env python3
"""The box (docs/box-design.md) as boxes: every part an axis-aligned block, checked.

Each part is a block in the case's frame, in mm: x from the left inside wall, y from the
rear inside wall toward the player, z up from the base plate.  The script checks that no
two blocks share space unless the pair is listed as meant to (a socket on its board), prints
the smallest clearances, and draws a plan and a section.

    python3 enclosure/src/box_layout.py            # check every case, write the SVG
    python3 enclosure/src/box_layout.py hammond    # one case, and draw that one
    python3 enclosure/src/box_layout.py --holes hammond tayda    # the hole table
    python3 enclosure/src/box_layout.py --tayda                  # the same, as Tayda's Box Tool takes it
    rsvg-convert -w 1700 docs/diagrams/box-layout.svg -o docs/diagrams/box-layout.png

"1590DD" is not one case.  Hammond's and Tayda's differ in depth, wall, width and pillars, so
the layout is checked in each maker's drawing (CASES) and at the owner's measured depth.
It exits non-zero if anything collides in any of them.  Numbers marked "est." are estimates to be replaced
from the maker's drawing when the part is chosen; the rest are from the drawings named beside
them or from the owner's measurements of 2026-11-14.  No third-party Python is needed.
"""

from __future__ import annotations

import os
import sys

# Inside sizes at the face (the tub's floor, the narrow end of the draft), in mm.
#   tayda:   drawing A-5141 "1590DD", 2024-06-06: inside height 30.5, floor 2.5, wall 2.2.
#            Length and width are its outside sizes at the floor (182.9, 113.9) less two walls.
#            Four screws, in the corners; the bosses reach 3.75 mm in (171 and 102 between them).
#   hammond: drawing 1590DD: inside 179.26 x 112.26 x 32.00, wall and floor 2.50.  Six screws
#            on 178 x 110 (and the middle of the long sides); the bosses' reach is est. from
#            the 101.07 between the middle pair.
#   hammond-30: Hammond's, which the owner's case is, at the 30 mm he measured inside it
#            (the drawing says 32.00): the shallowest the design has to fit.
CASES = {
    "tayda": dict(W=178.5, D=109.5, H=30.5, wall=2.2, mid=False, half=0.0, reach=(4.0, 4.0),
                  source="Tayda drawing A-5141"),
    "hammond": dict(W=179.26, D=112.26, H=32.0, wall=2.5, mid=True, half=5.5, reach=(6.5, 7.0),
                    source="Hammond drawing 1590DD"),
    "hammond-30": dict(W=179.26, D=112.26, H=30.0, wall=2.5, mid=True, half=5.5,
                       reach=(6.5, 7.0), source="Hammond drawing 1590DD, 30 mm deep"),
}
DEFAULT = "tayda"                  # the shallowest drawing, and the case Tayda's service drills
NEUTRIK_MAX_PANEL = 3.0            # NCJ6FA-H, drawing 20004521
JACKS = (("out socket", 125.0), ("EXT FS socket", 143.7), ("guitar in socket", 162.4))
USBC_X, MIDI_X, MIC_Y = 40.0, 76.0, 47.0
ENCODER, BUTTONS = (131.1, 30.0), ((125.0, 55.0), (141.0, 55.0))
LAMPS = ((125.0, 64.0), (141.0, 64.0))    # one in front of each button (the owner, 2026-11-16)
# The fan (the owner, 2026-11-16: assume one is needed; 2026-11-17: one only, in the floor
# between footswitches 1 and 2, drawing in through a thin dust filter, with vents only in the
# rear wall).  30 x 30 x 10 mm, 5 V, two wires (Sunon's MF30100V2-1000U-A99 is the kind), lying
# on the base plate on a 1 mm filter, held by two screws through the base plate.  It sits in
# front of the Pi board and under the footswitches, whose bodies end 14.5 mm above the base.
# The air leaves through the rear wall, at the gap between the Pi and the Pi board.
FAN, FILTER = (30.0, 10.0), 1.0
FAN_Y0 = 74.5                      # the fan's rear edge: 2.5 mm in front of the Pi board
FAN_VENTS = [(10.5 * c, 10.5 * s) for c, s in
             ((1, 0), (.5, .866), (-.5, .866), (-1, 0), (-.5, -.866), (.5, -.866))]   # six of 8 mm
FAN_SCREWS = ((12.0, 12.0), (-12.0, -12.0))          # two of the fan's four holes, 24 mm apart
# Air out: two 9 mm holes between the USB-C and MIDI sockets, in the height of the gap between
# the Pi and the Pi board.  (x, mm above the Pi board's top).  Round, so a coin cannot get in.
EXHAUST = ((53.0, 5.1), (64.6, 5.1))
FLOOR = 2.5                        # the face's thickness, both makers

W = D = H = CX = 0.0
CASE: dict = {}
PARTS: list[dict] = []


def part(name, x0, x1, y0, y1, z0, z1, group, colour="#cccccc", note=""):
    PARTS.append(dict(name=name, x=(x0, x1), y=(y0, y1), z=(z0, z1), group=group,
                      colour=colour, note=note))


def build(name):
    """Fill PARTS for one case."""
    global W, D, H, CX, CASE
    CASE = CASES[name]
    W, D, H, CX = CASE["W"], CASE["D"], CASE["H"], CASE["W"] / 2
    PARTS.clear()

    # --- the case -------------------------------------------------------------------
    rx, ry = CASE["reach"]
    hw = CASE["half"]                                  # the middle pillars' half-width, est.
    spots = [(0, rx, 0), (CX - hw, CX + hw, 0), (W - rx, W, 0),
             (0, rx, 1), (CX - hw, CX + hw, 1), (W - rx, W, 1)]
    for i, (x0, x1, front) in enumerate(spots):
        if i in (1, 4) and not CASE["mid"]:
            continue
        y0, y1 = (D - ry, D) if front else (0, ry)
        part(f"pillar {i + 1}", x0, x1, y0, y1, 0, H, "case", "#d9d5c8")

    # --- the screen and the Pi ---------------------------------------------------------
    # Window 99 x 59, 10 from the left, 9 from the rear (the owner).  The module's own outline
    # is not published, and it clears the corner pillars in the prototype, so only the window's
    # own area is modelled, 7 mm thick.
    part("screen module", 10, 109, 9, 68, 23, H, "pi", "#e3e0f7", "frame not modelled")
    # Pi 5, 85 x 56 (Raspberry Pi's mechanical drawing), component side down.  Its left end is
    # 26 mm from the left wall and its rear edge 10 mm from the rear wall, from the owner's
    # measurements of the header plug.  Its board is 13 mm below the face (screen 7 + standoff 6).
    PIX, PIY, PI_Z = 26.0, 10.0, H - 13.0 - 1.6          # PI_Z: the Pi's component face
    part("Pi 5 board", PIX, PIX + 85, PIY, PIY + 56, PI_Z, PI_Z + 1.6, "pi", "#c9c4ee")
    part("Pi USB and Ethernet", PIX + 67, PIX + 88, PIY + 1, PIY + 55, 0.0, PI_Z, "pi",
         "#c9c4ee", "fills the depth; 3 mm past the board's end")
    part("Pi header pins", PIX + 7.1, PIX + 57.9, PIY + 50, PIY + 55, PI_Z - 8.5, PI_Z, "pi",
         "#8f88d8")
    part("Pi power and HDMI sockets", PIX + 6, PIX + 44, PIY - 1, PIY + 8, PI_Z - 3.4, PI_Z,
         "pi", "#8f88d8")
    SOC = (PIX + 33.0, PIY + 23.0)                        # est. from the drawing
    part("heat block", SOC[0] - 7.5, SOC[0] + 7.5, SOC[1] - 7.5, SOC[1] + 7.5, 0.0, PI_Z - 2.4,
         "heat", "#f3c2b0", "on the base plate, pad on top; position est.")

    # --- the Pi board (a HAT on the Pi's header) ---------------------------------------
    PB_TOP = PI_Z - 11.0                                   # a HAT sits 11 mm from the Pi
    part("Pi board", 12, 83, 2, 72, PB_TOP - 1.6, PB_TOP, "piboard", "#b9d6f2",
         "cut out around the heat block")
    part("Pi board header socket", PIX + 6.5, PIX + 58.5, PIY + 49.5, PIY + 55.5, PB_TOP,
         PI_Z - 8.5 + 6.0, "piboard", "#7fb2e5")
    # SHOU HAN TYPE-C 16PIN L8.35: 8.94 x 3.26, 8.35 long, its mouth about 2.5 past the
    # board's edge and so about 2 mm into the wall.
    part("USB-C power socket", USBC_X - 4.5, USBC_X + 4.5, 0, 6.4, PB_TOP, PB_TOP + 3.3,
         "piboard", "#7fb2e5", "SHOU HAN TYPE-C 16PIN L8.35")
    # XKB PJ-324M0: 11.5 wide, 6.45 tall, 10.7 behind the wall, axis 3.0 above the board,
    # an M6 nose 3.55 long that sits in the wall.
    part("MIDI socket (3.5 mm)", MIDI_X - 6, MIDI_X + 6, 0, 10.7, PB_TOP, PB_TOP + 6.5,
         "piboard", "#7fb2e5", "XKB PJ-324M0")

    # --- the audio board -----------------------------------------------------------------
    AB_TOP = 4.0
    part("audio board", 115.0, 172.0, 2, 106, AB_TOP - 1.6, AB_TOP, "audio", "#bfe6d6")
    part("audio board, mic tongue", 172.0, 177.5, 12, 98, AB_TOP - 1.6, AB_TOP, "audio",
         "#bfe6d6")
    # Neutrik NMJ6HCD2 (drawing ST-NMJ6HCD2): 18.2 wide, 15.67 tall, 20.6 behind the wall,
    # its axis 7.53 above the board; an 11.4 mm hole.  18.7 apart leaves 0.5 between bodies.
    for name, cx in JACKS:
        part(name, cx - 9.1, cx + 9.1, 0, 21, AB_TOP, AB_TOP + 15.7, "audio", "#6cc9a6",
             "Neutrik NMJ6HCD2")
    # Neutrik NCJ6FA-H (drawing 20004521): 25 x 25 behind the wall, 24.5 deep, its centre
    # 12.5 above the board, pins 3.5 below the body.
    part("mic combo socket", W - 24.5, W, MIC_Y - 12.5, MIC_Y + 12.5, AB_TOP, AB_TOP + 25.0,
         "audio", "#6cc9a6", "Neutrik NCJ6FA-H")

    # --- the footswitches (the owner's part: 13 x 13 body, 29.7 with lugs, sunk 16 mm) -----
    for i, fx in enumerate((CX - 69, CX, CX + 69)):
        part(f"footswitch {i + 1}", fx - 11, fx + 18.7, D - 29 - 6.5, D - 29 + 6.5, H - 16.0,
             H - 3.0, "fs", "#e8e4d6", "13 mm body with its top 3 mm below the face; lugs sideways")

    # --- the controls on the face -------------------------------------------------------
    # One board, held by the encoder's nut: Bourns PEC11R-4215F-S0024 (M7 bush, body about
    # 7 mm behind the face, pins 1.9 mm through the board), and two board-mounted buttons in
    # front of it (the owner, 2026-11-14).  The board starts behind the rear sockets and
    # stops short of the mic socket, so nothing of it is above either.  Positions are a
    # proposal: encoder at (131.1, 30), buttons at (125, 55) and (141, 55).
    part("control board and its parts", 115.5, 152.5, 21.5, 68.5, H - 10.5, H, "control",
         "#f6dfb4", "board 7 mm below the face; pin ends 1.9 mm below it")

    # --- the fan ------------------------------------------------------------------------
    fx, fy = fan_centre()
    part("fan's filter", fx - FAN[0] / 2, fx + FAN[0] / 2, fy - FAN[0] / 2, fy + FAN[0] / 2,
         0, FILTER, "fan", "#e9eef1", "1 mm, under the fan")
    part("fan", fx - FAN[0] / 2, fx + FAN[0] / 2, fy - FAN[0] / 2, fy + FAN[0] / 2, FILTER,
         FILTER + FAN[1], "fan", "#cfe8f5", "30 x 30 x 10 mm on the base plate, drawing in")


def fan_centre():
    """The fan's centre: midway between footswitches 1 and 2, in front of the Pi board."""
    return CX - 34.5, FAN_Y0 + FAN[0] / 2


# Pairs that are meant to touch or pass through each other.
ALLOWED = {
    frozenset(("heat block", "Pi board")),             # the cut-out
    frozenset(("Pi board header socket", "Pi header pins")),
}
SAME_GROUP_OK = {"pi", "piboard", "audio", "control", "case", "fan"}


def overlap(a, b):
    return [min(a[k][1], b[k][1]) - max(a[k][0], b[k][0]) for k in "xyz"]


def check():
    hits, near = [], []
    for i, a in enumerate(PARTS):
        for b in PARTS[i + 1:]:
            if a["group"] == b["group"] and a["group"] in SAME_GROUP_OK:
                continue
            if frozenset((a["name"], b["name"])) in ALLOWED:
                continue
            o = overlap(a, b)
            if min(o) > 0.01:
                hits.append((a["name"], b["name"], o))
            else:
                # the gap is the largest negative overlap when the others overlap
                gaps = [-v for v in o if v <= 0.01]
                if len(gaps) == 1 and gaps[0] < 3.0:
                    axis = "xyz"[[v <= 0.01 for v in o].index(True)]
                    near.append((gaps[0], a["name"], b["name"], axis))
    return hits, sorted(near)


def inside():
    out = []
    for p in PARTS:
        if p["x"][0] < -0.01 or p["x"][1] > W + 0.01 or p["y"][0] < -0.01 \
                or p["y"][1] > D + 0.01 or p["z"][0] < -0.01 or p["z"][1] > H + 0.01:
            out.append(p["name"])
    return out


# --- drawing ---------------------------------------------------------------------------
def n(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def svg():
    S = 5.0                                            # px per mm
    ox, oy = 30, 40
    sec_x = ox + W * S + 60                            # the section, to the right
    width, height = sec_x + H * S + 40, oy + D * S + 70
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{n(width)}" height="{n(height)}" '
         f'viewBox="0 0 {n(width)} {n(height)}" font-family="Helvetica, Arial, sans-serif">',
         f'<rect width="{n(width)}" height="{n(height)}" fill="#fff"/>',
         f'<text x="{ox}" y="22" font-size="15" fill="#222">The box in {CASE["source"]}\'s '
         f'case ({n(W)} x {n(D)} x {n(H)} mm inside): plan from above '
         f'(rear wall at top), and a section at x = 160 looking from the right</text>',
         f'<rect x="{ox}" y="{oy}" width="{n(W * S)}" height="{n(D * S)}" rx="8" fill="none" '
         f'stroke="#333" stroke-width="1.5"/>']
    order = {"case": 0, "piboard": 1, "audio": 1, "heat": 2, "pi": 3, "fs": 4, "control": 5,
             "fan": 2}
    for p in sorted(PARTS, key=lambda q: (order[q["group"]], q["z"][0])):
        x0, x1 = p["x"]
        y0, y1 = p["y"]
        dash = ' stroke-dasharray="6 4" fill-opacity="0.25"' if p["group"] in ("control",) \
            else ' fill-opacity="0.8"'
        if p["name"] in ("Pi 5 board", "screen module"):
            dash = ' fill-opacity="0.35"'
        o.append(f'<rect x="{n(ox + x0 * S)}" y="{n(oy + y0 * S)}" width="{n((x1 - x0) * S)}" '
                 f'height="{n((y1 - y0) * S)}" fill="{p["colour"]}" stroke="#444" '
                 f'stroke-width="0.7"{dash}/>')
    labels = [("Pi 5 on the screen", 70, 30), ("Pi board", 22, 62), ("heat block", 59, 34),
              ("USB-C", 40, -1.5), ("MIDI", 76, -1.5), ("out", 125, -1.5), ("EXT FS", 143.7, -1.5),
              ("in", 162.4, -1.5), ("mic", 166, 48), ("audio board", 140, 98),
              ("encoder", 131, 31), ("B1  B2", 133, 56), ("fan, on the base", 54.75, 101), ("FS1", 24, 82), ("FS2", 93, 82), ("FS3", 162, 82), ("USB, Ethernet", 103.5, 40)]
    for s, lx, ly in labels:
        o.append(f'<text x="{n(ox + lx * S)}" y="{n(oy + ly * S)}" font-size="12" '
                 f'text-anchor="middle" fill="#111">{s}</text>')
    # section at x = 160: y across, z up
    sx, sy = sec_x, oy
    o.append(f'<rect x="{n(sx)}" y="{n(sy)}" width="{n(H * S)}" height="{n(D * S)}" '
             f'fill="none" stroke="#333" stroke-width="1.5"/>')
    o.append(f'<text x="{n(sx)}" y="{n(sy + D * S + 18)}" font-size="12" fill="#333">base'
             f'</text><text x="{n(sx + H * S)}" y="{n(sy + D * S + 18)}" font-size="12" '
             f'text-anchor="end" fill="#333">face</text>')
    for p in PARTS:
        if p["x"][0] <= 160 <= p["x"][1]:
            y0, y1 = p["y"]
            z0, z1 = p["z"]
            o.append(f'<rect x="{n(sx + z0 * S)}" y="{n(sy + y0 * S)}" '
                     f'width="{n((z1 - z0) * S)}" height="{n((y1 - y0) * S)}" '
                     f'fill="{p["colour"]}" stroke="#444" stroke-width="0.7" fill-opacity="0.85"/>')
    o.append(f'<line x1="{n(ox + 160 * S)}" y1="{oy - 6}" x2="{n(ox + 160 * S)}" '
             f'y2="{n(oy + D * S + 6)}" stroke="#b33" stroke-width="0.8" stroke-dasharray="8 5"/>')
    o.append(f'<text x="{ox}" y="{n(oy + D * S + 40)}" font-size="12" fill="#555">Blocks, not '
             f'shapes: each part is its bounding box. Dashed: on the face, above the boards. '
             f'Sizes marked est. in box_layout.py are estimates.</text>')
    o.append("</svg>")
    return "\n".join(o)


def holes(name):
    """The case's holes, from its centre lines and from the outside of the face."""
    build(name)
    pb_top = H - 13.0 - 1.6 - 11.0
    below = lambda z: FLOOR + H - z                    # mm below the face's outside
    rows = [("face", "screen window, 99 x 59", 59.5 - CX, D / 2 - 38.5, "rectangle"),
            ("face", "encoder", ENCODER[0] - CX, D / 2 - ENCODER[1], "7.2")]
    rows += [("face", f"button {i + 1}", bx - CX, D / 2 - by, "7.5")
             for i, (bx, by) in enumerate(BUTTONS)]
    rows += [("face", f"lamp {i + 1}", lx - CX, D / 2 - ly, "3.3")
             for i, (lx, ly) in enumerate(LAMPS)]
    rows += [("face", f"footswitch {i + 1}", fx - CX, D / 2 - (D - 29), "12")
             for i, fx in enumerate((CX - 69, CX, CX + 69))]
    rows += [("rear wall", "USB-C power", USBC_X - CX, below(pb_top + 1.65), "10"),
             ("rear wall", "MIDI in", MIDI_X - CX, below(pb_top + 3.0), "6.5")]
    rows += [("rear wall", jn.replace(" socket", ""), jx - CX, below(4.0 + 7.53), "11.4")
             for jn, jx in JACKS]
    rows += [("rear wall", "air out", ix - CX, below(pb_top + dz), "9") for ix, dz in EXHAUST]
    fx, fy = fan_centre()
    rows += [("base", "air in (fan)", fx + dx - CX, D / 2 - (fy + dy), "8") for dx, dy in FAN_VENTS]
    rows += [("base", "fan screw", fx + dx - CX, D / 2 - (fy + dy), "3.0") for dx, dy in FAN_SCREWS]
    rows += [("right wall", "mic", D / 2 - MIC_Y, below(4.0 + 12.5), "22"),
             ("right wall", "mic screw", D / 2 - MIC_Y + 9.9, below(4.0 + 12.5 + 9.9), "3.2"),
             ("right wall", "mic screw", D / 2 - MIC_Y - 9.9, below(4.0 + 12.5 - 9.9), "3.2")]
    print(f"== holes, {name} ({CASE['source']})")
    print("   face and base: mm right of centre, mm toward the rear of centre, seen from above")
    print("   walls: mm along the wall from its centre (rear and front walls: toward the player's"
          " right; left and right walls: toward the rear), mm below the outside of the face")
    for wall, what, a, b, dia in rows:
        print(f"   {wall:10s} {what:24s} {a:7.1f} {b:7.1f}   {dia}")
    print(f"   {len(rows) - 1} round holes and the window")
    return rows


COAT = 0.4        # Tayda: add 0.4 mm to every diameter when the case is powder-coated
# Tayda's Box Tool draws the 1590DD upright: the face 117 mm wide and 185 mm high, B and D its
# short walls, C and E its long ones, each 33 mm deep (read from the tool's own picture,
# 2026-11-16).  The pedal is turned a quarter turn anticlockwise to fit it, so its rear wall is
# Tayda's left.
# The base plate is Tayda's "Lid", drawn the size of the face.  Tayda gives no orientation for
# it; every other side's coordinates are as seen from outside, so the lid's are taken as seen
# from below: the face's frame turned over about the pedal's long axis, which mirrors the
# front-to-rear direction.  The lid's screws are symmetric, so it is fitted whichever way round
# puts the fan's holes under the gap between footswitches 1 and 2.
SIDES = {"face": "A", "rear wall": "C", "front wall": "E", "right wall": "B", "left wall": "D",
         "base": "Lid"}
TAYDA_SIDE = {"A": (117.0, 185.0), "B": (117.0, 33.0), "D": (117.0, 33.0), "C": (33.0, 185.0),
              "E": (33.0, 185.0), "Lid": (117.0, 185.0)}


def tayda_rows():
    """The holes in Tayda's frame: (side, what, x, y, width, height, round), sizes as drilled."""
    rows = holes("tayda")
    half = (H + FLOOR) / 2                           # the tub's outside height, halved
    out = []
    for wall, what, a, b, dia in rows:
        side = SIDES[wall]
        if side == "A":
            x, y = -b, a
        elif side == "Lid":
            x, y = b, a
        elif side == "C":
            x, y = half - b, a
        elif side == "E":
            x, y = b - half, a
        elif side == "B":
            x, y = -a, b - half
        else:
            x, y = -a, half - b
        if dia == "rectangle":
            out.append((side, what, x, y, 59 + COAT, 99 + COAT, False))
        else:
            out.append((side, what, x, y, float(dia) + COAT, float(dia) + COAT, True))
    return out


def tayda():
    """The holes as Tayda's Box Tool takes them: per side, X and Y in mm from the centre of that
    side's full outside, X to the right and Y up, and the diameter to drill (finished size plus
    0.4 mm for the powder coat; nothing under 3 mm).  Sides as in the tool's unfolded picture,
    which has the face upright: the pedal's right wall is B (top), its rear wall C (left), its
    front wall E (right), its left wall D (bottom).  The walls fold away from the face, so on C
    the face is to the right, on E to the left, on B below and on D above.  Returns True if a
    hole reaches the edge of its side as the tool draws it."""
    rows = tayda_rows()
    print(f"== for Tayda's Box Tool: 1590DD, the tub {H + FLOOR:g} mm high outside")
    print("   side  what                          X       Y    drill")
    bad = False
    for side, what, x, y, w, h, is_round in rows:
        size = f"{w:.1f}" if is_round else f"rectangle {w:g} wide, {h:g} high"
        sw, sh = TAYDA_SIDE[side]
        edge = min(sw / 2 - abs(x) - w / 2, sh / 2 - abs(y) - h / 2)
        note = ""
        if edge <= 0:
            bad, note = True, "   OVER THE EDGE OF ITS SIDE"
        elif edge < 2:
            note = f"   {edge:.1f} mm from the side's edge"
        print(f"   {side:5s} {what:24s} {x:7.1f} {y:7.1f}    {size}{note}")
    return bad


def report(name):
    build(name)
    hits, near = check()
    out = inside()
    print(f"== {name}: {len(PARTS)} parts in {W} x {D} x {H} mm, wall {CASE['wall']} "
          f"({CASE['source']})")
    for part_name in out:
        print(f"OUTSIDE THE CASE: {part_name}")
    for a, b, o in hits:
        print(f"COLLISION: {a} / {b}: overlap {o[0]:.1f} x {o[1]:.1f} x {o[2]:.1f} mm")
    if CASE["wall"] > NEUTRIK_MAX_PANEL:
        print(f"WALL TOO THICK for the mic socket: {CASE['wall']} > {NEUTRIK_MAX_PANEL}")
    print("  tightest clearances (under 3 mm):")
    for gap, a, b, axis in near:
        print(f"  {gap:5.1f} mm in {axis}: {a} / {b}")
    for part_name in ("mic combo socket", "guitar in socket"):
        p = next(q for q in PARTS if q["name"] == part_name)
        print(f"  {part_name}: z {p['z'][0]:.1f}-{p['z'][1]:.1f}, "
              f"{H - p['z'][1]:.1f} mm below the face")
    return bool(hits or out or CASE["wall"] > NEUTRIK_MAX_PANEL)


def main():
    args = sys.argv[1:]
    if args and args[0] == "--tayda":
        return int(tayda())
    if args and args[0] == "--holes":
        for name in args[1:] or ["hammond"]:
            holes(name)
        return 0
    names = args or list(CASES)
    bad = [name for name in names if report(name)]
    drawn = names[0] if len(names) == 1 else DEFAULT
    build(drawn)
    here = os.path.dirname(os.path.abspath(__file__))
    dst = os.path.join(here, "..", "..", "docs", "diagrams", "box-layout.svg")
    with open(dst, "w") as f:
        f.write(svg())
    print(f"wrote {os.path.normpath(dst)} ({drawn})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Draw the medium (1590DD-size) pedal's internal layout, top down, as an SVG.

This is a *layout draft*, not a drilling template.  The case interior is
178.26 x 110.26 mm, the player's edge is at the bottom, and the layout follows the
owner's latest positions:

  * screen cutout 99 x 59 mm, 10 mm from the left and 9 mm from the top;
  * the Pi 5 landscape behind it, USB-C/HDMI at the top edge;
  * three footswitches, the middle one on the centre line, +/-69 mm either side;
  * input and output jacks both on the top edge;
  * the WM8960 codec between the jacks, FS3, the Pi and the right wall;
  * the output board and the Pico (standing on edge) in the front strip.

    python3 enclosure/src/medium_layout.py
    rsvg-convert -w 1600 docs/diagrams/medium-layout.svg \
        -o docs/diagrams/medium-layout.png
    rsvg-convert -f pdf -w 1134 -h 824 docs/diagrams/medium-layout.svg \
        -o docs/diagrams/medium-layout.pdf

No third-party Python is needed.  Units are millimetres in the case's internal
frame: x = 0 at the left wall, y = 0 at the rear wall, y grows toward the player.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# The case and the parts
# ---------------------------------------------------------------------------

W, D = 178.26, 110.26          # internal, mm
WALL = 4.87                    # outside 188.0 x 120.0 -> internal 178.26 x 110.26
CX = W / 2                     # 89.13

# Screen cutout: given directly by the owner.
CUT = dict(x=10.0, y=9.0, w=99.0, h=59.0, r=2.0)
CUT_CX = CUT["x"] + CUT["w"] / 2      # 59.5
CUT_CY = CUT["y"] + CUT["h"] / 2      # 38.5

# Raspberry Pi 5, landscape: 85 wide x 56 deep, centred behind the screen cutout.
# That is where the screen's own Pi standoffs put it.
PI = dict(x=CUT_CX - 42.5, y=CUT_CY - 28.0, w=85.0, h=56.0)
PI_HOLES = (58.0, 49.0)

# Three footswitches: the middle is on the centre line, the outer two 69 mm away.
FS_X = (CX - 69.0, CX, CX + 69.0)      # 20.13, 89.13, 158.13
FS_Y = D - 29.0                        # 81.26, centre 29 mm from the bottom edge
FS_BODY = (20.0, 14.4)                 # MC7105 can, plan (w, d)
FS_KEEPOUT_R = 12.0

# Input and output jacks, both on the top (rear) edge.  Body 20 mm deep, 20 mm wide.
IN_JACK = dict(x=148.0, y=0.0, w=20.0, h=20.0, cx=158.0, cy=10.0)
OUT_JACK = dict(x=110.0, y=0.0, w=20.0, h=20.0, cx=120.0, cy=10.0)

# SparkFun WM8960 breakout, 25.4 x 40.64, in the gap under the jacks.
CODEC = dict(x=128.0, y=20.0, w=25.4, h=40.64)

# Output board and Pico carrier in the front strip.
OUT_BOARD = dict(x=40.0, y=94.0, w=15.0, h=15.0)
PICO = dict(x=60.0, y=92.5, w=55.0, h=8.0, height=21.0)

# Lid screw bosses in the four corners (1590DD): ~8 mm diameter, 5 mm from each wall.
BOSS_R = 4.0
# Four corners plus the centres of the top and bottom edges: six full-height
# aluminium screw pillars in the real case.
BOSSES = [(5.0, 5.0), (W - 5.0, 5.0), (W - 5.0, D - 5.0), (5.0, D - 5.0),
          (CX, 5.0), (CX, D - 5.0)]

# ---------------------------------------------------------------------------
# SVG helpers
# ---------------------------------------------------------------------------

def n(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def rect(x, y, w, h, rx=0.0, fill="none", stroke="none", sw=0.6,
         dash=None, opacity=None):
    a = [f'x="{n(x)}"', f'y="{n(y)}"', f'width="{n(w)}"', f'height="{n(h)}"']
    if rx:
        a.append(f'rx="{n(rx)}"')
    a.append(f'fill="{fill}"')
    if stroke != "none":
        a.append(f'stroke="{stroke}"')
        a.append(f'stroke-width="{n(sw)}"')
    if dash:
        a.append(f'stroke-dasharray="{dash}"')
    if opacity is not None:
        a.append(f'opacity="{n(opacity)}"')
    return "<rect " + " ".join(a) + "/>"


def circle(cx, cy, r, fill="none", stroke="none", sw=0.6, dash=None, opacity=None):
    a = [f'cx="{n(cx)}"', f'cy="{n(cy)}"', f'r="{n(r)}"', f'fill="{fill}"']
    if stroke != "none":
        a.append(f'stroke="{stroke}"')
        a.append(f'stroke-width="{n(sw)}"')
    if dash:
        a.append(f'stroke-dasharray="{dash}"')
    if opacity is not None:
        a.append(f'opacity="{n(opacity)}"')
    return "<circle " + " ".join(a) + "/>"


def line(x1, y1, x2, y2, stroke="#222", sw=0.5, dash=None, marker_start=False,
         marker_end=False, opacity=None):
    a = [f'x1="{n(x1)}"', f'y1="{n(y1)}"', f'x2="{n(x2)}"', f'y2="{n(y2)}"',
         f'stroke="{stroke}"', f'stroke-width="{n(sw)}"', 'stroke-linecap="round"']
    if dash:
        a.append(f'stroke-dasharray="{dash}"')
    if marker_start:
        a.append('marker-start="url(#arrow)"')
    if marker_end:
        a.append('marker-end="url(#arrow)"')
    if opacity is not None:
        a.append(f'opacity="{n(opacity)}"')
    return "<line " + " ".join(a) + "/>"


def text(x, y, s, size=2.6, fill="#111", anchor="middle", weight="normal",
         style="normal", rotate=None, letter=False):
    a = [f'x="{n(x)}"', f'y="{n(y)}"', f'font-size="{n(size)}"', f'fill="{fill}"',
         f'text-anchor="{anchor}"']
    if weight != "normal":
        a.append(f'font-weight="{weight}"')
    if style != "normal":
        a.append(f'font-style="{style}"')
    if rotate is not None:
        a.append(f'transform="rotate({n(rotate)} {n(x)} {n(y)})"')
    if letter:
        a.append('letter-spacing="0.15"')
    return "<text " + " ".join(a) + ">" + esc(s) + "</text>"


def dim_h(x1, x2, y, label, size=2.3, above=True, color="#333"):
    out = [line(x1, y, x2, y, stroke=color, sw=0.35, marker_start=True, marker_end=True)]
    ty = y - 1.2 if above else y + 3.0
    out.append(text((x1 + x2) / 2, ty, label, size=size, fill=color,
                    style="italic"))
    return "\n".join(out)


def dim_v(y1, y2, x, label, size=2.3, color="#333"):
    out = [line(x, y1, x, y2, stroke=color, sw=0.35, marker_start=True, marker_end=True)]
    out.append(text(x - 1.3, (y1 + y2) / 2, label, size=size, fill=color,
                    anchor="middle", style="italic", rotate=-90))
    return "\n".join(out)


def leader(x1, y1, x2, y2, color="#555", sw=0.3):
    return line(x1, y1, x2, y2, stroke=color, sw=sw, dash="1.0 0.8")


# ---------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------

def plan() -> str:
    s: list[str] = ['<g id="plan" transform="translate(26 38)">']

    # --- case ------------------------------------------------------------
    s.append(rect(-WALL, -WALL, W + 2 * WALL, D + 2 * WALL, rx=6,
                  fill="#e7e3da", stroke="#b9b2a5", sw=0.5))
    s.append(rect(0, 0, W, D, rx=3, fill="#fcfcf9", stroke="#1b1b1b", sw=0.9))
    s.append(rect(1.6, 1.6, W - 3.2, D - 3.2, rx=2.2, fill="none",
                  stroke="#8d8578", sw=0.3, dash="2 1.5"))
    for bx, by in BOSSES:
        s.append(circle(bx, by, BOSS_R, fill="url(#hatch_alu)", stroke="#6d665c",
                        sw=0.6))
        s.append(circle(bx, by, 2.4, fill="#b0a99c", stroke="#4e4a42", sw=0.4))
        s.append(line(bx - 1.4, by, bx + 1.4, by, stroke="#4e4a42", sw=0.4))

    # --- orientation -----------------------------------------------------
    s.append(text(CX, -10.5, "REAR", size=3.0, fill="#555", weight="bold",
                  letter=True))
    s.append(text(CX, D + 12.5, "FRONT  /  PLAYER", size=3.0, fill="#555",
                  weight="bold", letter=True))
    s.append(line(CX, D + 3.0, CX, D + 9.0, stroke="#555", sw=0.4,
                  marker_end=True))

    # the two centre-edge pillars are the ones that catch the Pico
    s.append(text(86.0, 13.0, "6× full-height", size=1.45, fill="#4e4a42",
                  anchor="end", weight="bold"))
    s.append(text(86.0, 15.3, "screw pillars", size=1.45, fill="#4e4a42",
                  anchor="end", weight="bold"))
    s.append(leader(86.0, 12.5, 89.0, 6.5, color="#4e4a42"))
    s.append(text(83.0, 103.0, "full-height pillar", size=1.5, fill="#4e4a42",
                  anchor="end", weight="bold"))
    s.append(leader(83.0, 103.8, 88.0, 105.0, color="#4e4a42"))

    # --- input-sensitive region (behind the parts) -----------------------
    s.append(rect(125.0, 8.0, 51.0, 58.0, rx=3, fill="#ffebee",
                  stroke="#e57373", sw=0.35, dash="2 1.5", opacity=0.30))
    s.append(text(138.0, 12.5, "input-sensitive", size=1.7, fill="#c62828"))
    s.append(text(138.0, 15.3, "keep OUT wiring out", size=1.7, fill="#c62828"))

    # --- Pi, landscape, centred on the screen standoffs -----------------
    s.append(rect(PI["x"], PI["y"], PI["w"], PI["h"], rx=1.5,
                  fill="#e6f2e4", stroke="#2e7d32", sw=1.0))
    # USB-C and two micro HDMI on the top edge (per the owner)
    for xx, ww in ((39.0, 5.0), (47.0, 5.0), (54.0, 5.0)):
        s.append(rect(xx, PI["y"], ww, 4.0, rx=0.4, fill="#263238",
                      stroke="#263238", sw=0.2))
    s.append(text(CUT_CX, 7.5, "USB-C / HDMI  →  REAR", size=1.85,
                  fill="#1b5e20", weight="bold"))
    s.append(leader(59.5, 8.6, 59.5, 11.0, color="#1b5e20"))
    # USB-A and Ethernet on the right edge, toward the centre
    s.append(rect(PI["x"] + PI["w"], 24.0, 3.2, 9.0, rx=0.4,
                  fill="#263238", stroke="#263238", sw=0.2))
    s.append(rect(PI["x"] + PI["w"], 35.0, 3.2, 8.0, rx=0.4,
                  fill="#263238", stroke="#263238", sw=0.2))
    s.append(text(PI["x"] + PI["w"] + 5.0, 35.0, "USB-A / ETH", size=1.55,
                  fill="#1b5e20", rotate=90, weight="bold"))
    # 40-pin header along the bottom edge
    s.append(rect(30.5, PI["y"] + PI["h"] - 3.0, 50.8, 2.5, rx=0.3,
                  fill="#263238", stroke="#263238", sw=0.2))
    s.append(text(CUT_CX, PI["y"] + PI["h"] - 4.2, "40-pin", size=1.65,
                  fill="#263238", weight="bold"))
    # the screen's four M2.5 standoffs, on the Pi's 58 x 49 hole pattern
    for sx in (30.5, 88.5):
        for sy in (14.0, 63.0):
            s.append(circle(sx, sy, 1.6, fill="#b0bec5", stroke="#455a64", sw=0.4))
            s.append(line(sx - 0.9, sy, sx + 0.9, sy, stroke="#455a64", sw=0.25))
            s.append(line(sx, sy - 0.9, sx, sy + 0.9, stroke="#455a64", sw=0.25))
    s.append(text(CUT_CX, 57.0, "4× M2.5 screen standoffs", size=1.45,
                  fill="#455a64"))
    s.append(text(CUT_CX, 70.8, "PI 5  85 × 56  (ON SCREEN STANDOFFS)", size=2.0,
                  fill="#1b5e20", weight="bold"))

    # --- screen cutout, above the Pi -------------------------------------
    s.append(rect(CUT["x"], CUT["y"], CUT["w"], CUT["h"], rx=CUT["r"],
                  fill="#d32f2f", stroke="#b71c1c", sw=0.9,
                  dash="2.4 1.2", opacity=0.06))
    s.append(rect(CUT["x"], CUT["y"], CUT["w"], CUT["h"], rx=CUT["r"],
                  fill="none", stroke="#d32f2f", sw=0.9, dash="2.4 1.2"))
    s.append(text(CUT_CX, CUT_CY - 3.0, "SCREEN CUTOUT", size=3.2,
                  fill="#b71c1c", weight="bold", letter=True))
    s.append(text(CUT_CX, CUT_CY + 2.0, "99 × 59", size=4.6,
                  fill="#b71c1c", weight="bold"))
    s.append(text(CUT_CX, CUT_CY + 6.4, "10 from left · 9 from top",
                  size=2.05, fill="#b71c1c"))

    # --- footswitches -----------------------------------------------------
    for i, x in enumerate(FS_X):
        s.append(circle(x, FS_Y, FS_KEEPOUT_R, fill="#ffebee", stroke="#e57373",
                        sw=0.3, dash="1.5 1.0", opacity=0.55))
        s.append(rect(x - FS_BODY[0] / 2, FS_Y - FS_BODY[1] / 2, FS_BODY[0],
                      FS_BODY[1], rx=2.0, fill="#eceff1", stroke="#37474f", sw=0.8))
        s.append(circle(x, FS_Y, 6.0, fill="#b0bec5", stroke="#37474f", sw=0.6))
        s.append(circle(x, FS_Y, 4.4, fill="#cfd8dc", stroke="#37474f", sw=0.5))
        s.append(line(x - 2.4, FS_Y, x + 2.4, FS_Y, stroke="#607d8b", sw=0.4))
        s.append(line(x, FS_Y - 2.4, x, FS_Y + 2.4, stroke="#607d8b", sw=0.4))
        s.append(text(x, FS_Y - 9.5, f"FS{i + 1}", size=2.3, fill="#37474f",
                      weight="bold"))

    # --- output jack (top edge, left of input) ---------------------------
    oj = OUT_JACK
    s.append(rect(oj["x"], oj["y"], oj["w"], oj["h"], rx=2,
                  fill="#efebe9", stroke="#6d4c41", sw=0.7))
    s.append(circle(oj["cx"], 0.0, 7.4, fill="#d7ccc8", stroke="#6d4c41", sw=0.6))
    s.append(circle(oj["cx"], 0.0, 3.6, fill="#8d6e63", stroke="#6d4c41", sw=0.4))
    s.append(text(oj["cx"], 13.0, "OUT", size=3.0, fill="#4e342e", weight="bold"))
    s.append(text(oj["cx"], 16.2, "top edge", size=1.7, fill="#4e342e"))

    # --- input jack (top edge, right) -----------------------------------
    ij = IN_JACK
    s.append(rect(ij["x"], ij["y"], ij["w"], ij["h"], rx=2,
                  fill="#546e7a", stroke="#263238", sw=0.7))
    s.append(circle(ij["cx"], 0.0, 7.4, fill="#cfd8dc", stroke="#263238", sw=0.6))
    s.append(circle(ij["cx"], 0.0, 3.6, fill="#37474f", stroke="#263238", sw=0.4))
    s.append(text(ij["cx"], 13.0, "IN", size=3.0, fill="#fff", weight="bold"))
    s.append(text(ij["cx"], 16.2, "top edge", size=1.7, fill="#eceff1"))

    # --- codec ------------------------------------------------------------
    c = CODEC
    s.append(rect(c["x"], c["y"], c["w"], c["h"], rx=0.8,
                  fill="#fbe9e7", stroke="#c62828", sw=0.9))
    for xx in (c["x"] + 1.0, c["x"] + c["w"] - 3.2):
        s.append(rect(xx, c["y"] + 4.0, 2.2, c["h"] - 8.0, rx=0.3,
                      fill="#263238", stroke="#263238", sw=0.2))
    s.append(text(c["x"] + c["w"] / 2, c["y"] + 17.0, "WM8960", size=2.5,
                  fill="#b71c1c", weight="bold"))
    s.append(text(c["x"] + c["w"] / 2, c["y"] + 20.4, "CODEC", size=2.2,
                  fill="#b71c1c", weight="bold"))
    s.append(text(c["x"] + c["w"] / 2, c["y"] + 24.0, "25.4 × 40.6", size=2.0,
                  fill="#b71c1c"))

    # --- output board -----------------------------------------------------
    ob = OUT_BOARD
    s.append(rect(ob["x"], ob["y"], ob["w"], ob["h"], rx=1.0,
                  fill="#fff3e0", stroke="#ef6c00", sw=0.9))
    s.append(text(ob["x"] + ob["w"] / 2, ob["y"] + 5.4, "OUT", size=2.6,
                  fill="#e65100", weight="bold"))
    s.append(text(ob["x"] + ob["w"] / 2, ob["y"] + 8.6, "15 × 15", size=2.0,
                  fill="#e65100"))

    # --- Pico on edge -----------------------------------------------------
    p = PICO
    s.append(rect(p["x"], p["y"], p["w"], p["h"], rx=0.8,
                  fill="#f3e5f5", stroke="#6a1b9a", sw=0.9))
    s.append(rect(p["x"], p["y"], p["w"], p["h"], rx=0.8,
                  fill="url(#hatch_purple)", stroke="none", opacity=0.55))
    s.append(text(p["x"] + p["w"] / 2, p["y"] + 5.4, "PICO 2 W ON EDGE", size=2.5,
                  fill="#4a148c", weight="bold"))
    for xx in (p["x"] + 5, p["x"] + 22, p["x"] + 39):
        s.append(rect(xx, p["y"] + 0.3, 7.0, 3.0, rx=0.4,
                      fill="#ffffff", stroke="#6a1b9a", sw=0.5))
        s.append(text(xx + 3.5, p["y"] + 2.5, "XH", size=1.3, fill="#4a148c"))
    s.append(text(p["x"] + p["w"] + 2.0, p["y"] + 5.5, "21 mm tall", size=1.7,
                  fill="#4a148c", anchor="start"))

    # --- wiring hints -----------------------------------------------------
    # input jack -> codec
    s.append(line(ij["cx"], 10.0, c["x"] + c["w"] * 0.75, c["y"] + 2.0,
                  stroke="#c62828", sw=0.5, dash="1.5 1.0", marker_end=True))
    # codec -> Pi (I2S/I2C)
    s.append(line(c["x"], c["y"] + 20.0, PI["x"] + PI["w"] + 0.5, c["y"] + 20.0,
                  stroke="#6a1b9a", sw=0.5, dash="1.5 1.0", marker_end=True))
    s.append(text(108.0, c["y"] + 18.5, "I2S", size=1.6, fill="#6a1b9a"))
    # Pi -> Pico
    s.append('<polyline points="%s" fill="none" stroke="#1565c0" stroke-width="0.5" stroke-dasharray="1.5 1.0" marker-end="url(#arrow)"/>'
             % " ".join(f"{n(x)},{n(y)}" for x, y in
                        [(PI["x"] + PI["w"] + 1.0, 60.0), (112.0, 60.0),
                         (112.0, 96.0), (p["x"] + p["w"] - 1.0, p["y"] - 3.0)]))
    s.append(text(110.0, 88.0, "USB/UART", size=1.5, fill="#1565c0",
                  rotate=90))
    # output jack -> output board, down the right side and across the front
    s.append('<polyline points="%s" fill="none" stroke="#ef6c00" stroke-width="0.5" stroke-dasharray="1.5 1.0" marker-end="url(#arrow)"/>'
             % " ".join(f"{n(x)},{n(y)}" for x, y in
                        [(oj["cx"], 20.0), (112.0, 20.0), (112.0, 91.0),
                         (58.0, 91.0), (58.0, 97.0),
                         (ob["x"] + ob["w"], ob["y"] + 5.0)]))
    s.append(text(114.0, 50.0, "OUT", size=1.5, fill="#ef6c00", rotate=90))

    # --- dimensions -------------------------------------------------------
    s.append(dim_h(0, W, 118.0, "178.26 internal"))
    s.append(dim_v(0, D, -13.0, "110.26 internal"))
    s.append(dim_h(CUT["x"], CUT["x"] + CUT["w"], -5.5, "99", size=2.2))
    s.append(dim_v(CUT["y"], CUT["y"] + CUT["h"], -6.0, "59", size=2.2))

    s.append("</g>")
    return "\n".join(s)


# ---------------------------------------------------------------------------
# Notes panel
# ---------------------------------------------------------------------------

NOTES = [
    ("", "NOTES"),
    ("", ""),
    ("", "Case 178.26 × 110.26 × ~33 mm."),
    ("", "Front (player) bottom; rear top. mm."),
    ("", "6 screw pillars (corners + top/bottom"),
    ("", "centre) are full-height aluminium."),
    ("", "Keep parts and wires clear of them."),
    ("", "Draft — check before cutting."),
    ("", "Dashed = above / proposed."),
    ("", ""),
    ("1", "SCREEN cutout 99 × 59, 10 from"),
    ("", "left, 9 from top. No module outline"),
    ("", "is dimensioned; the cutout is exact."),
    ("", "The 9 mm strip above it is free for the"),
    ("", "Pi’s USB-C/HDMI leads; the Pi top edge"),
    ("", "sits 1.5 mm below the cutout top."),
    ("", ""),
    ("2", "Pi 5 85 × 56 landscape, centred"),
    ("", "on the screen’s Pi standoffs."),
    ("", "USB-C/HDMI on the top edge;"),
    ("", "USB-A/Ethernet on the right edge;"),
    ("", "40-pin header on the bottom edge."),
    ("", "Holes 58 × 49. The Pi is clear of"),
    ("", "the footswitches."),
    ("", ""),
    ("3", "FOOTSWITCHES: middle at W/2 ="),
    ("", "89.13; ±69 gives 20.13 / 158.13;"),
    ("", "29 mm from the bottom edge."),
    ("", ""),
    ("4", "IN / OUT both on the top edge:"),
    ("", "OUT x=120, IN x=158, ~38 mm apart."),
    ("", "Codec sits between them, FS3, the"),
    ("", "Pi and the right wall; input lead"),
    ("", "< 20 mm."),
    ("", ""),
    ("5", "CODEC WM8960 25.4 × 40.6,"),
    ("", "x=128..153, y=20..61."),
    ("", ""),
    ("6", "OUT BOARD 15 × 15, front-left,"),
    ("", "clear of the input side. A second"),
    ("", "fits beside it."),
    ("", ""),
    ("7", "PICO 2 W on edge: 55 × 8 plan,"),
    ("", "21 mm tall; moved up by the pillar"),
    ("", "width to clear it. XH sockets on top."),
    ("", ""),
    ("8", "Screen 7 + standoff 6 + Pi 17"),
    ("", "≈ 30 of 33; Pi clear of FS2 in plan."),
]


def notes() -> str:
    s = ['<g id="notes" transform="translate(212 38)">']
    y = 6.0
    for head, body in NOTES:
        if head == "NOTES":
            s.append(text(0, y, "NOTES", size=3.4, fill="#111", anchor="start",
                          weight="bold", letter=True))
            y += 5.4
            continue
        if head:
            s.append(text(0, y, head, size=1.95, fill="#111", anchor="start",
                          weight="bold"))
        if body:
            s.append(text(5.5, y, body, size=1.95, fill="#222", anchor="start"))
        y += 2.75
    s.append("</g>")
    return "\n".join(s)


# ---------------------------------------------------------------------------
# Section A-A: through x = 83, so it cuts the Pi and FS2
# ---------------------------------------------------------------------------

def section() -> str:
    s = ['<g id="section" transform="translate(26 168)">']
    s.append(text(0, 0, "SECTION A–A  (through x = 89: Pi, FS2, Pico and bottom-centre pillar)",
                  size=3.0, fill="#111", anchor="start", weight="bold"))
    ox, oy = 8.0, 5.0
    sx = 1.30
    sz = 0.65

    def X(y):
        return ox + y * sx

    def Z(z):
        return oy + (33.0 - z) * sz

    # base and lid
    s.append(rect(X(0), Z(0), X(D) - X(0), 1.2, fill="#b9b2a5",
                  stroke="#6d665c", sw=0.3))
    s.append(rect(X(0), Z(33), X(D) - X(0), 1.2, fill="#b9b2a5",
                  stroke="#6d665c", sw=0.3))
    s.append(line(X(0), Z(0), X(0), Z(33), stroke="#1b1b1b", sw=0.6))
    s.append(line(X(D), Z(0), X(D), Z(33), stroke="#1b1b1b", sw=0.6))
    # screen in the lid: y 9..68, z 26..33
    s.append(rect(X(CUT["y"]), Z(33), X(CUT["y"] + CUT["h"]) - X(CUT["y"]),
                  7 * sz, fill="#e8f1fb", stroke="#1565c0", sw=0.5))
    s.append(text((X(CUT["y"]) + X(CUT["y"] + CUT["h"])) / 2, Z(30.0),
                  "screen", size=1.8, fill="#0d47a1"))
    # standoffs z 20..26 at the two hole rows
    for yy in (14.0, 63.0):
        s.append(line(X(yy), Z(26), X(yy), Z(20), stroke="#607d8b", sw=0.8))
    s.append(text(X(38), Z(24.8), "standoffs", size=1.45, fill="#455a64"))
    # Pi: y 10.5..66.5, z 3..20
    s.append(rect(X(10.5), Z(20), X(66.5) - X(10.5), 17 * sz, fill="#e6f2e4",
                  stroke="#2e7d32", sw=0.5))
    s.append(text(X(38.5), Z(12.0), "Pi 5", size=1.8, fill="#1b5e20"))
    # FS2: y 74..88, z 14..33
    s.append(rect(X(74), Z(33), X(88) - X(74), 19 * sz, fill="#eceff1",
                  stroke="#37474f", sw=0.5))
    s.append(text(X(81), Z(22.0), "FS2", size=1.7, fill="#37474f"))
    # Pico on edge: y 92.5..100.5, z 5..26, just clear of the pillar
    s.append(rect(X(92.5), Z(26), X(100.5) - X(92.5), 21 * sz,
                  fill="#f3e5f5", stroke="#6a1b9a", sw=0.5))
    s.append(text(X(96.5), Z(15.5), "Pico", size=1.6, fill="#4a148c",
                  rotate=90))
    # full-height screw pillar at the bottom centre: y 101.3..109.3, z 0..33
    s.append(rect(X(101.3), Z(33), X(109.3) - X(101.3), 33 * sz,
                  fill="url(#hatch_alu)", stroke="#6d665c", sw=0.6))
    s.append(text(X(105.3), Z(16.5), "screw pillar", size=1.55, fill="#4e4a42",
                  rotate=90, weight="bold"))
    # height dimension
    s.append(line(X(D) + 5, Z(0), X(D) + 5, Z(33), stroke="#333", sw=0.35,
                  marker_start=True, marker_end=True))
    s.append(text(X(D) + 7.0, Z(16.5), "33", size=2.0, fill="#333",
                  style="italic"))
    s.append(text(X(0), Z(0) + 3.4, "REAR", size=1.7, fill="#555",
                  anchor="start", weight="bold"))
    s.append(text(X(D), Z(0) + 3.4, "FRONT", size=1.7, fill="#555",
                  anchor="end", weight="bold"))
    s.append(text(X(0), Z(0) + 7.0,
                  "screen 7 + standoff 6 + Pi 17 ≈ 30 of 33; Pi clear of FS2; pillar full height.",
                  size=1.75, fill="#555", anchor="start"))
    s.append("</g>")
    return "\n".join(s)


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------

def svg() -> str:
    head = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="300mm" height="218mm"
     viewBox="0 0 300 218" font-family="Helvetica Neue, Helvetica, Arial, sans-serif">
<title>Medium pedal — internal layout, top down</title>
<desc>Draft 2D layout of the 1590DD-size pedal: 99 x 59 screen cutout at the
top-left, Pi landscape behind it, three footswitches, input and output jacks on
the top edge, codec at the right, output board and Pico in the front strip.</desc>
<defs>
  <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5"
          markerWidth="4" markerHeight="4" orient="auto-start-reverse">
    <path d="M 0 0 L 10 5 L 0 10 z" fill="#555"/>
  </marker>
  <pattern id="hatch_purple" patternUnits="userSpaceOnUse" width="2.2" height="2.2"
           patternTransform="rotate(45)">
    <line x1="0" y1="0" x2="0" y2="2.2" stroke="#6a1b9a" stroke-width="0.45"/>
  </pattern>
  <pattern id="hatch_alu" patternUnits="userSpaceOnUse" width="1.6" height="1.6"
           patternTransform="rotate(45)">
    <line x1="0" y1="0" x2="0" y2="1.6" stroke="#8d8578" stroke-width="0.4"/>
  </pattern>
  <style>
    text {{ font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; }}
    .title {{ font-size: 6.2px; font-weight: 700; letter-spacing: 0.2px; }}
    .sub {{ font-size: 2.9px; fill: #444; }}
  </style>
</defs>
<rect width="300" height="218" fill="#ffffff"/>
<text x="26" y="12" class="title">MEDIUM PEDAL — INTERNAL LAYOUT, TOP DOWN</text>
<text x="26" y="18.5" class="sub">178.26 × 110.26 mm internal · draft, not a drilling template · positions from your corrections</text>
<text x="26" y="23.5" class="sub">Lid removed / see-through: the screen cutout is in the lid, the Pi hangs below it.</text>
'''
    body = "\n".join([plan(), notes(), section()])
    sb = ['<g id="scale" transform="translate(26 213)">']
    sb.append(line(0, 0, 50, 0, stroke="#111", sw=0.5, marker_start=True,
                   marker_end=True))
    for i in range(6):
        sb.append(line(i * 10, -1.2, i * 10, 1.2, stroke="#111", sw=0.4))
        sb.append(text(i * 10, 3.4, "0" if i == 0 else str(i * 10), size=1.8,
                       fill="#333"))
    sb.append(text(55, 0.8, "mm", size=2.2, fill="#333", anchor="start"))
    sb.append(text(0, -3.4,
                   "Drawing units are mm; print 300 mm wide for 1:1 (not to scale on screen).",
                   size=2.0, fill="#555", anchor="start"))
    sb.append("</g>")
    return head + body + "\n".join(sb) + "\n</svg>\n"


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.normpath(os.path.join(here, "..", "..", "docs", "diagrams",
                                        "medium-layout.svg"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(svg())
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""The box (docs/box-design.md) as boxes: every part an axis-aligned block, checked.

Each part is a block in the case's frame, in mm: x from the left inside wall, y from the
rear inside wall toward the player, z up from the base plate.  The script checks that no
two blocks share space unless the pair is listed as meant to (a socket on its board), prints
the smallest clearances, and draws a plan and a section.

    python3 enclosure/src/box_layout.py            # check, report, write the SVG
    rsvg-convert -w 1700 docs/diagrams/box-layout.svg -o docs/diagrams/box-layout.png

It exits non-zero if anything collides.  Numbers marked "est." are estimates to be replaced
from the maker's drawing when the part is chosen; the rest are from the drawings named beside
them or from the owner's measurements of 2026-11-14.  No third-party Python is needed.
"""

from __future__ import annotations

import os
import sys

W, D, H = 178.26, 110.26, 30.0     # inside; H measured by the owner
CX = W / 2

PARTS: list[dict] = []


def part(name, x0, x1, y0, y1, z0, z1, group, colour="#cccccc", note=""):
    PARTS.append(dict(name=name, x=(x0, x1), y=(y0, y1), z=(z0, z1), group=group,
                      colour=colour, note=note))


# --- the case -------------------------------------------------------------------
for i, (px, py) in enumerate([(5, 5), (CX, 5), (W - 5, 5), (5, D - 5), (CX, D - 5),
                              (W - 5, D - 5)]):
    part(f"pillar {i + 1}", px - 4, px + 4, py - 4, py + 4, 0, H, "case", "#d9d5c8")

# --- the screen and the Pi ---------------------------------------------------------
# Window 99 x 59, 10 from the left, 9 from the rear (the owner).  The module's own outline
# is not published, and it clears the corner pillars in the prototype, so only the window's
# own area is modelled, 7 mm thick.
part("screen module", 10, 109, 9, 68, 23, H, "pi", "#e3e0f7", "frame not modelled")
# Pi 5, 85 x 56 (Raspberry Pi's mechanical drawing), component side down.  Its left end is
# 26 mm from the left wall and its rear edge 10 mm from the rear wall, from the owner's
# measurements of the header plug.  Its board is 13 mm below the face (screen 7 + standoff 6).
PIX, PIY, PI_Z = 26.0, 10.0, H - 13.0 - 1.6          # PI_Z: the component face, 15.4
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
PB_TOP = PI_Z - 11.0                                   # 4.4: a HAT sits 11 mm from the Pi
part("Pi board", 12, 84, 2, 72, PB_TOP - 1.6, PB_TOP, "piboard", "#b9d6f2",
     "cut out around the heat block")
part("Pi board header socket", PIX + 6.5, PIX + 58.5, PIY + 49.5, PIY + 55.5, PB_TOP,
     PI_Z - 8.5 + 6.0, "piboard", "#7fb2e5")
part("USB-C power socket", 35.5, 44.5, 0, 7.5, PB_TOP, PB_TOP + 3.3, "piboard", "#7fb2e5")
part("MIDI socket (3.5 mm)", 71, 77, 0, 14, PB_TOP, PB_TOP + 5.0, "piboard", "#7fb2e5",
     "est.")

# --- the audio board -----------------------------------------------------------------
AB_TOP = 4.0
part("audio board", 115.5, 168.5, 2, 106, AB_TOP - 1.6, AB_TOP, "audio", "#bfe6d6")
part("audio board, mic tongue", 168.5, 177.5, 12, 98, AB_TOP - 1.6, AB_TOP, "audio",
     "#bfe6d6")
# 1/4-inch sockets: est. 16 wide, 12 tall, 23 behind the wall (Neutrik NMJ6HFD2's model).
for name, cx in (("out socket", 124.0), ("EXT FS socket", 141.5), ("guitar in socket", 159.0)):
    part(name, cx - 8, cx + 8, 0, 23, AB_TOP, AB_TOP + 12.0, "audio", "#6cc9a6", "size est.")
# Neutrik NCJ6FA-H (drawing 20004521): 25 x 25 behind the wall, 24.5 deep, its centre
# 12.5 above the board, pins 3.5 below the body.
MIC_Y = 47.0
part("mic combo socket", W - 24.5, W, MIC_Y - 12.5, MIC_Y + 12.5, AB_TOP, AB_TOP + 25.0,
     "audio", "#6cc9a6", "Neutrik NCJ6FA-H")

# --- the footswitches (the owner's part: 13 x 13 body, 29.7 with lugs, sunk 16 mm) -----
for i, fx in enumerate((CX - 69, CX, CX + 69)):
    part(f"footswitch {i + 1}", fx - 11, fx + 18.7, D - 29 - 6.5, D - 29 + 6.5, H - 16.0,
         H - 3.0, "fs", "#e8e4d6", "13 mm body with its top 3 mm below the face; lugs sideways")

# --- the controls on the face -------------------------------------------------------
ENC = (131.1, 27.1)                                    # the owner's position
part("control board and encoder", ENC[0] - 16, ENC[0] + 16, ENC[1] - 12, ENC[1] + 42,
     20.4, H, "control", "#f6dfb4", "board at z 21.9, EC11 body above it; est.")
part("button 2", 157.5, 172.5, 10.5, 25.5, 20.0, H, "control", "#f6dfb4",
     "10 mm deep; above the guitar socket")

# Pairs that are meant to touch or pass through each other.
ALLOWED = {
    frozenset(("heat block", "Pi board")),             # the cut-out
    frozenset(("Pi board header socket", "Pi header pins")),
}
SAME_GROUP_OK = {"pi", "piboard", "audio", "control", "case"}


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
         f'<text x="{ox}" y="22" font-size="15" fill="#222">The box: plan from above '
         f'(rear wall at top), and a section at x = 160 looking from the right</text>',
         f'<rect x="{ox}" y="{oy}" width="{n(W * S)}" height="{n(D * S)}" rx="8" fill="none" '
         f'stroke="#333" stroke-width="1.5"/>']
    order = {"case": 0, "piboard": 1, "audio": 1, "heat": 2, "pi": 3, "fs": 4, "control": 5}
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
              ("USB-C", 40, -1.5), ("MIDI", 74, -1.5), ("out", 124, -1.5), ("EXT FS", 141.5, -1.5),
              ("in", 159, -1.5), ("mic", 166, 48), ("audio board", 140, 98),
              ("encoder", 131, 28), ("FS1", 24, 82), ("FS2", 93, 82), ("FS3", 162, 82),
              ("B2", 165, 19), ("USB, Ethernet", 103.5, 40)]
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


def main():
    hits, near = check()
    out = inside()
    print(f"{len(PARTS)} parts in a {W} x {D} x {H} mm case")
    for name in out:
        print(f"OUTSIDE THE CASE: {name}")
    for a, b, o in hits:
        print(f"COLLISION: {a} / {b}: overlap {o[0]:.1f} x {o[1]:.1f} x {o[2]:.1f} mm")
    print("Tightest clearances (under 3 mm):")
    for gap, a, b, axis in near:
        print(f"  {gap:4.1f} mm in {axis}: {a} / {b}")
    for name, z in (("mic combo socket", None), ("guitar in socket", None)):
        p = next(q for q in PARTS if q["name"] == name)
        print(f"{name}: z {p['z'][0]:.1f}-{p['z'][1]:.1f}, {H - p['z'][1]:.1f} mm below the face")
    here = os.path.dirname(os.path.abspath(__file__))
    dst = os.path.join(here, "..", "..", "docs", "diagrams", "box-layout.svg")
    with open(dst, "w") as f:
        f.write(svg())
    print("wrote", os.path.normpath(dst))
    return 1 if hits or out else 0


if __name__ == "__main__":
    sys.exit(main())

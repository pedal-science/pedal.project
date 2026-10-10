#!/usr/bin/env python3
"""Board 1: the 9 V supply, the input buffer and the output stage, on Kemo E005 stripboard.

The whole circuit on one board: 50 x 14 of the Kemo board's holes, 124.5 x 33.0 mm used out of
its 100 x 160 mm, which does not fit the enclosure.  Board A (`stripboard/board_a.py`) is the
same circuit aimed at the enclosure and split across boards; this one is the breadboard's
soldered successor and stays as built.

The layout is data.  The netlist is not: it lives in `stripboard/nets.py`, shared with board A
and checked against the case schematic, and running this checks the layout against it --
every lead on the net it should be on, no two nets joined, nothing on a cut hole, no lead
under another part's body, everything inside the outline -- and writes two drawings: the
component side, and the copper side mirrored, which is what you see when you cut the tracks.

Coordinates are holes: x along the strips (0 at the left, seen from the component side),
y across them (row 0 at the top).  Turn the board so the strips run left to right.

    python3 stripboard/board1.py        # check, then write board1-*.svg beside this file
"""
import sys
from pathlib import Path

import nets as NET
import stripboard as SB

W, H = 50, 14  # the part of the board used: 50 holes along the strips, rows 0-13

# Cut holes: the track is broken at that hole, so it belongs to neither side.
CUTS = {
    (14, 1), (19, 1), (29, 1), (38, 1),
    (15, 2), (19, 2), (24, 2),
    (12, 3), (19, 3), (24, 3), (31, 3), (37, 3), (44, 3),
    (19, 4),
    (4, 6), (9, 6), (15, 6), (25, 6),
    (32, 8), (38, 8),
    (32, 12), (38, 12),
}

# Wire links on the component side: (from hole, to hole).
LINKS = [
    ((17, 1), (17, 2)),   # U1A follower: OUT A to -IN A
    ((22, 2), (22, 3)),   # U1B follower: OUT B to -IN B
    ((27, 1), (27, 3)),   # VF down to the bias chain
    ((40, 3), (40, 4)),   # the bias point onto the VB strip
    ((48, 3), (48, 5)),   # R4's ground end to the GND strip
    ((16, 4), (16, 5)),   # U1 pin 4's strip to the GND strip
    ((24, 6), (24, 4)),   # VB across to R6
    ((0, 0), (0, 5)),     # the two ground buses: GND_P to GND_A
    ((23, 5), (23, 10)),  # GND strip 5 to GND strip 10
    ((41, 8), (41, 10)),  # R8's ground end
    ((42, 12), (42, 10)), # R10's ground end
]

# Parts: ref -> (kind, value, [(hole, net), ...]).  The net names are the netlist's
# (`stripboard/nets.py`); the values are the netlist's too, and are checked against it.
# Lead order matters for polarised parts: electrolytics list + first, the diode lists its
# anode first, U1 lists pins 1-8 -- the same order the netlist numbers them in.
# kind sets the body drawn and checked: 'r' lying resistor, 'd' lying diode, 'film' box
# capacitor lying along the strip, 'cer' small ceramic, 'el' radial electrolytic (diameter
# in mm), 'dip8' the socket.
PARTS = {
    'D1': ('d', '1N5817', [((41, 1), 'V9_RAW'), ((36, 1), 'V9')]),
    'C1': ('el6.3', '100µF 25V', [((34, 1), 'V9'), ((34, 0), 'GND_P')]),
    'R1': ('r', '100Ω', [((32, 1), 'V9'), ((28, 1), 'VF')]),
    'C2': ('el6.3', '100µF 25V', [((25, 1), 'VF'), ((25, 0), 'GND_P')]),
    'C3': ('cer', '100nF', [((22, 1), 'VF'), ((22, 0), 'GND_P')]),
    'R2': ('r', '10k', [((29, 3), 'VF'), ((33, 3), 'BIAS_MID')]),
    'R3': ('r', '10k', [((35, 3), 'BIAS_MID'), ((39, 3), 'BIAS')]),
    'R4': ('r', '10k', [((42, 3), 'BIAS'), ((46, 3), 'GND_A')]),
    'C4': ('el5', '10µF 50V', [((30, 4), 'BIAS'), ((30, 5), 'GND_A')]),
    'U1': ('dip8', 'OPA2197 on adapter', [
        ((18, 1), 'LIN1'), ((18, 2), 'LIN1'), ((18, 3), 'IN_A'), ((18, 4), 'GND_A'),
        ((21, 4), 'BIAS'), ((21, 3), 'U1B'), ((21, 2), 'U1B'), ((21, 1), 'VF')]),
    'C5': ('film', '100nF film', [((3, 6), 'IN_RAW'), ((5, 6), 'IN_A')]),
    'R5': ('r', '330k', [((7, 6), 'IN_A'), ((11, 6), 'IN_B')]),
    'R6': ('r', '680k', [((13, 6), 'IN_B'), ((17, 6), 'BIAS')]),
    'C6': ('el6.3', '10µF bipolar', [((28, 7), 'HPL'), ((28, 8), 'OUT_L_N')]),
    'R7': ('r', '100Ω', [((30, 8), 'OUT_L_N'), ((34, 8), 'OUT_L')]),
    'R8': ('r', '1M', [((36, 8), 'OUT_L'), ((40, 8), 'GND_A')]),
    'C7': ('el6.3', '10µF bipolar', [((28, 11), 'HPR'), ((28, 12), 'OUT_R_N')]),
    'R9': ('r', '100Ω', [((30, 12), 'OUT_R_N'), ((34, 12), 'OUT_R')]),
    'R10': ('r', '1M', [((36, 12), 'OUT_R'), ((40, 12), 'GND_A')]),
}

# Wires leaving the board: label -> (hole, net, where it goes).  The switch is three pads
# rather than a part: the toggle bolts to the panel, so only its wires reach the board.
# U1.3 is where the switch's common lands, and the two throws tap R5 either side.
PADS = {
    'STAR': ((1, 5), 'GND_A', 'the star-ground tag (this board\'s one ground wire)'),
    '+9V': ((44, 1), 'V9_RAW', "the DC socket's +9 V contact"),
    'IN': ((1, 6), 'IN_RAW', 'input jack tip (screened cable core)'),
    'SW-I': ((17, 3), 'IN_A', 'Inst/Line switch, Inst throw: the buffer input (U1.3)'),
    'SW-L': ((12, 6), 'IN_B', 'Inst/Line switch, Line throw (past R5)'),
    'SW-C': ((6, 6), 'IN_A', 'Inst/Line switch, common: across C5, at the tip'),
    'LIN1': ((15, 1), 'LIN1', 'codec board LIN1 (right-hand row)'),
    'HPL': ((25, 7), 'HPL', 'codec board HPL'),
    'HPR': ((25, 11), 'HPR', 'codec board HPR'),
    'OUT-L': ((35, 8), 'OUT_L', 'OUT L jack tip'),
    'OUT-R': ((35, 12), 'OUT_R', 'OUT R jack tip'),
}


# Drawing ------------------------------------------------------------------
def svg(mirror):
    """Board 1's drawings, the format the build sheet has always shown.

    The layout is generic (`stripboard.py` draws wire stubs from the pads); board 1 keeps its
    own house style here, so its two published pictures are unchanged by the netlist move."""
    s = SB.Sheet(W, H, mirror=mirror)
    X, Y = s.X, s.Y
    w, h = s.w, s.h
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" '
         f'height="{h}" font-family="system-ui,sans-serif">',
         f'<rect width="{w}" height="{h}" fill="#f7f3ea"/>']

    for y in range(H):
        runs, start = [], None
        for x in range(W + 1):
            if x < W and (x, y) not in CUTS:
                start = x if start is None else start
            elif start is not None:
                runs.append((start, x - 1))
                start = None
        for a, b in runs:
            x1, x2 = sorted((X(a), X(b)))
            o.append(f'<rect x="{x1 - 9}" y="{Y(y) - 8}" width="{x2 - x1 + 18}" height="16" rx="3" '
                     f'fill="#d9a066" opacity="{0.9 if mirror else 0.35}"/>')
    for x in range(W):
        for y in range(H):
            o.append(f'<circle cx="{X(x)}" cy="{Y(y)}" r="2.6" fill="#3b2a1a"/>')
    for (x, y) in CUTS:
        o.append(f'<g stroke="#c00" stroke-width="3"><line x1="{X(x) - 7}" y1="{Y(y) - 7}" '
                 f'x2="{X(x) + 7}" y2="{Y(y) + 7}"/><line x1="{X(x) - 7}" y1="{Y(y) + 7}" '
                 f'x2="{X(x) + 7}" y2="{Y(y) - 7}"/></g>')
    for x in range(0, W, 5):
        o.append(f'<text x="{X(x)}" y="{M_}" font-size="12" text-anchor="middle" fill="#333">{x}</text>')
    for y in range(H):
        o.append(f'<text x="{40 - 26 if not mirror else w - 40 + 26}" y="{Y(y) + 4}" font-size="12" '
                 f'text-anchor="middle" fill="#333">{y}</text>')
    if not mirror:
        for a, b in LINKS:
            o.append(f'<line x1="{X(a[0])}" y1="{Y(a[1])}" x2="{X(b[0])}" y2="{Y(b[1])}" '
                     f'stroke="#1a5fb4" stroke-width="3.5" stroke-linecap="round"/>')
        for ref, (kind, val, leads) in PARTS.items():
            pts = [(X(hx), Y(hy)) for (hx, hy), _ in leads]
            if kind == 'dip8':
                x1, y1 = X(18) - 8, Y(1) - 10
                o.append(f'<rect x="{x1}" y="{y1}" width="{3 * SB.P + 16}" height="{3 * SB.P + 20}" rx="4" '
                         f'fill="#222" opacity=".85"/>')
                o.append(f'<circle cx="{X(18) + 6}" cy="{Y(1) - 2}" r="3" fill="#fff"/>')
                o.append(f'<text x="{X(19) + SB.P / 2}" y="{Y(2) + SB.P / 2 + 4}" font-size="11" '
                         f'text-anchor="middle" fill="#fff" font-weight="700">U1</text>')
                for i, (px, py) in enumerate(pts):
                    o.append(f'<text x="{px + (-12 if i < 4 else 12)}" y="{py + 4}" font-size="9" '
                             f'text-anchor="middle" fill="#fff">{i + 1}</text>')
                continue
            if kind.startswith('el'):
                d = float(kind[2:]) / 2.54 * SB.P
                cx, cy = (pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2
                o.append(f'<circle cx="{cx}" cy="{cy}" r="{d / 2}" fill="#2c3e8f" opacity=".8"/>')
                if 'bipolar' not in val:
                    o.append(f'<text x="{pts[0][0] + 9}" y="{pts[0][1] + 4}" font-size="12" fill="#fff" '
                             f'font-weight="800">+</text>')
                o.append(f'<text x="{cx + d / 2 + 3}" y="{cy + 4}" font-size="11" font-weight="700" '
                         f'fill="#111">{ref}</text>')
                continue
            (x1, y1), (x2, y2) = pts
            col = {'r': '#c8b27d', 'd': '#222', 'film': '#b33', 'cer': '#d68910'}[kind]
            o.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#777" stroke-width="2"/>')
            if kind == 'cer':
                o.append(f'<circle cx="{(x1 + x2) / 2}" cy="{(y1 + y2) / 2}" r="7" fill="{col}"/>')
            else:
                horiz = y1 == y2
                L = abs(x2 - x1) if horiz else abs(y2 - y1)
                bl, bw = max(L - 16, 14), 11
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                if horiz:
                    o.append(f'<rect x="{cx - bl / 2}" y="{cy - bw / 2}" width="{bl}" height="{bw}" rx="4" fill="{col}"/>')
                else:
                    o.append(f'<rect x="{cx - bw / 2}" y="{cy - bl / 2}" width="{bw}" height="{bl}" rx="4" fill="{col}"/>')
                if kind == 'd':  # cathode band
                    kx = x2 + (8 if x1 > x2 else -8) if horiz else x2
                    o.append(f'<rect x="{kx - 2}" y="{cy - bw / 2}" width="4" height="{bw}" fill="#ddd"/>')
            lx, ly = (x1 + x2) / 2, min(y1, y2) - 10
            o.append(f'<text x="{lx}" y="{ly}" font-size="11" font-weight="700" text-anchor="middle" '
                     f'fill="#111">{ref} {val}</text>')
        for label, ((hx, hy), net, _) in PADS.items():
            o.append(f'<circle cx="{X(hx)}" cy="{Y(hy)}" r="6" fill="none" stroke="#0a7d3b" stroke-width="3"/>')
            o.append(f'<text x="{X(hx)}" y="{Y(hy) + 20}" font-size="11" font-weight="800" '
                     f'text-anchor="middle" fill="#0a7d3b">{label}</text>')
    title = ('COPPER SIDE (mirrored): cut the tracks at the red crosses' if mirror
             else 'COMPONENT SIDE: parts, blue wire links, green off-board wires, red cuts')
    o.append(f'<text x="40" y="{h - 12}" font-size="15" font-weight="800" fill="#111">'
             f'Board 1 · {title}</text>')
    o.append('</svg>')
    return '\n'.join(o)


M_ = 40


if __name__ == '__main__':
    # IN_A is in two pieces on the board: U1.3's strip (SW-I) and the input network's (SW-C,
    # C5.2, R5.1).  There is no room for a link between row 3 and row 6 without crossing the
    # two ground buses, and the switch is the part that joins them anyway -- its throw and its
    # common are one node when the lever is at Inst.
    errs, info = SB.check(W, H, CUTS, LINKS, PARTS, PADS, off_board={'IN_A'},
                          carries=set(NET.PARTS))
    for e in errs:
        print('ERROR', e)
    if errs:
        sys.exit(1)
    here = Path(__file__).parent
    (here / 'board1-components.svg').write_text(svg(False))
    (here / 'board1-copper.svg').write_text(svg(True))
    mm = info['mm']
    print(f'ok: {len(PARTS)} parts, {len(LINKS)} links, {len(CUTS)} cuts, {len(PADS)} wires; '
          f'{info["cols"]}x{info["rows"]} holes = {mm[0]:.2f} x {mm[1]:.2f} mm; '
          f'drawings written')

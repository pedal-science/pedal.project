#!/usr/bin/env python3
"""Board A: the analogue board -- the input buffer, the bias and the output stage.

Board 1 (`stripboard/board1.py`) is the same circuit on one 124 x 33 mm piece of stripboard and
does not fit the enclosure.  Board A is that circuit for the enclosure, and it is **not the
whole analogue side on one plate**.  The split is by what the noise argues for, and every board
returns to the star tag on its own wire:

  * **board A** (this file): the input, the buffer, the bias and the output stage -- everything
    the signal touches, and nothing that switches or rectifies;
  * **the codec's breakout**: its own standoffs above board A, its ground on its own wire to
    the star (see "Why the codec is not on board A" below);
  * **the power board**: the 9 V input, D1, the bulk capacitance, R1/C2 and the 78L33 for the
    codec's AVDD -- the supply's currents, kept off board A's ground.  2a measured the codec at
    -93.5 dBFS(A) (about 21 uV A-weighted) on the bench, and 2b read the 90 Hz comb that a
    second ground path adds: the ground, not the LDO, is what the numbers limit;
  * **the control board** (board B in the enclosure): the Pico, MIDI and the relay driver --
    the switching `docs/build-board1.md` keeps off the analogue ground.

## Why the codec is not on board A

It was: `enclosure/src/layout.py` seats its two 16-pin socket strips on board A at hole (1, 2),
which takes columns 1 and 10 for rows 2-17 out of the 18 x 20 holes board A has.  With those
holes gone, a search over placements and routings -- greedy first, then a backtracking router --
found **no layout that closes**: the analogue stage plus the wires between it and the strips do
not fit in what is left.  The codec on its own standoffs, its pads on short fly leads and its
ground on its own wire to the star, is at least as good for noise (the analogue return is one
wire to the star either way, and 2a's comb was a *second* ground path, which this does not add)
and it is what makes the board close.  It is the variant this file builds.

The netlist is `stripboard/nets.py`, shared with board 1 and the case schematic.  Running this
checks the layout against it and writes three drawings:

    board_a-copper.svg      the copper side, mirrored, with the cuts
    board_a-components.svg  the component side: parts, links and the wires
    board_a-wiring.svg      what leaves the board, and where it goes

    python3 stripboard/board_a.py
"""
import sys
from pathlib import Path

import nets as NET
import stripboard as SB

W, H = 18, 20            # 45.72 x 50.8 mm: the enclosure's board A (enclosure/src/layout.py)

# U1's socket: pins 1-4 down column 4, 5-8 up column 7 (the socket's default orientation,
# notch towards row 5).  A column of four pins is four strips, and where two pins of
# different nets would share a strip the track is cut *between* them -- which is what a 3 mm
# spot-face cutter does when it is turned between two holes, and which strands neither pin.
U1X, U1Y = 4, 5
U1 = [(U1X, U1Y + i) for i in range(4)] + [(U1X + 3, U1Y + 3 - i) for i in range(4)]

CUTS = {
    (4.5, 5),                # U1.1, U1.2 (LIN1) from U1.8 (VF)
    (4.5, 6),                # U1.2 (LIN1) from U1.7 (U1B)
    (4.5, 7),                # U1.3 (IN_A) from U1.6 (U1B)
    (4.5, 8),                # U1.4 (GND_A) from U1.5 (BIAS)
    (10.5, 0),               # the input network: the tip from IN_A
    (11.5, 2),               # the input network: IN_A from IN_B
    (12.5, 9), (15.5, 9),    # the bias chain: BIAS_MID from BIAS, and BIAS from GND_A
    (11.5, 12),              # the codec's HPL from HPR
    (12.5, 13),              # the output stage: OUT_L_N from the ground row
    (2.5, 14), (3.5, 14),    # the left channel's ground end
    (12.5, 14), (13.5, 14),  # the right channel's ground end
}

LINKS = [
    # LIN1: U1.1 and U1.2 out, down column 2, to the codec's pad
    ((3, 5), (4, 5)), ((3, 5), (3, 6)), ((3, 6), (4, 6)),
    ((3, 5), (2, 5)), ((2, 5), (2, 9)), ((2, 9), (10, 9)),
    # IN_A: U1.3 out to the input network
    ((5, 7), (5, 4)), ((5, 4), (8, 4)), ((8, 4), (8, 1)), ((8, 1), (11, 1)),
    ((11, 1), (12, 1)), ((12, 1), (12, 2)), ((12, 2), (12, 3)),
    # IN_RAW: the tip, C5 and the switch's Inst throw
    ((11, 0), (10, 0)),
    # GND_A: U1.4 out, and R6/R4/R3's ground ends
    ((5, 8), (5, 10)), ((5, 10), (5, 11)), ((5, 11), (8, 11)) if False else ((5, 11), (7, 11)),
    ((7, 11), (7, 18)), ((7, 18), (7, 19)),
    # U1B: U1.7 and U1.6 out
    ((7, 7), (8, 7)) if False else ((7, 6), (7, 7)), ((8, 7), (8, 8)), ((8, 8), (8, 9)),
    # VF: U1.8 out to its rail
    ((8, 5), (9, 5)), ((9, 5), (17, 5)), ((17, 5), (17, 0)),
    # the bias chain: BIAS_MID and BIAS joined, and the chain's bottom to GND_A
    ((13, 9), (13, 6)), ((13, 6), (13, 5)), ((13, 5), (12, 5)),
    # HPL, HPR, V3A3 and the codec's ground
    ((10, 14), (11, 14)), ((11, 14), (11, 12)), ((11, 12), (10, 12)),
    ((11, 13), (10, 13)), ((11, 15), (10, 15)), ((11, 16), (10, 16)),
]

PARTS = {
    'U1':  ('dip8', 'OPA2197 on adapter', [
        (U1[0], 'LIN1'), (U1[1], 'LIN1'), (U1[2], 'IN_A'), (U1[3], 'GND_A'),
        (U1[4], 'BIAS'), (U1[5], 'U1B'), (U1[6], 'U1B'), (U1[7], 'VF')]),
    'C5':  ('film', '100nF film', [((10, 0), 'IN_RAW'), ((10, 2), 'IN_A')]),
    'R5':  ('r', '330k', [((8, 2), 'IN_A'), ((8, 6), 'IN_B')]),
    'R6':  ('r', '680k', [((8, 7), 'IN_B'), ((8, 11), 'BIAS')]),
    'C3':  ('cer', '100nF', [((14, 0), 'VF'), ((14, 1), 'GND_A')]),
    'C4':  ('el5', '10µF 50V', [((17, 1), 'BIAS'), ((17, 2), 'GND_A')]),
    'R2':  ('r', '10k', [((13, 2), 'VF'), ((13, 6), 'BIAS_MID')]),
    'R3':  ('r', '10k', [((13, 7), 'BIAS_MID'), ((13, 11), 'BIAS')]),
    'R4':  ('r', '10k', [((14, 2), 'BIAS'), ((14, 6), 'GND_A')]),
    'C6':  ('el6.3', '10µF bipolar', [((2, 13), 'HPL'), ((2, 15), 'OUT_L_N')]),
    'R7':  ('r', '100Ω', [((1, 15), 'OUT_L_N'), ((1, 19), 'OUT_L')]),
    'R8':  ('r', '1M', [((4, 15), 'OUT_L'), ((4, 19), 'GND_A')]),
    'C7':  ('el6.3', '10µF bipolar', [((12, 13), 'HPR'), ((12, 15), 'OUT_R_N')]),
    'R9':  ('r', '100Ω', [((11, 15), 'OUT_R_N'), ((11, 19), 'OUT_R')]),
    'R10': ('r', '1M', [((14, 15), 'OUT_R'), ((14, 19), 'GND_A')]),
}

PADS = {
    'IN':    ((11, 0), 'IN_RAW', "the input jack's tip, through the screened cable's core"),
    'SW-I':  ((12, 0), 'IN_RAW', 'Inst/Line switch, Inst throw (no padding)'),
    'SW-C':  ((11, 2), 'IN_A', 'Inst/Line switch, common: the top of R5 (the buffer input)'),
    'SW-L':  ((9, 2), 'IN_B', 'Inst/Line switch, Line throw: past R5 (the 0.33 pad)'),
    'LIN1':  ((10, 9), 'LIN1', "the codec's LIN1 pad, on a fly lead from its own standoffs"),
    'HPL':   ((10, 12), 'HPL', "the codec's HPL pad"),
    'HPR':   ((10, 13), 'HPR', "the codec's HPR pad"),
    'CGND':  ((10, 16), 'GND_A', "the codec's GND pad -- its own wire back to the star"),
    'V3A3':  ((10, 15), 'V3A3', "the codec's AVDD pad, from the power board's 78L33"),
    'OUT-L': ((3, 19), 'OUT_L', 'OUT L jack tip'),
    'OUT-R': ((13, 19), 'OUT_R', 'OUT R jack tip'),
    'STAR':  ((7, 19), 'GND_A', 'the star-ground tag'),
    'VF':    ((17, 0), 'VF', "the power board's filtered 9 V"),
    'V9':    ((17, 19), 'V9_RAW', "the power board's +9 V"),
}

CARRIES = {'C5', 'R5', 'R6', 'U1', 'C3', 'C4', 'R2', 'R3', 'R4',
           'C6', 'R7', 'R8', 'C7', 'R9', 'R10'}


# Drawing ---------------------------------------------------------------------------------
def draw():
    """The three drawings: copper with the cuts, the components, and the wires.

    Each part is its body, its reference and its value on a small light plate so the text
    stays readable over the strips; the links are the wires on the component side; the wires
    that leave the board are labelled stubs, so the picture and the build sheet are one."""
    here = Path(__file__).parent

    s = SB.Sheet(W, H, mirror=True)
    s.frame(CUTS)
    s.save(here / 'board_a-copper.svg',
           'Board A · COPPER SIDE (mirrored) · cut the tracks at the red bars')

    s = SB.Sheet(W, H)
    s.frame(CUTS)
    s.links(LINKS)
    for ref, (kind, val, leads) in PARTS.items():
        pts = [(s.X(h[0]), s.Y(h[1])) for h, _ in leads]
        col = {'r': '#c8b27d', 'd': '#222', 'film': '#b33',
               'cer': '#d68910'}.get(kind, '#2c3e8f')
        if kind == 'dip8':
            s.o.append(f'<rect x="{pts[0][0] - 8}" y="{pts[0][1] - 10}" '
                       f'width="{3 * SB.P + 16}" height="{3 * SB.P + 20}" rx="4" '
                       f'fill="#222" opacity=".85"/>')
            s.o.append(f'<circle cx="{pts[0][0] + 6}" cy="{pts[0][1] - 2}" r="3" fill="#fff"/>')
            tx, ty = pts[0][0] + SB.P * 1.5, pts[0][1] + SB.P * 1.5
        else:
            (x1, y1), (x2, y2) = pts
            s.o.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#777" '
                       f'stroke-width="2"/>')
            if kind.startswith('el'):
                d = float(kind[2:]) / 2.54 * SB.P
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                s.o.append(f'<circle cx="{cx}" cy="{cy}" r="{d / 2}" fill="{col}" '
                           f'opacity=".85"/>')
            elif kind == 'cer':
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                s.o.append(f'<circle cx="{cx}" cy="{cy}" r="7" fill="{col}"/>')
            else:
                horiz = y1 == y2
                L = abs(x2 - x1) if horiz else abs(y2 - y1)
                bl, bw = max(L - 16, 14), 11
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                if horiz:
                    s.o.append(f'<rect x="{cx - bl / 2}" y="{cy - bw / 2}" width="{bl}" '
                               f'height="{bw}" rx="4" fill="{col}"/>')
                else:
                    s.o.append(f'<rect x="{cx - bw / 2}" y="{cy - bl / 2}" width="{bw}" '
                               f'height="{bl}" rx="4" fill="{col}"/>')
            tx, ty = (x1 + x2) / 2 + 26, (y1 + y2) / 2 + 4
        label = f'{ref} {val}'
        w = 6.4 * len(label) + 10
        s.o.append(f'<rect x="{tx - w / 2}" y="{ty - 11}" width="{w}" height="16" rx="3" '
                   f'fill="#f7f3ea" opacity=".92"/>')
        s.o.append(f'<text x="{tx}" y="{ty + 1}" font-size="11" font-weight="700" '
                   f'text-anchor="middle" fill="#111">{label}</text>')
    for label, ((hx, hy), net, _) in PADS.items():
        s.o.append(f'<circle cx="{s.X(hx)}" cy="{s.Y(hy)}" r="6" fill="none" '
                   f'stroke="#0a7d3b" stroke-width="3"/>')
        s.o.append(f'<text x="{s.X(hx)}" y="{s.Y(hy) - 11}" font-size="11" '
                   f'font-weight="800" text-anchor="middle" fill="#0a7d3b">{label}</text>')
    s.save(here / 'board_a-components.svg',
           'Board A · COMPONENT SIDE · parts, links, wires, cuts')

    s = SB.Sheet(W, H, tw=300)
    s.frame(CUTS)
    for row, (label, ((hx, hy), net, _)) in enumerate(
            sorted(PADS.items(), key=lambda kv: kv[1][0])):
        col = SB.NETCOL.get(net, '#0a7d3b')
        x, y = s.X(hx), s.Y(hy)
        tx, ty = s.w - 14, SB.M + row * 26
        s.o.append(f'<path d="M {x} {y} L {x + 30} {y} L {tx - 40} {ty} L {tx} {ty}" '
                   f'fill="none" stroke="{col}" stroke-width="2" stroke-dasharray="6 4"/>')
        s.o.append(f'<text x="{tx - 4}" y="{ty + 4}" font-size="12" font-weight="700" '
                   f'text-anchor="end" fill="{col}">{label} · {net}</text>')
    s.save(here / 'board_a-wiring.svg',
           'Board A · WIRING · every wire that leaves the board')


def main():
    errs, info = SB.check(W, H, CUTS, LINKS, PARTS, PADS, carries=CARRIES)
    for e in errs:
        print('ERROR', e)
    if errs:
        draw()
        print('drawings written for the placement as it stands; the errors above are what is '
              'still wrong')
        return 1
    draw()
    mm = info['mm']
    print(f'ok: {len(PARTS)} parts, {len(LINKS)} links, {len(CUTS)} cuts, {len(PADS)} wires; '
          f'{info["cols"]}x{info["rows"]} holes = {mm[0]:.2f} x {mm[1]:.2f} mm; '
          f'the three drawings are written')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

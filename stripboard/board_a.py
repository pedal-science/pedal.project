#!/usr/bin/env python3
"""Board A: the analogue board -- the input buffer, the bias and the output stage.

STATUS, 2026-10-10: **placed to the corridor plan; the connectivity is not closed.**

Corridor-first worked where area did not.  `board_a-corridors.svg` decides which rows and
columns are wire-only -- IN_A alone at column 13 (the short high-impedance run, into the pin
beside it), the ground return at 14, the low-impedance trunk at 11, the codec's pads at 10 --
and the parts were then fitted into the bands between them.  The result is that this
placement has **no geometric errors at all**: no overlaps, nothing off the board, nothing
under another part's body, no lead in a corridor.  Three placement attempts and a change of
outline could not achieve that; deciding the corridors first did.

What is left is the connectivity: the nets the cuts leave in more than one piece, and the
strips that still need a cut between two nets.  The parts are where they should be, which is
the part that was failing.

Previous status follows.

**The connectivity is not closed.**  The outline is 18 x 24 holes
(45.72 x 60.96 mm), taller than the enclosure's plate, and the parts are placed.  What is
still wrong is reported when this runs: a handful of geometric collisions (a capacitor body
over a neighbouring lead) and the nets the cuts leave in more than one piece.  The drawings
are written anyway so the board can be looked at.

Three things were established and are worth keeping:

  * **The codec is not seated on board A.**  It stands above the board on its own taller
    standoffs and comes down on short fly leads (enclosure/src/bl_pedal.py, CODEC_STANDOFF).
    Seating its two 16-pin socket strips takes columns 1 and 10 for rows 2-17, and with those
    holes gone no placement of the analogue stage could be routed -- greedy 0 of 3000,
    backtracking 0 of 4222.  Moving the codec clear of board A instead puts a 55 mm lead on
    its *input* side, which is the one thing this placement exists to prevent.
  * **Growing the outline did not close it.**  18 x 20, 20 x 20, 22 x 20, 18 x 26, 18 x 30,
    22 x 26 and 22 x 30 were all tried, each for a bounded time, and none routed.  The board
    is not short of area: what it is short of is free *rows and columns* between the parts,
    which is a placement problem, not a size one.  The extra height to 18 x 24 did buy the
    output stage its own band clear of the codec's pads, which is why the outline is this one.
  * **A router that cannot route board 1 tells you about the router.**  Both search tools were
    validated against board 1, which is built and working, and neither could route it, so
    neither is trusted to say a layout is impossible.  Both were removed from the tree.

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

W, H = 18, 24            # 45.72 x 60.96 mm: taller than the enclosure's plate, because the
                         # analogue stage does not close on 18 x 20 (docs/board-a-netlist.md)

# U1's socket: pins 1-4 down column 4, 5-8 up column 7 (the socket's default orientation,
# notch towards row 5).  A column of four pins is four strips, and where two pins of
# different nets would share a strip the track is cut *between* them -- which is what a 3 mm
# spot-face cutter does when it is turned between two holes, and which strands neither pin.
U1X, U1Y = 4, 6
U1 = [(U1X, U1Y + i) for i in range(4)] + [(U1X + 3, U1Y + 3 - i) for i in range(4)]

# U1's socket, stood upright: pins 1-4 down column 12, 5-8 up column 15.  Its two pin columns
# are the two things that want a corridor each: pin 3 is the high-impedance node, which must
# reach the switch taps in the shortest run the board allows, and pins 1-2 are the buffer's
# output, which is low impedance and may go the long way.
U1X, U1Y = 12, 5
U1 = [(U1X, U1Y + i) for i in range(4)] + [(U1X + 3, U1Y + 3 - i) for i in range(4)]

CUTS = {
    # the socket's columns: pins that share a strip and are on different nets are separated
    # by a cut *between* two holes, which strands neither pin.
    (12, 5.5), (12, 6.5), (12, 7.5),
    (15, 5.5), (15, 6.5), (15, 7.5),
    # the input network
    (16.5, 1), (16.5, 2),
    # the bias chain
    (15.5, 3), (15.5, 4), (15.5, 6), (15.5, 7), (15.5, 13), (16.5, 13),
    # the output stage
    (1.5, 20), (3.5, 21), (2.5, 21), (4.5, 19), (4.5, 20), (5.5, 21), (6.5, 21),
    (15.5, 20), (15.5, 21), (16.5, 21),
}

LINKS = []
PARTS = {
    'U1':  ('dip8', 'OPA2197 on adapter', [
        (U1[0], 'LIN1'), (U1[1], 'LIN1'), (U1[2], 'IN_A'), (U1[3], 'GND_A'),
        (U1[4], 'BIAS'), (U1[5], 'U1B'), (U1[6], 'U1B'), (U1[7], 'VF')]),
    # the input network, in the rear right band beside the jack
    'C5':  ('film', '100nF film', [((17, 0), 'IN_RAW'), ((17, 2), 'IN_A')]),
    'R5':  ('r', '330k', [((17, 3), 'IN_A'), ((17, 7), 'IN_B')]),
    'R6':  ('r', '680k', [((17, 8), 'IN_B'), ((17, 12), 'BIAS')]),
    # the bias chain, in the right band below it
    'C3':  ('cer', '100nF', [((16, 3), 'VF'), ((16, 4), 'GND_A')]),
    'C4':  ('el5', '10µF 50V', [((14, 3), 'BIAS'), ((14, 4), 'GND_A')]),
    'R2':  ('r', '10k', [((17, 13), 'VF'), ((17, 17), 'BIAS_MID')]),
    'R3':  ('r', '10k', [((16, 13), 'BIAS_MID'), ((16, 17), 'BIAS')]),
    'R4':  ('r', '10k', [((16, 18), 'BIAS'), ((16, 22), 'GND_A')]),
    # the output stage, in the front band
    'C6':  ('el6.3', '10µF bipolar', [((1, 15), 'HPL'), ((1, 17), 'OUT_L_N')]),
    'R7':  ('r', '100Ω', [((1, 19), 'OUT_L_N'), ((1, 23), 'OUT_L')]),
    'R8':  ('r', '1M', [((3, 19), 'OUT_L'), ((3, 23), 'GND_A')]),
    'C7':  ('el6.3', '10µF bipolar', [((5, 15), 'HPR'), ((5, 17), 'OUT_R_N')]),
    'R9':  ('r', '100Ω', [((5, 19), 'OUT_R_N'), ((5, 23), 'OUT_R')]),
    'R10': ('r', '1M', [((7, 19), 'OUT_R'), ((7, 23), 'GND_A')]),
}

PADS = {
    'IN':    ((15, 0), 'IN_RAW', "the input jack's tip, through the screened cable's core"),
    'SW-I':  ((16, 0), 'IN_RAW', 'Inst/Line switch, Inst throw (no padding)'),
    'SW-C':  ((16, 1), 'IN_A', 'Inst/Line switch, common: the top of R5 (the buffer input)'),
    'SW-L':  ((16, 2), 'IN_B', 'Inst/Line switch, Line throw: past R5 (the 0.33 pad)'),
    'LIN1':  ((10, 8), 'LIN1', "the codec's LIN1 pad, on a fly lead from its own standoffs"),
    'HPL':   ((10, 10), 'HPL', "the codec's HPL pad"),
    'HPR':   ((10, 12), 'HPR', "the codec's HPR pad"),
    'V3A3':  ((10, 14), 'V3A3', "the codec's AVDD pad, from the power board's 78L33"),
    'CGND':  ((10, 15), 'GND_A', "the codec's GND pad -- its own wire back to the star"),
    'OUT-L': ((2, 22), 'OUT_L', 'OUT L jack tip'),
    'OUT-R': ((12, 22), 'OUT_R', 'OUT R jack tip'),
    'STAR':  ((9, 22), 'GND_A', 'the star-ground tag'),
    'VF':    ((16, 11), 'VF', "the power board's filtered 9 V"),
    'V9':    ((17, 20), 'V9_RAW', "the power board's +9 V"),
}

CARRIES = {'C5', 'R5', 'R6', 'U1', 'C3', 'C4', 'R2', 'R3', 'R4',
           'C6', 'R7', 'R8', 'C7', 'R9', 'R10'}


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

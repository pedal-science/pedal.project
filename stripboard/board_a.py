#!/usr/bin/env python3
"""Board A: the analogue board -- the input buffer, the bias and the output stage.

STATUS, 2026-10-10: **the placement carries the spare-hole rule and the exits rule; it does
not pass the exits rule, and the runs are not wired.**

The exits rule is the new one, and it is the answer this pass was for: a placement can have a
free hole beside every lead and still be impossible to wire, because the wire that would use
that hole cannot *get* there.  `stripboard/_place.py` now asks the router's own question before
the routing -- can a wire reach every piece of every net? -- and this placement fails it on
**IN_A, IN_B, GND_A, HPL, HPR, OUT_L_N and OUT_R_N**.  The details are below.  The parts are
where the last pass left them; what changed is that the board can now be *asked*.

Two things happened in this pass, and the first is the more useful.

**A defect in the checker.**  `stripboard.copper` unioned holes along a row and, through the
links, between rows -- but never *within* a column.  On this board that meant two things were
invisible: a part lying down a column (a resistor's two leads are in different rows, and the
part's own body joins the two strips) was never credited with joining them, and nothing could
ever be reported as shorted down a column.  `board1.py` -- built, measured and working -- now
checks out with the same numbers as before, so the fix reads the board the way the board is:
**a part that bridges two rows is unioned like a link, a socket's pins are not, and a link may
only be soldered where its own net already is.**  The last of those is new rule 3b: a wire end
joins the hole's piece of strip, so a wire ending in a hole on another net's strip is a short
that the union-find by itself cannot see, because the union it makes is what hides it.

**The placement, moved to satisfy the rule the routing kept asking for.**  Every lead and pad
hole now has a hole beside it that a wire may end in (`_place.py` measures this), and no two
neighbouring leads of different parts are on different nets.  The output stage is what moved:
its six parts stand in one band at row 16 -- C6 at x=0, C7 at x=3, the two 100 ohm resistors at
x=5 and x=7, the 1M resistors at x=12 and x=14 -- with the input chain's lower half at x=8.
The old placement had **three** leads with no hole beside them at all: C6.2 and C7.2, each
boxed in by its own neighbour's body, and R9.2 on the bottom edge with both gaps beside it cut.
No cut and no link could have freed any of them, which is why three routing attempts failed on
a placement that had no geometric errors.

What that cost: **nothing in area.**  The outline is unchanged at 18 x 24 holes
(45.72 x 60.96 mm).  It did cost the two 10 uF input capacitors their place at the board's
left edge, where they had been, and it moved the input chain's lower half from x=7 to x=8.

What is still open: **the runs are not wired, and running the exits rule says why.**  With the
cuts this placement needs -- 27 of them, derived per net by isolating each net's own span in a
row, and every one of the 27 is *load-bearing*: the checker reports a short if any single one
is removed -- the checker reports **12 nets in more than one piece and no two nets joined**.
The placement is legal and the copper is sound.

The exits rule is now in `_place.py`, and it is the router's own question asked in advance:
for each net, can a wire -- running only over free holes, and ending in a lead or in the free
hole beside a pad -- reach every piece of the net?  It says this placement **cannot be wired**,
and not because the router ran out of room.  The pieces are walled off from one another by the
cuts and by the neighbouring parts:

  * **IN_B** -- R5.2 at (8,7) reaches (9,7) and the row-7 dead end; R6.1 at (8,9) reaches
    (9,9); the switch's pad at (9,4) reaches (10,4).  Three pieces, three separate spaces.
    No cut can be removed to help: every one of the 27 is load-bearing;
  * **IN_A** -- U1.3 at (12,9) has exactly one free hole beside it, (11,9), and the wire that
    uses it comes down column 11, which dead-ends on row 1;
  * **HPL and HPR** -- C6.1 at (0,16) and C7.1 at (3,16) have one free hole each, (0,15) and
    (3,15), and row 15 carries **GND_A** (the cut at (17,4) and the C4/R4/BIAS row make it so).
    A wire cannot end on another net's copper, so the band's two coupling capacitors are sealed
    against the row that is their only way out -- which is the exits rule's whole point;
  * **GND_A** -- seven pieces and six separate spaces, and the codec's ground pad CGND at
    (10,15) can reach only (10,16), which carries OUT_L;
  * **OUT_L_N and OUT_R_N** -- their only way down the left of the board is column 0 and
    column 3, and row 21 is `V9_RAW` from end to end, so the wire's end lands on another net;
  * **V9_RAW** is a net with one pad and no other hole on the board, and that pad sits on the
    whole row the output wires need.

**7 of the 12 splits are GND_A**, which is the net the ground plan expects to be the hardest:
every part's return wants its own wire to the star, and the star is on the bottom edge, so
every return runs the length of a board whose middle rows are the parts.  That is a placement
question rather than a wiring one, exactly as this file argued before: the board needs each
net's *path* decided before the parts are fixed in place, and the exits rule is the first tool
that can say whether a placement has one.

Everything below is the reasoning that led here.

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
    (1.5, 16), (1.5, 17), (4.0, 16), (6.0, 16), (9.5, 16), (13.0, 16),
    (6.0, 20), (9.5, 20),
    (5.5, 2), (5.5, 3), (4.0, 10), (7.5, 9), (7.5, 10), (11.0, 10),
    (4.0, 14), (7.5, 14),
    (10.0, 7), (10.0, 9), (13.5, 7), (13.5, 8), (13.5, 9), (13.5, 10), (13.5, 12),
    (13.0, 4), (12.5, 3),
    (3.5, 23), (8.5, 23),
}

LINKS = []
PARTS = {
    'U1':  ('dip8', 'OPA2197 on adapter', [
        ((12, 7), 'LIN1'), ((12, 8), 'LIN1'), ((12, 9), 'IN_A'), ((12, 10), 'GND_A'),
        ((15, 10), 'BIAS'), ((15, 9), 'U1B'), ((15, 8), 'U1B'), ((15, 7), 'VF')]),
    'C5':  ('film', '100nF film', [((8, 0), 'IN_RAW'), ((8, 2), 'IN_A')]),
    'R5':  ('r', '680k', [((8, 3), 'IN_A'), ((8, 7), 'IN_B')]),
    'R6':  ('r', '330k', [((8, 9), 'IN_B'), ((8, 13), 'BIAS')]),
    'C3':  ('cer', '100nF', [((17, 3), 'VF'), ((17, 4), 'GND_A')]),
    'C4':  ('el5.2', '10µF 50V', [((3, 2), 'BIAS'), ((3, 3), 'GND_A')]),
    'R2':  ('r', '10k', [((3, 5), 'VF'), ((3, 9), 'BIAS_MID')]),
    'R3':  ('r', '10k', [((3, 10), 'BIAS_MID'), ((3, 14), 'BIAS')]),
    'R4':  ('r', '10k', [((5, 10), 'BIAS'), ((5, 14), 'GND_A')]),
    'C6':  ('el6.3', '10µF bipolar', [((0, 16), 'HPL'), ((0, 17), 'OUT_L_N')]),
    'R7':  ('r', '100Ω', [((5, 16), 'OUT_L_N'), ((5, 20), 'OUT_L')]),
    'R8':  ('r', '1M', [((12, 16), 'OUT_L'), ((12, 20), 'GND_A')]),
    'C7':  ('el6.3', '10µF bipolar', [((3, 16), 'HPR'), ((3, 17), 'OUT_R_N')]),
    'R9':  ('r', '100Ω', [((7, 16), 'OUT_R_N'), ((7, 20), 'OUT_R')]),
    'R10': ('r', '1M', [((14, 16), 'OUT_R'), ((14, 20), 'GND_A')]),
}

PADS = {
    'IN':    ((6, 0), 'IN_RAW', "the input jack's tip, through the screened cable's core"),
    'SW-I':  ((7, 0), 'IN_RAW', 'Inst/Line switch, Inst throw (no padding)'),
    'SW-C':  ((9, 1), 'IN_A', 'Inst/Line switch, common: the top of R5 (the buffer input)'),
    'SW-L':  ((9, 4), 'IN_B', 'Inst/Line switch, Line throw: past R5 (the 0.33 pad)'),
    'LIN1':  ((10, 8), 'LIN1', "the codec's LIN1 pad, on a fly lead from its own standoffs"),
    'HPL':   ((10, 10), 'HPL', "the codec's HPL pad"),
    'HPR':   ((10, 12), 'HPR', "the codec's HPR pad"),
    'V3A3':  ((10, 14), 'V3A3', "the codec's AVDD pad, from the power board's 78L33"),
    'CGND':  ((10, 15), 'GND_A', "the codec's GND pad -- its own wire back to the star"),
    'OUT-L': ((2, 23), 'OUT_L', 'OUT L jack tip'),
    'OUT-R': ((12, 23), 'OUT_R', 'OUT R jack tip'),
    'STAR':  ((5, 23), 'GND_A', 'the star-ground tag'),
    'VF':    ((17, 12), 'VF', "the power board's filtered 9 V"),
    'V9':    ((17, 21), 'V9_RAW', "the power board's +9 V"),
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
            # stagger the plates: two parts in one column would otherwise collide
            tx, ty = (x1 + x2) / 2 + 26 + (0 if (x1 + x2) / 2 % 2 else 0), \
                     (y1 + y2) / 2 + 4 + (14 if ref in ('R3', 'R4', 'SW-L', 'SW-C') else 0)
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

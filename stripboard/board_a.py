#!/usr/bin/env python3
"""Board A: the analogue board -- the input buffer, the bias and the output stage.

STATUS, 2026-10-10: **unfinished, and it does not draw.**  The parts below are placed legally --
no two overlap, nothing is off the board, no body covers another part's lead or pad -- and the
cuts are the ones that placement needs.  What is missing is the links: the cuts leave several
nets in more than one piece and the wires joining them are not written yet, so running this
reports which nets are still split.  See docs/board-a-netlist.md, "Where board A stands".

The finding behind that, measured rather than guessed: with the codec's two 16-pin socket
strips seated on board A (columns 1 and 10, rows 2-17, as enclosure/src/layout.py places
them), a search over placements and routings found none that closes -- the socket strips and
the analogue stage together leave too little copper for the wires between them.  The codec
going on its own standoffs, on a short fly lead, is the fallback that was agreed.

Board 1 (`stripboard/board1.py`) is the same circuit on one 124 x 33 mm piece of stripboard
and does not fit the enclosure.  Board A is that circuit split by what the noise argues for,
on boards that each return to the star tag on their own wire:

  * **board A** (this file): the input buffer, the bias and the output stage -- everything the
    signal touches, and nothing that switches or rectifies;
  * **the power board**: the 9 V input, D1, the bulk capacitance, R1/C2 and the 78L33 for the
    codec's AVDD.  Its currents are the ones that would otherwise run in board A's ground:
    2a's measurement is -93.5 dBFS(A) (about 21 uV A-weighted) with the codec on the bench's
    own supply, and 2b's reading of it is that the ground path, not the LDO, is the limit;
  * **the control board** (board B in the enclosure): the Pico, MIDI and the relay driver --
    the switching `docs/build-board1.md` keeps off the analogue ground.

The codec's breakout sits on standoffs above board A on its two 16-pin socket strips, which
`enclosure/src/layout.py` seats at hole (1, 2): they run down columns 1 and 10, rows 2-17.
Board A leaves those holes free.  The analogue stage sits in the right band (columns 11-17)
and the front band (rows 12-19), so its wires to the codec's right-hand row -- LIN1, HPL,
HPR, AVDD, GND -- are short, and the high-impedance input is in the rear-right corner beside
the jack and away from the codec's digital row in column 1.

The netlist is `stripboard/nets.py`, shared with board 1 and checked against the case
schematic.  Running this checks the layout against it and writes three drawings:

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

# The codec's socket strips and its right-hand row's pads: nothing else may use these holes.
CODEC_COLS = (1, 10)
CODEC_ROWS = range(2, 18)
CODEC = {'LIN1': (10, 9), 'HPL': (10, 12), 'HPR': (10, 14),
         'AVDD': (10, 15), 'GND': (10, 16)}

# U1's socket.  A column holds four of the eight pins and the other four land in the rows
# between them, so each socket row carries two pins, one on each side.  Where those two are on
# different nets the track is cut *between* them -- what a 3 mm spot-face cutter does when it
# is turned between two holes -- and neither pin is stranded.
#
#   row 5: U1.1 (LIN1) x14 | U1.8 (VF)   x15
#   row 6: U1.2 (LIN1) x14 | U1.7 (U1B)  x15
#   row 7: U1.3 (IN_A) x14 | U1.6 (U1B)  x15
#   row 8: U1.4 (GND)  x14 | U1.5 (BIAS) x15
#
# Columns 12 and 13 are left clear from row 0 to row 9: they are the corridor every wire
# between the socket and the rest of the board runs in, and nothing is placed there.
U1X, U1Y = 14, 5
U1 = [(U1X, U1Y + i) for i in range(4)] + [(U1X + 3, U1Y + 3 - i) for i in range(4)]

CUTS = {
    (10, 3.5), (10, 5.5),    # the codec's LIN1 pad, from the pad rows around it
    (12.5, 0),               # the input network: IN_RAW (the tip) from IN_A, across R5's row
    (14.5, 5), (14.5, 6), (14.5, 7), (14.5, 8),   # the socket's four rows, pin from pin
    (15.5, 6), (15.5, 8),    # U1.6 (U1B) from U1.7, and U1.5 (BIAS) out of row 8
    (12.5, 2),               # IN_A's run down column 12, from the corridor's other nets
    (16, 8.5),               # the bias chain's BIAS from VF
    (16, 12.5), (17, 12.5),  # the bias chain's BIAS_MID from BIAS, and BIAS from GND_A
    (2, 15.5), (3, 15.5), (4, 15.5), (12, 15.5), (13, 15.5),   # the output stage's grounds
    (16, 15.5), (17, 15.5),
}

LINKS = [
    # IN_RAW: the jack, C5.1 and the switch's Inst throw, then down column 13 to U1.3
    ((13, 0), (14, 0)), ((13, 0), (13, 1)), ((13, 1), (13, 7)), ((14, 7), (13, 7)),
    # IN_A: R5.1, C5.2, the switch's common, then down column 12 to U1.3
    ((13, 1), (13, 2)), ((13, 2), (12, 2)), ((12, 2), (12, 6)), ((12, 7), (12, 6)),
    # LIN1: U1.1 out to the codec's pad
    ((14, 5), (14, 4)), ((14, 4), (11, 4)), ((11, 4), (11, 6)), ((11, 6), (10, 6)),
    # GND_A: U1.4 out and down to the ground bus
    ((14, 8), (14, 9)), ((14, 9), (11, 9)), ((11, 9), (11, 17)), ((11, 17), (7, 17)),
    # U1B and BIAS
    ((16, 7), (16, 6)), ((16, 6), (16, 8)), ((16, 8), (16, 9)),
    # VF: U1.8 and the input network's rail
    ((15, 4), (15, 3)),
    # HPL, HPR, the codec's ground and V3A3
    ((10, 10), (11, 10)), ((11, 10), (11, 13)), ((11, 13), (10, 13)),
    ((11, 14), (10, 14)), ((11, 15), (10, 15)),
]

PARTS = {
    'U1':  ('dip8', 'OPA2197 on adapter', [
        (U1[0], 'LIN1'), (U1[1], 'LIN1'), (U1[2], 'IN_A'), (U1[3], 'GND_A'),
        (U1[4], 'BIAS'), (U1[5], 'U1B'), (U1[6], 'U1B'), (U1[7], 'VF')]),
    'C5':  ('film', '100nF film', [((14, 0), 'IN_RAW'), ((14, 2), 'IN_A')]),
    'R5':  ('r', '330k', [((13, 0), 'IN_A'), ((16, 0), 'IN_B')]),
    'R6':  ('r', '680k', [((16, 1), 'IN_B'), ((16, 5), 'BIAS')]),
    'C3':  ('cer', '100nF', [((15, 2), 'VF'), ((15, 3), 'GND_A')]),
    'C4':  ('el5', '10µF 50V', [((17, 9), 'BIAS'), ((17, 11), 'GND_A')]),
    'R2':  ('r', '10k', [((17, 12), 'VF'), ((17, 16), 'BIAS_MID')]),
    'R3':  ('r', '10k', [((17, 13), 'BIAS_MID'), ((17, 17), 'BIAS')]),
    'R4':  ('r', '10k', [((13, 13), 'BIAS'), ((13, 17), 'GND_A')]),
    'C6':  ('el6.3', '10µF bipolar', [((2, 16), 'HPL'), ((2, 17), 'OUT_L_N')]),
    'R7':  ('r', '100Ω', [((4, 15), 'OUT_L_N'), ((4, 19), 'OUT_L')]),
    'R8':  ('r', '1M', [((6, 15), 'OUT_L'), ((6, 19), 'GND_A')]),
    'C7':  ('el6.3', '10µF bipolar', [((12, 15), 'HPR'), ((12, 17), 'OUT_R_N')]),
    'R9':  ('r', '100Ω', [((15, 15), 'OUT_R_N'), ((15, 19), 'OUT_R')]),
    'R10': ('r', '1M', [((17, 15), 'OUT_R'), ((17, 19), 'GND_A')]),
}

PADS = {
    'IN':    ((14, 0), 'IN_RAW', "the input jack's tip, through the screened cable's core"),
    'SW-I':  ((11, 0), 'IN_RAW', 'Inst/Line switch, Inst throw (no padding)'),
    'SW-C':  ((11, 2), 'IN_A', 'Inst/Line switch, common: the top of R5 (the buffer input)'),
    'SW-L':  ((12, 3), 'IN_B', 'Inst/Line switch, Line throw: past R5 (the 0.33 pad)'),
    'LIN1':  ((10, 6), 'LIN1', "the codec's LIN1 pad"),
    'HPL':   ((10, 10), 'HPL', "the codec's HPL pad"),
    'HPR':   ((10, 13), 'HPR', "the codec's HPR pad"),
    'CGND':  ((10, 14), 'GND_A', "the codec's GND pad"),
    'V3A3':  ((10, 15), 'V3A3', "the codec's AVDD pad, from the power board's 78L33"),
    'OUT-L': ((3, 19), 'OUT_L', 'OUT L jack tip'),
    'OUT-R': ((13, 19), 'OUT_R', 'OUT R jack tip'),
    'STAR':  ((7, 18), 'GND_A', 'the star-ground tag'),
    'VF':    ((17, 3), 'VF', "the power board's filtered 9 V"),
    'V9':    ((17, 19), 'V9_RAW', "the power board's +9 V"),
}

CARRIES = {'C5', 'R5', 'R6', 'U1', 'C3', 'C4', 'R2', 'R3', 'R4',
           'C6', 'R7', 'R8', 'C7', 'R9', 'R10'}


def main():
    errs, info = SB.check(W, H, CUTS, LINKS, PARTS, PADS, carries=CARRIES)
    for e in errs:
        print('ERROR', e)
    if errs:
        return 1
    mm = info['mm']
    print(f'ok: {len(PARTS)} parts, {len(LINKS)} links, {len(CUTS)} cuts, {len(PADS)} wires; '
          f'{info["cols"]}x{info["rows"]} holes = {mm[0]:.2f} x {mm[1]:.2f} mm')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

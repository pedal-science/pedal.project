#!/usr/bin/env python3
"""Board A: the analogue board -- the input buffer, the bias and the output stage.

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

# U1's socket: pins 1-4 down column 11, 5-8 up column 14 (the socket's default orientation).
# A column of four pins is four strips, and where two of them are on different nets the strip
# between them is cut, at one of the two pins' own holes.  A pin whose strip is cut reaches
# its net through the hole beside it (the socket's moulding overhangs its pin rows by 1.27 mm
# -- half a hole -- so the hole beside a pin is free).
#
#   pins 1-4 down column 11: U1.1 U1.2 (LIN1) | U1.3 (IN_A) | U1.4 (GND_A)
#   pins 5-8 up column 14:   U1.6 U1.7 (U1B) | U1.8 (VF) | U1.5 (BIAS)
U1X, U1Y = 11, 9
U1 = [(U1X, U1Y + i) for i in range(4)] + [(U1X + 3, U1Y + 3 - i) for i in range(4)]

# The cuts this placement needs, from the strips the pins and the parts share.  THIS SET IS
# NOT YET COMPLETE: the run below reports which nets are still in more than one piece.  The
# placement itself is settled (no two parts overlap, nothing is off the board, the codec's
# socket strips and pads are clear); what is left is the links that carry each net between
# the pieces the cuts leave, which is why the script does not yet write its drawings.
CUTS = {
    (1, 0), (4, 0), (11, 0), (14, 0), (15, 0),
    (9, 12),
    (0, 18), (3, 18), (10, 18), (13, 18), (14, 18), (17, 18),
    (3, 19), (6, 19), (11, 19), (14, 19), (17, 19),
}

LINKS = []

PARTS = {
    'U1':  ('dip8', 'OPA2197 on adapter', [
        (U1[0], 'LIN1'), (U1[1], 'LIN1'), (U1[2], 'IN_A'), (U1[3], 'GND_A'),
        (U1[4], 'BIAS'), (U1[5], 'U1B'), (U1[6], 'U1B'), (U1[7], 'VF')]),
    'C5':  ('film', '100nF film', [((16, 0), 'IN_RAW'), ((16, 1), 'IN_A')]),
    'R5':  ('r', '330k', [((11, 0), 'IN_A'), ((14, 0), 'IN_B')]),
    'R6':  ('r', '680k', [((15, 0), 'IN_B'), ((15, 3), 'BIAS')]),
    'C4':  ('el5', '10µF 50V', [((7, 18), 'BIAS'), ((7, 19), 'GND_A')]),
    'R2':  ('r', '10k', [((14, 18), 'VF'), ((17, 18), 'BIAS_MID')]),
    'R3':  ('r', '10k', [((1, 0), 'BIAS_MID'), ((4, 0), 'BIAS')]),
    'R4':  ('r', '10k', [((8, 16), 'BIAS'), ((8, 19), 'GND_A')]),
    'C3':  ('cer', '100nF', [((11, 19), 'VF'), ((12, 19), 'GND_A')]),
    'C6':  ('el6.3', '10µF bipolar', [((9, 12), 'HPL'), ((9, 13), 'OUT_L_N')]),
    'R7':  ('r', '100Ω', [((0, 18), 'OUT_L_N'), ((3, 18), 'OUT_L')]),
    'R8':  ('r', '1M', [((3, 19), 'OUT_L'), ((6, 19), 'GND_A')]),
    'C7':  ('el6.3', '10µF bipolar', [((9, 14), 'HPR'), ((9, 15), 'OUT_R_N')]),
    'R9':  ('r', '100Ω', [((10, 18), 'OUT_R_N'), ((13, 18), 'OUT_R')]),
    'R10': ('r', '1M', [((14, 19), 'OUT_R'), ((17, 19), 'GND_A')]),
}

PADS = {
    'IN':    ((17, 0), 'IN_RAW', "the input jack's tip, through the screened cable's core"),
    'SW-I':  ((17, 1), 'IN_RAW', 'Inst/Line switch, Inst throw (no padding)'),
    'SW-C':  ((16, 1), 'IN_A', 'Inst/Line switch, common (the buffer input)'),
    'SW-L':  ((15, 1), 'IN_B', 'Inst/Line switch, Line throw (past R5)'),
    'LIN1':  ((10, 9), 'LIN1', "the codec's LIN1 pad"),
    'HPL':   ((10, 12), 'HPL', "the codec's HPL pad"),
    'HPR':   ((10, 14), 'HPR', "the codec's HPR pad"),
    'V3A3':  ((10, 15), 'V3A3', "the codec's AVDD pad, from the power board's 78L33"),
    'CGND':  ((10, 16), 'GND_A', "the codec's GND pad"),
    'OUT-L': ((2, 18), 'OUT_L', 'OUT L jack tip'),
    'OUT-R': ((12, 18), 'OUT_R', 'OUT R jack tip'),
    'STAR':  ((4, 19), 'GND_A', 'the star-ground tag'),
    'VF':    ((17, 19), 'VF', "the power board's filtered 9 V"),
    'V9':    ((17, 2), 'V9_RAW', "the power board's +9 V"),
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

#!/usr/bin/env python3
"""Board A's corridor plan: which rows and columns are wire-only, and why.

Corridor-first is the order a person lays stripboard in: decide the routes the nets need,
then fit the parts around them.  This is that plan as a drawing, so it can be looked at and
argued with before any placement is committed to.

    python3 stripboard/_corridors.py
"""
import pathlib
import stripboard as SB

W, H = 18, 24

# The codec's pads, on fly leads from its own standoffs above the board.  Its socket strips
# are NOT on board A (enclosure/src/layout.py, ON_STANDOFFS), so column 1 is free.
CODEC = {'LIN1': (10, 8), 'HPL': (10, 10), 'HPR': (10, 12),
         'V3A3': (10, 14), 'CGND': (10, 15)}

# The terminations, on the edges they belong to.
PADS = {
    'IN': (16, 0), 'SW-I': (14, 0), 'SW-C': (12, 1), 'SW-L': (15, 1),
    'LIN1': CODEC['LIN1'], 'HPL': CODEC['HPL'], 'HPR': CODEC['HPR'],
    'V3A3': CODEC['V3A3'], 'CGND': CODEC['CGND'],
    'OUT-L': (2, 23), 'OUT-R': (12, 23), 'STAR': (7, 23),
    'VF': (16, 0), 'V9': (17, 20),
}

# ---------------------------------------------------------------- the corridors
# A corridor is a row or column kept clear of parts so a net can run down it.  Each is
# justified by the net it carries: the short high-impedance node first, then ground, then
# what is only a wire.
COLUMNS = {
    12: 'IN_A: the one short high-impedance run, from the switch taps down to U1.3. '
        'Nothing else may use this column between rows 1 and 6.',
    14: 'GND_A and the codec\'s ground: one column down to the star row, so the analogue '
        'return is one wire and not a daisy chain.',
    8:  'LIN1 and the two output runs: the trunk from the socket and the codec pads down '
        'to the front band. Low impedance, so length is not the worry; crossing other '
        'nets is, which is why it is its own column.',
    10: 'the output runs: HPL and HPR from the codec\'s pads down to the front band, which '
        'is the only way past the pads that does not cross the input.',
}
ROWS = {
    2:  'the input network\'s node row: C5, R5 and the switch taps sit here, against the '
        'rear edge the jack is on.',
    6:  'the socket\'s top: U1.1/U1.2 (LIN1) and U1.8 (VF) live here.',
    21: 'the output stage\'s ground row and the star: every ground meets the star tag here, '
        'so nothing shares a return with anything else.',
    23: 'the bottom edge: OUT L, OUT R and the star tag leave from here.',
}
# The bands the parts live in, between the corridors.
BANDS = {
    'input':  (15, 17, 0, 4),
    'U1':     (12, 13, 5, 12),
    'bias':   (15, 17, 6, 13),
    'output': (0, 9, 17, 23),
    'output R': (15, 17, 14, 23),
}


def main():
    here = pathlib.Path(__file__).parent
    s = SB.Sheet(W, H, tw=90)
    s.frame([])
    # corridors, drawn as shaded lanes
    for col, why in COLUMNS.items():
        x = s.X(col)
        s.o.append(f'<rect x="{x - 11}" y="{SB.M - 12}" width="22" '
                   f'height="{(H - 1) * SB.P + 24}" fill="#1a5fb4" opacity=".13"/>')
        s.o.append(f'<text x="{x}" y="{SB.M + (H - 1) * SB.P + 26}" font-size="11" '
                   f'text-anchor="middle" fill="#1a5fb4" font-weight="700">col {col}</text>')
    for row, why in ROWS.items():
        y = s.Y(row)
        s.o.append(f'<rect x="{SB.M - 12}" y="{y - 11}" width="{(W - 1) * SB.P + 24}" '
                   f'height="22" fill="#0a7d3b" opacity=".13"/>')
        s.o.append(f'<text x="{s.X(W - 1) + 22}" y="{y + 4}" font-size="11" '
                   f'text-anchor="start" fill="#0a7d3b" font-weight="700">row {row}</text>')
    # the part bands
    for name, (x0, x1, y0, y1) in BANDS.items():
        s.o.append(f'<rect x="{s.X(x0) - 10}" y="{s.Y(y0) - 10}" '
                   f'width="{(x1 - x0) * SB.P + 20}" height="{(y1 - y0) * SB.P + 20}" '
                   f'fill="none" stroke="#8e44ad" stroke-width="2" stroke-dasharray="5 4"/>')
        s.o.append(f'<text x="{s.X(x0) - 6}" y="{s.Y(y1) + 20}" font-size="11" '
                   f'fill="#8e44ad" font-weight="700">{name}</text>')
    for label, (x, y) in PADS.items():
        s.o.append(f'<circle cx="{s.X(x)}" cy="{s.Y(y)}" r="6" fill="none" '
                   f'stroke="#0a7d3b" stroke-width="3"/>')
        s.o.append(f'<text x="{s.X(x)}" y="{s.Y(y) - 11}" font-size="11" '
                   f'font-weight="800" text-anchor="middle" fill="#0a7d3b">{label}</text>')
    s.save(here / 'board_a-corridors.svg',
           'Board A · CORRIDOR PLAN · blue: wire-only columns · green: wire-only rows · '
           'purple: where the parts go')
    print('wrote board_a-corridors.svg')
    print('\ncolumns kept clear:')
    for col in sorted(COLUMNS):
        print(f'  {col:2d}  {COLUMNS[col]}')
    print('\nrows kept clear:')
    for row in sorted(ROWS):
        print(f'  {row:2d}  {ROWS[row]}')
    print('\nwhere the parts go:')
    for name, (x0, x1, y0, y1) in BANDS.items():
        print(f'  {name:16s} columns {x0}-{x1}, rows {y0}-{y1}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

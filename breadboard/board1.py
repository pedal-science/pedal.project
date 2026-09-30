#!/usr/bin/env python3
"""Board 1 on an 830-point breadboard: the same circuit as stripboard/board1.py, for proving
it before it's soldered.

The netlist comes from stripboard/board1.py, so the two can't drift apart. Running this checks
the placement against it (every lead on its net, no nets joined, no hole used twice, nothing
under the op-amp adapter) and draws it.

Breadboard: columns 1-63, rows a-e above the centre channel and f-j below it. Each column's
a-e is one node and its f-j another. Two rails along the top (T+ above T-) and two along the
bottom (B+ above B-). Some 830-point boards split each rail in the middle: check yours.

    python3 breadboard/board1.py      # check, then write board1.svg beside this file
"""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / 'stripboard'))
import board1 as S  # noqa: E402

# Rails: T+ carries VF (the filtered supply), T- and B- are ground, B+ is unused.
RAILS = {'T+': 'VF', 'T-': 'GND', 'B-': 'GND'}

# Each part: ref -> holes, in the same lead order as stripboard/board1.py's PARTS.
PLACE = {
    'D1': ['c55', 'c50'],            # anode, cathode (band towards column 50)
    'C1': ['a50', 'T-'],             # + , -
    'R1': ['d50', 'd46'],
    'C2': ['b46', 'T-'],
    'C3': ['b20', 'T-'],
    'R2': ['T+', 'a27'],
    'R3': ['c27', 'c23'],
    'R4': ['a23', 'T-'],
    'C4': ['g15', 'B-'],             # + , -
    'U1': ['f20', 'f21', 'f22', 'f23', 'e23', 'e22', 'e21', 'e20'],   # pins 1-8
    'C5': ['g5', 'g7'],
    'R5': ['h7', 'h11'],
    'R6': ['i11', 'i15'],
    'C6': ['h30', 'h31'],
    'R7': ['g31', 'g35'],
    'R8': ['i35', 'B-'],
    'C7': ['h38', 'h39'],
    'R9': ['g39', 'g43'],
    'R10': ['i43', 'B-'],
}

# Jumper wires (solid-core, cut to length and laid flat).
JUMPERS = [
    ('a20', 'T+'),      # U1 pin 8 to VF
    ('a46', 'T+'),      # VF from R1 onto the rail
    ('i20', 'i21'),     # U1A follower: OUT A to -IN A
    ('b21', 'b22'),     # U1B follower: OUT B to -IN B
    ('b23', 'f15'),     # the bias across to R6 and C4
    ('j23', 'B-'),      # U1 pin 4 to ground
    ('T-', 'B-'),       # the two ground rails, joined once, at the left end
]

# Wires leaving the breadboard: label -> hole (labels as in stripboard/board1.py's PADS).
WIRES = {
    '+9V': 'a55', 'STAR': 'T-', 'IN': 'j5', 'SW-I': 'j7', 'SW-L': 'j11', 'SW-C': 'j22',
    'LIN1': 'j20', 'HPL': 'j30', 'HPR': 'j38', 'OUT-L': 'j35', 'OUT-R': 'j43',
}

# The adapter's board overhangs its pins by about 1.3-1.5 mm, so a jumper or lead in the rows
# next to its pins would push against it.
KEEP_OUT = {f'{r}{c}' for r in 'dg' for c in range(19, 25)} | {f'{r}{c}' for r in 'ef' for c in (19, 24)}


def node(h):
    if h in ('T+', 'T-', 'B+', 'B-'):
        return h
    row, col = h[0], int(h[1:])
    assert row in 'abcdefghij' and 1 <= col <= 63, h
    return f'{col}{"top" if row in "abcde" else "bot"}'


def check():
    errors = []
    used = {}

    def take(h, what):
        if h in ('T+', 'T-', 'B+', 'B-'):
            return
        if h in used:
            errors.append(f'{what} and {used[h]} share hole {h}')
        if h in KEEP_OUT:
            errors.append(f'{what} at {h} is under the op-amp adapter')
        used[h] = what

    parent = {}

    def find(n):
        parent.setdefault(n, n)
        while parent[n] != n:
            n = parent[n]
        return n

    for a, b in JUMPERS:
        take(a, f'jumper {a}-{b}')
        take(b, f'jumper {a}-{b}')
        parent[find(node(a))] = find(node(b))
    nets = {}
    if set(PLACE) != set(S.PARTS):
        errors.append(f'parts differ from the stripboard: {set(PLACE) ^ set(S.PARTS)}')
    for ref, holes in PLACE.items():
        leads = S.PARTS[ref][2]
        if len(holes) != len(leads):
            errors.append(f'{ref}: {len(holes)} holes for {len(leads)} leads')
            continue
        for i, (h, (_, net)) in enumerate(zip(holes, leads)):
            take(h, f'{ref}.{i + 1}')
            nets.setdefault(net, set()).add(find(node(h)))
    for label, h in WIRES.items():
        take(h, f'wire {label}')
        nets.setdefault(S.PADS[label][1], set()).add(find(node(h)))
    for rail, net in RAILS.items():
        nets.setdefault(net, set()).add(find(rail))
    for net, roots in nets.items():
        if len(roots) > 1:
            errors.append(f'net {net} is split into {len(roots)} pieces')
    owner = {}
    for net, roots in nets.items():
        for r in roots:
            if r in owner and owner[r] != net:
                errors.append(f'nets {owner[r]} and {net} are joined')
            owner[r] = net
    per_node = {}
    for h in used:
        per_node[node(h)] = per_node.get(node(h), 0) + 1
    for n, k in per_node.items():
        if k > 5:
            errors.append(f'{n} has {k} leads in 5 holes')
    return errors


# Drawing -------------------------------------------------------------------------------------

PX, M = 20, 36
ROWY = {'T+': 0, 'T-': 1, 'a': 3, 'b': 4, 'c': 5, 'd': 6, 'e': 7, 'f': 10, 'g': 11, 'h': 12, 'i': 13,
        'j': 14, 'B+': 16, 'B-': 17}


def xy(h, col_hint=None):
    if h in ('T+', 'T-', 'B+', 'B-'):
        return M + (col_hint - 1) * PX, M + ROWY[h] * PX
    return M + (int(h[1:]) - 1) * PX, M + ROWY[h[0]] * PX


def svg():
    w, hgt = 2 * M + 62 * PX, 2 * M + 17 * PX + 40
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {hgt}" width="{w}" height="{hgt}" '
         f'font-family="system-ui,sans-serif">', f'<rect width="{w}" height="{hgt}" fill="#f4f4f1"/>',
         f'<rect x="{M - 14}" y="{M - 14}" width="{62 * PX + 28}" height="{17 * PX + 28}" rx="8" fill="#fff" stroke="#ccc"/>']
    for rail, col in (('T+', '#d33'), ('T-', '#36c'), ('B+', '#d33'), ('B-', '#36c')):
        y = M + ROWY[rail] * PX
        o.append(f'<line x1="{M - 8}" y1="{y + (-8 if "+" in rail else 8)}" x2="{M + 62 * PX + 8}" '
                 f'y2="{y + (-8 if "+" in rail else 8)}" stroke="{col}" stroke-width="2"/>')
        o.append(f'<text x="{M - 26}" y="{y + 4}" font-size="11" fill="{col}" font-weight="700">{rail}</text>')
    for r in 'abcdefghij':
        o.append(f'<text x="{M - 24}" y="{M + ROWY[r] * PX + 4}" font-size="11" fill="#555">{r}</text>')
    for c in range(1, 64):
        x = M + (c - 1) * PX
        if c % 5 == 0 or c == 1:
            o.append(f'<text x="{x}" y="{M + 8.6 * PX + 4}" font-size="10" text-anchor="middle" fill="#555">{c}</text>')
        for r in ROWY:
            if r in ('T+', 'T-', 'B+', 'B-') and (c % 6 == 0):
                continue
            o.append(f'<rect x="{x - 3}" y="{M + ROWY[r] * PX - 3}" width="6" height="6" rx="1" fill="#bbb"/>')
    o.append(f'<rect x="{M - 10}" y="{M + 8 * PX - 6}" width="{62 * PX + 20}" height="{PX + 12}" fill="#eee"/>')

    def other_col(holes, i):
        for h in holes:
            if h not in ('T+', 'T-', 'B+', 'B-'):
                return int(h[1:]) + (1 if i else 0)
        return 2

    # the adapter
    x0, y0 = xy('e20')
    o.append(f'<rect x="{x0 - 12}" y="{y0 - 10}" width="{3 * PX + 24}" height="{3 * PX + 20}" rx="3" '
             f'fill="#1d4d34" opacity=".85"/><text x="{x0 + 1.5 * PX}" y="{y0 + 1.5 * PX + 4}" font-size="11" '
             f'text-anchor="middle" fill="#fff" font-weight="700">U1 OPA2197</text>')
    xp, yp = xy('f20')
    o.append(f'<circle cx="{xp}" cy="{yp + 14}" r="3" fill="#fff"/><text x="{xp - 12}" y="{yp + 18}" '
             f'font-size="10" fill="#fff">1</text>')
    colours = {'r': '#b8860b', 'd': '#222', 'film': '#c0392b', 'cer': '#e67e22', 'el6.3': '#2c3e8f',
               'el5': '#2c3e8f'}
    for ref, holes in PLACE.items():
        if ref == 'U1':
            continue
        kind, val = S.PARTS[ref][0], S.PARTS[ref][1]
        pts = [xy(h, other_col(holes, 0)) for h in holes]
        col = colours[kind]
        o.append(f'<line x1="{pts[0][0]}" y1="{pts[0][1]}" x2="{pts[1][0]}" y2="{pts[1][1]}" stroke="{col}" '
                 f'stroke-width="6" stroke-linecap="round" opacity=".9"/>')
        for p in pts:
            o.append(f'<circle cx="{p[0]}" cy="{p[1]}" r="4" fill="{col}"/>')
        if kind.startswith('el') and 'bipolar' not in val:
            o.append(f'<text x="{pts[0][0] + 5}" y="{pts[0][1] - 5}" font-size="13" font-weight="800" fill="{col}">+</text>')
        mx, my = (pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2
        vertical = abs(pts[0][0] - pts[1][0]) < 1
        tx, ty, anchor = (mx + 9, my + 4, 'start') if vertical else (mx, my - 9, 'middle')
        o.append(f'<text x="{tx}" y="{ty}" font-size="11" font-weight="700" text-anchor="{anchor}" '
                 f'fill="#111" stroke="#fff" stroke-width="3" paint-order="stroke">{ref} {val}</text>')
    for a, b in JUMPERS:
        ca = other_col([b], 0) if a in ('T+', 'T-', 'B+', 'B-') else None
        cb = other_col([a], 0) if b in ('T+', 'T-', 'B+', 'B-') else None
        if a == 'T-' and b == 'B-':
            ca = cb = 2
        pa, pb = xy(a, ca), xy(b, cb)
        o.append(f'<line x1="{pa[0]}" y1="{pa[1]}" x2="{pb[0]}" y2="{pb[1]}" stroke="#16a34a" stroke-width="3.5" '
                 f'stroke-linecap="round"/>')
    for label, h in WIRES.items():
        x, y = xy(h, 3)
        dy = 26 if h[0] in 'fghij' or h.startswith('B') else -18
        o.append(f'<circle cx="{x}" cy="{y}" r="6" fill="none" stroke="#7c3aed" stroke-width="3"/>'
                 f'<text x="{x}" y="{y + dy}" font-size="11" font-weight="800" text-anchor="middle" '
                 f'fill="#7c3aed">{label}</text>')
    o.append(f'<text x="{M}" y="{hgt - 14}" font-size="14" font-weight="800" fill="#111">Board 1 on the '
             f'breadboard · green: jumpers · purple: wires off the breadboard · T+ is VF (8.7 V), T− and B− are '
             f'ground</text></svg>')
    return '\n'.join(o)


if __name__ == '__main__':
    errs = check()
    for e in errs:
        print('ERROR', e)
    if errs:
        sys.exit(1)
    (HERE / 'board1.svg').write_text(svg())
    print(f'ok: {len(PLACE)} parts, {len(JUMPERS)} jumpers, {len(WIRES)} wires; board1.svg written')

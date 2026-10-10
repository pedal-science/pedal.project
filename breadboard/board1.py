#!/usr/bin/env python3
"""Board 1 on an 830-point breadboard: the same circuit as stripboard/board1.py, for proving
it before it's soldered.

The netlist comes from stripboard/nets.py, so the two can't drift apart. Running this checks
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
import nets as NET  # noqa: E402

# Rails: T+ carries VF (the filtered supply), T- and B- are ground, B+ is unused.  The net is
# the canonical one (nets.net_key), because the pedal's two ground nets are one node on a
# breadboard: the rail stands in for the star tag, and the doc's one jumper between T- and B-
# is where the power return's rail and the signal rail meet.  The placement below puts C1 and
# C2's returns on T- and every signal ground on B- -- the split the soldered board gets from
# its copper -- and nets.py's EQUIV is what says the two names are one node.
RAILS = {'T+': 'VF', 'T-': NET.net_key('GND_A'), 'B-': NET.net_key('GND_A')}

# Parts: ref -> holes, in the same lead order as stripboard/board1.py's PARTS.
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

# Wires leaving the breadboard: label -> hole.  The labels are the netlist's pad names
# (`stripboard/nets.py`), so each wire's net comes from there and not from this file: SW-C is
# the switch's common, on the follower's input at U1.3 (j22, where U1 pin 3 sits); SW-I is its
# Inst throw, node A past C5 (j7, with C5's far lead and R5's top lead); SW-L is the Line
# throw, node B (j11, between R5 and R6).  V9 is the DC socket's +9 V contact.
WIRES = {
    'V9': 'a55', 'STAR': 'T-', 'IN': 'j5', 'SW-I': 'j7', 'SW-L': 'j11', 'SW-C': 'j22',
    'LIN1': 'j20', 'HPL': 'j30', 'HPR': 'j38', 'OUT-L': 'j35', 'OUT-R': 'j43',
}

# The adapter's board overhangs its pins by about 1.3-1.5 mm, so a jumper or lead in the rows
# next to its pins would push against it.
KEEP_OUT = {f'{r}{c}' for r in 'dg' for c in range(19, 25)} | {f'{r}{c}' for r in 'ef' for c in (19, 24)}

# Nets this placement carries in two pieces on purpose, joined through the switch, which is off
# the board.  IN_A is node A -- the follower's input.  This placement carries it as two pieces:
# C5's far lead and R5's top lead are one (column 7: C5 at g5-g7, R5 at h7-h11) and U1.3's is
# the other (column 22).  The switch's two wires are what join them: SW-I's from j7 and SW-C's
# from j22, one on each piece, the same node only while the lever is at Inst.  That is the
# switch's whole job, so a jumper between the two columns is not a missing wire but a wrong
# one: it would tie node A to the follower's input permanently and leave the toggle unable to
# choose the Line tap.  There is nowhere to run one anyway: columns 19-24 are the op-amp
# adapter's keep-out, and this is the one net on the board that needs it.
#
# IN_RAW needs nothing off-board: it is the IN wire at j5 and C5's input lead at g5, and the
# five holes of column 5's lower half are one node.
OFF_BOARD = {'IN_A'}


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
        if ref not in S.PARTS:
            errors.append(f'{ref} is not a part of the stripboard layout')
            continue
        leads = S.PARTS[ref][2]
        if len(holes) != len(leads):
            errors.append(f'{ref}: {len(holes)} holes for {len(leads)} leads')
            continue
        for i, (h, (_, net)) in enumerate(zip(holes, leads)):
            take(h, f'{ref}.{i + 1}')
            nets.setdefault(NET.net_key(net), set()).add(find(node(h)))
    for label, h in WIRES.items():
        if label not in S.PADS:
            errors.append(f'wire {label} is not a pad on the stripboard layout')
            continue
        take(h, f'wire {label}')
        nets.setdefault(NET.net_key(S.PADS[label][1]), set()).add(find(node(h)))
    for rail, net in RAILS.items():
        nets.setdefault(NET.net_key(net), set()).add(find(rail))
    pad_roots = {}
    for label, h in WIRES.items():
        if label in S.PADS:
            pad_roots.setdefault(NET.net_key(S.PADS[label][1]), set()).add(find(node(h)))
    for net, roots in nets.items():
        if len(roots) > 1 and net not in OFF_BOARD:
            errors.append(f'net {net} is split into {len(roots)} pieces')
    for net in OFF_BOARD:
        if net not in nets:
            errors.append(f'off-board names {net}, which is not a net here')
        elif len(nets[net]) > 1 and len(pad_roots.get(net, ())) < 2:
            errors.append(f'net {net} is in {len(nets[net])} pieces with '
                          f'{len(pad_roots.get(net, ()))} wire(s): nothing joins the pieces')
    owner = {}
    for net, roots in nets.items():
        for r in roots:
            if r in owner and not NET.same_net(owner[r], net):
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


# Label placement.  Every text is placed, its box is worked out from the same table, and a
# label that would land on one already placed is moved: the drawing is checked for the fault a
# picture is the only witness to -- two labels in one place.  This is why the printer says
# nothing about collisions: it is the drawing that had them.
CHAR_W = {10: 4.9, 11: 5.3, 13: 6.3, 14: 6.9}      # average advance, measured from the drawn
                                                    # text (rsvg-convert, system-ui): a label
                                                    # is mostly digits and capitals, which are
                                                    # narrower than the 'm' a flat guess costs
TEXTS = []               # (box, text, its own body's box or None) drawn: no two may touch
OBSTACLES = []           # (box, what) part bodies and pad rings: no label on one


def _box(x, y, text, size, anchor):
    """The rectangle a text occupies, from its baseline position and anchor.

    Cap height above the baseline and the descender below it, by the font size: an 11px label
    is 11 * 0.72 + 11 * 0.2 tall, which is what keeps two labels a row apart from touching
    without pushing a label off the part it belongs to.
    """
    cw = CHAR_W[size]
    w = len(text) * cw
    x0 = x - w / 2 if anchor == 'middle' else (x - w if anchor == 'end' else x)
    return (x0, y - size * 0.78, x0 + w, y + size * 0.22)


def _overlaps(box, other, pad):
    return not (box[2] + pad < other[0] or other[2] + pad < box[0]
                or box[3] + pad < other[1] or other[3] + pad < box[1])


def _hits(box, pad=1.0, own=None):
    return (any(_overlaps(box, b, pad) for b, _, _ in TEXTS)
            or any(_overlaps(box, b, pad) for b, _ in OBSTACLES
                   if own is None or b is not own))


def _candidates(up, side):
    """Where to try a label, nearest the part first: along one axis, then the other."""
    step = 13
    order = [(0, 0)]
    for n in range(1, 7):
        order += [(0, s * n * step) for s in up] + [(s * n * step, 0) for s in side]
    return order


def fit(x, y, text, size, anchor, up=(1, -1), side=(1, -1), pad=0.0, own=None):
    """Place a label in the free space nearest (x, y).

    The drawing is checked for the fault only a picture shows: two labels in one place, or a
    label on a part's body or on a pad's ring.  Bodies and pads are registered as they are
    drawn, so a label that has nowhere to go is still drawn where it was asked for and the
    next one moves instead.
    """
    for dx, dy in _candidates(up, side):
        box = _box(x + dx, y + dy, text, size, anchor)
        if not _hits(box, pad, own):
            TEXTS.append((box, text, own))
            return x + dx, y + dy
    box = _box(x, y, text, size, anchor)
    TEXTS.append((box, text, own))
    return x, y


def svg():
    w, hgt = 2 * M + 62 * PX, 2 * M + 17 * PX + 40
    del TEXTS[:]
    del OBSTACLES[:]
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {hgt}" width="{w}" height="{hgt}" '
         f'font-family="system-ui,sans-serif">', f'<rect width="{w}" height="{hgt}" fill="#f4f4f1"/>',
         f'<rect x="{M - 14}" y="{M - 14}" width="{62 * PX + 28}" height="{17 * PX + 28}" rx="8" fill="#fff" stroke="#ccc"/>']
    for rail, col in (('T+', '#d33'), ('T-', '#36c'), ('B+', '#d33'), ('B-', '#36c')):
        y = M + ROWY[rail] * PX
        o.append(f'<line x1="{M - 8}" y1="{y + (-8 if "+" in rail else 8)}" x2="{M + 62 * PX + 8}" '
                 f'y2="{y + (-8 if "+" in rail else 8)}" stroke="{col}" stroke-width="2"/>')
        o.append(f'<text x="{M - 26}" y="{y + 4}" font-size="11" fill="{col}" font-weight="700">{rail}</text>')
        TEXTS.append((_box(M - 26, y + 4, rail, 11, 'start'), rail, None))
    for r in 'abcdefghij':
        o.append(f'<text x="{M - 24}" y="{M + ROWY[r] * PX + 4}" font-size="11" fill="#555">{r}</text>')
        TEXTS.append((_box(M - 24, M + ROWY[r] * PX + 4, r, 11, 'start'), r, None))
    for c in range(1, 64):
        x = M + (c - 1) * PX
        if c % 5 == 0 or c == 1:
            o.append(f'<text x="{x}" y="{M + 8.6 * PX + 4}" font-size="10" text-anchor="middle" fill="#555">{c}</text>')
            TEXTS.append((_box(x, M + 8.6 * PX + 4, str(c), 10, 'middle'), str(c), None))
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
             f'fill="#1d4d34" opacity=".85"/>')
    # Its top edge reaches into the column-number row, which is drawn before it, so the
    # obstacle starts below that row: the numbers are what the picture is read against.
    adapter = (x0 - 12, M + 8.6 * PX + 6, x0 + 3 * PX + 12, y0 + 3 * PX + 10)
    OBSTACLES.append((adapter, 'the adapter'))
    name_x = x0 + 1.5 * PX + 6      # clear of column 20's number, which the body's top edge
                                    # reaches into and which is drawn before it
    o.append(f'<text x="{name_x}" y="{y0 + 1.5 * PX + 4}" font-size="11" '
             f'text-anchor="middle" fill="#fff" font-weight="700">U1 OPA2197</text>')
    TEXTS.append((_box(name_x, y0 + 1.5 * PX + 4, 'U1 OPA2197', 11, 'middle'), 'U1 OPA2197',
              (x0 - 12, y0 - 10, x0 + 3 * PX + 12, y0 + 3 * PX + 10)))   # on its own body
    # Pin 1: the dot sits in the first pin's hole, and the numeral is placed off the adapter's
    # left edge and above it, where the body cannot cover it.
    xp, yp = xy('f20')
    o.append(f'<circle cx="{xp}" cy="{yp}" r="4.5" fill="#fff" stroke="#0a5"/>')
    px, py = fit(xp - 2, yp + 32, '1', 10, 'end', up=(-1, 1), side=(-1, 1))
    o.append(f'<text x="{px}" y="{py}" font-size="10" font-weight="800" fill="#0a5" '
             f'text-anchor="middle">1</text>')
    colours = {'r': '#b8860b', 'd': '#222', 'film': '#c0392b', 'cer': '#e67e22', 'el6.3': '#2c3e8f',
               'el5': '#2c3e8f'}
    # Two passes: every body, lead and pad on the board is known before the first label is
    # placed, so a label cannot be put where a part drawn later will land on it.
    bits = []
    for ref, holes in PLACE.items():
        if ref == 'U1':
            continue
        kind, val = S.PARTS[ref][0], S.PARTS[ref][1]
        pts = [xy(h, other_col(holes, 0)) for h in holes]
        col = colours[kind]
        mx, my = (pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2
        ax0, ax1 = sorted((pts[0][0], pts[1][0]))
        ay0, ay1 = sorted((pts[0][1], pts[1][1]))
        if kind.startswith('el'):
            r = float(kind[2:]) / 2.54 * PX / 2 + 1                  # the drawn disc's radius
            body = (mx - r, my - r, mx + r, my + r)
        elif kind == 'cer':
            body = (mx - 7, my - 7, mx + 7, my + 7)                  # a 2.5 mm disc
        else:
            half = 5.5 if abs(pts[0][0] - pts[1][0]) < 1 else 6.0     # the drawn bar's width
            half -= 1.0                                              # the halo covers it
            body = (ax0 - half, ay0 - half, ax1 + half, ay1 + half)   # the part's own body
        OBSTACLES.append((body, ref))
        for p in pts:
            OBSTACLES.append(((p[0] - 5, p[1] - 5, p[0] + 5, p[1] + 5), f'{ref} lead'))
        bits.append((ref, kind, val, pts, col, body, (mx, my), abs(pts[0][0] - pts[1][0]) < 1))
    for ref, kind, val, pts, col, body, (mx, my), vertical in bits:
        o.append(f'<line x1="{pts[0][0]}" y1="{pts[0][1]}" x2="{pts[1][0]}" y2="{pts[1][1]}" stroke="{col}" '
                 f'stroke-width="6" stroke-linecap="round" opacity=".9"/>')
        for p in pts:
            o.append(f'<circle cx="{p[0]}" cy="{p[1]}" r="4" fill="{col}"/>')
        if kind.startswith('el') and 'bipolar' not in val:
            o.append(f'<text x="{pts[0][0] + 5}" y="{pts[0][1] - 5}" font-size="13" font-weight="800" fill="{col}">+</text>')
        # A label goes above a part lying along a strip and beside one lying down a column; if
        # that place is taken it steps outward, a hole at a time, until it is clear.
        if vertical:
            tx, ty = fit(mx + 9, my + 4, f'{ref} {val}', 11, 'start', own=body)
            anchor = 'start'
        else:
            tx, ty = fit(mx, my - 9, f'{ref} {val}', 11, 'middle', up=(-1, 1), own=body)
            anchor = 'middle'
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
        o.append(f'<circle cx="{x}" cy="{y}" r="6" fill="none" stroke="#7c3aed" stroke-width="3"/>')
        OBSTACLES.append(((x - 6, y - 6, x + 6, y + 6), f'pad {label}'))
        tx, ty = fit(x, y + dy, label, 11, 'middle', up=(1, -1), side=(-1, 1))
        o.append(f'<text x="{tx}" y="{ty}" font-size="11" font-weight="800" text-anchor="middle" '
                 f'fill="#7c3aed">{label}</text>')
    title = ('Board 1 on the breadboard · green: jumpers · purple: wires off the breadboard · '
             'T+ is VF (8.7 V), T− and B− are one ground node')
    tw = len(title) * CHAR_W[14] + 2 * M
    if tw > w:                       # a title longer than the drawing gets its own canvas
        w = int(tw)
        o[0] = o[0].replace(f'viewBox="0 0 {2 * M + 62 * PX} {hgt}" width="{2 * M + 62 * PX}"',
                            f'viewBox="0 0 {w} {hgt}" width="{w}"')
        o[1] = f'<rect width="{w}" height="{hgt}" fill="#f4f4f1"/>'
    o.append(f'<text x="{M}" y="{hgt - 14}" font-size="14" font-weight="800" fill="#111">{title}</text></svg>')
    return '\n'.join(o)


if __name__ == '__main__':
    errs = check()
    for e in errs:
        print('ERROR', e)
    if errs:
        sys.exit(1)
    import xml.etree.ElementTree as ET
    drawing = svg()
    ET.fromstring(drawing)          # a drawing that is not well-formed XML is not written
    (HERE / 'board1.svg').write_text(drawing)
    clashes = [(ta, tb) for i, (a, ta, _) in enumerate(TEXTS) for b, tb, _ in TEXTS[i + 1:]
               if _overlaps(a, b, 0.5)]
    clashes += [(ta, what) for a, ta, own in TEXTS
                for b, what in OBSTACLES if b is not own and _overlaps(a, b, -0.5)]
    if clashes:
        print(f'WARNING {len(clashes)} label(s) overlap something')
        for a, b in clashes[:8]:
            print(f'   {a!r}  x  {b!r}')
    print(f'ok: {len(PLACE)} parts, {len(JUMPERS)} jumpers, {len(WIRES)} wires, '
          f'{len(OFF_BOARD)} net in two pieces, joined by the switch; board1.svg written')

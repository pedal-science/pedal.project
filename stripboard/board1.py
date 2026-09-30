#!/usr/bin/env python3
"""Board 1: the 9 V supply, the input buffer and the output stage, on Kemo E005 stripboard.

The layout is data. Running this checks it against the netlist (every lead on the net it
should be on, no two nets joined, nothing on a cut hole, no lead under another part's body)
and writes two drawings: the component side, and the copper side mirrored, which is what
you see when you cut the tracks.

Coordinates are holes: x along the strips (0 at the left, seen from the component side),
y across them (row 0 at the top). Turn the board so the strips run left to right.

    python3 stripboard/board1.py        # check, then write board1-*.svg beside this file
"""
import sys
from pathlib import Path

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
    ((1, 0), (1, 5)),     # GND strip 0 to GND strip 5
    ((23, 5), (23, 10)),  # GND strip 5 to GND strip 10
    ((41, 8), (41, 10)),  # R8's ground end
    ((42, 12), (42, 10)), # R10's ground end
]

# Parts: ref -> (kind, value, [(hole, net), ...]). Lead order matters for polarised parts:
# electrolytics list + first, the diode lists its anode first, U1 lists pins 1-8.
# kind sets the body drawn and checked: 'r' lying resistor, 'd' lying diode, 'film' box
# capacitor lying along the strip, 'cer' small ceramic, 'el' radial electrolytic (diameter
# in mm), 'dip8' the socket.
PARTS = {
    'D1': ('d', '1N5817', [((41, 1), 'VIN9'), ((36, 1), 'V9')]),
    'C1': ('el6.3', '100µF 25V', [((34, 1), 'V9'), ((34, 0), 'GND')]),
    'R1': ('r', '100Ω', [((32, 1), 'V9'), ((28, 1), 'VF')]),
    'C2': ('el6.3', '100µF 25V', [((25, 1), 'VF'), ((25, 0), 'GND')]),
    'C3': ('cer', '100nF', [((22, 1), 'VF'), ((22, 0), 'GND')]),
    'R2': ('r', '10k', [((29, 3), 'VF'), ((33, 3), 'N1')]),
    'R3': ('r', '10k', [((35, 3), 'N1'), ((39, 3), 'VB')]),
    'R4': ('r', '10k', [((42, 3), 'VB'), ((46, 3), 'GND')]),
    'C4': ('el5', '10µF 50V', [((30, 4), 'VB'), ((30, 5), 'GND')]),
    'U1': ('dip8', 'OPA2197 on adapter', [
        ((18, 1), 'OUTA'), ((18, 2), 'OUTA'), ((18, 3), 'PINA'), ((18, 4), 'GND'),
        ((21, 4), 'VB'), ((21, 3), 'OUTB'), ((21, 2), 'OUTB'), ((21, 1), 'VF')]),
    'C5': ('film', '100nF film', [((3, 6), 'IN'), ((5, 6), 'A')]),
    'R5': ('r', '680k', [((7, 6), 'A'), ((11, 6), 'B')]),
    'R6': ('r', '330k', [((13, 6), 'B'), ((17, 6), 'VB')]),
    'C6': ('el6.3', '10µF bipolar', [((28, 7), 'HPL'), ((28, 8), 'NL')]),
    'R7': ('r', '100Ω', [((30, 8), 'NL'), ((34, 8), 'OUTL')]),
    'R8': ('r', '1M', [((36, 8), 'OUTL'), ((40, 8), 'GND')]),
    'C7': ('el6.3', '10µF bipolar', [((28, 11), 'HPR'), ((28, 12), 'NR')]),
    'R9': ('r', '100Ω', [((30, 12), 'NR'), ((34, 12), 'OUTR')]),
    'R10': ('r', '1M', [((36, 12), 'OUTR'), ((40, 12), 'GND')]),
}

# Wires leaving the board: label -> (hole, net, where it goes).
PADS = {
    'STAR': ((0, 0), 'GND', 'the star-ground tag'),
    '+9V': ((44, 1), 'VIN9', 'the DC socket\'s +9 V contact'),
    'IN': ((1, 6), 'IN', 'input jack tip (screened cable core)'),
    'SW-I': ((6, 6), 'A', 'Inst/Line switch, Inst throw'),
    'SW-L': ((12, 6), 'B', 'Inst/Line switch, Line throw'),
    'SW-C': ((15, 3), 'PINA', 'Inst/Line switch, common'),
    'LIN1': ((15, 1), 'OUTA', 'codec board LIN1 (right-hand row)'),
    'HPL': ((25, 7), 'HPL', 'codec board HPL'),
    'HPR': ((25, 11), 'HPR', 'codec board HPR'),
    'OUT-L': ((35, 8), 'OUTL', 'OUT L jack tip'),
    'OUT-R': ((35, 12), 'OUTR', 'OUT R jack tip'),
}


def check():
    errors = []
    # Union-find over holes: along each strip, broken at cuts; then links.
    parent = {}

    def find(h):
        parent.setdefault(h, h)
        while parent[h] != h:
            parent[h] = parent[parent[h]]
            h = parent[h]
        return h

    def union(a, b):
        parent[find(a)] = find(b)

    for y in range(H):
        for x in range(W - 1):
            a, b = (x, y), (x + 1, y)
            if a not in CUTS and b not in CUTS:
                union(a, b)
    for a, b in LINKS:
        union(a, b)

    used = {}  # hole -> what's in it

    def occupy(h, what):
        x, y = h
        if not (0 <= x < W and 0 <= y < H):
            errors.append(f'{what} at {h} is off the board')
        if h in CUTS:
            errors.append(f'{what} at {h} is on a cut hole')
        if h in used:
            errors.append(f'{what} and {used[h]} share hole {h}')
        used[h] = what

    for a, b in LINKS:
        occupy(a, f'link {a}-{b}')
        occupy(b, f'link {a}-{b}')
    net_of = {}  # net -> set of roots
    for ref, (_, _, leads) in PARTS.items():
        for i, (h, net) in enumerate(leads):
            occupy(h, f'{ref}.{i + 1}')
            net_of.setdefault(net, set()).add(find(h))
    for label, (h, net, _) in PADS.items():
        occupy(h, f'pad {label}')
        net_of.setdefault(net, set()).add(find(h))

    for net, roots in net_of.items():
        if len(roots) > 1:
            errors.append(f'net {net} is split into {len(roots)} pieces')
    owner = {}
    for net, roots in net_of.items():
        for r in roots:
            if r in owner and owner[r] != net:
                errors.append(f'nets {owner[r]} and {net} are joined')
            owner[r] = net

    # Bodies: holes a lying part covers, and radial circles.
    for ref, (kind, _, leads) in PARTS.items():
        pts = [h for h, _ in leads]
        if kind in ('r', 'd', 'film'):
            (x1, y1), (x2, y2) = pts
            span = abs(x2 - x1) + abs(y2 - y1)
            need = {'r': 4, 'd': 4, 'film': 2}[kind]
            if span < need:
                errors.append(f'{ref}: leads {span} holes apart, needs {need}')
            covered = [(x, y1) for x in range(min(x1, x2) + 1, max(x1, x2))] if y1 == y2 else \
                      [(x1, y) for y in range(min(y1, y2) + 1, max(y1, y2))]
            for h in covered:
                if h in used:
                    errors.append(f'{ref}\'s body covers {used[h]} at {h}')
        elif kind.startswith('el'):
            r = float(kind[2:]) / 2 / 2.54 + 0.15  # radius in holes, plus a little
            cx = sum(p[0] for p in pts) / 2
            cy = sum(p[1] for p in pts) / 2
            for h, what in used.items():
                if what.startswith(ref + '.'):
                    continue
                if (h[0] - cx) ** 2 + (h[1] - cy) ** 2 < r * r:
                    errors.append(f'{ref}\'s body covers {what} at {h}')
        elif kind == 'dip8':
            for x in range(18, 22):
                for y in range(1, 5):
                    h = (x, y)
                    if h in used and not used[h].startswith('U1.') and h not in CUTS:
                        errors.append(f'U1\'s socket covers {used[h]} at {h}')
    return errors


# Drawing ------------------------------------------------------------------

P = 22  # pixels per hole
M = 40  # margin
NETCOL = {'GND': '#555', 'VIN9': '#c0392b', 'V9': '#e67e22', 'VF': '#d35400', 'VB': '#8e44ad',
          'N1': '#9b59b6'}


def svg(mirror):
    def X(x):
        return M + ((W - 1 - x) if mirror else x) * P

    def Y(y):
        return M + y * P

    w, h = 2 * M + (W - 1) * P, 2 * M + (H - 1) * P + 30
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
         f'font-family="system-ui,sans-serif">',
         f'<rect width="{w}" height="{h}" fill="#f7f3ea"/>']
    # strips, broken at cuts
    for y in range(H):
        xs = [x for x in range(W) if (x, y) not in CUTS]
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
    # column numbers every 5, row numbers
    for x in range(0, W, 5):
        o.append(f'<text x="{X(x)}" y="{M - 18}" font-size="12" text-anchor="middle" fill="#333">{x}</text>')
    for y in range(H):
        o.append(f'<text x="{M - 26 if not mirror else w - M + 26}" y="{Y(y) + 4}" font-size="12" '
                 f'text-anchor="middle" fill="#333">{y}</text>')
    if not mirror:
        for a, b in LINKS:
            o.append(f'<line x1="{X(a[0])}" y1="{Y(a[1])}" x2="{X(b[0])}" y2="{Y(b[1])}" '
                     f'stroke="#1a5fb4" stroke-width="3.5" stroke-linecap="round"/>')
        for ref, (kind, val, leads) in PARTS.items():
            pts = [(X(hx), Y(hy)) for (hx, hy), _ in leads]
            if kind == 'dip8':
                x1, y1 = X(18) - 8, Y(1) - 10
                o.append(f'<rect x="{x1}" y="{y1}" width="{3 * P + 16}" height="{3 * P + 20}" rx="4" '
                         f'fill="#222" opacity=".85"/>')
                o.append(f'<circle cx="{X(18) + 6}" cy="{Y(1) - 2}" r="3" fill="#fff"/>')
                o.append(f'<text x="{X(19) + P / 2}" y="{Y(2) + P / 2 + 4}" font-size="11" '
                         f'text-anchor="middle" fill="#fff" font-weight="700">U1</text>')
                for i, (px, py) in enumerate(pts):
                    o.append(f'<text x="{px + (-12 if i < 4 else 12)}" y="{py + 4}" font-size="9" '
                             f'text-anchor="middle" fill="#fff">{i + 1}</text>')
                continue
            if kind.startswith('el'):
                d = float(kind[2:]) / 2.54 * P
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
    o.append(f'<text x="{M}" y="{h - 12}" font-size="15" font-weight="800" fill="#111">'
             f'Board 1 · {title}</text>')
    o.append('</svg>')
    return '\n'.join(o)


if __name__ == '__main__':
    errs = check()
    for e in errs:
        print('ERROR', e)
    if errs:
        sys.exit(1)
    here = Path(__file__).parent
    (here / 'board1-components.svg').write_text(svg(False))
    (here / 'board1-copper.svg').write_text(svg(True))
    print(f'ok: {len(PARTS)} parts, {len(LINKS)} links, {len(CUTS)} cuts, {len(PADS)} wires; '
          f'drawings written')

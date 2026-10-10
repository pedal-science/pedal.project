#!/usr/bin/env python3
"""The stripboard checker and drawing, shared by every board layout.

A layout is data: `PARTS` (each with its leads on named nets), `LINKS` (wires on the
component side), `CUTS` (holes where the track is broken) and `PADS` (where a wire leaves the
board).  `stripboard/nets.py` holds the netlist those leads are checked against, so a layout
can be redone without the netlist, or the netlist changed, without the two drifting.

`check()` enforces five rules:

  1. every lead is on the net the netlist puts that pin on -- and every pin of a part the
     board carries is on the board;
  2. no two nets are joined by the copper (a missed cut, or a part lying across two strips);
  3. nothing sits on a cut hole;
  4. no lead, link or pad is under another part's body;
  5. the fit rule: every hole the board uses is inside its outline, and the outline is
     printed in millimetres and holes.

A part that lies along a strip joins the holes it spans unless the cut list says otherwise,
which is what rule 2 catches: it is the classic stripboard mistake and it is silent until
something hums.

Boards are drawn from the same data, so the picture, the build sheet and the check are one
thing.  Coordinates are holes: x along the strips (0 at the left, seen from the component
side), y across them (row 0 at the top).
"""
from collections import defaultdict

import nets as NET

# Pixels per hole and margin, for every drawing.
P = 22
M = 40

NETCOL = {'GND': '#555', 'VF': '#e67e22', 'V9': '#c0392b', 'V9_RAW': '#c0392b',
          'BIAS': '#8e44ad', 'BIAS_MID': '#9b59b6', 'V3A3': '#b8860b'}


def ref_of(pin):
    return pin.partition('.')[0]


def body_holes(kind, pts):
    """The holes a part's body covers, given its lead holes."""
    (x1, y1), (x2, y2) = pts[0], pts[1]
    if kind in ('r', 'd', 'film'):
        if y1 == y2:
            return [(x, y1) for x in range(min(x1, x2) + 1, max(x1, x2))]
        return [(x1, y) for y in range(min(y1, y2) + 1, max(y1, y2))]
    if kind == 'cer':
        return []                      # a 2.5 mm disc between two holes: nothing to cover
    return []


def check(bw, bh, cuts, links, parts, pads, expect_size=None, off_board=(),
          carries=None):
    """Check one board.  Returns (errors, info).

    bw, bh      the outline, in holes (18, 20 is 45.72 x 50.8 mm of stripboard)
    cuts        where the track is broken.  Two forms, and both are real cuts:
                  * (x, y)          at that hole -- the copper there is gone, so a lead in
                                    that hole is joined to nothing unless a hole beside it
                                    carries it to its net;
                  * (x + 0.5, y)    *between* that hole and the one to its right (and
                                    (x, y + 0.5) between it and the one below).  This is what
                                    a 3 mm spot-face cutter does when it is turned between
                                    two holes, which is how a stripboard is normally cut: it
                                    separates the two holes and destroys neither.
    links       [((x, y), (x, y)), ...] wires on the component side
    parts       {ref: (kind, value, [(hole, net), ...])}
    pads        {label: (hole, net, where it goes)} -- wires leaving the board
    off_board   nets the board carries in more than one piece on purpose, joined through a
                part that is not on the board (board 1's Inst/Line toggle joins U1.3 to the
                input network through the switch).  Each must have at least two pads, so the
                join is one the builder can actually make; a net broken by a missed cut has
                no pads to join it and is still an error.
    carries     the netlist parts this board carries.  A circuit built on more than one board
                has its parts spread over them, so each board says which are its own; every
                other part is another board's business.  None means "all of them".
    """
    errors = []
    cuts = set(cuts)

    # -- 1. the netlist agrees with the layout -------------------------------------------
    for ref, (kind, value, leads) in parts.items():
        if ref not in NET.PARTS:
            errors.append(f'{ref} is not a part in the netlist')
            continue
        want = NET.nets_using(ref)
        got = {f'{ref}.{i + 1}': net for i, (_, net) in enumerate(leads)}
        if len(leads) != NET.PARTS[ref]['pins']:
            errors.append(f'{ref} has {len(leads)} leads, the netlist says '
                          f'{NET.PARTS[ref]["pins"]} pins')
        for pin, net in sorted(got.items()):
            if pin not in want:
                errors.append(f'{pin} is on {net}, but {ref} has no such pin')
            elif not NET.same_net(want[pin], net):
                errors.append(f'{pin} is on {net}, the netlist says {want[pin]}')
    for ref in (NET.PARTS if carries is None else carries):
        if ref not in parts:
            errors.append(f'{ref} is carried by this board but not placed on it')
    for ref in parts:
        if carries is not None and ref not in carries:
            errors.append(f'{ref} is on the board but not in its carries list')
    for label, (hole, net, _) in pads.items():
        if net not in NET.NETS and net not in NET.RAILS:
            errors.append(f'pad {label} is on net {net}, which is not in the netlist')

    # -- 2. the copper: union-find over holes, along the strips and through the links ----
    parent = {}

    def find(h):
        parent.setdefault(h, h)
        while parent[h] != h:
            parent[h] = parent[parent[h]]
            h = parent[h]
        return h

    def union(a, b):
        parent[find(a)] = find(b)

    def broken(a, b):
        """Is the track cut between these two neighbouring holes?"""
        if a in cuts or b in cuts:
            return True
        (x1, y1), (x2, y2) = a, b
        mid = ((x1 + x2) / 2, (y1 + y2) / 2)
        return mid in cuts

    for y in range(bh):
        for x in range(bw - 1):
            a, b = (x, y), (x + 1, y)
            if not broken(a, b):
                union(a, b)
    for a, b in links:
        union(a, b)

    used = {}                              # hole -> what is in it
    wire_span = {}                         # hole -> the link running over it
    wire_end = {}                          # hole -> the link ending in it
    lead_holes = set()                     # holes a lead is in
    lead_ref = {}                          # hole -> the lead in it

    def occupy(h, what, wire=False, end=False):
        """Put something in a hole.

        The rules, which are what stripboard actually needs:
          * a lead, a pad and another lead can never share a hole (that is a short);
          * a wire may end where a lead is (that is a soldered joint) but not where a pad is,
            and not where another wire ends;
          * nothing may be soldered where a wire only passes over.
        """
        if not (0 <= h[0] < bw and 0 <= h[1] < bh):
            errors.append(f'{what} at {h} is outside the board {bw}x{bh}')
        if h in cuts and not what.startswith('lead '):
            errors.append(f'{what} at {h} is on a cut hole')
        if h in used:
            if wire and used[h].startswith('lead'):
                pass                       # a wire ending on a lead: the joint
            elif wire and used[h].startswith('link ') and end:
                errors.append(f'{what} and {used[h]} both end at {h}')
            elif wire and end and h in wire_end:
                errors.append(f'{what} and {wire_end[h]} both end at {h}')
            elif used[h].startswith('link '):
                errors.append(f'{what} at {h} is under {used[h]}')
            elif wire and used[h].startswith('pad '):
                errors.append(f'{what} ends on the pad hole {h} ({used[h]})')
            else:
                errors.append(f'{what} and {used[h]} share hole {h}')
        if end and h in wire_end:
            errors.append(f'{what} and {wire_end[h]} both end at {h}')
        used[h] = what
        if wire:
            wire_span[h] = what
            if end:
                wire_end[h] = what

    # Nets that are one node in the pedal (EQUIV) are one net here, so a single ground bus
    # that carries both names is not reported as two nets joined.
    net_of = defaultdict(set)              # net -> the copper islands carrying it
    for ref, (_, _, leads) in parts.items():
        for i, (h, net) in enumerate(leads):
            occupy(h, f'lead {ref}.{i + 1}')
            lead_holes.add(h)
            lead_ref[h] = f'{ref}.{i + 1}'
            net_of[NET.net_key(net)].add(find(h))
    for label, (h, net, _) in pads.items():
        occupy(h, f'pad {label}')
        net_of[NET.net_key(net)].add(find(h))

    # A lead may sit on a cut hole -- the strip is broken at that hole, so the pin is on
    # neither side -- as long as it can still reach its net: through the hole beside it, or
    # along the piece of strip the cut left it on.  If neither, the pin is wired to nothing.
    for h in sorted(lead_holes):
        x, y = h
        if h not in cuts:
            continue
        # The strip left on either side is part of the pin's net, so a cut *between* holes
        # does not strand it.  Only a cut at the pin's own hole can, and then the pin needs a
        # hole beside it to reach its net through.
        strip_either_side = False
        for p in ((x - 1, y), (x + 1, y)):
            if 0 <= p[0] < bw and not broken(h, p):
                strip_either_side = True
        beside = [(x + dx, y + dy) for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0))]
        free_beside = any(0 <= p[0] < bw and 0 <= p[1] < bh and p not in cuts
                          and p not in used for p in beside)
        if not strip_either_side and not free_beside:
            errors.append(f'{lead_ref[h]} is on the cut hole {h} with nothing beside it '
                          f'and no strip left to reach its net along')

    for net, roots in net_of.items():
        if len(roots) > 1 and net not in off_board:
            errors.append(f'net {net} is split into {len(roots)} pieces')
    pad_roots = defaultdict(set)           # net -> islands a pad reaches
    for label, (h, net, _) in pads.items():
        pad_roots[NET.net_key(net)].add(find(h))
    for net in off_board:
        if net not in net_of:
            errors.append(f'off_board names {net}, which is not a net on the board')
        elif len(roots_ := net_of[net]) > 1 and len(pad_roots[net]) < 2:
            errors.append(f'net {net} is in {len(roots_)} pieces with '
                          f'{len(pad_roots[net])} pad(s): nothing joins the pieces')
    owner = {}
    for net, roots in net_of.items():
        for r in roots:
            if r in owner and not NET.same_net(owner[r], net):
                errors.append(f'nets {owner[r]} and {net} are joined')
            owner[r] = net

    # -- 4. bodies ----------------------------------------------------------------------
    for ref, (kind, _, leads) in parts.items():
        pts = [h for h, _ in leads]
        if kind in ('r', 'd', 'film'):
            if pts[0][0] != pts[1][0] and pts[0][1] != pts[1][1]:
                errors.append(f'{ref} is not lying along a strip or a column')
                continue
            span = abs(pts[1][0] - pts[0][0]) + abs(pts[1][1] - pts[0][1])
            need = {'r': 4, 'd': 4, 'film': 2}[kind]
            if span < need:
                errors.append(f'{ref}: leads {span} holes apart, needs {need}')
        for h in body_holes(kind, pts):
            if h in used and used[h] != f'lead {ref}.1' and used[h] != f'lead {ref}.2':
                errors.append(f"{ref}'s body covers {used[h]} at {h}")
        if kind.startswith('el'):
            r = float(kind[2:]) / 2 / 2.54 + 0.15          # radius in holes, plus a little
            cx = sum(p[0] for p in pts) / 2
            cy = sum(p[1] for p in pts) / 2
            for h, what in used.items():
                if what.startswith('lead ' + ref + '.'):
                    continue
                if (h[0] - cx) ** 2 + (h[1] - cy) ** 2 < r * r:
                    errors.append(f"{ref}'s body covers {what} at {h}")
        if kind == 'dip8':
            xs = sorted({p[0] for p in pts})
            ys = sorted({p[1] for p in pts})
            for x in range(min(xs), max(xs) + 1):
                for y in range(min(ys), max(ys) + 1):
                    h = (x, y)
                    if h in used and not used[h].startswith('lead ' + ref + '.') \
                            and h not in cuts:
                        errors.append(f"{ref}'s socket covers {used[h]} at {h}")

    # -- 5. the fit rule ----------------------------------------------------------------
    for net, roots in net_of.items():
        for r in roots:
            if not (0 <= r[0] < bw and 0 <= r[1] < bh):
                errors.append(f'net {net} reaches {r}, outside the board')
    size_x, size_y = (bw - 1) * 2.54, (bh - 1) * 2.54
    info = dict(holes=bw * bh, cols=bw, rows=bh,
                mm=(size_x, size_y),
                used_holes=len(used), cuts=len(cuts), links=len(links))
    if expect_size is not None and (bw, bh) != expect_size:
        errors.append(f'outline is {bw}x{bh} holes, expected {expect_size}')
    return errors, info


# ---------------------------------------------------------------- drawing
def esc(t):
    return (str(t).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


class Sheet:
    """One SVG, in hole coordinates, with the strips, the cuts and the numbering."""

    def __init__(self, bw, bh, mirror=False, tw=0):
        self.bw, self.bh, self.mirror = bw, bh, mirror
        self.extra = tw                       # extra right-hand width, for wire labels
        self.o = []
        self.w = 2 * M + (bw - 1) * P + self.extra
        self.h = 2 * M + (bh - 1) * P + 30

    def X(self, x):
        return M + ((self.bw - 1 - x) if self.mirror else x) * P

    def Y(self, y):
        return M + y * P

    def frame(self, cuts):
        o = self.o
        o.append(f'<rect width="{self.w}" height="{self.h}" fill="#f7f3ea"/>')
        cuts = set(cuts)
        for y in range(self.bh):
            runs, start = [], None
            for x in range(self.bw + 1):
                if x < self.bw and (x, y) not in cuts:
                    start = x if start is None else start
                elif start is not None:
                    runs.append((start, x - 1))
                    start = None
            for a, b in runs:
                x1, x2 = sorted((self.X(a), self.X(b)))
                o.append(f'<rect x="{x1 - 9}" y="{self.Y(y) - 8}" width="{x2 - x1 + 18}" '
                         f'height="16" rx="3" fill="#d9a066" '
                         f'opacity="{0.9 if self.mirror else 0.35}"/>')
        for x in range(self.bw):
            for y in range(self.bh):
                o.append(f'<circle cx="{self.X(x)}" cy="{self.Y(y)}" r="2.6" fill="#3b2a1a"/>')
        for (x, y) in cuts:
            o.append(f'<g stroke="#c00" stroke-width="3">'
                     f'<line x1="{self.X(x) - 7}" y1="{self.Y(y) - 7}" '
                     f'x2="{self.X(x) + 7}" y2="{self.Y(y) + 7}"/>'
                     f'<line x1="{self.X(x) - 7}" y1="{self.Y(y) + 7}" '
                     f'x2="{self.X(x) + 7}" y2="{self.Y(y) - 7}"/></g>')
        for x in range(0, self.bw, 5):
            o.append(f'<text x="{self.X(x)}" y="{M - 18}" font-size="12" text-anchor="middle" '
                     f'fill="#333">{x}</text>')
        for y in range(self.bh):
            tx = M - 26 if not self.mirror else self.w - M + 26
            o.append(f'<text x="{tx}" y="{self.Y(y) + 4}" font-size="12" text-anchor="middle" '
                     f'fill="#333">{y}</text>')

    def links(self, links, colour='#1a5fb4'):
        for a, b in links:
            self.o.append(f'<line x1="{self.X(a[0])}" y1="{self.Y(a[1])}" '
                          f'x2="{self.X(b[0])}" y2="{self.Y(b[1])}" stroke="{colour}" '
                          f'stroke-width="3.5" stroke-linecap="round"/>')

    def wires(self, wires):
        """Off-board wires, as stubs leaving the board edge with the label at the end.

        wires: [(label, (hole), colour)] -- each is drawn from its hole out to the edge and
        beyond, so the picture and the wiring table read as one thing."""
        for label, h, colour in wires:
            x, y = h
            if x >= self.bw - 3:
                x2, anchor = self.w - 12, 'end'
            elif x <= 2:
                x2, anchor = 12, 'start'
            else:
                x2, anchor = (self.X(x) + 60 if not label.startswith('-') else self.X(x) - 60), \
                             'start'
            y2 = self.Y(y)
            self.o.append(f'<line x1="{self.X(x)}" y1="{y2}" x2="{x2}" y2="{y2}" '
                          f'stroke="{colour}" stroke-width="2" stroke-dasharray="6 4"/>')
            self.o.append(f'<text x="{x2 + (6 if anchor == "start" else -6)}" y="{y2 + 4}" '
                          f'font-size="11" font-weight="700" text-anchor="{anchor}" '
                          f'fill="{colour}">{esc(label)}</text>')

    def save(self, path, title):
        self.o.append(f'<text x="{M}" y="{self.h - 12}" font-size="15" font-weight="800" '
                      f'fill="#111">{esc(title)}</text>')
        self.o.append('</svg>')
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" '
                f'width="{self.w}" height="{self.h}" font-family="system-ui,sans-serif">')
        path.write_text('\n'.join([head] + self.o))


def wires_from(pads, pad_colour=None):
    """[(label, hole, colour)] for the wire stubs, coloured by net."""
    out = []
    for label, (h, net, _) in pads.items():
        col = (pad_colour or {}).get(net, NETCOL.get(net, '#0a7d3b'))
        out.append((label, h, col))
    return out

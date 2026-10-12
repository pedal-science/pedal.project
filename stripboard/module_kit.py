#!/usr/bin/env python3
"""What the pedal's module boards are built from, beyond `stripboard.py`.

The module boards are `docs/modules.md`'s proposal: each circuit on its own small piece of
stripboard, joined to the rest of the pedal by keyed cables.  Their cables, pinouts and ground
tree are the map's (`docs/diagrams/modules.html`), and this reads them from the map instead of
keeping a second copy, so a board cannot drift from it:

  * a header's pin count, and which of its pins carry ground, are the map's;
  * a cable the map says carries no ground (the relay coil, the MIDI DIN pair, the battery
    sense, the toggle) has no pin on a board ground;
  * the ground each board hangs from reaches the cable the map's tree points towards the root.

The layouts are in `stripboard/module_boards.py`.  Each is checked by `stripboard.check()`,
against a `Netlist` (this file) with `nets.py`'s interface, and then by the checks below, which
`stripboard.check()` does not make: connector bodies, standoffs, sockets and modules, and a
split check that does not count a socket as joining its own pins.

Coordinates are holes, as everywhere in `stripboard/`: x along the strips, y across them.
"""
import collections
import math
import re
from pathlib import Path

import stripboard as SB

HERE = Path(__file__).resolve().parent
MAP_HTML = HERE.parent / 'docs' / 'diagrams' / 'modules.html'

P = SB.P                     # pixels per hole
PITCH = 2.54                 # mm per hole
STANDOFF_HOLE = 2.5          # mm: the hole drilled for an M2.5 nylon standoff
STANDOFF_FOOT = 5.0          # mm: what the standoff and its screw head cover


# ---------------------------------------------------------------- the netlist
class Netlist:
    """A netlist with `nets.py`'s interface, so `stripboard.check()` can be asked about it.

    `base` is a netlist to start from: the input, output and 9 V boards carry `nets.py`'s
    circuit, split over boards, so they start from it and add only what the modules add.
    `nets` may name one of the base's nets, to put more pins on it."""

    def __init__(self, parts=None, nets=None, base=None, rails=None, equiv=(),
                 keep_equiv=True):
        self.PARTS, self.NETS, self.RAILS, self.EQUIV = {}, {}, {}, []
        if base is not None:
            self.PARTS.update(base.PARTS)
            self.NETS.update({n: set(p) for n, p in base.NETS.items()})
            self.RAILS.update(base.RAILS)
            if keep_equiv:
                self.EQUIV.extend(set(g) for g in base.EQUIV)
        for ref, (kind, value, pins) in (parts or {}).items():
            self.PARTS[ref] = dict(kind=kind, value=value, pins=pins)
        for net, pins in (nets or {}).items():
            self.NETS.setdefault(net, set()).update(pins)
        self.RAILS.update(rails or {})
        self.EQUIV.extend(set(g) for g in equiv)

    def net_of(self):
        out = {}
        for net, pins in self.NETS.items():
            for pin in pins:
                if pin in out:
                    raise SystemExit(f'{pin} is on both {out[pin]} and {net}')
                out[pin] = net
        return out

    def nets_using(self, ref):
        by_pin = self.net_of()
        return {f'{ref}.{n}': by_pin.get(f'{ref}.{n}')
                for n in range(1, self.PARTS[ref]['pins'] + 1)}

    def same_net(self, a, b):
        return a == b or any(a in g and b in g for g in self.EQUIV)

    def net_key(self, net):
        for g in self.EQUIV:
            if net in g:
                return sorted(g)[0]
        return net

    def problems(self, refs):
        errs, by_pin = [], self.net_of()
        for pin in sorted(by_pin):
            ref, _, num = pin.partition('.')
            if ref not in self.PARTS:
                errs.append(f'net {by_pin[pin]} names {pin}, but {ref} is not a part')
            elif not num.isdigit() or not 1 <= int(num) <= self.PARTS[ref]['pins']:
                errs.append(f'net {by_pin[pin]} names {pin}, but {ref} has '
                            f'{self.PARTS[ref]["pins"]} pins')
        for ref in refs:
            for n in range(1, self.PARTS[ref]['pins'] + 1):
                if f'{ref}.{n}' not in by_pin:
                    errs.append(f'{ref}.{n} is on no net')
        return errs


# ---------------------------------------------------------------- the map
_SPACE = re.compile(r'(?:\s+|//[^\n]*)*')
_NUMBER = re.compile(r'-?\d+(?:\.\d+)?')
_NAME = re.compile(r'[A-Za-z_$][\w$]*')


def _js(src, i):
    """The JavaScript literal at src[i:] -- object, array, string, number or name -- and
    where it ends.  The map's data is literals only, which is all this reads."""
    i = _SPACE.match(src, i).end()
    c = src[i]
    if c in '{[':
        close, out = ('}', {}) if c == '{' else (']', [])
        i += 1
        while True:
            i = _SPACE.match(src, i).end()
            if src[i] == close:
                return out, i + 1
            if c == '{':
                if src[i] in '\'"':
                    key, i = _js(src, i)
                else:
                    m = _NAME.match(src, i)
                    key, i = m.group(), m.end()
                i = _SPACE.match(src, i).end() + 1          # the colon
                out[key], i = _js(src, i)
            else:
                v, i = _js(src, i)
                out.append(v)
            i = _SPACE.match(src, i).end()
            if src[i] == ',':
                i += 1
    if c in '\'"':
        out, i = [], i + 1
        while src[i] != c:
            if src[i] == '\\':
                i += 1
            out.append(src[i])
            i += 1
        return ''.join(out), i + 1
    m = _NUMBER.match(src, i)
    if m:
        t = m.group()
        return (float(t) if '.' in t else int(t)), m.end()
    m = _NAME.match(src, i)
    return {'null': None, 'true': True, 'false': False}.get(m.group(), m.group()), m.end()


def pin_name(text):
    """A map pin's short name: 'LIN1 — the buffer’s output' is LIN1."""
    return '—' if text.startswith('—') else text.split(' — ')[0]


def pin_role(text):
    """gnd, nc (the map leaves it unused) or sig."""
    name = pin_name(text)
    if name.startswith('GND') or name == 'BAT −':
        return 'gnd'
    return 'nc' if name == '—' else 'sig'


class Map:
    """docs/diagrams/modules.html's parts (`N`) and cables (`C`), and its ground tree."""

    def __init__(self, path=MAP_HTML):
        src = path.read_text()
        const = {}
        for name in ('N', 'C'):
            const[name] = _js(src, src.index(f'const {name}=') + len(f'const {name}='))[0]
        self.nodes = const['N']
        self.cables = {c['id']: c for c in const['C']}
        self.parent = self._tree()

    def _tree(self, root='CORE'):
        """{ground node: the cable it hangs from, towards the root} -- the Pi is the root."""
        adj = collections.defaultdict(list)
        for c in self.cables.values():
            if c.get('g') and not c.get('svc'):
                a, b = c['g']
                adj[a].append((b, c['id']))
                adj[b].append((a, c['id']))
        parent, todo = {root: None}, collections.deque([root])
        while todo:
            u = todo.popleft()
            for v, cid in adj[u]:
                if v not in parent:
                    parent[v] = cid
                    todo.append(v)
        return parent

    def other_end(self, cid, node):
        c = self.cables[cid]
        return c['to'] if c['from'] == node else c['from']

    def title(self, node):
        return self.nodes[node]['t']


MAP = Map()

# The Pi 40-pin header's ground pins, 1-based, as the header numbers them.
PI_GND_PINS = (6, 9, 14, 20, 25, 30, 34, 39)

CONNECTOR = {
    'XH': 'JST-XH {n}-way (B{n}B-XH-A)',
    'KK': 'Molex KK 254 {n}-way',
    'BOX': '2×{h} IDC box header',
    'PIN': '2.54 mm pin header',
}


# ---------------------------------------------------------------- connectors
class Header:
    """A connector: the end of one of the map's cables, a jumper, or a test point.

    Its pins run down a column (`up` runs them up), one strip each: a connector lying along a
    strip would join its own pins.  `nets` is the board net of each pin, pin 1 first, and None
    where the map leaves the pin unused -- which is then given copper of its own, so a plug
    that does carry something on that pin finds nothing to join it to.

    A 'BOX' header has two rows: odd pins down `at`'s column, even pins in the column beside it
    (to the left with `even_left`).  Its two pins on each strip are parted by a cut between the
    holes: a knife cut, since the pins are 2.54 mm apart."""

    BODY = {'XH': (1, 1), 'KK': (1, 0), 'BOX': (1, 2), 'PIN': (0, 0)}   # side, beyond the ends

    def __init__(self, at, nets, cable=None, name=None, family='XH', up=False, names=None,
                 to=None, even_left=False, what=None, show=None):
        self.at, self.nets, self.cable = at, list(nets), cable
        self.name = name or cable
        self.family, self.up, self.even_left = family, up, even_left
        self.names, self.to, self.what = names, to, what
        self.show = show                     # which pins to name in the drawing (BOX)

    def holes(self):
        x, y = self.at
        dy = -1 if self.up else 1
        if self.family == 'BOX':
            dx = -1 if self.even_left else 1
            return [(x + (i % 2) * dx, y + (i // 2) * dy) for i in range(len(self.nets))]
        return [(x, y + i * dy) for i in range(len(self.nets))]

    def label(self, i):
        return f'{self.name}.{i + 1}'

    def body(self):
        """(holes the body covers, holes beside it nothing may be soldered in)."""
        hs = self.holes()
        side, ends = self.BODY[self.family]
        xs, ys = [h[0] for h in hs], [h[1] for h in hs]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        if self.family == 'BOX':
            occ = {(x, y) for x in range(x0 - side, x1 + side + 1)
                   for y in range(y0 - ends, y1 + ends + 1)}
            return occ, set()
        occ = {(x, y) for x in range(x0 - side, x1 + side + 1) for y in range(y0, y1 + 1)}
        clr = set()
        for k in range(1, ends + 1):
            clr |= {(x0, y0 - k), (x0, y1 + k)}
        return occ, clr

    def pin_names(self):
        if self.names:
            return list(self.names)
        if self.cable:
            return [pin_name(t) for t in MAP.cables[self.cable]['pins']]
        return [''] * len(self.nets)

    def describe(self):
        if self.what:
            return self.what
        n = len(self.nets)
        return CONNECTOR[self.family].format(n=n, h=n // 2)


# ---------------------------------------------------------------- part geometry
DIP = {'dip6': 6, 'dip8': 8, 'relay': 10}


def _span(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def part_body(kind, holes):
    """(holes the part covers besides its leads, what is wrong with its own geometry)."""
    errs, body = [], set()
    if kind in ('r', 'd', 'film', 'rs', 'ds', 'cer') or kind.startswith('el'):
        a, b = holes
        if a[0] != b[0] and a[1] != b[1]:
            return body, ['is not along a strip or down a column']
        least, most = {'r': (4, 9), 'd': (4, 9), 'film': (2, 4), 'rs': (1, 2), 'ds': (1, 2),
                       'cer': (1, 1)}.get(kind, (1, 1))
        if kind.startswith('el'):
            least = most = SB.lead_span(kind)[1]
        if not least <= _span(a, b) <= most:
            errs.append(f'has its leads {_span(a, b)} holes apart; a {kind} needs '
                        f'{least}-{most}')
        if kind in ('r', 'd', 'film'):
            body = set(SB.body_holes(kind, holes))
        if kind.startswith('el'):
            r = SB.body_radius(kind)
            cx, cy = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            body = {(x, y) for x in range(int(cx - r) - 1, int(cx + r) + 2)
                    for y in range(int(cy - r) - 1, int(cy + r) + 2)
                    if (x - cx) ** 2 + (y - cy) ** 2 < r * r} - set(holes)
    elif kind in DIP:
        n = DIP[kind]
        x, y = holes[0]
        want = [(x, y + i) for i in range(n // 2)] + [(x + 3, y + n // 2 - 1 - i)
                                                       for i in range(n // 2)]
        if list(holes) != want:
            errs.append(f'is not a {n}-pin DIP footprint: pins 1-{n // 2} down a column, '
                        f'the rest back up the column three holes along')
        body = {(xx, yy) for xx in range(x, x + 4) for yy in range(y, y + n // 2)} - set(holes)
    elif kind == 'to92':
        a, b, c = holes
        if not (_span(a, b) == 1 and _span(b, c) == 1 and _span(a, c) == 2
                and (a[0] == c[0] or a[1] == c[1])):
            errs.append('has its three legs out of line: a TO-92 goes in three holes in a row')
    elif kind != 'module':
        errs.append(f'is a {kind}, which the kit does not know')
    return body, errs


# ---------------------------------------------------------------- one board
class Board:
    """One module board: its outline, parts, headers, links, standoffs and notes.

    parts    {ref: (kind, value, [hole of pin 1, pin 2, ...])} -- the nets come from the
             netlist, so a layout puts a part's pins in holes and cannot put them on a net
    links    [((x, y), (x, y), net)]: wires on the component side.  The net is what the wire
             is for, and it is checked: the copper at each end has to be that net's
    mounts   standoff holes, drilled 2.5 mm through a hole of the grid
    grounds  {board ground net: the map's ground node it is}
    modules  {ref: dict(outline=(x0, y0, x1, y1) in holes, names=[pin names],
             joined=[[pins joined inside it], ...], label=...)} for a bought board seated in
             socket strips: links may pass under it, parts may not
    """

    def __init__(self, key, node, W, H, netlist, parts, headers=(), links=(), mounts=(),
                 cuts=(), grounds=None, off_board=(), trim=(), carries=None, modules=None,
                 title=None, job=None, notes=(), alias=None, absent=(), part_notes=None,
                 pin_labels=None):
        self.key, self.node, self.W, self.H = key, node, W, H
        self.netlist, self.parts_at = netlist, dict(parts)
        self.headers, self.links = list(headers), list(links)
        self.mounts, self.manual_cuts = list(mounts), set(cuts)
        self.grounds = dict(grounds or {})
        self.off_board, self.trim = set(off_board), set(trim)
        self.carries = set(carries) if carries is not None else set(self.parts_at)
        self.modules = dict(modules or {})
        self.title = title or MAP.title(node)
        self.job = job or MAP.nodes[node].get('job', '')
        self.notes, self.alias = list(notes), dict(alias or {})
        self.absent, self.part_notes = set(absent), dict(part_notes or {})
        self.pin_labels = dict(pin_labels or {})
        self._build()

    # -- the data the checker takes ----------------------------------------------------
    def _build(self):
        nl = self.netlist
        self.errors = nl.problems(sorted(self.carries))
        self.parts = {}
        for ref, (kind, value, holes) in self.parts_at.items():
            if ref not in nl.PARTS:
                self.errors.append(f'{ref} is not a part in the netlist')
                continue
            nets = nl.nets_using(ref)
            if len(holes) != len(nets):
                self.errors.append(f'{ref} has {len(holes)} holes, the netlist says '
                                   f'{len(nets)} pins')
                continue
            self.parts[ref] = (kind, value, [(h, nets[f'{ref}.{i + 1}'])
                                             for i, h in enumerate(holes)])
        self.pads, rails = {}, {}
        for hd in self.headers:
            for i, (h, net) in enumerate(zip(hd.holes(), hd.nets)):
                if net is None:
                    net = f'NC:{hd.label(i)}'
                    rails[net] = 'a pin the map leaves unused'
                self.pads[hd.label(i)] = (h, net, hd.name)
        self.check_netlist = Netlist(base=nl, rails=rails)
        self.tagged = {}                                # hole -> net, for every soldered thing
        for ref, (_, _, leads) in self.parts.items():
            for h, net in leads:
                self.tagged[h] = net
        for _, (h, net, _) in self.pads.items():
            self.tagged[h] = net
        self.solder = set(self.tagged)
        self.wire_holes = set()
        for a, b, net in self.links:
            for h in SB._span(a, b):
                self.wire_holes.add(h)
            for h in (a, b):
                self.tagged.setdefault(h, net)
        self.cuts = self._cuts()

    def _cuts(self):
        """The manual cuts, the standoffs (a 2.5 mm hole takes the copper with it), and the
        cuts that keep each strip to one net.

        Wherever two soldered holes along a strip are on different nets and nothing already
        breaks the strip between them, one cut: at a free hole between them, nearest the
        middle, or between the two holes when there is no free hole.  Then the nets in `trim`
        (the 1 MΩ input) have their strips cut short at both ends, so each is no longer than
        the parts on it."""
        nl = self.check_netlist
        cuts = set(self.manual_cuts) | set(self.mounts)
        blocked = self.solder | self.wire_holes | set(self.mounts)

        def broken(y, a, b):
            return any(cy == y and a < cx < b for cx, cy in cuts)

        for y in range(self.H):
            xs = sorted(x for (x, yy) in self.tagged if yy == y)
            for a, b in zip(xs, xs[1:]):
                na, nb = self.tagged[(a, y)], self.tagged[(b, y)]
                if nl.same_net(na, nb) or broken(y, a, b):
                    continue
                free = [x for x in range(a + 1, b) if (x, y) not in blocked]
                if na in self.trim:
                    free.sort()
                elif nb in self.trim:
                    free.sort(reverse=True)
                else:
                    free.sort(key=lambda x: (abs(x - (a + b) / 2), x))
                cuts.add((free[0], y) if free else (a + 0.5, y))
        for y in range(self.H):
            xs = sorted(x for (x, yy) in self.tagged if yy == y)
            for x in xs:
                net = self.tagged[(x, y)]
                if net not in self.trim:
                    continue
                run = [xx for xx in xs if nl.same_net(self.tagged[(xx, y)], net)
                       and not broken(y, min(x, xx), max(x, xx))]
                lo, hi = min(run), max(run)
                if lo > 0 and not broken(y, -1, lo):
                    cuts.add((lo - 1, y) if (lo - 1, y) not in blocked else (lo - 0.5, y))
                if hi < self.W - 1 and not broken(y, hi, self.W):
                    cuts.add((hi + 1, y) if (hi + 1, y) not in blocked else (hi + 0.5, y))
        return cuts

    def joins(self):
        """Pairs of holes joined inside a bought module (its own ground plane)."""
        out = []
        for ref, m in self.modules.items():
            leads = self.parts[ref][2]
            for group in m.get('joined', ()):
                hs = [leads[p - 1][0] for p in group]
                out += list(zip(hs, hs[1:]))
        return out

    def copper(self):
        return SB.copper(self.W, self.H, self.cuts,
                         [(a, b) for a, b, _ in self.links] + self.joins())

    # -- the checks ---------------------------------------------------------------------
    def check(self):
        errs = list(self.errors)
        links = [(a, b) for a, b, _ in self.links]
        e, self.info = SB.check(self.W, self.H, self.cuts, links, self.parts, self.pads,
                                off_board=self.off_board, carries=self.carries,
                                netlist=self.check_netlist)
        errs += e
        errs += self._check_pieces()
        errs += self._check_bodies()
        errs += self._check_mounts()
        errs += self._check_map()
        return errs

    def _check_pieces(self):
        """Each net in one piece, without `stripboard.check()`'s allowance that a part joins
        its own leads in one column: a socket's pins are joined by nothing, and an op-amp
        whose follower link is missing must show as a split net, not pass."""
        errs, nl = [], self.check_netlist
        find = self.copper()
        pieces = collections.defaultdict(set)
        for h, net in self.tagged.items():
            if h in self.solder:
                pieces[nl.net_key(net)].add(find(h))
        for net, roots in sorted(pieces.items()):
            if len(roots) > 1 and net not in self.off_board:
                errs.append(f'net {net} is in {len(roots)} pieces of copper')
        for a, b, net in self.links:
            for h in (a, b):
                on = {nl.net_key(n) for hh, n in self.tagged.items()
                      if hh in self.solder and find(hh) == find(h)}
                if nl.net_key(net) not in on:
                    errs.append(f'the {net} link {a}-{b} ends on {sorted(on)} copper at {h}')
                if h in self.solder:
                    errs.append(f'the link {a}-{b} ends in a lead or pin hole at {h}: '
                                f'end it in the free hole beside')
        for c in self.cuts:
            if c in self.solder:
                errs.append(f'a cut at {c} is in a hole a lead or pin goes through')
        return errs

    def objects(self):
        """[(name, holes it covers, holes nothing may be soldered in, raised over)], and
        what is wrong with any part's own footprint."""
        out, errs = [], []
        for ref, (kind, _, leads) in self.parts.items():
            holes = [h for h, _ in leads]
            body, e = part_body(kind, holes)
            errs += [f'{ref} {x}' for x in e]
            raised = set()
            if ref in self.modules:
                x0, y0, x1, y1 = self.modules[ref]['outline']
                raised = {(x, y) for x in range(math.ceil(x0), math.floor(x1) + 1)
                          for y in range(math.ceil(y0), math.floor(y1) + 1)} - set(holes)
            out.append((ref, set(holes) | body, set(), raised))
        for hd in self.headers:
            occ, clr = hd.body()
            out.append((hd.name, occ, clr, set()))
        for m in self.mounts:
            x, y = m
            ring = {(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)} - {m}
            out.append((f'the standoff at {m}', {m}, ring, set()))
        return out, errs

    def _check_bodies(self):
        objs, errs = self.objects()
        own = {}
        for ref, (_, _, leads) in self.parts.items():
            for h, _ in leads:
                own[h] = ref
        for _, (h, _, name) in self.pads.items():
            own[h] = name
        for i, (na, occ_a, clr_a, raised_a) in enumerate(objs):
            off = [h for h in occ_a if not (0 <= h[0] < self.W and 0 <= h[1] < self.H)]
            if off:
                errs.append(f'{na} reaches {off[0]}, off the board')
            for nb, occ_b, clr_b, _ in objs[i + 1:]:
                if occ_a & occ_b:
                    errs.append(f'{na} and {nb} both cover {sorted(occ_a & occ_b)[0]}')
                crowd = (occ_a & clr_b) | (occ_b & clr_a)
                if crowd:
                    errs.append(f'{na} and {nb} are too close at {sorted(crowd)[0]}')
            for h in self.solder:
                if own.get(h) != na and (h in occ_a or h in clr_a or h in raised_a):
                    errs.append(f'{own.get(h, "a pin")} at {h} is under or beside {na}')
            for h in self.wire_holes:
                if h in occ_a or h in clr_a:
                    errs.append(f'a link at {h} runs under or beside {na}')
            for nb, occ_b, _, _ in objs:
                if nb != na and raised_a & occ_b:
                    errs.append(f'{nb} is under {na}, which sits on socket strips above it')
        return errs

    def _check_mounts(self):
        errs = []
        if len(self.mounts) < 2:
            errs.append(f'{len(self.mounts)} standoff hole(s): a board wants at least two')
        for x, y in self.mounts:
            if not (1 <= x <= self.W - 2 and 1 <= y <= self.H - 2):
                errs.append(f'the standoff at {(x, y)} is on the edge row: a 2.5 mm hole '
                            f'there breaks through the board edge')
        return errs

    def _check_map(self):
        """Every connector against the map: pins, ground, and the cable towards the root."""
        errs, mine = [], set()
        node = self.node

        def is_mine(gnode):
            return gnode == node or gnode.startswith(node + ':')

        for hd in self.headers:
            if not hd.cable:
                continue
            c = MAP.cables.get(hd.cable)
            if c is None:
                errs.append(f'{hd.cable} is not a cable in the map')
                continue
            if node not in (c['from'], c['to']):
                errs.append(f'{hd.cable} joins {c["from"]} and {c["to"]}, not {node}')
            mine.add(hd.cable)
            pins = c['pins']
            conn = c['conn'] if isinstance(c['conn'], str) else c['conn']['A']
            if conn != 'IDC40' and len(pins) != len(hd.nets):
                errs.append(f'{hd.cable} has {len(hd.nets)} pins here, {len(pins)} in the map')
                continue
            want = {'XH': {'XH'}, 'IDC14': {'KK', 'BOX'}, 'IDC40': {'BOX'}, 'SH4': {'PIN'}}
            if hd.family not in want.get(conn, {hd.family}):
                errs.append(f'{hd.cable} is a {hd.family} header, the map says {conn}')
            # D1 is the Pi's whole 40-pin header. The map describes it in one line rather
            # than forty, and the board carries the header one pin to one pin.
            if conn == 'IDC40':
                if len(hd.nets) != 40:
                    errs.append(f'{hd.cable} has {len(hd.nets)} pins; the Pi header has 40')
                elif not all(hd.nets[i - 1] in self.grounds for i in PI_GND_PINS):
                    errs.append(f'{hd.cable}: the Pi header\'s eight ground pins are not all '
                                f'on this board\'s ground')
                continue
            gnode = next((g for g in (c.get('g') or ()) if is_mine(g)), None)
            for i, (text, net) in enumerate(zip(pins, hd.nets)):
                role = pin_role(text)
                ground = self.is_ground(net)
                if role == 'nc' and net is not None:
                    errs.append(f'{hd.label(i)} is on {net}; the map leaves it unused')
                if role != 'nc' and net is None:
                    errs.append(f'{hd.label(i)} is unconnected; the map says {pin_name(text)}')
                if role == 'gnd' and not ground:
                    errs.append(f'{hd.label(i)} is {pin_name(text)} in the map but on {net}')
                if role == 'sig' and ground:
                    errs.append(f'{hd.label(i)} is on ground ({net}); the map says '
                                f'{pin_name(text)}')
                if ground and c.get('g') is None:
                    errs.append(f'{hd.cable} carries no ground in the map, but '
                                f'{hd.label(i)} is on {net}')
                if ground and gnode and self.grounds[net] != gnode:
                    errs.append(f'{hd.label(i)} is on {net} ({self.grounds[net]}), but '
                                f'{hd.cable} carries the ground of {gnode}')
        for c in MAP.cables.values():
            if (node in (c['from'], c['to']) and c['k'] != 'ext' and not c.get('svc')
                    and c['id'] not in mine and c['id'] not in self.absent):
                errs.append(f'the map has {c["id"]} on {node}, and this board has no header '
                            f'for it')
        for net, gnode in self.grounds.items():
            up = MAP.parent.get(gnode)
            if up is None:
                errs.append(f'{gnode} is not in the map\'s ground tree')
                continue
            hd = next((h for h in self.headers if h.cable == up), None)
            # A ground may reach that cable under its own name, under a name the netlist
            # calls the same node, or through a module that joins the two. The carrier's
            # analogue bus meets the digital ground inside the codec, and only there.
            if not self._ground_reaches(net, hd):
                errs.append(f'{net} ({gnode}) must reach {up}, the cable towards the root, '
                            f'and does not')
        # Two grounds of one map node meet inside a module, not on the board's copper.
        by_node = collections.defaultdict(list)
        for net, gnode in self.grounds.items():
            by_node[gnode].append(net)
        bare = SB.copper(self.W, self.H, self.cuts, [(a, b) for a, b, _ in self.links])
        full = self.copper()
        for nets in by_node.values():
            holes = {net: next(h for h, n in self.tagged.items()
                               if h in self.solder and self.check_netlist.same_net(n, net))
                     for net in nets}
            for i, a in enumerate(nets):
                for b in nets[i + 1:]:
                    if bare(holes[a]) == bare(holes[b]):
                        errs.append(f'{a} and {b} are joined by the board\'s copper; '
                                    f'they may meet only inside the module')
                    elif full(holes[a]) != full(holes[b]):
                        errs.append(f'{a} and {b} never meet')
        return errs

    def _ground_reaches(self, net, header):
        """True when `net` gets to the root cable, itself or through a module."""
        if header is None:
            return False
        nl, find = self.check_netlist, self.copper()

        def on(name):
            return [h for h, n in self.tagged.items()
                    if h in self.solder and nl.same_net(n, name)]

        if any(nl.same_net(n, net) for n in header.nets if n is not None):
            return True
        here = {find(h) for h in on(net)}
        for other in self.grounds:
            if not any(nl.same_net(n, other) for n in header.nets if n is not None):
                continue
            if any(find(h) in here for h in on(other)):
                return True
        return False

    def is_ground(self, net):
        return net is not None and any(self.check_netlist.same_net(net, g)
                                       for g in self.grounds)

    def root_cable(self, net):
        return MAP.parent.get(self.grounds.get(net))

    # -- what the drawing needs ---------------------------------------------------------
    def pieces(self):
        """[(y, x0, x1, net or None)]: every run of strip between cuts, and what it carries."""
        nl, find = self.check_netlist, self.copper()
        net_at_root = {}
        for h, net in self.tagged.items():
            net_at_root.setdefault(find(h), set()).add(nl.net_key(net))
        out = []
        for y in range(self.H):
            x = 0
            while x < self.W:
                if (x, y) in self.cuts:
                    x += 1
                    continue
                x0 = x
                while x + 1 < self.W and (x + 1, y) not in self.cuts \
                        and (x + 0.5, y) not in self.cuts:
                    x += 1
                nets = net_at_root.get(find((x0, y)), set())
                out.append((y, x0, x, sorted(nets)[0] if len(nets) == 1 else
                            ('?' if nets else None)))
                x += 1
        return out

    def size_mm(self):
        return self.W * PITCH, self.H * PITCH


# ---------------------------------------------------------------- drawing
def esc(t):
    return str(t).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


GREEN, RED, AMBER, BLUE = '#15803d', '#b91c1c', '#b45309', '#1a5fb4'
KIND_COLOUR = {'audio': '#c2410c', 'power': '#b91c1c', 'digital': '#1d4ed8',
               'control': '#7e22ce', 'service': '#6b7280'}
SUPPLY = re.compile(r'^(V9|VF|V9_RAW|VRAIL|5V|VIN|VSYS|V5|AVDD|VA|COIL\+)')
LOGIC = re.compile(r'^(3V3)')


def net_colour(board, net):
    if net in (None, '?') or net.startswith('NC:'):
        return None
    keys = {board.check_netlist.net_key(g) for g in board.grounds}
    if board.check_netlist.net_key(net) in keys:
        return GREEN
    if SUPPLY.match(net):
        return RED
    if LOGIC.match(net):
        return AMBER
    return None


def text_w(s, size, bold=False):
    return len(s) * size * (0.60 if bold else 0.56)


class Placer:
    """Labels that do not land on each other, or on what the drawing has said is solid."""

    def __init__(self):
        self.boxes = []

    def block(self, x0, y0, x1, y1):
        self.boxes.append((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))

    def hits(self, b):
        return sum(1 for o in self.boxes
                   if b[0] < o[2] and b[2] > o[0] and b[1] < o[3] and b[3] > o[1])

    def place(self, s, size, spots, bold=True):
        """Put text at the first of `spots` [(x, y, anchor)] that is clear, else at the least
        crowded one, and say where."""
        best = None
        w, h = text_w(s, size, bold), size * 1.15
        for x, y, anchor in spots:
            x0 = x - (w if anchor == 'end' else w / 2 if anchor == 'middle' else 0)
            b = (x0 - 2, y - h * 0.82, x0 + w + 2, y + h * 0.25)
            n = self.hits(b)
            if best is None or n < best[0]:
                best = (n, (x, y, anchor), b)
            if n == 0:
                break
        self.boxes.append(best[2])
        return best[1]


class View:
    """One side of the board: hole (x, y) to pixels, mirrored for the copper side."""

    def __init__(self, board, ox, oy, mirror=False):
        self.b, self.ox, self.oy, self.mirror = board, ox, oy, mirror

    def X(self, x):
        return self.ox + ((self.b.W - 1 - x) if self.mirror else x) * P

    def Y(self, y):
        return self.oy + y * P

    def pt(self, h):
        return self.X(h[0]), self.Y(h[1])


class Svg:
    def __init__(self):
        self.o = []

    def add(self, s):
        self.o.append(s)

    def line(self, x1, y1, x2, y2, stroke, w=1.5, extra=''):
        self.o.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                      f'stroke="{stroke}" stroke-width="{w}" {extra}/>')

    def text(self, x, y, s, size=11, anchor='start', fill='#111', bold=False):
        weight = ' font-weight="700"' if bold else ''
        self.o.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" '
                      f'text-anchor="{anchor}" fill="{fill}"{weight}>{esc(s)}</text>')

    def plate(self, x, y, s, size, anchor, fill='#111', bold=True, bg='#fffdf7', op=0.9):
        w = text_w(s, size, bold)
        x0 = x - (w if anchor == 'end' else w / 2 if anchor == 'middle' else 0)
        self.o.append(f'<rect x="{x0 - 2:.1f}" y="{y - size * 0.92:.1f}" width="{w + 4:.1f}" '
                      f'height="{size * 1.2:.1f}" rx="2" fill="{bg}" opacity="{op}"/>')
        self.text(x, y, s, size, anchor, fill, bold)


SIDE = 250            # px either side of the board for the connectors' labels
PANEL = 480           # px for the parts, connectors and notes


def draw(board, path, extra_title=None):
    """The build sheet: the component side, the copper side mirrored, and beside them the
    parts, the connectors and the notes."""
    W, H = board.W, board.H
    s = Svg()
    top = 104
    comp = View(board, SIDE + P / 2, top + 30 + P / 2)
    cop = View(board, SIDE + P / 2, comp.oy + H * P + 78, mirror=True)
    width = int(SIDE + W * P + SIDE + PANEL)
    placer = Placer()
    pieces = board.pieces()

    def al(t):
        return board.alias.get(t, t)

    for v, name in ((comp, 'COMPONENT SIDE'),
                    (cop, 'COPPER SIDE, mirrored: what you see when you cut the tracks')):
        _draw_copper(board, s, v, name, pieces, v is comp)
    _draw_net_names(board, s, cop, pieces, al)
    for h in board.solder:
        px, py = cop.pt(h)
        s.add(f'<circle cx="{px}" cy="{py}" r="4.2" fill="none" stroke="#3b2a1a" '
              f'stroke-width="1.6"/>')
    for mx, my in board.mounts:
        px, py = comp.pt((mx, my))
        r = STANDOFF_FOOT / PITCH * P / 2
        placer.block(px - r, py - r, px + r, py + r)

    labels = []
    _draw_modules(board, s, comp, al)
    _draw_links(board, s, comp)
    _draw_parts(board, s, comp, placer, labels, al)
    _draw_headers(board, s, comp, placer, labels, al)
    for t, spots in labels:
        x, y, anchor = placer.place(t, 10.5, spots)
        s.plate(x, y, t, 10.5, anchor)

    mm = board.size_mm()
    s.text(24, 36, extra_title or board.title, 22, bold=True)
    s.text(24, 58, f'{W} × {H} holes · cut to {mm[0]:.1f} × {mm[1]:.1f} mm · '
                   f'{len([c for c in board.cuts if c not in board.mounts])} cuts · '
                   f'{len(board.links)} links · {len(board.mounts)} standoff holes '
                   f'({STANDOFF_HOLE:g} mm, for M2.5 nylon standoffs)', 12.5, fill='#444')
    s.text(24, 77, board.job, 11.5, fill='#555')
    px0 = SIDE + W * P + SIDE + 10
    y = top + 4
    for kind, t in panel_lines(board):
        if kind == 'h':
            y += 12
            s.text(px0, y, t, 12.5, bold=True, fill='#222')
            y += 4
            continue
        for k, part in enumerate(wrap(t, 76 if kind != 'cont' else 72)):
            y += 14.5
            indent = 12 if (kind == 'cont' or k > 0) else 0
            cut = part.find('  ') if (kind == 'row' and k == 0) else -1
            if cut > 0:
                s.add(f'<text x="{px0}" y="{y:.1f}" font-size="11" fill="#222">'
                      f'<tspan font-weight="700">{esc(part[:cut])}</tspan>'
                      f'{esc(part[cut:])}</text>')
            else:
                s.text(px0 + indent, y, part, 11, fill='#333')
        y += 2
    height = int(max(cop.oy + H * P + 34, y + 30)) + 22
    s.text(24, height - 14, 'Red ✕: cut the track at that hole (red bar: cut between two '
                            'holes). Lines: wire links on the component side (green carries '
                            'ground). Strips tinted green carry ground, red a supply, amber '
                            '3.3 V. White circles: standoff holes; dashed: what the standoff '
                            'covers.', 10, fill='#555')
    head = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}" font-family="system-ui,-apple-system,'
            f'Segoe UI,Helvetica,Arial,sans-serif"><rect width="{width}" height="{height}" '
            f'fill="#fbf8f1"/>')
    path.write_text('\n'.join([head] + s.o + ['</svg>']))


def _draw_copper(board, s, v, name, pieces, component):
    W, H = board.W, board.H
    x0, y0 = v.ox - P / 2, v.oy - P / 2
    s.text(x0, y0 - 30, name, 12.5, bold=True, fill='#333')
    s.add(f'<rect x="{x0}" y="{y0}" width="{W * P}" height="{H * P}" rx="3" '
          f'fill="{"#f3ecdc" if component else "#e9dcc0"}" stroke="#8a7f6a" '
          f'stroke-width="1.2"/>')
    for y, a, b, net in pieces:
        xa, xb = sorted((v.X(a), v.X(b)))
        box = (f'x="{xa - P * 0.42:.1f}" y="{v.Y(y) - P * 0.36:.1f}" '
               f'width="{xb - xa + P * 0.84:.1f}" height="{P * 0.72:.1f}" rx="3"')
        s.add(f'<rect {box} fill="#d9a066" opacity="{0.3 if component else 0.95}"/>')
        col = '#e11d48' if net == '?' else net_colour(board, net)
        if col:
            s.add(f'<rect {box} fill="{col}" opacity="{0.2 if component else 0.34}"/>')
    for x in range(W):
        for y in range(H):
            s.add(f'<circle cx="{v.X(x)}" cy="{v.Y(y)}" r="2.3" fill="#4a3826"/>')
    op = 0.4 if component else 1
    for cx, cy in sorted(board.cuts):
        if (cx, cy) in board.mounts:
            continue
        py = v.Y(cy)
        if cx != int(cx):
            px = (v.X(math.floor(cx)) + v.X(math.ceil(cx))) / 2
            s.line(px, py - 10, px, py + 10, '#c00', 4, f'opacity="{op}"')
        else:
            px = v.X(cx)
            s.add(f'<g stroke="#c00" stroke-width="{2 if component else 3}" opacity="{op}">'
                  f'<line x1="{px - 6}" y1="{py - 6}" x2="{px + 6}" y2="{py + 6}"/>'
                  f'<line x1="{px - 6}" y1="{py + 6}" x2="{px + 6}" y2="{py - 6}"/></g>')
    for x in range(0, W, 5):
        s.text(v.X(x), y0 - 8, str(x), 10, 'middle', '#555')
    for y in range(H):
        if v.mirror:
            s.text(x0 + W * P + 6, v.Y(y) + 3.5, str(y), 9, 'start', '#777')
        else:
            s.text(x0 - 6, v.Y(y) + 3.5, str(y), 9, 'end', '#777')
    for mx, my in board.mounts:
        px, py = v.pt((mx, my))
        s.add(f'<circle cx="{px}" cy="{py}" r="{STANDOFF_FOOT / PITCH * P / 2:.1f}" '
              f'fill="none" stroke="#6b7280" stroke-width="1.2" stroke-dasharray="3 3"/>')
        s.add(f'<circle cx="{px}" cy="{py}" r="{STANDOFF_HOLE / PITCH * P / 2:.1f}" '
              f'fill="#fff" stroke="#374151" stroke-width="2"/>')


def _draw_net_names(board, s, v, pieces, al):
    for y, a, b, net in pieces:
        if net in (None, '?') or net.startswith('NC:') or b - a < 2:
            continue
        xa, xb = sorted((v.X(a), v.X(b)))
        t = al(net)
        if text_w(t, 8.5, True) > xb - xa + P * 0.5:
            continue
        s.add(f'<text x="{(xa + xb) / 2:.1f}" y="{v.Y(y) + 3:.1f}" font-size="8.5" '
              f'text-anchor="middle" font-weight="700" fill="#3b2410">{esc(t)}</text>')


def _draw_modules(board, s, v, al):
    for ref, m in board.modules.items():
        x0, y0, x1, y1 = m['outline']
        px0, py0, px1, py1 = v.X(x0), v.Y(y0), v.X(x1), v.Y(y1)
        s.add(f'<rect x="{px0:.1f}" y="{py0:.1f}" width="{px1 - px0:.1f}" '
              f'height="{py1 - py0:.1f}" rx="5" fill="{m.get("fill", "#fde68a")}" '
              f'opacity="0.4" stroke="#92400e" stroke-width="1.5" stroke-dasharray="7 4"/>')
        leads = board.parts[ref][2]
        xs = sorted({h[0] for h, _ in leads})
        for cx in xs:
            ys = [h[1] for h, _ in leads if h[0] == cx]
            s.add(f'<rect x="{v.X(cx) - 5}" y="{v.Y(min(ys)) - 9}" width="10" '
                  f'height="{(max(ys) - min(ys)) * P + 18}" rx="2" fill="#1f2937" '
                  f'opacity="0.85"/>')
        for i, (h, net) in enumerate(leads):
            px, py = v.pt(h)
            s.add(f'<circle cx="{px}" cy="{py}" r="3" fill="#e5e7eb"/>')
            first = h[0] == xs[0]
            s.text(px + (9 if first else -9), py + 3.5, m['names'][i], 8.5,
                   'start' if first else 'end', '#78350f', bold=True)
        lines = m.get('label', f'{ref} {board.parts[ref][1]}').split('\n')
        cy = (py0 + py1) / 2 - (len(lines) - 1) * 8
        for k, t in enumerate(lines):
            s.plate((px0 + px1) / 2, cy + k * 16, t, 12, 'middle', '#78350f', True,
                    '#fef3c7', 0.95)


def _draw_links(board, s, v):
    for a, b, net in board.links:
        col = GREEN if net_colour(board, net) == GREEN else BLUE
        (x1, y1), (x2, y2) = v.pt(a), v.pt(b)
        s.line(x1, y1, x2, y2, col, 3.6, 'stroke-linecap="round"')
        for px, py in ((x1, y1), (x2, y2)):
            s.add(f'<circle cx="{px}" cy="{py}" r="3.6" fill="{col}"/>')


def _draw_parts(board, s, v, placer, labels, al):
    for ref, (kind, val, leads) in board.parts.items():
        if ref in board.modules:
            continue
        pts = [v.pt(h) for h, _ in leads]
        name = f'{al(ref)} {val}'
        pins = board.pin_labels.get(ref)
        if kind in DIP:
            n = DIP[kind]
            xa, xb = min(p[0] for p in pts) - 10, max(p[0] for p in pts) + 10
            ya, yb = min(p[1] for p in pts) - 11, max(p[1] for p in pts) + 11
            s.add(f'<rect x="{xa}" y="{ya}" width="{xb - xa}" height="{yb - ya}" rx="3" '
                  f'fill="{"#44403c" if kind == "relay" else "#27272a"}" opacity="0.9"/>')
            if kind == 'relay':
                s.add(f'<rect x="{xa}" y="{ya}" width="{xb - xa}" height="5" fill="#e5e7eb"/>')
            else:
                s.add(f'<path d="M{(xa + xb) / 2 - 6} {ya} a6 6 0 0 0 12 0" fill="#f3ecdc"/>')
            for i, (px, py) in enumerate(pts):
                s.add(f'<circle cx="{px}" cy="{py}" r="3.4" fill="#d4d4d8"/>')
                t = pins[i] if pins else str(i + 1)
                first = i < n // 2
                s.text(px + (6 if first else -6), py + 3.2, t, 8, 'start' if first else 'end',
                       '#fafafa', bold=True)
            placer.block(xa, ya, xb, yb)
            labels.append((name, [((xa + xb) / 2, ya - 6, 'middle'),
                                  ((xa + xb) / 2, yb + 13, 'middle'),
                                  (xb + 6, (ya + yb) / 2, 'start'),
                                  (xa - 6, (ya + yb) / 2, 'end')]))
            continue
        if kind == 'to92':
            (xa, ya), (xb, yb), (xc, yc) = pts
            if ya == yc:
                s.add(f'<path d="M{min(xa, xc) - 10} {yb + 4} L{max(xa, xc) + 10} {yb + 4} '
                      f'A14 12 0 0 0 {min(xa, xc) - 10} {yb + 4} Z" fill="#27272a" '
                      f'opacity="0.9"/>')
            else:
                s.add(f'<path d="M{xb - 4} {min(ya, yc) - 10} L{xb - 4} {max(ya, yc) + 10} '
                      f'A12 14 0 0 1 {xb - 4} {min(ya, yc) - 10} Z" fill="#27272a" '
                      f'opacity="0.9"/>')
            for (px, py), t in zip(pts, pins or ['1', '2', '3']):
                s.add(f'<circle cx="{px}" cy="{py}" r="3" fill="#d4d4d8"/>')
                s.text(px + 7, py + 3.2, t, 8, 'start', '#fafafa', bold=True)
            placer.block(min(xa, xc) - 12, min(ya, yc) - 12, max(xa, xc) + 12,
                         max(ya, yc) + 12)
            labels.append((name, [(xb - 10, yb + 4, 'end'), (xb + 18, yb + 4, 'start'),
                                  (xb, min(ya, yc) - 15, 'middle'),
                                  (xb, max(ya, yc) + 22, 'middle')]))
            continue
        (x1, y1), (x2, y2) = pts
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        horiz = y1 == y2
        if kind.startswith('el'):
            r = SB.EL[kind]['d'] / 2 / PITCH * P
            s.add(f'<circle cx="{mx}" cy="{my}" r="{r:.1f}" fill="#2c3e8f" opacity="0.82"/>')
            for px, py in pts:
                s.add(f'<circle cx="{px}" cy="{py}" r="3" fill="#cbd5e1"/>')
            if 'bipolar' in val:
                s.text(mx, my + 3.5, 'BP', 8.5, 'middle', '#fff', True)
            else:
                s.text(x1 + (8 if not horiz else 0), y1 + (4 if not horiz else -6), '+', 12,
                       'start' if not horiz else 'middle', '#fff', True)
            placer.block(mx - r, my - r, mx + r, my + r)
            labels.append((name, [(mx + r + 4, my + 4, 'start'), (mx - r - 4, my + 4, 'end'),
                                  (mx, my - r - 4, 'middle'), (mx, my + r + 12, 'middle')]))
            continue
        s.line(x1, y1, x2, y2, '#8b8b8b', 2)
        if kind in ('r', 'film', 'd'):
            L = abs(x2 - x1) if horiz else abs(y2 - y1)
            bl, bw = max(L - 18, 14), 12 if kind == 'film' else 10
            col = {'r': '#d6bd8a', 'film': '#b33', 'd': '#222'}[kind]
            w_, h_ = (bl, bw) if horiz else (bw, bl)
            s.add(f'<rect x="{mx - w_ / 2}" y="{my - h_ / 2}" width="{w_}" height="{h_}" '
                  f'rx="4" fill="{col}"/>')
            placer.block(mx - w_ / 2, my - h_ / 2, mx + w_ / 2, my + h_ / 2)
            if kind == 'd':
                kx, ky = x2 + (x1 - x2) * 0.3, y2 + (y1 - y2) * 0.3
                if horiz:
                    s.line(kx, my - bw / 2, kx, my + bw / 2, '#ddd', 3)
                else:
                    s.line(mx - bw / 2, ky, mx + bw / 2, ky, '#ddd', 3)
        elif kind in ('rs', 'ds'):
            s.add(f'<circle cx="{x1}" cy="{y1}" r="7.5" '
                  f'fill="{"#d6bd8a" if kind == "rs" else "#222"}" stroke="#6b5a35" '
                  f'stroke-width="1"/>')
            placer.block(x1 - 8, y1 - 8, x1 + 8, y1 + 8)
            if kind == 'ds':
                # the band is at the top of a standing diode, over the cathode's bent lead
                ux, uy = (x2 - x1) / P, (y2 - y1) / P
                s.line(x1 + ux * 3 - uy * 7, y1 + uy * 3 + ux * 7,
                       x1 + ux * 3 + uy * 7, y1 + uy * 3 - ux * 7, '#ddd', 2.5)
        elif kind == 'cer':
            s.add(f'<ellipse cx="{mx}" cy="{my}" rx="{8 if horiz else 6}" '
                  f'ry="{6 if horiz else 8}" fill="#d68910"/>')
            placer.block(mx - 8, my - 8, mx + 8, my + 8)
        for i, (px, py) in enumerate(pts):
            s.add(f'<circle cx="{px}" cy="{py}" r="3" fill="#9ca3af"/>')
        if kind in ('d', 'ds'):
            kx, ky = pts[1]
            s.text(kx + (6 if horiz else 7), ky + (13 if horiz else 3.5), 'K', 8, 'start',
                   '#111', True)
        spots = ([(mx, my - 10, 'middle'), (mx, my + 18, 'middle')] if horiz else
                 [(mx + 12, my + 4, 'start'), (mx - 12, my + 4, 'end')])
        spots += [(mx + 12, my - 10, 'start'), (mx - 12, my - 10, 'end'),
                  (mx + 12, my + 18, 'start'), (mx - 12, my + 18, 'end'),
                  (mx, my - 23, 'middle'), (mx, my + 31, 'middle'),
                  (mx + 24, my + 4, 'start'), (mx - 24, my + 4, 'end')]
        labels.append((name, spots))


def _draw_headers(board, s, v, placer, labels, al):
    W = board.W
    edge_l, edge_r = v.ox - P / 2, v.ox - P / 2 + W * P
    for hd in board.headers:
        hs = hd.holes()
        occ, _ = hd.body()
        xs, ys = [h[0] for h in occ], [h[1] for h in occ]
        cable = MAP.cables.get(hd.cable) if hd.cable else None
        colour = KIND_COLOUR.get(cable['k'], '#333') if cable else '#374151'
        pad = 8 if hd.family == 'PIN' else 6
        xa, xb = v.X(min(xs)) - pad, v.X(max(xs)) + pad
        ya, yb = v.Y(min(ys)) - pad - (0 if hd.family in ('PIN', 'BOX') else 3), \
            v.Y(max(ys)) + pad + (0 if hd.family in ('PIN', 'BOX') else 3)
        fill = '#1f2937' if hd.family == 'PIN' else '#f8fafc'
        s.add(f'<rect x="{xa}" y="{ya}" width="{xb - xa}" height="{yb - ya}" rx="3" '
              f'fill="{fill}" stroke="{colour}" stroke-width="2"/>')
        placer.block(xa, ya, xb, yb)
        for i, h in enumerate(hs):
            px, py = v.pt(h)
            if i == 0:
                s.add(f'<rect x="{px - 5}" y="{py - 5}" width="10" height="10" fill="{colour}" '
                      f'stroke="#fff" stroke-width="1"/>')
            else:
                s.add(f'<rect x="{px - 3.5}" y="{py - 3.5}" width="7" height="7" '
                      f'fill="{"#e5e7eb" if hd.family == "PIN" else "#374151"}"/>')
        names = hd.pin_names()
        mid = sum(h[0] for h in hs) / len(hs)
        side = 'left' if mid <= 2.5 else 'right' if mid >= W - 3.5 else None
        if hd.family == 'BOX':
            show = hd.show if hd.show is not None else range(len(hs))
            for i in show:
                px, py = v.pt(hs[i])
                odd_col = i % 2 == 0
                left = odd_col != hd.even_left
                name = names[i] if i < len(names) and names[i] else ''
                t = f'{i + 1} {name}' if name else str(i + 1)
                x, anchor = (xa - 4, 'end') if left else (xb + 4, 'start')
                s.plate(x, py + 3.5, t, 8.5, anchor, colour, True)
                w = text_w(t, 8.5, True)
                placer.block(x - (w if anchor == 'end' else 0), py - 8,
                             x + (0 if anchor == 'end' else w), py + 4)
        else:
            widest = 0
            for i, h in enumerate(hs):
                px, py = v.pt(h)
                t = f'{i + 1} {names[i]}' if len(hs) > 1 else names[i]
                if side == 'left':
                    x, anchor = edge_l - 8, 'end'
                elif side == 'right':
                    x, anchor = edge_r + 8, 'start'
                else:
                    x, anchor = xb + 4, 'start'
                fill = colour if names[i] != '—' else '#9ca3af'
                if side:
                    s.text(x, py + 3.5, t, 9.5, anchor, fill, True)
                else:
                    s.plate(x, py + 3.5, t, 9, anchor, fill, True)
                w = text_w(t, 9.5, True)
                widest = max(widest, w)
                placer.block(x - (w if anchor == 'end' else 0), py - 8,
                             x + (0 if anchor == 'end' else w), py + 5)
        title = al(hd.name)
        if hd.cable:
            dest = hd.to or f'→ {MAP.title(MAP.other_end(hd.cable, board.node))}'
            sub = [dest, hd.describe()]
            if any(board.root_cable(n) == hd.cable for n in board.grounds
                   if n in hd.nets):
                sub.append('ground → towards the root')
            elif cable.get('g') is None:
                sub.append('carries no ground')
        else:
            sub = [hd.to] if hd.to else []
        if side and hd.family != 'BOX':
            gap = widest + 14
            x = edge_l - 8 - gap if side == 'left' else edge_r + 8 + gap
            anchor = 'end' if side == 'left' else 'start'
            y0 = v.Y(hs[0][1]) if not hd.up else v.Y(hs[-1][1])
            y0 = min(v.Y(h[1]) for h in hs)
            w = text_w(title, 12, True) + 10
            xr = x - w if side == 'left' else x
            s.add(f'<rect x="{xr}" y="{y0 - 9}" width="{w}" height="17" rx="4" fill="#fff" '
                  f'stroke="{colour}" stroke-width="1.6"/>')
            s.text(xr + w / 2, y0 + 3.5, title, 12, 'middle', colour, True)
            for k, t in enumerate(sub):
                s.text(x, y0 + 21 + 12.5 * k, t, 9.5, anchor,
                       GREEN if t.startswith('ground') else '#374151',
                       t.startswith('ground'))
        else:
            t = f'{title} {sub[0]}' if sub else title
            labels.insert(0, (t, [((xa + xb) / 2, ya - 6, 'middle'),
                                  ((xa + xb) / 2, yb + 13, 'middle'),
                                  (xb + 6, (ya + yb) / 2 + 4, 'start'),
                                  (xa - 6, (ya + yb) / 2 + 4, 'end')]))


def wrap(t, n):
    words, out, cur = t.split(' '), [], ''
    for w in words:
        if cur and len(cur) + 1 + len(w) > n:
            out.append(cur)
            cur = w
        else:
            cur = f'{cur} {w}' if cur else w
    if cur:
        out.append(cur)
    return out


def panel_lines(board):
    """The text beside the drawing: parts, connectors, ground, notes."""
    al = board.alias
    out = [('h', 'Parts')]
    for ref, (kind, val, _) in sorted(board.parts.items(), key=lambda kv: _ref_key(kv[0])):
        note = board.part_notes.get(ref, '')
        out.append(('row', f'{al.get(ref, ref)}  {val}{" — " + note if note else ""}'))
    out.append(('h', 'Connectors (pin 1 is the large filled square)'))
    for hd in board.headers:
        if hd.cable:
            c = MAP.cables[hd.cable]
            dest = hd.to or f'→ {MAP.title(MAP.other_end(hd.cable, board.node))}'
            pins = ' · '.join(f'{i + 1} {pin_name(t)}' for i, t in enumerate(c['pins']))
            out.append(('row', f'{al.get(hd.name, hd.name)}  {dest}, {hd.describe()}: {pins}'))
            if c.get('g') is None:
                out.append(('cont', 'No ground: ' + c['nog'] + '.'))
        else:
            names = hd.pin_names()
            pins = (' · '.join(f'{i + 1} {n}' for i, n in enumerate(names))
                    if len(names) > 1 else names[0])
            out.append(('row', f'{hd.name}  {hd.to + ": " if hd.to else ""}{pins}'))
    out.append(('h', 'Ground'))
    for net, gnode in board.grounds.items():
        up = board.root_cable(net)
        out.append(('text', f'{al.get(net, net)} reaches the root through '
                            f'{al.get(up, up)} only '
                            f'({MAP.title(MAP.other_end(up, board.node))}).'))
    if board.notes:
        out.append(('h', 'Notes'))
        for n in board.notes:
            out.append(('text', n))
    return out


def _ref_key(ref):
    m = re.match(r'([A-Z]+)(\d+)', ref)
    return (m.group(1), int(m.group(2))) if m else (ref, 0)

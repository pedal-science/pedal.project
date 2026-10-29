#!/usr/bin/env python3
"""The module boards as stripmaster documents.

`stripboard/module_boards.py` is where the boards are laid out and checked against the
netlist and the map.  This writes four of them -- the codec carrier, the input buffer, the
output board and the footswitches' Pico board -- as `.stripmaster` files beside their build sheets in `module-boards/`, so they
can be opened, turned over and edited in stripmaster (`../stripmaster`, the workspace's
stripboard designer).  The layout stays here: these files are derived, and a change made in
stripmaster is a change to carry back into `module_boards.py`.

What a board becomes:

  * its size, every cut (a hole, or a knife cut between two holes where `module_kit` puts one
    at x.5), and its standoff holes as stripmaster's mounting holes;
  * every part in its holes, pin 1 where the layout puts it, with its designator and value,
    and the pin names the build sheet prints;
  * every connector as the right housing (JST-XH, Molex KK, a pin header for a shunt, a pin
    for a test point), named for its cable, with the map's pin names;
  * every link as a sleeved jumper, which is what a link on the component side is: only its
    ends touch copper;
  * every pin and pad soldered.

The output board is built twice, L and R, from the same holes.  It is written once, as
`output.stripmaster`, with both boards' designators on each part ("C6/C7").

Then each file is read back by stripmaster's own model (`Tools/stripmaster-dump` in the
stripmaster repository) and checked against the layout: the same holes for every pin, nothing
dropped, and the same nets -- every hole `module_kit` puts on one net is on one stripmaster
net, and no two nets meet.  Without the stripmaster checkout it says so and skips that check.

    python3 stripboard/stripmaster_export.py [file.stripmaster ...]

Name files to write only those: a document edited in stripmaster and not yet carried back
is otherwise overwritten.
"""
import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import module_boards as MB

HERE = Path(__file__).resolve().parent
OUT = HERE / 'module-boards'
DUMP = HERE.parents[2] / 'stripmaster' / 'Tools' / 'stripmaster-dump'
FORMAT_VERSION = 3

# module_kit kind -> stripmaster catalogue part
KINDS = {
    'r': ('resistor', 'standard'),
    'rs': ('resistor', 'standard'),
    'film': ('capacitor', 'film'),
    'cer': ('capacitor', 'ceramicMLCC'),
    'el5.2': ('capacitor', 'electrolytic'),
    'el6.3': ('capacitor', 'electrolytic'),
    'd': ('diode', 'signal'),
    'ds': ('diode', 'signal'),
    'dip8': ('ic', 'opamp8'),
    'to92': ('power', 'regulator'),
}
TWO_LEAD = {'r', 'rs', 'film', 'cer', 'el5.2', 'el6.3', 'd', 'ds'}
TO92_PINS = {'O': 'OUT', 'G': 'GND', 'I': 'IN'}
# The catalogue's modules, by the layout's value: (member, holes between the rows, both rows
# numbered the same way down, the pins the module joins).  The WM8960 is two headers of 16
# with one ground plane under both.  The Pico is a DIP-40 seven holes wide; the catalogue
# joins its grounds but not AGND (pin 33), which a layout may still join on the board's copper,
# and the read-back's net check is what holds it to that.
MODULES = {
    'WM8960': (('module', 'wm8960'), 9, True, [[1, 10, 11, 15, 16, 17]]),
    'Pico 2 WH': (('module', 'pico'), 7, False, [[3, 8, 13, 18, 23, 28, 38]]),
}


# ---------------------------------------------------------------- stripmaster's geometry
def two_row_holes(anchor, axis, per_side, spacing, parallel, flipped):
    """stripmaster's pin-number order for a two-row part (PlacedComponent.pinHoles)."""
    x, y = anchor
    if axis == 'vertical':
        near = [(x, y + i) for i in range(per_side)]
        far = [(x + spacing, y + i) for i in range(per_side)]
    else:
        near = [(x + i, y) for i in range(per_side)]
        far = [(x + i, y + spacing) for i in range(per_side)]
    if parallel:
        holes = near + far
    elif axis == 'vertical':
        holes = near + far[::-1]
    else:
        holes = far + near[::-1]
    return half_turn(holes) if flipped else holes


def half_turn(holes):
    xs, ys = [h[0] for h in holes], [h[1] for h in holes]
    return [(min(xs) + max(xs) - x, min(ys) + max(ys) - y) for x, y in holes]


def row_placement(holes):
    """(anchor, axis, flipped) for pins in one straight row, pin 1 first."""
    xs, ys = {h[0] for h in holes}, {h[1] for h in holes}
    if len(holes) == 1:
        return holes[0], 'vertical', False
    if len(ys) == 1:
        axis = 'horizontal'
    elif len(xs) == 1:
        axis = 'vertical'
    else:
        raise SystemExit(f'pins {holes} are not in a row')
    anchor = min(holes, key=lambda h: (h[1], h[0]))
    step = (1, 0) if axis == 'horizontal' else (0, 1)
    straight = [(anchor[0] + step[0] * i, anchor[1] + step[1] * i) for i in range(len(holes))]
    if len(holes) > 2 and sorted(holes) != sorted(straight):
        raise SystemExit(f'pins {holes} are not in adjacent holes')
    return anchor, axis, list(holes) != sorted(holes, key=lambda h: (h[1], h[0]))


def two_row_placement(holes, spacing, parallel):
    xs, ys = [h[0] for h in holes], [h[1] for h in holes]
    anchor = (min(xs), min(ys))
    per_side = len(holes) // 2
    for axis in ('vertical', 'horizontal'):
        for flipped in (False, True):
            if two_row_holes(anchor, axis, per_side, spacing, parallel, flipped) == list(holes):
                return anchor, axis, flipped
    raise SystemExit(f'pins {holes} are not a {len(holes)}-pin footprint stripmaster knows')


# ---------------------------------------------------------------- one board
def point(h):
    return {'column': int(h[0]), 'row': int(h[1])}


def header_value(hd):
    """What is printed on a connector: the part to order, short enough to read on the board.
    A shunt header says how the shunt is set; its pin names say what it joins."""
    if hd.to and not hd.cable:
        return 'shunt fitted' if hd.to.startswith('shunt fitted') else hd.to.split(' ')[0]
    if hd.family == 'XH':
        return f'B{len(hd.nets)}B-XH-A'
    if hd.family == 'KK':
        return f'KK 254 {len(hd.nets)}-way'
    return None


class Writer:
    def __init__(self, board):
        self.board, self.key = board, board.key
        self.components, self.jumpers, self.expected = [], [], []

    def uid(self, *what):
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f'pedal.project/{self.key}/' + '/'.join(what))).upper()

    def add(self, what, ref, anchor, axis, flipped, holes, span=1, legs=None,
            designator=None, value=None, pin_names=None):
        component = {
            'id': self.uid('part', what),
            'reference': {'categoryID': ref[0], 'memberID': ref[1]},
            'anchor': point(anchor),
            'axis': axis,
            'span': span,
            'legCount': legs if legs is not None else len(holes),
            'flipped': flipped,
        }
        if designator:
            component['designator'] = designator
        if value:
            component['value'] = value
        if pin_names and any(pin_names):
            component['pinNames'] = list(pin_names)
        self.components.append(component)
        self.expected.append((f'{ref[0]}.{ref[1]}', designator, [list(h) for h in holes]))

    def part(self, ref, label=None, value=None):
        kind, value_, holes = self.board.parts_at[ref]
        holes = [tuple(h) for h in holes]
        designator = label or ref
        value = value or value_
        if kind in TWO_LEAD:
            anchor, axis, flipped = row_placement(holes)
            a, b = holes
            span = abs(a[0] - b[0]) + abs(a[1] - b[1]) + 1
            catalogue = KINDS[kind]
            if kind.startswith('el') and 'bipolar' in value:
                catalogue = ('capacitor', 'bipolar')
            if kind == 'd' and value.startswith('1N58'):
                catalogue = ('diode', 'schottky')
            self.add(ref, catalogue, anchor, axis, flipped, holes, span=span, legs=2,
                     designator=designator, value=value)
        elif kind == 'dip8':
            anchor, axis, flipped = two_row_placement(holes, 3, parallel=False)
            self.add(ref, KINDS[kind], anchor, axis, flipped, holes,
                     designator=designator, value=value)
        elif kind == 'to92':
            anchor, axis, flipped = row_placement(holes)
            names = [TO92_PINS.get(p, p) for p in self.board.pin_labels.get(ref, [])]
            self.add(ref, KINDS[kind], anchor, axis, flipped, holes,
                     designator=designator, value=value, pin_names=names)
        elif kind == 'module':
            if value_ not in MODULES:
                raise SystemExit(f'{self.key}: {ref} is a {value_}, which the catalogue lacks')
            catalogue, spacing, parallel, joins = MODULES[value_]
            mine = [set(group) for group in self.board.modules[ref].get('joined', [])]
            for group in joins:
                if not any(set(group) <= m for m in mine):
                    raise SystemExit(f'{ref}: the catalogue joins pins {group}, and the layout '
                                     f'does not')
            anchor, axis, flipped = two_row_placement(holes, spacing, parallel=parallel)
            self.add(ref, catalogue, anchor, axis, flipped, holes,
                     designator=designator, value=value)
        else:
            raise SystemExit(f'{self.key}: {ref} is a {kind}, which the export does not know')

    def header(self, hd, label=None, names=None):
        holes = [tuple(h) for h in hd.holes()]
        anchor, axis, flipped = row_placement(holes)
        names = names or hd.pin_names()
        if hd.family == 'PIN' and len(holes) == 1:
            ref = ('misc', 'testpoint')
        elif hd.family == 'XH' and hd.cable:
            ref = ('connector', 'jstXH')
        elif hd.family == 'KK':
            ref = ('connector', 'molexKK')
        elif hd.family in ('XH', 'PIN'):
            # A header for a shunt, not a cable: a plain 2.54 mm pin header.
            ref = ('connector', 'headerVariable')
        else:
            raise SystemExit(f'{self.key}: {hd.name} is a {hd.family} header')
        value = header_value(hd)
        self.add(f'header {hd.name}', ref, anchor, axis, flipped, holes, legs=len(holes),
                 designator=label or hd.name, value=value, pin_names=names)

    def link(self, index, a, b):
        route = [a]
        while route[-1] != b:
            x, y = route[-1]
            if x != b[0]:
                route.append((x + (1 if b[0] > x else -1), y))
            else:
                route.append((x, y + (1 if b[1] > y else -1)))
        self.jumpers.append({'id': self.uid('link', str(index)), 'kind': 'insulated',
                             'route': [point(h) for h in route]})

    def document(self, when):
        board = self.board
        cut_holes, cut_gaps = set(), set()
        for x, y in board.cuts:
            if (x, y) in board.mounts:
                continue
            if x == int(x):
                cut_holes.add((int(x), y))
            else:
                cut_gaps.add((int(x - 0.5), y))
        soldered = {h for _, (_, _, leads) in board.parts.items() for h, _ in leads}
        soldered |= {h for h, _, _ in board.pads.values()}
        order = lambda h: (h[1], h[0])
        return {
            'formatVersion': FORMAT_VERSION,
            'state': {
                'board': {
                    'columns': board.W,
                    'rows': board.H,
                    'cutHoles': [point(h) for h in sorted(cut_holes, key=order)],
                    'cutGaps': [point(h) for h in sorted(cut_gaps, key=order)],
                    'mountHoles': [point(h) for h in sorted(board.mounts, key=order)],
                    'solderedHoles': [point(h) for h in sorted(soldered, key=order)],
                    'jumpers': self.jumpers,
                    'components': self.components,
                },
                'history': {'entries': [], 'cursor': 0},
                'view': {'orientation': 0, 'side': 'top', 'panX': 0, 'panY': 0},
                'createdAt': when,
                'modifiedAt': when,
            },
        }


def write(board, label=None, header_label=None, header_names=None):
    """One board as a Writer, its parts and headers named by `label`/`header_label`."""
    w = Writer(board)
    for ref in board.parts_at:
        w.part(ref, label=(label or {}).get(ref))
    for hd in board.headers:
        w.header(hd, label=(header_label or {}).get(hd.name),
                 names=(header_names or {}).get(hd.name))
    for i, (a, b, _) in enumerate(board.links):
        w.link(i, tuple(a), tuple(b))
    return w


def output_pair():
    """Output L and R are one board built twice: the same holes, two sets of names."""
    left, right = MB.output_board('L'), MB.output_board('R')
    by_holes = {tuple(map(tuple, holes)): ref for ref, (_, _, holes) in right.parts_at.items()}
    label = {}
    for ref, (kind, value, holes) in left.parts_at.items():
        other = by_holes.get(tuple(map(tuple, holes)))
        if other is None or right.parts_at[other][:2] != (kind, value):
            raise SystemExit(f'output R has no part where L has {ref}')
        label[ref] = ref if other == ref else f'{ref}/{other}'
    header_label, header_names = {}, {}
    for hl, hr in zip(left.headers, right.headers):
        if hl.at != hr.at or len(hl.nets) != len(hr.nets):
            raise SystemExit(f'output L {hl.name} and R {hr.name} are not in the same holes')
        header_label[hl.name] = hl.name if hl.name == hr.name else f'{hl.name}/{hr.name}'
        header_names[hl.name] = [a if a == b else f'{a}/{b}'
                                 for a, b in zip(hl.pin_names(), hr.pin_names())]
    if sorted(left.cuts) != sorted(right.cuts) or \
            [link[:2] for link in left.links] != [link[:2] for link in right.links]:
        raise SystemExit('output L and R are cut or linked differently')
    return left, write(left, label, header_label, header_names)


# ---------------------------------------------------------------- the check
def expected_nets(board):
    """{net key: holes} for every soldered hole and link end the layout names, less the nets
    the layout leaves in pieces on purpose (joined off the board, like the toggle's node A)."""
    nl = board.check_netlist
    out = {}
    for h, net in board.tagged.items():
        key = nl.net_key(net)
        if net in board.off_board or key in board.off_board:
            continue
        out.setdefault(key, set()).add(tuple(h))
    return out


def joined_inside(board):
    """{net key: group}: nets a bought module joins on its own board, which may share a
    stripmaster net -- the carrier's DGND and AGND meet on the WM8960 and nowhere else."""
    nl, group = board.check_netlist, {}
    for a, b in board.joins():
        na, nb = (nl.net_key(board.tagged[tuple(h)]) for h in (a, b))
        merged = group.get(na, {na}) | group.get(nb, {nb})
        for n in merged:
            group[n] = merged
    return group


def verify(paths_and_writers):
    if not DUMP.exists():
        print(f'skip  the read-back check: no stripmaster checkout at {DUMP.parents[1]}')
        return 0
    paths = [str(p) for p, _ in paths_and_writers]
    run = subprocess.run([str(DUMP), *paths], capture_output=True, text=True)
    if run.returncode:
        print(run.stderr, end='')
        return 1
    failed = 0
    for dump, (path, w) in zip(json.loads(run.stdout), paths_and_writers):
        errs = []
        doc = w.document(0)['state']['board']
        if (dump['columns'], dump['rows']) != (w.board.W, w.board.H):
            errs.append(f'board is {dump["columns"]}x{dump["rows"]}')
        for field in ('cutHoles', 'cutGaps', 'mountHoles'):
            if len(dump[field]) != len(doc[field]):
                errs.append(f'{field}: wrote {len(doc[field])}, read {len(dump[field])}')
        if len(dump['jumpers']) != len(w.jumpers):
            errs.append(f'wrote {len(w.jumpers)} links, read {len(dump["jumpers"])}')
        if len(dump['parts']) != len(w.expected):
            errs.append(f'wrote {len(w.expected)} parts, read {len(dump["parts"])}')
        for got, (ref, designator, holes) in zip(dump['parts'], w.expected):
            if (got['reference'], got['designator'], got['pins']) != (ref, designator, holes):
                errs.append(f'{designator}: wrote {ref} at {holes}, read {got["reference"]} at '
                            f'{got["pins"]}')
        # The layout's nets are copper: strips, links and a module's own joins. stripmaster's
        # `nets` also run through resistors and diodes, so read its copper nets where it has
        # them; a stripmaster from before that change has only `nets`, and they are copper.
        nets = dump.get('copperNets', dump['nets'])
        net_of = {}
        for i, net in enumerate(nets):
            for h in net:
                net_of[tuple(h)] = i
        seen, together = {}, joined_inside(w.board)
        for name, holes in sorted(expected_nets(w.board).items()):
            found = {net_of.get(h, ('alone', h)) for h in holes}
            if len(found) > 1:
                errs.append(f'{name} is in {len(found)} pieces in stripmaster')
            for f in found:
                if f in seen and seen[f] != name and seen[f] not in together.get(name, ()):
                    errs.append(f'{name} and {seen[f]} are one net in stripmaster')
                seen[f] = name
        if errs:
            failed += 1
            print(f'FAIL  {path.name} read back')
            for e in errs:
                print(f'      {e}')
        else:
            print(f'ok    {path.name} read back: {len(dump["parts"])} parts, '
                  f'{len(dump["jumpers"])} links, {len(nets)} nets agree')
    return failed


def when():
    """The layout's last commit, so the files only change when the boards do."""
    try:
        stamp = subprocess.run(
            ['git', 'log', '-1', '--format=%at', '--', 'module_boards.py', 'module_kit.py',
             'nets.py', 'stripmaster_export.py'],
            cwd=HERE, capture_output=True, text=True, check=True).stdout.strip()
        moment = datetime.fromtimestamp(int(stamp), timezone.utc)
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
        moment = datetime.now(timezone.utc)
    # Swift's default Date encoding: seconds since 2001-01-01.
    return (moment - datetime(2001, 1, 1, tzinfo=timezone.utc)).total_seconds()


def main():
    OUT.mkdir(exist_ok=True)
    stamp = when()
    output, output_writer = output_pair()
    jobs = [
        ('codec-carrier.stripmaster', MB.carrier_board(), None),
        ('input-buffer.stripmaster', MB.input_board(), None),
        ('output.stripmaster', output, output_writer),
        ('footswitch-pico.stripmaster', MB.footswitch_board(), None),
    ]
    wanted = set(sys.argv[1:])
    unknown = wanted - {name for name, _, _ in jobs}
    if unknown:
        raise SystemExit(f'no such document: {", ".join(sorted(unknown))}')
    if wanted:
        jobs = [job for job in jobs if job[0] in wanted]
    written, failed = [], 0
    for name, board, w in jobs:
        errs = board.check()
        if errs:
            failed += 1
            print(f'FAIL  {board.key} does not pass its own check; not written')
            for e in errs:
                print(f'      {e}')
            continue
        w = w or write(board)
        path = OUT / name
        text = json.dumps(w.document(stamp), indent=2, sort_keys=True, ensure_ascii=False,
                          separators=(',', ' : '))
        path.write_text(text + '\n')
        written.append((path, w))
        print(f'wrote {path.relative_to(HERE.parent)}  {board.W}x{board.H}, '
              f'{len(w.components)} parts, {len(w.jumpers)} links')
    failed += verify(written)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())

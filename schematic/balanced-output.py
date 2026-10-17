#!/usr/bin/env python3
"""One balanced (XLR) output channel: the wiring table, checked against KiCad's netlist.

The schematic is `schematic/balanced-output/balanced-output.kicad_sch`. Unlike
`case-wiring.py`, this script does not write it: it was drawn through the Konnect MCP tools,
which keep KiCad's UUIDs and cross-references intact. This file is the table the drawing must
match. Export the netlist and check it:

    kicad-cli sch export netlist -o schematic/balanced-output/balanced-output.net \\
        schematic/balanced-output/balanced-output.kicad_sch
    python3 schematic/balanced-output.py

The design and its reasoning are docs/balanced-outputs.md (D15). References share the pedal's
one numbering with the stripboard layouts (stripboard/module_boards.py, the xlr boards).
"""
import re
import sys
from pathlib import Path

NETLIST = Path(__file__).resolve().parent / 'balanced-output' / 'balanced-output.net'

# net: the pins on it. Pin numbers are the KiCad symbols' (the relay's are EN 50005: 11/12/14
# and 21/22/24 are pole 1 and pole 2's COM/NC/NO, A1/A2 the coil; the stripboard maps them to
# the TQ2-5V's own pins).
WIRING = {
    'GND':    'J11.1 J11.3 R39.2 C19.2 C20.2 C21.2 U5.4 R36.2 R37.2 D9.2 D11.2',
    '+9V':    'J11.4 R40.1',
    'V9F':    'R40.2 C20.1 C21.1 U5.8 R38.1 D8.1 D10.1',
    'VREF':   'R38.2 R39.1 C19.1 R29.2 R31.2 U5.5 K2.12 K2.22',
    'HPL':    'J11.2 C16.1',
    'C_IN':   'C16.2 R28.1 J13.1 SW3.1',
    'TAP':    'R28.2 R29.1 J13.3 SW3.3',
    'PADCOM': 'SW3.2 J13.2 R30.1',
    'X':      'R30.2 R31.1 U5.3 K2.11 K2.21',
    'AOUT':   'U5.1 U5.2 R34.1 R32.1',
    'H':      'R34.2 C17.1 D8.2 D9.1',
    'HC':     'C17.2 R41.1',
    'HOT':    'R41.2 R36.1 J12.1 J15.2',
    'INVN':   'R32.2 U5.6 R33.1',
    'BOUT':   'U5.7 R33.2 R35.1',
    'CN':     'R35.2 C18.1 D10.2 D11.1',
    'CC':     'C18.2 R42.1',
    'COLD':   'R42.2 R37.1 J12.2 J15.3',
    'COIL+':  'J14.3 K2.A1 D7.1',
    'COIL-':  'J14.1 K2.A2 D7.2',
    'PIN1':   'J15.1 SW4.1 C22.1',
    'CASE':   'SW4.2 C22.2',
}
# Pins left open on purpose: the input cable's fifth way, the coil cable's middle way, and the
# relay's two normally-open contacts.
UNUSED = {'J11.5', 'J14.2', 'K2.14', 'K2.24'}


def netlist(path=NETLIST):
    """{net name: sorted pins} from a KiCad netlist, power flags left out."""
    s = path.read_text()
    s = s[s.index('(nets'):]
    out = {}
    for blk in re.split(r'\n\s*\(net\n', s)[1:]:
        name = re.search(r'\(name "([^"]+)"\)', blk).group(1).lstrip('/')
        pins = re.findall(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', blk)
        out[name] = sorted(f'{r}.{p}' for r, p in pins if not r.startswith('#'))
    return out


def check(path=NETLIST):
    got, errs = netlist(path), []
    for net, pins in WIRING.items():
        want = sorted(pins.split())
        if got.get(net) != want:
            errs.append(f'{net}: the schematic has {got.get(net)}, the table {want}')
    for net, pins in got.items():
        if net in WIRING:
            continue
        if net.startswith('unconnected-') and len(pins) == 1 and pins[0] in UNUSED:
            continue
        errs.append(f'{net} is not in the table: {pins}')
    unused = {p for n, ps in got.items() if n.startswith('unconnected-') for p in ps}
    for pin in sorted(UNUSED - unused):
        errs.append(f'{pin} should be left unconnected')
    return errs


if __name__ == '__main__':
    errs = check()
    for e in errs:
        print('FAIL', e)
    if errs:
        sys.exit(1)
    print(f'ok: {len(WIRING)} nets and {len(UNUSED)} unused pins match the schematic')

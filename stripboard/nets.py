#!/usr/bin/env python3
"""The analogue circuit's netlist, in one place.

The connections of a circuit do not change when it is moved onto a different piece of
stripboard, so they are written here once and every layout is checked against them:
`stripboard/board1.py`, `stripboard/board_a.py`, and the case schematic
(`schematic/case-wiring.py`, whose exported KiCad netlist is checked against the same list).

A net is a set of component pins.  Nothing here knows about holes, so a layout can be redone
without touching this file, and a net that is right in one layout cannot be wrong in another.

The circuit, so the nets can be read (values in `docs/bom.md`, the reasoning in
`docs/hardware-handoff.md` and `plan.md` Phase 2b):

    jack tip ──C5── IN_A ──R5── IN_B ──R6── BIAS
                     │                 │
                   SW.2               SW.1
                     └────── SW.3 ─────┘        SW is the panel's Inst/Line toggle, drawn
                              │                  here instead of as three pads
                            U1.3
    U1 is a follower: U1.1 = U1.2 = the buffer's output, which is the codec's LIN1
    BIAS is about 2.9 V from R2/R3/R4 off the filtered 9 V, with C4 across it
    codec HPL/HPR ──C6/C7── R7/R9 ── the output pads, with R8/R10 holding the jacks at 0 V

The 9 V side (D1, R1, C1, C2 and the regulators) is board A's power board; the input, the
buffer, the bias and the output stage are the analogue board.

Two rules this file is checked against, and that it checks itself:

  * every pin of a part is on exactly one net -- a part with a pin missing is one nobody will
    wire, and a pin on two nets is a short;
  * no two nets share a pin.

Run it directly to check those two and print the netlist:

    python3 stripboard/nets.py
"""
# Parts, so a pin can be checked against what the part actually has.
# p1 and p2 name the two leads of a part that has no pin numbers (an 'r' has p1 and p2, a
# diode's p1 is its anode); a 'sw' is the panel switch, whose pins are its two throws and
# its common.
PARTS = {
    'D1':  dict(kind='d',     value='1N5817',             pins=2),
    'R1':  dict(kind='r',     value='100Ω',               pins=2),
    'C1':  dict(kind='el6.3', value='100µF 25V',          pins=2),
    'C2':  dict(kind='el6.3', value='100µF 25V',          pins=2),
    'C3':  dict(kind='cer',   value='100nF',              pins=2),
    'R2':  dict(kind='r',     value='10k',                pins=2),
    'R3':  dict(kind='r',     value='10k',                pins=2),
    'R4':  dict(kind='r',     value='10k',                pins=2),
    'C4':  dict(kind='el5.2', value='10µF 50V',           pins=2),
    'U1':  dict(kind='dip8',  value='OPA2197 on adapter', pins=8),
    'R5':  dict(kind='r',     value='330k',               pins=2),
    'R6':  dict(kind='r',     value='680k',               pins=2),
    'C5':  dict(kind='film',  value='100nF film',         pins=2),
    'C6':  dict(kind='el6.3', value='10µF bipolar',       pins=2),
    'R7':  dict(kind='r',     value='100Ω',               pins=2),
    'R8':  dict(kind='r',     value='1M',                 pins=2),
    'C7':  dict(kind='el6.3', value='10µF bipolar',       pins=2),
    'R9':  dict(kind='r',     value='100Ω',               pins=2),
    'R10': dict(kind='r',     value='1M',                 pins=2),
}

# The nets.  A pin is 'REF.PIN'.
#
# The Inst/Line switch is three pads, not a part: the toggle bolts to the panel, so only its
# wires reach a board, and a board that carries them draws three pads.  Its common is IN_A --
# the buffer's input, where R5's top lead also lands -- and its two throws are the two ways
# the input can be padded: SW-I to IN_RAW (Inst: no padding, the follower sees the whole
# signal, about 1.0x) and SW-L to IN_B, past R5 (Line: R5/R6 divide it down, about 0.33x,
# -9.7 dB).  R5 is 330k and R6 is 680k: that ratio is what makes the Line pad -9.7 dB, and
# the two in series are the 1 MΩ the jack sees.
NETS = {
    # input, from the jack to the codec
    'IN_RAW':   {'C5.1'},                                   # the jack tip, screened cable
    'IN_A':     {'C5.2', 'R5.1', 'U1.3'},                   # the unity-gain tap, and the
                                                            #   buffer's input: 1 MΩ at the
                                                            #   jack even with the switch open
    'IN_B':     {'R5.2', 'R6.1'},                           # the 0.33 tap
    'LIN1':     {'U1.1', 'U1.2'},                           # the follower's output
    'BIAS':     {'R3.2', 'R4.1', 'C4.1', 'U1.5', 'R6.2'},   # about 2.9 V
    'BIAS_MID': {'R2.2', 'R3.1'},                           # the divider's middle
    'U1B':      {'U1.6', 'U1.7'},                           # the unused half, wired as a
                                                            # follower so nothing floats
    # outputs, from the codec's pads to the jacks
    'HPL':     {'C6.1'},
    'HPR':     {'C7.1'},
    'OUT_L_N': {'C6.2', 'R7.1'},
    'OUT_R_N': {'C7.2', 'R9.1'},
    'OUT_L':   {'R7.2', 'R8.1'},
    'OUT_R':   {'R9.2', 'R10.1'},
    # supply
    'V9_RAW': {'D1.1'},
    'V9':     {'D1.2', 'C1.1', 'R1.1'},
    'VF':     {'R1.2', 'C2.1', 'C3.1', 'R2.1', 'U1.8'},
    # ground.  Two nets, not one: board A carries GND_A (the input reference, the buffer and
    # its decoupling), the power board carries GND_P (the 9 V return and the bulk capacitors'
    # charging current).  They meet at the star tag and nowhere else, so the 100 Hz current in
    # C1/C2 does not flow through the copper the input reference sits on.
    #  They are one node electrically, and two nets here, because each board has its own
    #  copper: that is what EQUIV below says, and what the star tag makes true.
    'GND_A':  {'C3.2', 'C4.2', 'R4.2', 'U1.4', 'R8.2', 'R10.2'},
    'GND_P':  {'C1.2', 'C2.2'},
}

# The codec's analogue supply (its AVDD, 3.3 V from the 78L33) has no part of the analogue
# circuit on it: it is a wire from the power board's regulator to the codec's pad.  It is
# named here so the wiring table can use one name for it, and checked to be empty of pins.
RAILS = {'V3A3': "the 78L33's output, on its way to the codec's AVDD"}

# Nets that are one node in the pedal but separate pieces of copper on separate boards, tied
# at the star tag.  A layout may use either name for the same node: board 1, which is the
# whole circuit on one board with one ground bus, uses GND_A wherever the netlist says GND_P.
# This is what makes "one ground reference per board, each with its own wire to the star" a
# thing the data says rather than a thing the prose says.
EQUIV = [
    {'GND_A', 'GND_P'},
]


def same_net(a, b):
    """True when a layout net and a netlist net are the same node in the pedal."""
    if a == b:
        return True
    return any(a in group and b in group for group in EQUIV)


def net_key(net):
    """The name a net is known by in the netlist, following EQUIV."""
    for group in EQUIV:
        if net in group:
            return sorted(group)[0]
    return net

# Wires off the board, and between boards: label -> (net, what it is and where it goes).
# The same for every layout of the same circuit; which *hole* each one lands on is the
# layout's business.  A layout may use any of these, and must use the ones a net needs to
# reach the rest of the pedal.
PADS = {
    'IN':    ('IN_RAW', "the input jack's tip, through the screened cable's core"),
    'SW-I':  ('IN_RAW', 'the Inst/Line switch, Inst throw (the tip, across C5)'),
    'SW-L':  ('IN_B',   'the Inst/Line switch, Line throw (past R5: the 0.33 pad)'),
    'SW-C':  ('IN_A',   'the Inst/Line switch, common (the buffer input, U1.3)'),
    'LIN1':  ('LIN1',   "the codec board's LIN1 pad (the audio end of its right-hand row)"),
    'HPL':   ('HPL',    "the codec board's HPL pad"),
    'HPR':   ('HPR',    "the codec board's HPR pad"),
    'OUT-L': ('OUT_L',  'OUT L jack tip'),
    'OUT-R': ('OUT_R',  'OUT R jack tip'),
    'STAR':  ('GND_A',  'the star-ground tag'),
    'V9':    ('V9_RAW', "the DC socket's +9 V contact"),
    'VF':    ('VF',     "the power board's filtered 9 V"),
    'GND-P': ('GND_P',  "the power board's ground: the 9 V return and C1/C2"),
    'V3A3':  ('V3A3',   "the power board's 78L33 output, on its way to the codec's AVDD"),
}


def net_of():
    """{pin: net}, refusing a pin that is on two nets."""
    out = {}
    for net, pins in NETS.items():
        for pin in pins:
            if pin in out:
                raise SystemExit(f'{pin} is on both {out[pin]} and {net}')
            out[pin] = net
    return out


def check_parts():
    """Every pin a part has is on exactly one net; every net names a part that exists."""
    errs, by_pin = [], net_of()
    for pin, net in sorted(by_pin.items()):
        ref, _, num = pin.partition('.')
        if ref not in PARTS:
            errs.append(f'{net} names {pin}, but {ref} is not a part')
        elif not num.isdigit() or not 1 <= int(num) <= PARTS[ref]['pins']:
            errs.append(f'{net} names {pin}, but {ref} has {PARTS[ref]["pins"]} pins')
    for ref, part in PARTS.items():
        for n in range(1, part['pins'] + 1):
            if f'{ref}.{n}' not in by_pin:
                errs.append(f'{ref}.{n} is on no net')
    return errs


def value_of(ref):
    return PARTS[ref]['value']


def nets_using(ref):
    """{pin: net} for one part, in pin order."""
    by_pin = net_of()
    return {f'{ref}.{n}': by_pin[f'{ref}.{n}']
            for n in range(1, PARTS[ref]['pins'] + 1)}


def main():
    errs = check_parts()
    for e in errs:
        print('ERROR', e)
    if errs:
        return 1
    for net in sorted(NETS):
        print(f'  {net:9s} ' + '  '.join(sorted(NETS[net])))
    for rail, what in RAILS.items():
        print(f'  {rail:9s} (no board pins: {what})')
    print(f'ok: {len(PARTS)} parts, {len(NETS)} nets, {len(RAILS)} rail, '
          f'{sum(len(v) for v in NETS.values())} pin connections')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

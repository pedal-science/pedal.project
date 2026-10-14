#!/usr/bin/env python3
"""Stripboard sketches for the pedal's modules.

One small board per circuit, joined by the keyed cables in `docs/diagrams/modules.html`.
The reasoning is `docs/modules.md`; this file is the boards.  Each layout is data, checked
by `stripboard/module_kit.py` against the netlist and against the map, and drawn as one
build sheet: the component side, the copper side mirrored, and the parts and pinouts.

These are sketches to start from, kept readable rather than packed.  An XH header's 2.50 mm
pitch sits in the 2.54 mm holes; on a header this short the difference disappears into the
holes.  The standoff holes are drilled 2.5 mm, for M2.5 nylon standoffs.

    python3 stripboard/module_boards.py
"""
import sys
from pathlib import Path

import nets as NET
import module_kit as K

OUT = Path(__file__).resolve().parent / 'module-boards'


def link(a, b, net):
    return (a, b, net)


def dip(x, y, n):
    """Pin holes of an n-pin DIP, pin 1 at (x, y), as seen from the component side."""
    h = n // 2
    return [(x, y + i) for i in range(h)] + [(x + 3, y + h - 1 - i) for i in range(h)]


# ---------------------------------------------------------------- the output board
def output_board(side):
    """One channel of the output network.  L and R are the same board.

    The tip's network (C, R series, R bleed) keeps the codec's 1.65 V off the jack.  The ring's
    is the same three parts with ground where HPL is, so a TRS lead into a balanced input sees
    matched impedances on tip and ring: the jack is impedance-balanced on TRS and plain
    unbalanced on TS (docs/balanced-outputs.md, step 1)."""
    left = side == 'L'
    cap, series, bleed = ('C6', 'R7', 'R8') if left else ('C7', 'R9', 'R10')
    rcap, rseries, rbleed = ('C14', 'R24', 'R25') if left else ('C15', 'R26', 'R27')
    hot, mid, tip = (('HPL', 'OUT_L_N', 'OUT_L') if left else ('HPR', 'OUT_R_N', 'OUT_R'))
    ring, rmid = ('OUT_L_RING', 'OUT_L_RN') if left else ('OUT_R_RING', 'OUT_R_RN')
    near, far = ('A5', 'A7') if left else ('A6', 'A9')
    node = 'OUTL' if left else 'OUTR'
    title = 'Output L' if left else 'Output R — the same board as Output L'
    nl = K.Netlist(
        base=NET, keep_equiv=False,
        parts={rcap: ('el6.3', '10µF bipolar', 2), rseries: ('r', '100Ω', 2),
               rbleed: ('r', '1M', 2)},
        nets={ring: {f'{rcap}.1', f'{rbleed}.1'}, rmid: {f'{rcap}.2', f'{rseries}.1'},
              'GND_A': {f'{rseries}.2', f'{rbleed}.2'}})
    #            ref     kind      value              pin holes, in the netlist's pin order
    parts = {
        cap:     ('el6.3', NET.PARTS[cap]['value'],    [(6, 3), (6, 4)]),
        series:  ('r',     NET.PARTS[series]['value'], [(9, 4), (9, 8)]),
        bleed:   ('r',     NET.PARTS[bleed]['value'],  [(11, 8), (11, 2)]),
        rcap:    ('el6.3', '10µF bipolar',             [(4, 6), (4, 7)]),
        rseries: ('r',     '100Ω',                     [(10, 7), (10, 2)]),
        rbleed:  ('r',     '1M',                       [(8, 6), (8, 2)]),
    }
    headers = [
        K.Header((1, 2), ['GND_A', hot, None], cable=near),                 # from the carrier
        K.Header((16, 2), ['GND_A', tip, ring, None], cable=far),            # to the relay, or
    ]                                                                        # straight to the jack
    links = [link((12, 8), (12, 3), tip), link((14, 4), (14, 6), ring)]
    return K.Board(
        key=f'output-{side.lower()}', node=node, W=18, H=12, netlist=nl, parts=parts,
        headers=headers, links=links, mounts=[(4, 10), (15, 10)],
        carries={cap, series, bleed, rcap, rseries, rbleed}, grounds={'GND_A': node},
        alias={'GND_A': 'GND', ring: 'RING'},
        title=title,
        notes=[
            'Build it twice. The two boards are identical, so they swap: only the cable '
            'labels change.',
            'The capacitors are bipolar. Either way round.',
            'The bleed holds the jack at 0 V. The codec pin sits at about 1.65 V, so it '
            'must only ever meet the jack through the capacitor.',
            f'The ring has the tip\'s network with ground in place of {hot}: {rcap}, '
            f'{rseries} and {rbleed} match {cap}, {series} and {bleed}. A TRS lead into a '
            'balanced input is then impedance-balanced; a TS plug shorts the ring to the '
            'sleeve and the network does nothing. Pair the two capacitors on a meter: the '
            'closer they are, the more hum a balanced input rejects.',
            'Ground arrives from the carrier with the signal and leaves for the jack in '
            'the same cable as the tip and the ring. No separate sleeve wire.',
        ] if left else [
            'The same cuts, the same parts and the same holes as Output L.',
            'This channel does not pass through the relay. Its cable runs straight to '
            'the OUT R jack.',
        ])


# ---------------------------------------------------------------- the 9 V power board
def power_board():
    nl = K.Netlist(
        base=NET, keep_equiv=False,
        parts={'R11': ('r', '680k', 2), 'R12': ('r', '100k', 2)},
        nets={'BAT': {'R11.1'}, 'VBAT': {'R11.2'}, 'VDC': {'R12.2'},
              'V9_RAW': {'R12.1'}})
    parts = {
        'D1':  ('d', NET.PARTS['D1']['value'], [(6, 4), (10, 4)]),
        'C1':  ('el6.3', NET.PARTS['C1']['value'], [(13, 4), (13, 3)]),
        'R11': ('r', '680k', [(7, 10), (11, 10)]),
        'R12': ('r', '100k', [(5, 4), (5, 9)]),
    }
    headers = [
        K.Header((1, 3), ['GND_P', 'V9_RAW', 'BAT'], cable='P2',
                 names=['GND', '+9V sleeve', 'SW lug']),
        K.Header((1, 8), ['GND_P', None, 'BAT'], cable='P3',
                 names=['BAT −', '—', 'BAT +']),
        K.Header((16, 3), ['GND_P', 'V9'], cable='P1'),
        K.Header((16, 8), ['VBAT', 'VDC', None], cable='P4',
                 names=['VBAT', 'VDC', '—']),
    ]
    links = [
        link((4, 3), (4, 8), 'GND_P'),     # the battery's − to the barrel's centre
        link((3, 5), (3, 10), 'BAT'),      # the battery's + to the socket's switch lug
        link((13, 10), (13, 8), 'VBAT'),
    ]
    return K.Board(
        key='power-9v', node='PWR9', W=18, H=14, netlist=nl, parts=parts,
        headers=headers, links=links, mounts=[(6, 12), (14, 12)],
        cuts=[(2, 9)], carries={'D1', 'C1', 'R11', 'R12'}, grounds={'GND_P': 'PWR9'},
        alias={'GND_P': 'GND', 'V9_RAW': '9V in', 'BAT': 'BAT+'},
        title='9 V power',
        part_notes={
            'D1': 'band towards the right, the cathode',
            'C1': 'stripe (−) on row 3',
            'R11': 'the battery meter, top resistor',
            'R12': 'adapter present, top resistor',
        },
        notes=[
            'The sleeve is +9 V and the centre pin is 0 V: the Cioks outlet is '
            'centre-negative. Confirm the socket with a meter before trusting the lugs.',
            'With no plug in, the socket\'s switch joins the SW lug to the sleeve, so '
            'the battery feeds the diode. A plug opens the switch. The board does not '
            'join those two itself.',
            'One diode protects both sources. The battery plug is 3-way, so it cannot '
            'go into the 2-way output.',
            'No filter here. The 9 V leaves protected and unfiltered; the input board '
            'filters its own supply.',
            'The two sense wires carry no ground. Each has its resistor at this end, '
            'and the few microamps return through the tree. The bottom resistors and '
            'the capacitors are on the control board.',
        ])


# ---------------------------------------------------------------- MIDI in
def midi_board():
    """The H11L1M, beside the DIN socket. The drawing's pin 1 is the opto's pin 1."""
    nl = K.Netlist(
        keep_equiv=False,
        parts={
            'U2': ('dip6', 'H11L1M', 6),
            'R13': ('r', '220Ω', 2),
            'D2': ('ds', '1N4148', 2),
            'C8': ('cer', '100nF', 2),
            'R14': ('rs', '1k', 2),
        },
        nets={
            'DIN4': {'R13.1'},
            'ANODE': {'R13.2', 'U2.1', 'D2.2'},   # the diode's cathode, on the LED anode
            'KATH': {'U2.2', 'D2.1'},             # the diode's anode, on the LED cathode
            'NCU': {'U2.3'},
            'VO': {'U2.4', 'R14.2'},
            'GND': {'U2.5', 'C8.2'},
            'VCC': {'U2.6', 'C8.1', 'R14.1'},
        })
    parts = {
        'U2': ('dip6', 'H11L1M', dip(10, 4, 6)),
        'D2': ('ds', '1N4148', [(7, 5), (7, 4)]),
        'R13': ('r', '220Ω', [(9, 12), (9, 4)]),
        'C8': ('cer', '100nF', [(15, 4), (15, 5)]),
        'R14': ('rs', '1k', [(16, 4), (16, 6)]),
    }
    headers = [
        K.Header((1, 4), ['GND', 'VO', 'VCC'], cable='C2'),
        K.Header((1, 12), ['DIN4', 'KATH'], cable='C3', names=['DIN 4', 'DIN 5']),
    ]
    g, rx, v3 = 'GND', 'VO', 'VCC'
    links = [
        link((3, 4), (3, 1), g), link((3, 1), (14, 1), g), link((14, 1), (14, 5), g),
        link((4, 5), (4, 3), rx), link((4, 3), (14, 3), rx), link((14, 3), (14, 6), rx),
        link((5, 6), (5, 2), v3), link((5, 2), (17, 2), v3), link((17, 2), (17, 4), v3),
        link((8, 13), (8, 5), 'KATH'),
    ]
    return K.Board(
        key='midi-in', node='MIDI', W=20, H=18, netlist=nl, parts=parts,
        headers=headers, links=links, mounts=[(3, 16), (17, 16)],
        cuts=[(6, 4), (6, 5), (6, 6)], carries=set(parts), grounds={'GND': 'MIDI'},
        title='MIDI in',
        pin_labels={'U2': ['A', 'K', '', 'VO', 'GND', 'V+'],
                    'D2': ['a', 'k']},
        part_notes={
            'U2': 'pin 1 at the top left, the LED anode',
            'D2': 'across the LED, reversed: its band towards the anode',
            'R13': 'from DIN pin 4',
            'R14': 'pull-up to 3.3 V',
            'C8': 'across the opto’s supply',
        },
        notes=[
            'DIN pin 4 feeds the LED through 220 Ω. DIN pin 5 is the LED’s return. '
            'DIN pin 2, the shield, is not connected: the controller’s ground never '
            'reaches the pedal.',
            'The diode is fitted the wrong way for a signal diode, on purpose. It '
            'conducts only if a cable is wired backwards.',
            'Current in the loop pulls VO low, which is a UART zero. An idle loop '
            'leaves it high. The Pico sees it on a UART RX pin.',
            'Ground arrives from the control board on C2 and goes no further.',
        ])


# ---------------------------------------------------------------- the bypass relay
def relay_board():
    """TQ2-5V. Pin 1 is the top of the left column, the stripe end, seen from above.

    That is the component-side view. The datasheet draws the bottom view, which is this
    picture mirrored, so its pin 1 sits on the other side. The stripe marks the pin 1 end
    either way: pin 1 to pin 10 reads about 178 Ω, the coil.
    """
    nl = K.Netlist(
        keep_equiv=False,
        parts={
            'K1': ('relay', 'TQ2-5V', 10),
            'D2': ('d', '1N4148', 2),
            'R15': ('rs', '10M', 2),
        },
        nets={
            'COIL+': {'K1.1', 'D2.2'},
            'NC_LINK': {'K1.2', 'K1.9'},
            'NCA': {'K1.3'},
            'IN_TIP': {'K1.4'},
            'NO_A': {'K1.5', 'R15.1'},
            'NO_B': {'K1.6'},
            'OUT_TIP': {'K1.7'},
            'NCB': {'K1.8'},
            'COIL-': {'K1.10', 'D2.1'},
            'IN_GND': {'R15.2'},
            'OUT_RING': set(),
        },
        rails={'OUT_GND': 'the OUT L lane’s ground, passed straight through'})
    parts = {
        'K1': ('relay', 'TQ2-5V', dip(6, 4, 10)),
        'D2': ('d', '1N4148', [(4, 2), (8, 2)]),
        'R15': ('rs', '10M', [(4, 13), (4, 12)]),
    }
    headers = [
        K.Header((1, 6), ['IN_GND', 'IN_TIP'], cable='A1'),
        K.Header((1, 12), ['IN_GND', 'NO_A'], cable='A2'),
        K.Header((16, 11), ['OUT_GND', 'NO_B', 'OUT_RING', None], cable='A7'),
        K.Header((16, 6), ['OUT_GND', 'OUT_TIP', 'OUT_RING', None], cable='A8'),
        K.Header((1, 2), ['COIL-', None, 'COIL+'], cable='C1',
                 names=['COIL −', '—', '+5 V']),
    ]
    links = [
        link((11, 2), (11, 3), 'COIL+'), link((11, 3), (5, 3), 'COIL+'),
        link((5, 3), (5, 4), 'COIL+'),
        link((3, 2), (3, 1), 'COIL-'), link((3, 1), (10, 1), 'COIL-'),
        link((10, 1), (10, 4), 'COIL-'),
        link((3, 6), (3, 12), 'IN_GND'),
        link((5, 13), (5, 8), 'NO_A'),
        link((13, 6), (13, 11), 'OUT_GND'),
        link((12, 12), (12, 8), 'NO_B'),
        link((14, 8), (14, 13), 'OUT_RING'),
    ]
    return K.Board(
        key='bypass-relay', node='RELAY', W=18, H=18, netlist=nl, parts=parts,
        headers=headers, links=links, mounts=[(8, 16), (14, 16)],
        carries=set(parts), grounds={'IN_GND': 'RELAY:IN', 'OUT_GND': 'RELAY:OUT'},
        title='Bypass relay',
        alias={'IN_GND': 'IN gnd', 'OUT_GND': 'OUT gnd', 'IN_TIP': 'IN tip',
               'OUT_TIP': 'OUT tip', 'NO_A': 'to input', 'NO_B': 'from out L',
               'OUT_RING': 'OUT ring',
               'NC_LINK': 'bypass', 'COIL+': '+5 V', 'COIL-': 'coil −'},
        pin_labels={'K1': ['+', 'NC', '', 'IN', '→buf', '←out', 'OUT', '', 'NC', '−']},
        part_notes={
            'K1': 'stripe to the top. Pins 1 and 10 are the coil, about 178 Ω',
            'D2': 'across the coil, band towards +5 V',
            'R15': 'holds the buffer side at 0 V while the relay is in bypass',
        },
        notes=[
            'De-energised is bypass. The two NC contacts sit on one strip, so with the '
            'coil off the IN jack’s tip reaches the OUT L jack’s tip and the buffer is '
            'out of circuit. Energised, the jack goes to the input board and OUT L comes '
            'back from the output board.',
            'Confirm the contacts with a meter before the audio is wired: pin 4 to pin 2, '
            'and pin 7 to pin 9, should beep with the coil unpowered, and open when 5 V '
            'is across the coil.',
            'The IN lane’s ground and the OUT L lane’s ground both pass straight through, '
            'and they are not joined. OUT L’s ring passes straight through too: the relay '
            'switches only the tips. Neither touches the coil. The coil cable brings no '
            'ground of its own: the transistor that switches it is on the control board.',
            'Unplug this board and the jack cables fit the input and output boards '
            'directly. The pinouts are the same.',
        ])


# ---------------------------------------------------------------- the input buffer
def input_board():
    """The guitar buffer. The op-amp and its supply sit as they do on board 1; the
    input chain is one row lower, which leaves a corridor for the connector wires.
    IN_A is in two pieces, and the toggle joins them."""
    nl = K.Netlist(base=NET, keep_equiv=False)
    nl.NETS['GND_P'].discard('C2.2')
    nl.NETS['GND_A'].add('C2.2')
    parts = {
        'C5': ('film', '100nF film', [(5, 12), (7, 12)]),
        'R5': ('r', '680k', [(9, 12), (13, 12)]),
        'R6': ('r', '330k', [(15, 12), (19, 12)]),
        'U1': ('dip8', 'OPA2197', [(19, 1), (19, 2), (19, 3), (19, 4),
                                   (22, 4), (22, 3), (22, 2), (22, 1)]),
        'C3': ('cer', '100nF', [(23, 1), (23, 0)]),
        'C2': ('el6.3', '100µF 25V', [(25, 1), (25, 0)]),
        'R1': ('r', '100Ω', [(33, 1), (29, 1)]),
        'R2': ('r', '10k', [(28, 3), (32, 3)]),
        'R3': ('r', '10k', [(34, 3), (38, 3)]),
        'R4': ('r', '10k', [(40, 3), (44, 3)]),
        'C4': ('el5.2', '10µF 50V', [(30, 4), (30, 5)]),
    }
    headers = [
        K.Header((1, 5), ['GND_A', 'IN_RAW'], cable='A2'),
        K.Header((1, 8), ['IN_A', 'IN_A', 'IN_B'], cable='A3',
                 names=['SW-I', 'SW-C', 'SW-L']),
        K.Header((48, 6), ['GND_A', 'LIN1', 'GND_A', 'V9'], cable='A4'),
    ]
    g = 'GND_A'
    links = [
        link((18, 1), (18, 2), 'LIN1'),
        link((23, 2), (23, 3), 'U1B'),
        link((27, 1), (27, 3), 'VF'),
        link((39, 3), (39, 4), 'BIAS'),
        link((45, 3), (45, 5), g),
        link((16, 4), (16, 5), g),
        link((39, 0), (39, 5), g),
        link((3, 6), (4, 6), 'IN_RAW'), link((4, 6), (4, 12), 'IN_RAW'),
        link((3, 8), (8, 8), 'IN_A'), link((8, 8), (8, 12), 'IN_A'),
        link((3, 10), (3, 13), 'IN_B'), link((3, 13), (14, 13), 'IN_B'),
        link((14, 13), (14, 12), 'IN_B'),
        link((3, 9), (3, 7), 'IN_A'), link((3, 7), (17, 7), 'IN_A'),
        link((17, 7), (17, 3), 'IN_A'),
        link((15, 1), (15, 11), 'LIN1'), link((15, 11), (44, 11), 'LIN1'),
        link((44, 11), (44, 7), 'LIN1'),
        link((24, 12), (24, 4), 'BIAS'),
        link((39, 1), (39, 13), 'V9'), link((39, 13), (46, 13), 'V9'),
        link((46, 13), (46, 9), 'V9'),
        link((46, 6), (46, 5), g),
        link((44, 8), (44, 5), g),
    ]
    return K.Board(
        key='input-buffer', node='INPUT', W=50, H=14, netlist=nl, parts=parts,
        headers=headers, links=links, mounts=[(26, 8), (34, 8)],
        cuts=[(3.5, 8), (3.5, 9), (3.5, 10), (3.5, 12), (10, 6), (20, 8),
              (30, 7), (45, 6), (45.5, 3)],
        carries=set(parts), grounds={'GND_A': 'INPUT'}, off_board={'IN_A'},
        trim={'IN_A', 'IN_B', 'IN_RAW'},
        alias={'GND_A': 'GND', 'IN_RAW': 'IN', 'IN_A': 'node A', 'IN_B': 'node B',
               'V9': '+9 V', 'BIAS_MID': 'bias mid'},
        title='Input buffer',
        part_notes={
            'U1': 'pin 1 at the top left. The spare half is a follower on the bias',
            'C5': 'film, not ceramic',
            'C4': '+ on row 4, stripe on row 5',
            'C2': '+ on row 1, stripe on row 0',
            'R1': 'with C2, the supply filter — it lives here, not on the 9 V board',
            'R5': '680 kΩ, the top of the Line pad',
            'R6': '330 kΩ, the shunt to the bias',
        },
        notes=[
            'The op-amp and its supply sit where they do on board 1. The connectors '
            'are new, and so is the filter: R1 and C2 have moved here from the 9 V board.',
            'Mount it directly behind the IN jack and the toggle. The toggle’s three '
            'wires are the 1 MΩ node, and in the first test they were 14 dB of the '
            'hum, so keep them as short as the panel allows.',
            'SW-I and SW-C are the same node and are not joined on the board. The '
            'toggle joins them. At Line, pin 3 to the bias reads 330 kΩ; at Inst, '
            '1.01 MΩ.',
            'Ground arrives on A4, with the signal and the supply, and that is this '
            'board’s only ground.',
        ])


def carrier_board():
    """The codec carrier. D2 is a single-row KK header, so it fits the strips: each of
    its pins on its own row, the grounds linked, and a wire for every signal whose row
    is not already the codec's. Analogue ground and digital ground meet only in the
    codec module."""
    j4 = ['DGND', 'BCLK', 'LRCLK', 'DACDAT', 'ALRC', 'ADCDAT', 'SCL', 'SDA', 'V3',
          'DGND', 'DGND', 'SPKVDD', 'VIN', 'EN', 'DGND', 'DGND']
    j5 = ['AGND', 'RIN3', 'RIN2', 'RIN1', 'LIN1', 'LIN2', 'LIN3', 'MICB', 'HPL',
          'OUT3', 'HPR', 'AVDD', 'SLP', 'SLN', 'SRP', 'SRN']
    nets = {}
    for i, name in enumerate(j4 + j5):
        nets.setdefault(name, set()).add(f'M1.{i + 1}')
    for name, pins in {
        'V5A': {'U3.1', 'C10.1'}, 'V33': {'U4.1', 'C11.1'},
        'V9': {'U3.3', 'U4.3'}, 'AGND': {'U3.2', 'U4.2', 'C10.2', 'C11.2'},
    }.items():
        nets.setdefault(name, set()).update(pins)
    nets.setdefault('V5', set())
    nl = K.Netlist(keep_equiv=False, parts={
        'M1': ('module', 'SparkFun WM8960', 32),
        'U3': ('to92', '78L05', 3), 'U4': ('to92', '78L33', 3),
        'C10': ('el5.2', '10µF 50V', 2), 'C11': ('el5.2', '10µF 50V', 2),
    }, nets=nets, rails={'CASE': 'the case bond, open unless the jumper is fitted'})
    Y, X = 8, 14
    holes = [(X, Y + i) for i in range(16)] + [(X + 9, Y + i) for i in range(16)]
    parts = {
        'M1': ('module', 'WM8960', holes),
        # down the column, so the three legs are on three strips: OUT, GND, IN
        'U3': ('to92', '78L05', [(3, 28), (3, 29), (3, 30)]),
        'C10': ('el5.2', '10µF', [(7, 28), (7, 29)]),
        'U4': ('to92', '78L33', [(8, 31), (8, 32), (8, 33)]),
        'C11': ('el5.2', '10µF', [(10, 31), (10, 32)]),
    }
    d2y = Y
    headers = [
        K.Header((2, d2y), ['DGND', 'BCLK', 'DGND', 'LRCLK', 'DGND', 'ADCDAT', 'DGND',
                            'DACDAT', 'DGND', 'SDA', 'SCL', 'DGND', 'V3', 'VIN'],
                 cable='D2', family='KK'),
        K.Header((26, 11), ['AGND', 'LIN1', 'AGND', 'V9'], cable='A4'),
        K.Header((26, 16), ['AGND', 'HPL', None], cable='A5'),
        K.Header((26, 20), ['AGND', 'HPR', None], cable='A6'),
        K.Header((26, 26), ['AGND', 'RIN1', 'AGND', 'V9'], cable='A10'),
        K.Header((26, 4), ['AGND', 'V9'], cable='P1'),
        K.Header((14, 26), ['VIN', 'VIN', 'V5A'], name='VIN',
                 names=['Pi 5 V', 'VIN', '78L05'], to='shunt fitted: Pi 5 V to VIN'),
        K.Header((18, 26), ['V33', 'AVDD'], name='AVDD',
                 names=['78L33', 'AVDD'], to='open until the AVDD-ISO cut'),
        K.Header((22, 26), ['AGND', 'CASE'], name='CASE',
                 names=['GND', 'case'], to='open unless the case is bonded'),
        K.Header((30, 12), ['LIN1'], name='TP LIN1', family='PIN', names=['LIN1']),
        K.Header((30, 17), ['HPL'], name='TP HPL', family='PIN', names=['HPL']),
        K.Header((30, 21), ['HPR'], name='TP HPR', family='PIN', names=['HPR']),
        K.Header((30, 8), ['AGND'], name='TP GND', family='PIN', names=['GND']),
    ]
    links, cuts = [], []
    # D2 rows whose net is not already the codec's get a cut, then a wire over the top.
    same = {0, 1, 5}
    for i in range(14):
        if i not in same:
            cuts.append((9.5, d2y + i))
    # digital ground: D2's own rows on column 4, the codec's rows on column 12
    d2_gnd = [d2y + i for i in (0, 2, 4, 6, 8, 11)]
    for a, b in zip(d2_gnd, d2_gnd[1:]):
        links.append(link((4, a), (4, b), 'DGND'))
    codec_gnd = [Y + i for i in (0, 9, 10, 14, 15)]
    for a, b in zip(codec_gnd, codec_gnd[1:]):
        links.append(link((12, a), (12, b), 'DGND'))
    # each mismatched signal: up its own column, across a free row, down to the codec
    bring = [
        ('LRCLK', d2y + 3, Y + 2, 5, 10, 1),
        ('DACDAT', d2y + 7, Y + 3, 6, 11, 2),
        ('SDA', d2y + 9, Y + 7, 7, 15, 3),
        ('SCL', d2y + 10, Y + 6, 8, 16, 4),
        ('V3', d2y + 12, Y + 8, 9, 17, 5),
    ]
    for net, yd, yc, cd, cc, row in bring:
        links += [link((cd, yd), (cd, row), net), link((cd, row), (cc, row), net),
                  link((cc, row), (cc, yc), net)]
    # D2's 5 V is VIN while the shunt is fitted.
    links += [
        link((5, d2y + 13), (5, 27), 'VIN'), link((5, 27), (12, 27), 'VIN'),
        link((12, 26), (12, 27), 'VIN'),
        link((11, 20), (11, 27), 'VIN'),
        link((16, 19), (16, 27), 'AVDD'),
        link((16, 31), (16, 26), 'V33'),
        link((4, 30), (4, 35), 'V9'), link((4, 35), (31, 35), 'V9'),
        link((31, 35), (31, 29), 'V9'), link((31, 29), (31, 14), 'V9'),
        link((31, 14), (31, 5), 'V9'),
        link((9, 33), (9, 35), 'V9'),
        link((29, 4), (29, 8), 'AGND'),
        link((29, 8), (29, 11), 'AGND'), link((29, 11), (29, 13), 'AGND'),
        link((29, 13), (29, 16), 'AGND'), link((29, 16), (29, 19), 'AGND'),
        link((29, 19), (29, 20), 'AGND'), link((29, 20), (29, 26), 'AGND'),
        link((29, 26), (29, 28), 'AGND'),
        link((2, 29), (2, 34), 'AGND'), link((2, 34), (29, 34), 'AGND'),
        link((29, 34), (29, 28), 'AGND'), link((7, 32), (7, 34), 'AGND'),
        link((24, 16), (24, 7), 'HPL'), link((24, 7), (28, 7), 'HPL'),
        link((28, 7), (28, 17), 'HPL'),
        link((24, 18), (24, 24), 'HPR'), link((24, 24), (28, 24), 'HPR'),
        link((28, 24), (28, 21), 'HPR'),
        link((24, 11), (24, 33), 'RIN1'), link((24, 33), (28, 33), 'RIN1'),
        link((28, 33), (28, 27), 'RIN1'),
    ]
    for y in (11, 13, 16, 18, 19):
        cuts.append((24.5, y))
    cuts.append((15.5, 27))
    return K.Board(
        key='codec-carrier', node='CODEC', W=32, H=36, netlist=nl, parts=parts,
        headers=headers, links=links, mounts=[(1, 24), (7, 24)], cuts=cuts,
        carries=set(parts), grounds={'DGND': 'CODEC', 'AGND': 'CODEC'},
        modules={'M1': dict(outline=(13, 7, 24, 24), names=j4 + j5,
                            joined=[[1, 10, 11, 15, 16, 17]],
                            label='SparkFun WM8960\nin its socket strips')},
        alias={'DGND': 'DGND', 'AGND': 'AGND', 'V3': '3V3', 'V5': '5 V', 'V9': '+9 V',
               'V5A': '78L05', 'V33': '78L33', 'VIN': 'VIN'},
        title='Codec carrier',
        pin_labels={'U3': ['O', 'G', 'I'], 'U4': ['O', 'G', 'I']},
        part_notes={
            'M1': 'GND at the top of each row, as on the SparkFun board',
            'U3': 'legs down the column: OUT, GND, IN. Flat face to the left',
            'U4': 'the same way round',
            'C10': '+ on the 78L05 output',
            'C11': '+ on the 78L33 output',
        },
        notes=[
            'D2 is a single-row Molex KK header, which is what the strips can hold. '
            'Its grounds go to the codec’s digital pins and nowhere on the analogue bus.',
            'The VIN shunt is drawn linking the Pi’s 5 V to VIN, which is how the board '
            'is brought up. Move it onto the 78L05 for 2c’s first leg. Leave the AVDD '
            'shunt open until the AVDD-ISO cut is made.',
            'The case bond is open. It is the only place the case may touch, and only '
            'while nothing else does.',
            'OUT3 is not connected. Never ground it.',
        ])


def breakout_board():
    """The Pi's 40-pin header, taken once, and a keyed cable for each board.

    Odd pins of the box header run down column 6 and even pins down column 7, with
    the track cut between them on every row. Each signal then has its own wire to
    its own connector."""
    nets = [None] * 40
    for pin in K.PI_GND_PINS:
        nets[pin - 1] = 'GND'
    for pin, name in {1: 'V3', 2: 'V5', 3: 'SDA', 4: 'V5', 5: 'SCL', 8: 'TX',
                      10: 'RX', 12: 'BCLK', 35: 'LRCLK', 38: 'ADCDAT',
                      40: 'DACDAT'}.items():
        nets[pin - 1] = name
    nl = K.Netlist(keep_equiv=False, rails={
        'GND': 'the Pi header ground', 'V3': '3.3 V', 'V5': '5 V',
        'SDA': 'I2C data', 'SCL': 'I2C clock', 'TX': 'Pi TX, pin 8',
        'RX': 'Pi RX, pin 10', 'BCLK': 'bit clock', 'LRCLK': 'frame clock',
        'ADCDAT': 'codec to Pi', 'DACDAT': 'Pi to codec'})
    Y = 4
    headers = [
        K.Header((6, Y), nets, cable='D1', family='BOX',
                 names=[n or '' for n in nets],
                 show=[0, 1, 2, 3, 4, 7, 9, 11, 34, 37, 39]),
        K.Header((22, 4), ['GND', 'BCLK', 'GND', 'LRCLK', 'GND', 'ADCDAT', 'GND',
                           'DACDAT', 'GND', 'SDA', 'SCL', 'GND', 'V3', 'V5'],
                 cable='D2', family='KK'),
        K.Header((22, 22), ['GND', 'RX', 'TX', 'V5'], cable='D3'),
    ]
    # pin p (1-based) sits at row Y + (p-1)//2; odd pins in column 6, even in 7.
    def row(pin):
        return Y + (pin - 1) // 2

    def src(pin):
        return (4, row(pin)) if pin % 2 else (9, row(pin))

    links = []
    # ground: the odd pins down column 2, the even pins down column 12, joined underneath
    odd = [p for p in K.PI_GND_PINS if p % 2]
    even = [p for p in K.PI_GND_PINS if p % 2 == 0]
    for a, b in zip(odd, odd[1:]):
        links.append(link((2, row(a)), (2, row(b)), 'GND'))
    for a, b in zip(even, even[1:]):
        links.append(link((12, row(a)), (12, row(b)), 'GND'))
    links += [link((2, row(odd[-1])), (2, 36), 'GND'),
              link((2, 36), (12, 36), 'GND'),
              link((12, 36), (12, row(even[-1])), 'GND')]
    d2_gnd = [4, 6, 8, 10, 12, 15, 22]
    for a, b in zip(d2_gnd, d2_gnd[1:]):
        links.append(link((24, a), (24, b), 'GND'))
    links.append(link((24, 22), (24, 36), 'GND'))
    links.append(link((24, 36), (12, 36), 'GND'))
    links.append(link((19, 17), (19, 25), 'V5'))
    # one corridor row each, so the wires never share a hole
    routes = [('V3', 1, 16, 30), ('V5', 2, 17, 31), ('SDA', 3, 13, 32),
              ('SCL', 5, 14, 33), ('TX', 8, 24, 34), ('RX', 10, 23, 35),
              ('BCLK', 12, 5, 37), ('LRCLK', 35, 7, 38), ('ADCDAT', 38, 9, 39),
              ('DACDAT', 40, 11, 40)]
    for net, pin, dest_row, corridor in routes:
        a = src(pin)
        links += [link(a, (a[0], corridor), net),
                  link((a[0], corridor), (20, corridor), net),
                  link((20, corridor), (20, dest_row), net)]
    # pin 4's 5 V is the same rail; a short wire joins it to pin 2's row
    links.append(link((9, row(4)), (9, row(2)), 'V5'))
    return K.Board(
        key='core-breakout', node='HUB', W=26, H=42, netlist=nl, parts={},
        headers=headers, links=links,         mounts=[(16, 20), (16, 26)], grounds={'GND': 'HUB'}, absent={'D6'},
        alias={'GND': 'GND', 'V3': '3V3', 'V5': '5 V'},
        title='Core breakout',
        notes=[
            'One 40-way box header, cut between its two rows on every strip — a knife '
            'cut, because the pins are 2.54 mm apart and a spot cutter will not fit. '
            'The ribbon plugs in once; everything else unplugs here.',
            'D2 is the 14-way KK header the codec carrier takes. Its grounds are six '
            'of the Pi’s own ground pins, one beside each clock and data wire.',
            'LINK’s 5 V is pin 4, so the codec’s VIN keeps pin 2. They are the same '
            'rail on the Pi; the separate pins are only so the two leads do not share '
            'a socket.',
            'The test points are the header pins themselves: BCLK is pin 12, LRCLK pin '
            '35, ADCDAT pin 38, DACDAT pin 40, SDA pin 3 and SCL pin 5. A Qwiic port, '
            'if it is wanted, taps those same I2C pins; it is not drawn.',
        ])


def control_board():
    """The Pico and everything it drives.

    GP0 and GP1 are the link the firmware already uses. Every other GPIO label is a
    proposal: the firmware has not claimed those pins, and the drawing says so.
    """
    gnd_pins = [3, 8, 13, 18, 23, 28, 33, 38]
    nets = {
        'GND': {f'M2.{n}' for n in gnd_pins} | {'Q1.1', 'R21.2', 'R22.2', 'R23.2',
                                                'C12.2', 'C13.2'},
        'V5': {'D4.1'}, 'VSYS': {'D4.2', 'M2.39'},
        'TX': {'M2.1'}, 'RX': {'M2.2'},
        'BASE': {'Q1.2', 'R20.2', 'R21.1'},
        'COILN': {'Q1.3'}, 'RELAY': {'M2.6', 'R20.1'},
        'MIDI': {'M2.7'}, 'V3': {'M2.36'},
        'VB': {'M2.32', 'R22.1', 'C12.1'},
        'VDC': {'M2.34', 'R23.1', 'C13.1'},
    }
    for i, pin in enumerate((9, 10, 11, 12)):
        nets[f'L{i + 1}'] = {f'M2.{pin}', f'R{16 + i}.1'}
        nets[f'LEDO{i + 1}'] = {f'R{16 + i}.2'}
    for name, pin in (('FS1', 14), ('FS2', 15), ('FS3', 16),
                      ('EA', 21), ('EB', 22), ('EP', 24), ('BACK', 25)):
        nets[name] = {f'M2.{pin}'}
    used = {pin for pins in nets.values() for pin in pins}
    for pin in range(1, 41):
        if f'M2.{pin}' not in used:
            nets[f'P{pin}'] = {f'M2.{pin}'}
    nl = K.Netlist(keep_equiv=False, parts={
        'M2': ('module', 'Pico 2 WH', 40),
        'D4': ('d', '1N5817', 2),
        'Q1': ('to92', 'BC337', 3),
        'R16': ('r', '1k', 2), 'R17': ('r', '1k', 2),
        'R18': ('r', '1k', 2), 'R19': ('r', '1k', 2),
        'R20': ('r', '1k', 2), 'R21': ('rs', '100k', 2),
        'R22': ('r', '330k', 2), 'R23': ('r', '100k', 2),
        'C12': ('cer', '100nF', 2), 'C13': ('cer', '100nF', 2),
    }, nets=nets)
    PY, PX = 8, 16
    left = [(PX, PY + i) for i in range(20)]
    right = [(PX + 7, PY + 19 - i) for i in range(20)]
    parts = {
        'M2': ('module', 'Pico 2 WH', left + right),
        'D4': ('d', '1N5817', [(8, 4), (12, 4)]),
        'Q1': ('to92', 'BC337', [(6, 12), (6, 13), (6, 14)]),
        'R21': ('rs', '100k', [(4, 13), (4, 12)]),
        'R20': ('r', '1k', [(15, 13), (11, 13)]),
        'R16': ('r', '1k', [(15, 16), (11, 16)]),
        'R17': ('r', '1k', [(15, 17), (11, 17)]),
        'R18': ('r', '1k', [(15, 18), (11, 18)]),
        'R19': ('r', '1k', [(15, 19), (11, 19)]),
        'R22': ('r', '330k', [(32, 16), (32, 20)]),
        'R23': ('r', '100k', [(33, 14), (33, 10)]),
        'C12': ('cer', '100nF', [(36, 16), (36, 15)]),
        'C13': ('cer', '100nF', [(37, 14), (37, 15)]),
    }
    headers = [
        K.Header((2, 7), ['GND', 'TX', 'RX', 'V5'], cable='D3',
                 names=['GND', 'TX GP0', 'RX GP1', '5 V']),
        K.Header((2, 28), ['COILN', None, 'V5'], cable='C1',
                 names=['COIL −', '—', '+5 V']),
        K.Header((40, 1), ['GND', 'MIDI', 'V3'], cable='C2',
                 names=['GND', 'RX GP5', '3V3']),
        K.Header((40, 30), ['GND', 'FS1', 'FS2', 'FS3', 'LEDO1', 'LEDO2', 'LEDO3',
                            'LEDO4'], cable='C4',
                 names=['GND', 'FS1', 'FS2', 'FS3', 'LED1', 'LED2', 'LED3', 'LED4']),
        K.Header((40, 39), ['GND', 'EA', 'EB', 'EP', 'BACK', 'V3'], cable='C5',
                 names=['GND', 'A', 'B', 'push', 'back', '3V3']),
        K.Header((2, 46), ['VB', 'VDC', None], cable='P4',
                 names=['VBAT', 'VDC', '—']),
    ]
    links = [
        link((6, 7), (9, 7), 'GND'), link((9, 7), (9, 15), 'GND'),
        link((8, 12), (8, 15), 'GND'),
        link((4, 10), (4, 4), 'V5'), link((5, 10), (5, 30), 'V5'),
        link((30, 4), (30, 9), 'VSYS'),
        link((0, 14), (0, 28), 'COILN'),
        link((38, 1), (38, 10), 'GND'), link((38, 20), (38, 30), 'GND'),
        link((38, 30), (38, 39), 'GND'),
        link((18, 14), (18, 2), 'MIDI'),
        link((26, 3), (26, 12), 'V3'), link((26, 12), (26, 44), 'V3'),
        link((17, 21), (17, 31), 'FS1'), link((18, 22), (18, 32), 'FS2'),
        link((19, 23), (19, 33), 'FS3'),
        link((8, 16), (8, 34), 'LEDO1'), link((9, 17), (9, 35), 'LEDO2'),
        link((10, 18), (10, 36), 'LEDO3'), link((7, 19), (7, 37), 'LEDO4'),
        link((27, 27), (27, 40), 'EA'), link((28, 26), (28, 41), 'EB'),
        link((29, 24), (29, 42), 'EP'), link((31, 23), (31, 43), 'BACK'),
        link((34, 16), (34, 46), 'VB'), link((35, 14), (35, 47), 'VDC'),
    ]
    gnd_rows = {PY + n - 1 for n in gnd_pins if n <= 20}
    cuts = {(20, y) for y in range(PY, PY + 20) if y not in gnd_rows}
    cuts |= {(6, 10), (10, 4), (10, 12), (10, 14), (13, 13)}
    cuts |= {(13, y) for y in range(16, 20)}
    names = ['GP0 TX', 'GP1 RX', 'GND', 'GP2', 'GP3', 'GP4 relay', 'GP5 MIDI', 'GND',
             'GP6 LED', 'GP7 LED', 'GP8 LED', 'GP9 LED', 'GND', 'GP10 FS', 'GP11 FS',
             'GP12 FS', 'GP13', 'GND', 'GP14', 'GP15',
             'GP16 A', 'GP17 B', 'GND', 'GP18 push', 'GP19 back', 'GP20', 'GP21', 'GND',
             'GP22', 'RUN', 'GP26', 'GP27 bat', 'GND', 'GP28 dc', 'ADC', '3V3', '3V3EN',
             'GND', 'VSYS', 'VBUS']
    return K.Board(
        key='control', node='CTRL', W=44, H=52, netlist=nl, parts=parts,
        headers=headers, links=links, cuts=cuts,
        mounts=[(12, 2), (42, 18)],
        carries=set(parts), grounds={'GND': 'CTRL'}, absent={'C6'},
        modules={'M2': dict(outline=(16.2, 7.2, 22.8, 27.8), names=names, joined=[gnd_pins],
                            label='Pico 2 WH\nUSB this end')},
        alias={'GND': 'GND', 'V5': '5 V', 'VSYS': 'VSYS', 'COILN': 'coil −',
               'VB': 'VBAT', 'VDC': 'VDC'},
        title='Control',
        pin_labels={'D4': ['a', 'k'], 'Q1': ['E', 'B', 'C']},
        part_notes={
            'D4': 'band towards VSYS, the right-hand lead',
            'Q1': 'flat face towards you, pins down: emitter, base, collector. '
                  'That is the usual BC337 order; check the bag before soldering',
            'R20': 'GP4 to the base',
            'R21': 'base to the emitter, so the relay stays off while the Pico boots',
            'R16': 'LED 1, and the three beside it LED 2 to LED 4, each 1 kΩ',
            'R22': 'battery sense, the bottom resistor, to ground',
            'R23': 'adapter-present sense, the bottom resistor',
            'C12': 'across the battery divider, at the ADC pin',
            'C13': 'across the adapter-present divider',
        },
        notes=[
            'GP0 and GP1 are the link, which the firmware already uses. Every other '
            'GPIO on this drawing is a proposal. The firmware has not claimed those '
            'pins, so treat the labels as a suggestion for the first build.',
            'The diode is why the Pico keeps running when the Pi reboots. Its 5 V is '
            'the header’s last pin, which is the Pi’s pin 4, and the band faces VSYS. '
            'VBUS, the pin beside it, is left open.',
            'The coil’s low side is switched here, so the cable to the relay carries '
            'no ground. The 100 kΩ holds the transistor off until something explicitly '
            'turns the relay on. The flyback diode is on the relay board.',
            'The USB console lead and the Debug Probe plug into the Pico’s own '
            'sockets. They are not headers on this board.',
            'The expression jack is not drawn. Its plug is the map’s C6, and its '
            'filter would sit at one of the remaining ADC pins.',
            'Cut every strip between the Pico’s two rows, at the marked hole, and the '
            'strips under the series resistors. The four ground rows are joined inside '
            'the Pico, so a cut on a ground row does not break the ground.',
        ])


def boards():
    return [output_board('L'), output_board('R'), power_board(), midi_board(),
            relay_board(), input_board(), carrier_board(), breakout_board(),
            control_board()]


def main():
    OUT.mkdir(exist_ok=True)
    failed = 0
    for board in boards():
        errs = board.check()
        K.draw(board, OUT / f'{board.key}.svg')
        mm = board.size_mm()
        if errs:
            failed += 1
            print(f'FAIL {board.key}  {board.W}x{board.H} = {mm[0]:.1f} x {mm[1]:.1f} mm')
            for e in errs:
                print(f'    {e}')
        else:
            print(f'ok   {board.key}  {board.W}x{board.H} holes = {mm[0]:.1f} x {mm[1]:.1f} mm'
                  f'  {len(board.cuts)} cuts, {len(board.links)} links')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())

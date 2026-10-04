#!/usr/bin/env python3
"""Case wiring schematic: the IN jack and the two output jacks in the prototype case.

The wiring is held here as data (instances, wires, junctions, no-connects, notes) and
emitted as a KiCad schematic, in the same spirit as stripboard/board1.py and
breadboard/board1.py: everything comes from the table, and the script then checks it
against KiCad's own exported netlist rather than against its own opinion.

    python3 schematic/case-wiring.py                  # write prototype-case.kicad_sch
    python3 schematic/case-wiring.py --check FILE.net # compare with an exported netlist

Pin positions are computed from the symbols in KiCad's libraries, so wires land on pins
instead of near them.  Verify with:

    kicad-cli sch erc --severity-all -o /tmp/erc.rpt schematic/prototype-case.kicad_sch
    kicad-cli sch export netlist -o /tmp/case.net schematic/prototype-case.kicad_sch
    python3 schematic/case-wiring.py --check /tmp/case.net
    kicad-cli sch export svg -o /tmp/render schematic/prototype-case.kicad_sch

Two things this sheet deliberately does NOT do.  The screened cable's braid is drawn as a
wire bonded to the sleeve (J1 pin S) and ending, at the other end, in a no-connect marker:
that is what "the screen is grounded at one end only" means, and the far end really does
connect to nothing.  And the core is one continuous wire, because that is what it is.
"""
import os
import re
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "prototype-case.kicad_sch")

# UUIDs come from a counter seeded into a fixed namespace, not from uuid4(): re-running this
# script on unchanged wiring must write the same file, so a diff in git means a real change.
UUID_NS = uuid.UUID("8f14e45f-ceea-467a-9a5b-1d5a1f4f6f2a")
_uuid_seq = 0


def uid():
    global _uuid_seq
    _uuid_seq += 1
    return str(uuid.uuid5(UUID_NS, "seq-%d" % _uuid_seq))

SYMBOL_DIRS = [
    os.environ.get("KICAD_SYMBOL_DIR", ""),
    "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols",
    "/usr/share/kicad/symbols",
]

# ---------------------------------------------------------------- s-expressions
def block(s, i):
    """Text of the balanced group starting at s[i] == '(' and the index after it."""
    depth, j, inq = 0, i, False
    while j < len(s):
        c = s[j]
        if inq:
            if c == "\\":
                j += 2
                continue
            if c == '"':
                inq = False
        elif c == '"':
            inq = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return s[i:j + 1], j + 1
        j += 1
    raise ValueError("unbalanced s-expression")


def children(blk):
    """The top-level groups inside a block, as strings."""
    inner = blk[1:-1] if blk.startswith("(") else blk
    out, i = [], 0
    while i < len(inner):
        if inner[i] == "(":
            sub, i = block(inner, i)
            out.append(sub)
        else:
            i += 1
    return out


def lib_text(fname):
    for d in SYMBOL_DIRS:
        if d and os.path.exists(os.path.join(d, fname)):
            with open(os.path.join(d, fname), encoding="utf-8") as fh:
                return fh.read()
    raise SystemExit("symbol library %s not found; set KICAD_SYMBOL_DIR" % fname)


def lib_symbol(fname, name):
    """The (symbol "name" ...) block from a .kicad_sym, renamed to <lib>:<name>."""
    s = lib_text(fname)
    i = s.find('(symbol "%s"' % name)
    if i < 0:
        raise SystemExit("symbol %s not in %s" % (name, fname))
    blk, _ = block(s, i)
    nick = fname[:-len(".kicad_sym")]
    return blk.replace('(symbol "%s"' % name, '(symbol "%s:%s"' % (nick, name), 1)


def lib_pins(fname, name):
    """{pin number: (x, y)} in library coordinates (y up)."""
    s = lib_text(fname)
    i = s.find('(symbol "%s"' % name)
    blk, _ = block(s, i)
    pins, k = {}, 0
    while True:
        k = blk.find("(pin ", k)
        if k < 0:
            return pins
        sub, after = block(blk, k)
        at = re.search(r"\(at ([-\d.]+) ([-\d.]+) (\d+)\)", sub)
        num = re.search(r'\(number "([^"]*)"', sub)
        if at and num:
            pins[num.group(1)] = (float(at.group(1)), float(at.group(2)))
        k = after


# ---------------------------------------------------------------- the parts
# key: (library file, symbol name, value)
PARTS = {
    "IN_JACK":   ("Connector_Audio.kicad_sym", "AudioJack3_Switch", "NMJ6HF-S"),
    "OUT_JACK":  ("Connector_Audio.kicad_sym", "AudioJack3_Switch", "NMJ6HF-S"),
    "R":         ("Device.kicad_sym", "R", ""),
    "C_POL":     ("Device.kicad_sym", "C_Polarized", ""),
    "STRIP":     ("Connector_Generic.kicad_sym", "Conn_01x04", ""),
    "CODEC_HDR": ("Connector_Generic.kicad_sym", "Conn_01x04", ""),
    "GND":       ("power.kicad_sym", "GND", "GND"),
    "PWR_FLAG":  ("power.kicad_sym", "PWR_FLAG", "PWR_FLAG"),
}

# ref, part, (x, y), (reference pos), (value pos), value override
# Every coordinate is a multiple of 1.27 mm (KiCad's connection grid).  The two output
# channels are the same circuit, one 26.67 mm below the other, so they read across.
INSTANCES = [
    ("J1",   "IN_JACK",   (60.96, 57.15),   (44.45, 60.96),   (44.45, 63.5),    None),
    ("J2",   "OUT_JACK",  (60.96, 105.41),  (44.45, 105.41),  (44.45, 107.95),  None),
    ("J5",   "OUT_JACK",  (60.96, 132.08),  (44.45, 132.08),  (44.45, 134.62),  None),
    ("C1",   "C_POL",     (120.65, 96.52),  (124.46, 93.98),  (124.46, 97.79),  "10u"),
    ("R1",   "R",         (120.65, 106.68), (124.46, 104.14), (124.46, 107.95), "100"),
    ("R2",   "R",         (120.65, 116.84), (124.46, 114.3),  (124.46, 118.11), "1M"),
    ("C2",   "C_POL",     (138.43, 123.19), (142.24, 120.65), (142.24, 124.46), "10u"),
    ("R3",   "R",         (138.43, 133.35), (142.24, 130.81), (142.24, 134.62), "100"),
    ("R4",   "R",         (138.43, 143.51), (142.24, 140.97), (142.24, 144.78), "1M"),
    ("J3",   "STRIP",     (255.27, 113.03), (250.19, 104.14), (250.19, 106.68), "STRIP 4-WAY (IN THE CASE)"),
    ("J4",   "CODEC_HDR", (255.27, 64.77),  (250.19, 55.88),  (250.19, 58.42),  "CODEC HEADER (TODAY)"),
    ("#PWR01", "GND",     (66.04, 48.26),   (61.0, 44.45),    (61.0, 51.0),     None),
    ("#PWR02", "GND",     (66.04, 72.39),   (61.0, 68.58),    (61.0, 75.0),     None),
    ("#PWR03", "GND",     (73.66, 105.41),  (69.0, 101.6),    (69.0, 108.4),    None),
    ("#PWR04", "GND",     (120.65, 120.65), (116.0, 116.84),  (116.0, 123.7),   None),
    ("#PWR05", "GND",     (73.66, 132.08),  (69.0, 128.27),   (69.0, 135.1),    None),
    ("#PWR09", "GND",     (73.66, 100.33),  (69.0, 96.52),    (69.0, 103.3),    None),
    ("#PWR10", "GND",     (73.66, 127.0),   (69.0, 123.19),   (69.0, 130.0),    None),
    ("#PWR06", "GND",     (138.43, 147.32), (134.0, 143.51),  (134.0, 150.3),   None),
    ("#PWR07", "GND",     (250.19, 74.93),  (254.0, 71.12),   (254.0, 78.0),    None),
    ("#PWR08", "GND",     (30.48, 93.98),   (34.5, 90.17),    (34.5, 97.0),     None),
    ("#FLG01", "PWR_FLAG", (30.48, 88.9),   (26.5, 85.09),    (26.5, 91.9),     None),
]

# Every wire, as ((x1, y1), (x2, y2)).  Horizontal or vertical only.
WIRES = [
    # IN jack: the core of the screened cable, one continuous conductor, to LIN1
    ((66.04, 62.23), (250.19, 62.23)),     # J1.T -> J4.1 (codec LIN1)
    ((66.04, 48.26), (66.04, 52.07)),      # GND -> J1.S (sleeve)
    ((66.04, 64.77), (66.04, 72.39)),      # J1.TN (tip switch) -> GND
    # OUT L jack: tip to the strip; sleeve and ring to ground, each on its own wire
    ((66.04, 100.33), (73.66, 100.33)),    # J2.S -> GND
    ((66.04, 105.41), (73.66, 105.41)),    # J2.R -> GND
    ((66.04, 110.49), (120.65, 110.49)),   # J2.T -> node
    ((120.65, 110.49), (250.19, 110.49)),  # node -> J3.1 (strip)
    # the OUT L fixture, on the breadboard today
    ((120.65, 100.33), (120.65, 102.87)),  # C1.2 -> R1.1
    ((120.65, 110.49), (120.65, 113.03)),  # node -> R2.1
    ((120.65, 92.71), (218.44, 92.71)),    # C1.1 (+) ->
    ((218.44, 92.71), (218.44, 64.77)),    #   up
    ((218.44, 64.77), (250.19, 64.77)),    #   -> J4.2 (codec HPL)
    # OUT R jack: the same circuit, one strip pin along
    ((66.04, 127.0), (73.66, 127.0)),      # J5.S -> GND
    ((66.04, 132.08), (73.66, 132.08)),    # J5.R -> GND
    ((66.04, 137.16), (138.43, 137.16)),   # J5.T -> node
    ((138.43, 137.16), (233.68, 137.16)),  # node ->
    ((233.68, 137.16), (233.68, 113.03)),  #   up
    ((233.68, 113.03), (250.19, 113.03)),  #   -> J3.2 (strip)
    # the OUT R fixture
    ((138.43, 127.0), (138.43, 129.54)),   # C2.2 -> R3.1
    ((138.43, 137.16), (138.43, 139.7)),   # node -> R4.1
    ((138.43, 119.38), (226.06, 119.38)),  # C2.1 (+) ->
    ((226.06, 119.38), (226.06, 67.31)),   #   up
    ((226.06, 67.31), (250.19, 67.31)),    #   -> J4.3 (codec HPR)
    # the codec's ground, and the ERC ground reference
    ((250.19, 69.85), (250.19, 74.93)),    # J4.4 -> GND
    ((30.48, 88.9), (30.48, 93.98)),       # PWR_FLAG -> GND
]

JUNCTIONS = [
    (120.65, 110.49),  # OUT L node: jack, strip, R1, R2
    (138.43, 137.16),  # OUT R node: jack, strip, R3, R4
]

NO_CONNECTS = [
    (66.04, 57.15),    # J1.R   - IN is mono
    (66.04, 59.69),    # J1.RN
    (66.04, 54.61),    # J1.SN  - sleeve switch, unused
    (66.04, 107.95),   # J2.RN  - cable detection later
    (66.04, 113.03),   # J2.TN
    (66.04, 102.87),   # J2.SN
    (66.04, 134.62),   # J5.RN
    (66.04, 139.7),    # J5.TN
    (66.04, 129.54),   # J5.SN
    (250.19, 115.57),  # J3.3   - reserved: INST/LINE switch
    (250.19, 118.11),  # J3.4   - reserved: DC socket +9 V
]

LABELS = [
    ("IN", (149.86, 62.23)),
    ("OUT_L_TIP", (160.02, 110.49)),
    ("OUT_R_TIP", (160.02, 137.16)),
]

# Dashed drawings, not wires.  The jacket, so the core and braid read as one cable; the
# braid itself, which is bonded to the sleeve at one end and cut at the other, so it is not
# a net of its own; and the cut mark.
RECTS = [
    ((73.66, 47.63), (198.12, 64.77)),
]
POLYS = [
    [(66.04, 52.07), (193.04, 52.07)],                                   # the braid
    [(191.77, 50.8), (194.31, 53.34)],                                   # cut mark
    [(191.77, 53.34), (194.31, 50.8)],
]

NOTES = [
    (78.74, 50.8, "screen (braid): bonded to the sleeve at this end only"),
    (147.32, 50.8, "far end: cut flush + heatshrunk, connects to nothing"),
    (104.14, 56.5, "one screened cable (CBBR4177) - core and braid in one jacket"),
    (30, 78, "J1, J2 and J5 pin names, as the stock KiCad jack symbol draws them:"),
    (30, 80.5, "T = tip, R = ring, S = sleeve, TN = tip switch, RN = ring switch,"),
    (30, 83, "SN = sleeve switch.  SN and RN are unused on all three jacks."),
    (36.83, 88.9, "PWR_FLAG: the 0 V comes from the star tag (board 1 later);"),
    (36.83, 91.44, "this marks the GND net as driven for ERC."),
    (30, 156, "The input: screened cable CBBR4177."),
    (30, 158.5, "core: J1 tip -> J4 pin 1 (codec LIN1)."),
    (30, 161, "screen: bonded to J1 pin S (sleeve) at this end only; the far"),
    (30, 163.5, "end is cut flush, so the braid makes no second ground"),
    (30, 166, "connection anywhere."),
    (30, 171, "Later: J4 is removed - the core wire lands on board 1's IN pad,"),
    (30, 173.5, "and J3 pins 1 and 2 go to board 1's OUT-L and OUT-R pads with"),
    (30, 176, "the bypass relay in those runs (Phase 3.6).  Leave them long."),
    (105, 156, "GND: every ground symbol here is the same node - the case's M3"),
    (105, 158.5, "star tag.  One wire per item, no daisy chains.  The codec's GND"),
    (105, 161, "reaches it on one wire only."),
    (105, 166, "J1 pin TN (tip switch) is soldered to the sleeve lug at the"),
    (105, 168.5, "jack, so an empty jack holds the input at 0 V."),
    (105, 173, "OUT R (J5) is wired exactly like OUT L (J2): its own fixture,"),
    (105, 175.5, "its own strip pin, and sleeve and ring to the star."),
    (180, 156, "Output fixtures (on the breadboard today, 2a 8b)"),
    (180, 158.5, "HPL and HPR sit at about 1.65 V DC.  A jack must never see"),
    (180, 161, "them directly: always through the 10 uF (+ towards the codec)"),
    (180, 163.5, "and the 100 ohm.  The 1M holds each tip at 0 V DC."),
    (180, 168.5, "J3 pin 1 = OUT L tip, pin 2 = OUT R tip.  Pins 3 and 4 are"),
    (180, 171, "reserved for the INST/LINE switch and the DC socket (+9 V)."),
    (258.0, 62.23, "1  LIN1 (codec, today)"),
    (258.0, 64.77, "2  HPL (codec)"),
    (258.0, 67.31, "3  HPR (codec)"),
    (258.0, 69.85, "4  GND (codec)"),
    (258.0, 110.49, "1  OUT L tip"),
    (258.0, 113.03, "2  OUT R tip"),
    (258.0, 115.57, "3  INST/LINE switch (later)"),
    (258.0, 118.11, "4  DC socket +9 V (later)"),
]

TITLE = "Prototype case - jack wiring: IN, OUT L and OUT R"
REV = "draft 2"

# What the netlist must say.  Power symbols are ignored, and a pin alone in a net counts
# as unconnected (that is how KiCad reports a no-connect).
INTENDED = {
    "GND": {"J1.S", "J1.TN", "J2.S", "J2.R", "J5.S", "J5.R", "R2.2", "R4.2", "J4.4"},
    "IN": {"J1.T", "J4.1"},
    "OUT_L_TIP": {"J2.T", "J3.1", "R1.2", "R2.1"},
    "OUT_R_TIP": {"J5.T", "J3.2", "R3.2", "R4.1"},
    "OUT L fixture: R1-C1": {"R1.1", "C1.2"},
    "OUT L fixture: C1-HPL": {"C1.1", "J4.2"},
    "OUT R fixture: R3-C2": {"R3.1", "C2.2"},
    "OUT R fixture: C2-HPR": {"C2.1", "J4.3"},
}
UNCONNECTED = {"J1.R", "J1.RN", "J1.SN", "J2.RN", "J2.TN", "J2.SN",
               "J5.RN", "J5.TN", "J5.SN", "J3.3", "J3.4"}


def pin_pos(part, at):
    """{pin: (x, y)} on the sheet.  Rotation 0, no mirror: (X + px, Y - py)."""
    fname, sym, _ = PARTS[part]
    pins = lib_pins(fname, sym)
    return {n: (round(at[0] + x, 4), round(at[1] - y, 4)) for n, (x, y) in pins.items()}


def build():
    lib_ids, seen = [], set()
    for ref, part, at, _, _, _ in INSTANCES:
        fname, sym, _ = PARTS[part]
        key = "%s:%s" % (fname[:-len(".kicad_sym")], sym)
        if key not in seen:
            lib_ids.append(lib_symbol(fname, sym))
            seen.add(key)

    root = str(uid())
    out = []
    out.append("(kicad_sch")
    out.append("\t(version 20250114)")
    out.append('\t(generator "eeschema")')
    out.append('\t(generator_version "9.0")')
    out.append('\t(uuid "%s")' % root)
    out.append('\t(paper "A4")')
    out.append("\t(title_block")
    out.append('\t\t(title "%s")' % TITLE)
    out.append('\t\t(rev "%s")' % REV)
    out.append('\t\t(comment 1 "Generated by schematic/case-wiring.py; checked with ERC and the exported netlist.")')
    out.append("\t)")
    out.append("\t(lib_symbols")
    out.extend(lib_ids)
    out.append("\t)")

    def dashed(item):
        out.append("\t\t(stroke")
        out.append("\t\t\t(width 0.1524)")
        out.append("\t\t\t(type dash)")
        out.append("\t\t)")
        out.append("\t\t(fill")
        out.append("\t\t\t(type none)")
        out.append("\t\t)")
        out.append('\t\t(uuid "%s")' % uid())
        out.append("\t)")

    for (x1, y1), (x2, y2) in RECTS:
        out.append("\t(rectangle")
        out.append("\t\t(start %s %s)" % (x1, y1))
        out.append("\t\t(end %s %s)" % (x2, y2))
        dashed(None)

    for pts in POLYS:
        out.append("\t(polyline")
        out.append("\t\t(pts")
        out.append("\t\t\t" + " ".join("(xy %s %s)" % pt for pt in pts))
        out.append("\t\t)")
        dashed(None)

    for x, y in JUNCTIONS:
        out.append("\t(junction")
        out.append("\t\t(at %s %s)" % (x, y))
        out.append("\t\t(diameter 0)")
        out.append("\t\t(color 0 0 0 0)")
        out.append('\t\t(uuid "%s")' % uid())
        out.append("\t)")

    for x, y in NO_CONNECTS:
        out.append("\t(no_connect")
        out.append("\t\t(at %s %s)" % (x, y))
        out.append('\t\t(uuid "%s")' % uid())
        out.append("\t)")

    for (x1, y1), (x2, y2) in WIRES:
        out.append("\t(wire")
        out.append("\t\t(pts")
        out.append("\t\t\t(xy %s %s) (xy %s %s)" % (x1, y1, x2, y2))
        out.append("\t\t)")
        out.append("\t\t(stroke")
        out.append("\t\t\t(width 0)")
        out.append("\t\t\t(type default)")
        out.append("\t\t)")
        out.append('\t\t(uuid "%s")' % uid())
        out.append("\t)")

    for x, y, text in NOTES:
        out.append('\t(text "%s"' % text.replace('"', '\\"'))
        out.append("\t\t(exclude_from_sim no)")
        out.append("\t\t(at %s %s 0)" % (x, y))
        out.append("\t\t(effects")
        out.append("\t\t\t(font")
        out.append("\t\t\t\t(size 1.27 1.27)")
        out.append("\t\t\t)")
        out.append("\t\t\t(justify left bottom)")
        out.append("\t\t)")
        out.append('\t\t(uuid "%s")' % uid())
        out.append("\t)")

    for name, (x, y) in LABELS:
        out.append('\t(label "%s"' % name)
        out.append("\t\t(at %s %s 0)" % (x, y))
        out.append("\t\t(effects")
        out.append("\t\t\t(font")
        out.append("\t\t\t\t(size 1.27 1.27)")
        out.append("\t\t\t)")
        out.append("\t\t\t(justify left bottom)")
        out.append("\t\t)")
        out.append('\t\t(uuid "%s")' % uid())
        out.append("\t)")

    placed = {}
    for ref, part, at, refpos, valpos, valover in INSTANCES:
        fname, sym, value = PARTS[part]
        lib_id = "%s:%s" % (fname[:-len(".kicad_sym")], sym)
        if valover is not None:
            value = valover
        pins = pin_pos(part, at)
        placed[ref] = pins
        out.append("\t(symbol")
        out.append('\t\t(lib_id "%s")' % lib_id)
        out.append("\t\t(at %s %s 0)" % (at[0], at[1]))
        out.append("\t\t(unit 1)")
        out.append("\t\t(exclude_from_sim no)")
        out.append("\t\t(in_bom yes)")
        out.append("\t\t(on_board yes)")
        out.append("\t\t(dnp no)")
        out.append('\t\t(uuid "%s")' % uid())
        for prop, val, pos in (("Reference", ref, refpos), ("Value", value, valpos)):
            out.append('\t\t(property "%s" "%s"' % (prop, val))
            out.append("\t\t\t(at %s %s 0)" % (pos[0], pos[1]))
            out.append("\t\t\t(effects")
            out.append("\t\t\t\t(font")
            out.append("\t\t\t\t\t(size 1.27 1.27)")
            out.append("\t\t\t\t)")
            out.append("\t\t\t\t(justify left)")
            if ref.startswith("#"):        # power symbols carry no visible text
                out.append("\t\t\t\t(hide yes)")
            out.append("\t\t\t)")
            out.append("\t\t)")
        for prop in ("Footprint", "Datasheet", "Description"):
            out.append('\t\t(property "%s" ""' % prop)
            out.append("\t\t\t(at %s %s 0)" % (at[0], at[1]))
            out.append("\t\t\t(effects")
            out.append("\t\t\t\t(font")
            out.append("\t\t\t\t\t(size 1.27 1.27)")
            out.append("\t\t\t\t)")
            out.append("\t\t\t\t(hide yes)")
            out.append("\t\t\t)")
            out.append("\t\t)")
        for num in sorted(pins):
            out.append('\t\t(pin "%s"' % num)
            out.append('\t\t\t(uuid "%s")' % uid())
            out.append("\t\t)")
        out.append("\t\t(instances")
        out.append('\t\t\t(project "case-wiring"')
        out.append('\t\t\t\t(path "/%s"' % root)
        out.append('\t\t\t\t\t(reference "%s")' % ref)
        out.append("\t\t\t\t\t(unit 1)")
        out.append("\t\t\t\t)")
        out.append("\t\t\t)")
        out.append("\t\t)")
        out.append("\t)")
    out.append("\t(sheet_instances")
    out.append('\t\t(path "/"')
    out.append('\t\t\t(page "1")')
    out.append("\t\t)")
    out.append("\t)")
    out.append("\t(embedded_fonts no)")
    out.append(")")
    return "\n".join(out) + "\n", placed


def check_geometry(placed):
    """Every wire end must land on a pin, another wire end, or a point on a wire."""
    pin_pts, wire_ends = {}, {}
    for ref, pins in placed.items():
        for num, pt in pins.items():
            pin_pts.setdefault(pt, []).append("%s.%s" % (ref, num))
    for w in WIRES:
        for pt in w:
            wire_ends[pt] = wire_ends.get(pt, 0) + 1
    bad = []
    ignore = set(NO_CONNECTS)          # cut ends are meant to land on nothing
    for w in WIRES:
        for pt in w:
            on_wire = any(
                (w2[0][0] == w2[1][0] == pt[0] and min(w2[0][1], w2[1][1]) <= pt[1] <= max(w2[0][1], w2[1][1]))
                or (w2[0][1] == w2[1][1] == pt[1] and min(w2[0][0], w2[1][0]) <= pt[0] <= max(w2[0][0], w2[1][0]))
                for w2 in WIRES if w2 is not w
            )
            if pt not in pin_pts and wire_ends[pt] < 2 and not on_wire and pt not in ignore:
                bad.append(pt)
    return bad


def check_netlist(path):
    s = open(path, encoding="utf-8").read()
    i = s.find("(nets")
    if i < 0:
        raise SystemExit("no (nets ...) in %s" % path)
    body, _ = block(s, i)
    got = []
    for net in children(body):
        if not net.startswith("(net"):
            continue
        members = set()
        for node in children(net):
            if not node.startswith("(node"):
                continue
            r = re.search(r'\(ref "([^"]+)"\)', node)
            p = re.search(r'\(pin "([^"]+)"\)', node)
            if r and p and not r.group(1).startswith("#"):
                members.add("%s.%s" % (r.group(1), p.group(1)))
        if len(members) > 1:          # a pin alone in a net is an unconnected pin
            got.append(members)
    ok = True
    remaining = [set(v) for v in INTENDED.values()]
    for members in got:
        for want in remaining:
            if members == want:
                print("  ok      %s" % ", ".join(sorted(members)))
                remaining.remove(want)
                break
        else:
            print("  EXTRA   %s" % ", ".join(sorted(members)))
            ok = False
    for want in remaining:
        print("  MISSING %s" % ", ".join(sorted(want)))
        ok = False
    seen = set()
    for members in got:
        seen |= members
    for pin in sorted(UNCONNECTED):
        if pin in seen:
            print("  BAD     %s should be unconnected" % pin)
            ok = False
    print("netlist check: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main():
    if "--check" in sys.argv:
        return check_netlist(sys.argv[sys.argv.index("--check") + 1])
    text, placed = build()
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("wrote %s" % OUT)
    print("\npins on the sheet:")
    for ref in sorted(placed):
        if ref.startswith("#"):
            continue
        print("  %-5s %s" % (ref, "  ".join("%s=(%s, %s)" % (n, p[0], p[1]) for n, p in sorted(placed[ref].items()))))
    bad = check_geometry(placed)
    print("\nwire ends not landing on anything: %s" % (bad if bad else "none"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

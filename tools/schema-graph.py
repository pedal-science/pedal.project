#!/usr/bin/env python3
"""Generate the schema graph views.

One source of truth for the two model graphs (ljoss rig tree, namchain rig
document, the engine.schema catalogue, and the transformation between them),
written out in two explorable formats:

  docs/schemas/schema-graph.drawio   - open in draw.io (diagrams.net) or the
                                       draw.io desktop app: four pages, edges
                                       and vertices, pan/zoom/search.
  docs/schemas/schema-graph.graphml  - open in yEd (free): Layout ->
                                       Hierarchical arranges each tab.

The graph data below is curated from the schemas and their source of truth
(ljoss RigDesigner/Model, namchain src/graph/rig.cpp, src/nodes/{builtin,
macros}.cpp, src/daemon/daemon.cpp); the schemas stay the precise contract and
this script only draws them.

Run:  python3 tools/schema-graph.py
"""

from __future__ import annotations

import html
import pathlib

OUT_DRAWIO = pathlib.Path("docs/schemas/schema-graph.drawio")
OUT_GRAPHML = pathlib.Path("docs/schemas/schema-graph.graphml")

# ---------------------------------------------------------------------------
# Node kinds -> draw.io style fragments
# ---------------------------------------------------------------------------

NODE_STYLE = {
    "ljoss": "rounded=1;whiteSpace=wrap;html=1;arcSize=8;fillColor=#dae8fc;strokeColor=#6c8ebf;",
    "engine": "rounded=1;whiteSpace=wrap;html=1;arcSize=8;fillColor=#d5e8d4;strokeColor=#82b366;",
    "catalog": "rounded=1;whiteSpace=wrap;html=1;arcSize=8;fillColor=#ffe6cc;strokeColor=#d79b00;",
    "primitive": "rounded=1;whiteSpace=wrap;html=1;arcSize=8;fillColor=#e1d5e7;strokeColor=#9673a6;",
    "enum": "rounded=1;whiteSpace=wrap;html=1;arcSize=24;fillColor=#fff2cc;strokeColor=#d6b656;",
    "external": "rounded=1;whiteSpace=wrap;html=1;arcSize=8;fillColor=#f5f5f5;strokeColor=#666666;dashed=1;",
    "note": "text;html=1;align=left;verticalAlign=middle;whiteSpace=wrap;fontSize=11;fontColor=#555555;",
    "rednote": "text;html=1;align=left;verticalAlign=middle;whiteSpace=wrap;fontSize=11;fontColor=#b85450;",
}

EDGE_STYLE = {
    "contains": "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;whiteSpace=wrap;endArrow=block;fontSize=10;labelBackgroundColor=#FFFFFF;strokeColor=#404040;",
    "signal": "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;whiteSpace=wrap;endArrow=block;fontSize=10;labelBackgroundColor=#FFFFFF;strokeColor=#9673a6;fontColor=#6c4d80;",
    "ref": "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;whiteSpace=wrap;endArrow=open;dashed=1;fontSize=10;labelBackgroundColor=#FFFFFF;strokeColor=#808080;fontColor=#555555;",
    "refuse": "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;whiteSpace=wrap;endArrow=block;dashed=1;fontSize=10;labelBackgroundColor=#FFFFFF;strokeColor=#b85450;fontColor=#b85450;",
}

# ---------------------------------------------------------------------------
# The graph data
# ---------------------------------------------------------------------------

def N(key, title, lines=(), kind="ljoss", col=None):
    return {"key": key, "title": title, "lines": list(lines), "kind": kind, "col": col}


def E(src, dst, label="", kind="contains", back=False):
    return {"src": src, "dst": dst, "label": label, "kind": kind, "back": back}


PAGES = []

# --- Page 1: the ljoss rig document ----------------------------------------

PAGES.append({
    "name": "1 · ljoss rig tree",
    "subtitle": "the designer's document — a series/parallel tree, one file per rig (<uuid>.rig.json)",
    "nodes": [
        N("rig", "Rig", ["id: uuid", "name: string", "layout: RigLayout", "chains: SignalChain[]",
                         "createdAt / modifiedAt: ISO-8601"]),
        N("chain", "SignalChain", ["id: uuid", "name: string", "source: SourceKind",
                                   "input / output: IONode", "elements: ChainElement[]"]),
        N("element", "ChainElement", ["block: Block", "parallel: ParallelSection",
                                      "a series/parallel tree —", "deliberately not a DAG"], "enum"),
        N("block", "Block", ["id: uuid", "componentID: string (catalogue id)", "isEnabled: bool = true",
                             "values: {param → ParamValue}"]),
        N("pv", "ParamValue", ["number(Double)", "option(String)", "flag(Bool)",
                               "on disk: {\"case\": {\"_0\": …}}"], "enum"),
        N("par", "ParallelSection", ["id: uuid", "splitMode: SplitMode = yCable",
                                     "crossoverHz / balance: number", "lanes: Lane[]"]),
        N("lane", "Lane", ["id: uuid", "elements: ChainElement[]", "level: dB · pan: −1…1",
                           "isMuted · invertPhase"]),
        N("ionode", "IONode", ["id: uuid", "values: {param → ParamValue}",
                               "fixed endpoints — never", "removable or reorderable"]),
        N("lay", "RigLayout", ["single", "dual", "a viewing preference — hidden", "chains are still sent"], "enum"),
        N("src", "SourceKind", ["guitar · bass · vocal"], "enum"),
        N("sm", "SplitMode", ["yCable", "aB", "crossover", "dynamic", "only yCable reaches", "today's engine"], "enum"),
        N("cat", "Catalogue component", ["componentID → ComponentSpec", "(ParamSpec[]: kind, bounds,", "default, unit)",
                                         "defaults live here,", "not in the rig file"], "external"),
        N("n1", "one file per rig", ["saved by Store/RigLibrary.swift;", "unknown keys are ignored on load"], "note"),
    ],
    "edges": [
        E("rig", "chain", "chains 1…N"),
        E("rig", "lay", "layout"),
        E("chain", "ionode", "input 1"),
        E("chain", "ionode", "output 1"),
        E("chain", "src", "source"),
        E("chain", "element", "elements 0…N"),
        E("element", "block", "block"),
        E("element", "par", "parallel"),
        E("block", "pv", "values 0…N — only what", "contains"),
        E("ionode", "pv", "values 0…N"),
        E("par", "lane", "lanes (≥2 after normalize)"),
        E("lane", "element", "elements 0…N — the recursion"),
        E("par", "sm", "splitMode"),
        E("block", "cat", "componentID →", "ref"),
    ],
})

# --- Page 2: the namchain rig document -------------------------------------

PAGES.append({
    "name": "2 · namchain rig document",
    "subtitle": "what rig.apply accepts, rig.get returns, and the daemon keeps as last.json — the form a rig is transformed into",
    "nodes": [
        N("doc", "Rig document", ["name?: string", "meta?: object", "chains  — or —", "nodes + connections",
                                  "(exactly one form)"], "engine"),
        N("chain", "Chain", ["id: string (non-empty)", "name?: string", "input_channel?: int ≥ 0",
                             "output_channel?: int ≥ 0", "nodes: Node[]", "connections?: Connection[]",
                             "meta?: object"], "engine"),
        N("node", "Node", ["type: string (required)", "id? · element? (one needed)", "role?: string",
                           "bypass?: bool = false", "params: {…: number}", "strings: {…: string}",
                           "+ any other key → inline", "parameter: number | bool | string"], "engine"),
        N("conn", "Connection", ["from: node id", "from_port?: int = 0", "to: node id", "to_port?: int = 0"],
           "engine"),
        N("meta", "meta", ["any object", "carried, never parsed"], "engine"),
        N("nt", "NodeType", ["the node's type id,", "from engine.schema (page 3).", "Unknown keys are refused, not",
                             "ignored — a client's own data", "goes in meta."], "external"),
        N("n2", "strict by contract", ["the parser (src/graph/rig.cpp) refuses unknown keys", "at every level except the node"], "note"),
    ],
    "edges": [
        E("doc", "chain", "chains 1…N", "contains"),
        E("doc", "node", "nodes (legacy form → chain 'main')", "ref"),
        E("doc", "conn", "connections (legacy form)", "ref"),
        E("chain", "node", "nodes 1…N — order is irrelevant,", "contains"),
        E("chain", "conn", "connections 0…N"),
        E("conn", "node", "from →", "ref"),
        E("conn", "node", "to →", "ref"),
        E("node", "nt", "type = a catalogue id", "ref"),
        E("doc", "meta", "meta"),
        E("chain", "meta", "meta"),
        E("node", "meta", "meta"),
    ],
})

# --- Page 3: the engine.schema catalogue -----------------------------------

PAGES.append({
    "name": "3 · engine.schema catalogue",
    "subtitle": "the answer to {\"method\":\"engine.schema\"} — what a palette, an inspector and a validator are built from",
    "nodes": [
        N("prim", "NodeType", ["id · name · category", "kind: \"primitive\"", "ports: {in[], out[]}",
                               "arity: Arity | null", "flags: Flags", "latency_samples · tail_samples",
                               "params: Param[]", "per_port_params: Param[]"], "catalog"),
        N("macro", "MacroType", ["id · name · category", "kind: \"macro\"", "inputs · outputs",
                                 "channels = 1 · stereo = false", "bypass: roles | crossfade", "roles: Role[]",
                                 "params: Param[] (+targets)"], "catalog"),
        N("port", "Port", ["name: in0 / out0", "channels: 1", "optional: inputs only —",
                           "unconnected = silence"], "catalog"),
        N("arity", "Arity", ["param: \"inputs\" | \"outputs\"", "min · max · default", "only nc.split / nc.mix;",
                             "null for a fixed shape"], "catalog"),
        N("flags", "Flags", ["stateful", "has_lookback", "has_tail", "bypassable (1→1 only)",
                             "block_delay"], "catalog"),
        N("param", "Param", ["id · name", "kind: ParamKind", "unit: Hz | dB | ms | … | null",
                             "default: number | null", "min / max · min_inclusive", "max_inclusive",
                             "step · snap", "scale: ParamScale", "rampable · patchable · hidden",
                             "required · one_of · one_of_required", "options | options_from", "aliases"],
           "catalog"),
        N("option", "Option", ["value: the wire value", "label: the display label"], "catalog"),
        N("role", "Role", ["role: addressable name", "type: a primitive id"], "catalog"),
        N("target", "Target", ["role: which lowered node", "param: its parameter",
                               "transform: Transform", "scale: number"], "catalog"),
        N("kind", "ParamKind", ["number", "option", "flag"], "enum"),
        N("scale", "ParamScale", ["linear", "log"], "enum"),
        N("tf", "Transform", ["direct", "db_to_linear", "linear_to_db", "one_minus", "scale_by"], "enum"),
        N("plist", "11 primitives", ["nc.input · nc.output · nc.gain", "nc.eq.biquad · nc.delay · nc.nam",
                                     "nc.cab.ir · nc.split · nc.mix", "nc.bypass · nc.unit_delay"],
           "catalog"),
        N("mlist", "7 macros", ["fx.eq.bands · fx.eq.tilt", "fx.filter.cut · fx.mix.drywet",
                                "fx.delay.feedback", "fx.amp.tonestack · fx.cab.ir"], "catalog"),
        N("n3", "one array, palette order", ["primitives and macros share the list,", "told apart by kind"], "note"),
    ],
    "edges": [
        E("prim", "port", "ports.in / ports.out"),
        E("prim", "arity", "arity", "ref"),
        E("prim", "flags", "flags"),
        E("prim", "param", "params 0…N"),
        E("prim", "param", "per_port_params 0…N (runtime, by port)", "contains"),
        E("macro", "role", "roles"),
        E("role", "prim", "type = a primitive id", "ref", back=True),
        E("macro", "param", "params 0…N"),
        E("param", "target", "targets (macro params only)"),
        E("target", "role", "role →", "ref"),
        E("target", "tf", "transform"),
        E("param", "kind", "kind"),
        E("param", "scale", "scale"),
        E("param", "option", "options (one of options / options_from)", "ref"),
        E("plist", "prim", "one entry per type", "ref"),
        E("mlist", "macro", "one entry per type", "ref"),
    ],
})

# --- Page 4: the transformation --------------------------------------------

PAGES.append({
    "name": "4 · tree → document → lowered graph",
    "subtitle": "ljoss flattens the topology, the engine lowers the blocks — the designer's tree, the document that is sent, and the primitives that actually render",
    "nodes": [
        # Left column: the ljoss tree
        N("cin", "Chain input (IONode)", ["element = input UUID"], "ljoss", col=0),
        N("cout", "Chain output (IONode)", ["values.level → gain_db"], "ljoss", col=0),
        N("amp", "Block · amp.britplexi", ["engine.model: option", "bass/mid/treble: 0–10 knobs",
                                           "gain/master: out-of-band"], "ljoss", col=0),
        N("cab", "Block · cab.412brit", ["engine.ir: option", "level: number",
                                         "mic/distance/axis:", "out-of-band"], "ljoss", col=0),
        N("del", "Block · delay.digital", ["time: ms", "feedback: 0–10 knob", "mix: 0–100",
                                           "sync: out-of-band"], "ljoss", col=0),
        N("eq", "Block · eq.highcut", ["freq: Hz", "slope: \"12 dB\" | \"24 dB\""], "ljoss", col=0),
        N("par", "ParallelSection · yCable", ["lanes: 2…N", "one element id on", "split and mix"], "ljoss", col=0),
        N("lane", "Lane", ["level: −6 dB", "isMuted · invertPhase"], "ljoss", col=0),
        N("unmapped", "a block with no mapping", ["(verb.*, dyn.*, …)"], "ljoss", col=0),
        N("ab", "ParallelSection", ["aB | crossover | dynamic"], "ljoss", col=0),
        N("ref1", "refused:", ["\"has no engine equivalent", "on this device\""], "rednote", col=1),
        N("ref2", "refused by name:", ["\"only a Y split is built\" —", "not quietly flattened"], "rednote", col=1),
        N("bnote", "Block.isEnabled = false", ["→ every lowered node gets", "bypass: true (state stays warm)"], "note", col=0),
        # Middle column: the engine document
        N("nin", "nc.input", ["id: \"in\"", "element = input UUID"], "engine", col=1),
        N("nout", "nc.output", ["id: \"out\"", "element = output UUID"], "engine", col=1),
        N("nam", "nc.nam", ["model: library id"], "engine", col=1),
        N("tone", "fx.amp.tonestack", ["bass/mid/treble: dB", "mid_freq: Hz"], "engine", col=1),
        N("cabn", "fx.cab.ir", ["ir: library id", "low_cut / high_cut: Hz", "level_db: dB"], "engine", col=1),
        N("deln", "fx.delay.feedback", ["time: ms", "feedback: 0…0.95", "mix: 0…1"], "engine", col=1),
        N("cutn", "fx.filter.cut", ["high_cut: Hz", "high_slope: \"12\" | \"24\""], "engine", col=1),
        N("split", "nc.split", ["outputs = lane count"], "engine", col=1),
        N("mix", "nc.mix", ["inputs = lane count", "lane i on port i"], "engine", col=1),
        N("gain", "nc.gain", ["gain (linear) — lane", "gain_db (dB) — output level"], "engine", col=1),
        N("chnote", "channel binding", ["chain input_channel / output_channel", "by position — chain 0 → channel 0"], "note", col=1),
        # Right: the lowered primitives
        N("bb", "nc.eq.biquad", ["role: bass"]),
        N("bm", "nc.eq.biquad", ["role: mid"]),
        N("bt", "nc.eq.biquad", ["role: treble"]),
        N("clow", "nc.eq.biquad", ["role: low — highpass"]),
        N("cir", "nc.cab.ir", ["role: ir"]),
        N("chigh", "nc.eq.biquad", ["role: high — lowpass"]),
        N("clev", "nc.gain", ["role: level"]),
        N("ddry", "nc.gain", ["role: dry"]),
        N("dsum", "nc.mix", ["role: sum"]),
        N("dline", "nc.delay", ["role: line"]),
        N("dfb", "nc.gain", ["role: fb"]),
        N("dtap", "nc.unit_delay", ["role: tap — block_delay"]),
        N("dwet", "nc.gain", ["role: wet"]),
        N("dout", "nc.mix", ["role: out"]),
        N("idnote", "engine-minted ids", ["a lowered node is <element>/<role>", "a client draws rig.get's", "\"lowered\" view, it does not", "rebuild it from roles"], "note"),
    ],
    "edges": [
        # The flattening: tree → document
        E("cin", "nin", "element = input UUID"),
        E("cout", "nout", "element = output UUID"),
        E("cout", "gain", "level → gain_db (−60…24)", "ref"),
        E("amp", "nam", "engine.model → \"model\"", "contains"),
        E("amp", "tone", "bass/mid/treble:", "contains"),
        E("cab", "cabn", "engine.ir → \"ir\"", "contains"),
        E("del", "deln", "time direct", "contains"),
        E("eq", "cutn", "freq → high_cut", "contains"),
        E("par", "split", "outputs = lanes"),
        E("par", "mix", "inputs = lanes"),
        E("lane", "gain", "level/mute/polarity →", "ref"),
        E("split", "deln", "lane 0 series…", "signal"),
        E("deln", "gain", "…then the lane's gain", "signal"),
        E("gain", "mix", "port 0", "signal"),
        E("split", "mix", "empty lane = dry path:", "ref"),
        # Refusals
        E("unmapped", "ref1", "", "refuse"),
        E("ab", "ref2", "", "refuse"),
        # Macro lowering: tonestack
        E("tone", "bb", "role bass", "signal"),
        E("bb", "bm", "signal", "signal"),
        E("bm", "bt", "signal", "signal"),
        E("tone", "bb", "bass → gain_db", "ref"),
        E("tone", "bm", "mid → gain_db", "ref"),
        E("tone", "bt", "treble → gain_db", "ref"),
        E("tone", "bm", "mid_freq → freq", "ref"),
        # Macro lowering: cab
        E("cabn", "clow", "role low — highpass @ low_cut", "signal"),
        E("clow", "cir", "signal", "signal"),
        E("cir", "chigh", "role high — lowpass @ high_cut", "signal"),
        E("chigh", "clev", "role level — level_db", "signal"),
        # Macro lowering: delay (the feedback loop)
        E("deln", "ddry", "input goes two ways: dry…", "signal"),
        E("deln", "dsum", "…and into the loop", "signal"),
        E("dsum", "dline", "signal", "signal"),
        E("dline", "dfb", "signal", "signal"),
        E("dfb", "dtap", "signal", "signal"),
        E("dtap", "dsum", "feedback loop — tap breaks the cycle", "signal", back=True),
        E("dline", "dwet", "wet tap", "signal"),
        E("ddry", "dout", "dry", "signal"),
        E("dwet", "dout", "wet", "signal"),
    ],
})

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

MARGIN = 30
COL_GAP = 70
ROW_GAP = 26
TITLE_H = 60


def node_size(node):
    all_lines = [node["title"]] + node["lines"]
    width = min(max(140, max(len(l) for l in all_lines) * 6.6 + 28), 330)
    height = 24 + 14.5 * len(node["lines"])
    return width, height


def layout_page(page):
    nodes = {n["key"]: n for n in page["nodes"]}
    # effective column per node; free nodes get layer from their free preds, base 2 on page 4
    base = 2 if page["name"].startswith("4") else 0
    free = [n for n in page["nodes"] if n["col"] is None]
    layer = {}
    # Kahn-style longest-path layering over the free nodes, skipping back edges
    preds = {n["key"]: set() for n in free}
    for e in page["edges"]:
        if e["back"]:
            continue
        if e["src"] in nodes and e["dst"] in nodes and e["src"] in preds and e["dst"] in preds:
            preds[e["dst"]].add(e["src"])
    remaining = list(free)
    assigned = set()
    while remaining:
        progressed = False
        for n in list(remaining):
            ready = preds[n["key"]].issubset(assigned)
            if ready:
                layer[n["key"]] = max([layer[p] + 1 for p in preds[n["key"]] if p in layer] or [0])
                assigned.add(n["key"])
                remaining.remove(n)
                progressed = True
        if not progressed:  # a cycle among free nodes: assign remaining by order
            for n in remaining:
                layer[n["key"]] = 0
                assigned.add(n["key"])
            remaining = []
    # place into columns
    columns = {}
    for n in page["nodes"]:
        col = n["col"] if n["col"] is not None else base + layer.get(n["key"], 0)
        columns.setdefault(col, []).append(n)
    # geometry
    width, height = {}, {}
    for n in page["nodes"]:
        width[n["key"]], height[n["key"]] = node_size(n)
    col_widths = {c: max(width[n["key"]] for n in ns) for c, ns in columns.items()}
    total_w = sum(col_widths[c] for c in sorted(columns)) + COL_GAP * (len(columns) - 1) + 2 * MARGIN
    positions = {}
    col_heights = {}
    x = MARGIN
    for c in sorted(columns):
        y = MARGIN + TITLE_H
        for n in columns[c]:
            positions[n["key"]] = (x + (col_widths[c] - width[n["key"]]) / 2, y)
            y += height[n["key"]] + ROW_GAP
        col_heights[c] = y - MARGIN - TITLE_H
        x += col_widths[c] + COL_GAP
    total_h = max(col_heights.values()) + 2 * MARGIN + TITLE_H
    # vertically centre the columns
    for c, ns in columns.items():
        offset = (max(col_heights.values()) - col_heights[c]) / 2
        for n in ns:
            x, y = positions[n["key"]]
            positions[n["key"]] = (x, y + offset)
    return nodes, positions, width, height, total_w, total_h


def html_label(node):
    lines = "".join(f"{html.escape(l)}<br>" for l in node["lines"])
    return f"<b>{html.escape(node['title'])}</b><br><font style='font-size:10px'>{lines}</font>"


def drawio_pages():
    import xml.sax.saxutils as sx

    def esc(text):
        return sx.escape(text, {'"': "&quot;"})

    pages_xml = []
    for pi, page in enumerate(PAGES):
        nodes, positions, width, height, total_w, total_h = layout_page(page)
        cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
        ids = {key: f"p{pi}n{i}" for i, key in enumerate(nodes)}
        # page title
        cells.append(
            f'<mxCell id="p{pi}t" value="{esc('<b>' + page['name'] + '</b> — ' + page['subtitle'])}"'
            f' style="text;html=1;align=left;verticalAlign=middle;whiteSpace=wrap;fontSize=15;"'
            f' vertex="1" parent="1"><mxGeometry x="30" y="12" width="{total_w - 60}" height="40" as="geometry"/></mxCell>')
        for key, node in nodes.items():
            x, y = positions[key]
            cells.append(
                f'<mxCell id="{ids[key]}" value="{esc(html_label(node))}"'
                f' style="{NODE_STYLE[node["kind"]]}fontSize=12;" vertex="1" parent="1">'
                f'<mxGeometry x="{x:.0f}" y="{y:.0f}" width="{width[key]:.0f}" height="{height[key]:.0f}" as="geometry"/></mxCell>')
        # edges, with spread anchors for parallel edges between the same pair
        pair_count = {}
        for e in page["edges"]:
            pair_count[(e["src"], e["dst"])] = pair_count.get((e["src"], e["dst"]), 0) + 1
        pair_used = {}
        for ei, e in enumerate(page["edges"]):
            if e["src"] not in nodes or e["dst"] not in nodes:
                continue
            pair = (e["src"], e["dst"])
            pair_used[pair] = pair_used.get(pair, 0) + 1
            n_edges = pair_count[pair]
            idx = pair_used[pair]
            sx_, sy = positions[e["src"]]
            tx, ty = positions[e["dst"]]
            sw, sh = width[e["src"]], height[e["src"]]
            tw, th = width[e["dst"]], height[e["dst"]]
            # anchor on facing borders, spread vertically for parallel edges
            spread = (idx - (n_edges + 1) / 2) * 16
            if tx + tw <= sx_:  # target is left of source: exit left, enter right
                exit_x, exit_y = sx_, sy + sh / 2 + spread
                entry_x, entry_y = tx + tw, ty + th / 2 + spread
            else:  # exit right, enter left
                exit_x, exit_y = sx_ + sw, sy + sh / 2 + spread
                entry_x, entry_y = tx, ty + th / 2 + spread
            style = EDGE_STYLE[e["kind"]]
            if e["kind"] == "refuse":  # self loop stub
                cells.append(
                    f'<mxCell id="p{pi}e{ei}" value="{esc(e["label"])}" style="{style}" edge="1" parent="1"'
                    f' source="{ids[e["src"]]}" target="{ids[e["dst"]]}">'
                    f'<mxGeometry relative="1" as="geometry"/></mxCell>')
                continue
            cells.append(
                f'<mxCell id="p{pi}e{ei}" value="{esc(e["label"])}" style="{style}" edge="1" parent="1"'
                f' source="{ids[e["src"]]}" target="{ids[e["dst"]]}">'
                f'<mxGeometry relative="1" as="geometry">'
                f'<mxPoint x="{exit_x:.0f}" y="{exit_y:.0f}" as="sourcePoint"/>'
                f'<mxPoint x="{entry_x:.0f}" y="{entry_y:.0f}" as="targetPoint"/>'
                f'</mxGeometry></mxCell>')
        pages_xml.append(
            f'<diagram id="p{pi}" name="{esc(page['name'])}">'
            f'<mxGraphModel dx="800" dy="600" grid="1" gridSize="10" guides="1" tooltips="1" connect="1"'
            f' arrows="1" fold="1" page="1" pageScale="1" pageWidth="{total_w:.0f}" pageHeight="{total_h:.0f}"'
            f' math="0" shadow="0"><root>{"".join(cells)}</root></mxGraphModel></diagram>')
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<mxfile host="app.diagrams.net" modified="2026-01-01T00:00:00.000Z" agent="tools/schema-graph.py" version="24.0.0" type="device">'
            + "".join(pages_xml) + "</mxfile>")


def graphml():
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns"',
        ' xmlns:y="http://www.yworks.com/xml/graphml"',
        ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
        ' xsi:schemaLocation="http://graphml.graphdrawing.org/xmlns http://www.yworks.com/xml/schema/graphml/1.1/ygraphml.xsd">',
        '<key id="label" for="node" attr.name="label" attr.type="string"/>',
        '<key id="elabel" for="edge" attr.name="label" attr.type="string"/>',
    ]
    for page in PAGES:
        parts.append(f'<graph id="{page["name"]}" edgedefault="directed">')
        for n in page["nodes"]:
            label = n["title"] + "\n" + "\n".join(n["lines"])
            parts.append(f'<node id="{n["key"]}"><data key="label">{html.escape(label)}</data></node>')
        for i, e in enumerate(page["edges"]):
            parts.append(
                f'<edge id="{e["src"]}-{e["dst"]}-{i}" source="{e["src"]}" target="{e["dst"]}">'
                f'<data key="elabel">{html.escape(e["label"])}</data></edge>')
        parts.append("</graph>")
    parts.append("</graphml>")
    return "\n".join(parts)


def main():
    OUT_DRAWIO.write_text(drawio_pages())
    OUT_GRAPHML.write_text(graphml())
    print(f"wrote {OUT_DRAWIO} and {OUT_GRAPHML}")


if __name__ == "__main__":
    main()

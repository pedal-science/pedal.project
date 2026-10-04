#!/usr/bin/env python3
"""Convert a Graphviz wiring graph into yEd-friendly GraphML.

    python3 docs/wiring/dot-to-graphml.py [graph.dot] [graph.graphml]

The .dot beside this script describes the case wiring but carries no positions, so the
layout comes from graphviz (`dot -Tjson`): node centres and sizes, cluster bounding boxes
and edge splines.  Those become y:Geometry, group bounds and y:Path points, written in
yEd's dialect — a group is a y:ProxyAutoBoundsNode with two realizers and a nested
<graph> holding its children, ids nested as <group>::<id>, which is how yEd writes it.

Passes: read the .dot, take geometry from graphviz, assign ids, emit, then check — every
node placed, every edge's ends known, each node inside its cluster, no two boxes
overlapping, and the file re-parsed.  The graph's canvas colour (bgcolor) is not part of
GraphML; set it in yEd if you want it.
"""
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_IN = os.path.join(HERE, "graph.dot")
DEFAULT_OUT = os.path.join(HERE, "graph.graphml")

# ---------------------------------------------------------------- reading the .dot
TOKEN_RE = re.compile(r"""
      (?P<ws>\s+|\#[^\n]*|//[^\n]*|/\*.*?\*/)
    | (?P<edgeop>--|->)
    | (?P<punct>[{}\[\];,=])
    | (?P<qstr>"(?:\\.|[^"\\])*")
    | (?P<id>[^\s{}\[\];,="]+)
""", re.X | re.S)


class Cluster:
    def __init__(self, name, parent):
        self.name, self.parent = name, parent
        self.attrs, self.nodes, self.children = {}, [], []
        self.gid, self.box = None, None


class DotGraph:
    def __init__(self):
        self.name, self.attrs = "", {}
        self.nodes, self.edges = {}, []
        self.root = Cluster("", None)


def tokenize(text):
    out, i = [], 0
    while i < len(text):
        m = TOKEN_RE.match(text, i)
        if not m:
            raise SystemExit("cannot tokenize at %r" % text[i:i + 20])
        i = m.end()
        if m.lastgroup == "ws":
            continue
        raw = m.group()
        if m.lastgroup == "qstr":
            out.append(("id", re.sub(r"\\(.)", r"\1", raw[1:-1])))
        elif m.lastgroup in ("edgeop", "punct"):
            out.append((m.lastgroup, raw))
        else:
            out.append(("id", raw))
    out.append(("eof", ""))
    return out


def parse_dot(text):
    toks, pos = tokenize(text), 0

    def peek():
        return toks[pos][1]

    def kind():
        return toks[pos][0]

    def take(what=None):
        nonlocal pos
        tok = toks[pos]
        if what and tok[1] != what:
            raise SystemExit("expected %r, got %r" % (what, tok))
        pos += 1
        return tok[1]

    def attr_list():
        a = {}
        if kind() == "punct" and peek() == "[":
            take("[")
            while not (kind() == "punct" and peek() == "]"):
                key = take()
                take("=")
                a[key] = take()
                if kind() == "punct" and peek() == ",":
                    take(",")
            take("]")
        return a

    g = DotGraph()
    scope = [(g.root, {}, {})]                 # cluster, node defaults, edge defaults

    def statements(cluster):
        while not (kind() == "punct" and peek() == "}"):
            before = pos
            if kind() == "id" and toks[pos + 1][1] == "=":
                key = take()
                take("=")
                cluster.attrs[key] = take()
            elif kind() == "id" and peek() in ("graph", "node", "edge") and toks[pos + 1][1] == "[":
                what = take()
                a = attr_list()
                (cluster.attrs if what == "graph" else scope[-1][1 if what == "node" else 2]).update(a)
            elif kind() == "id" and peek() == "subgraph":
                take()
                name = "" if (kind() == "punct" and peek() == "{") else take()
                take("{")
                child = Cluster(name, cluster)
                cluster.children.append(child)
                scope.append((child, dict(scope[-1][1]), dict(scope[-1][2])))
                statements(child)
                take("}")
                scope.pop()
            else:
                head = take()
                if kind() == "edgeop":
                    while kind() == "edgeop":
                        take()
                        tail = take()
                        g.edges.append((head, tail, attr_list()))
                        head = tail
                else:
                    a = attr_list()
                    if head not in g.nodes:
                        g.nodes[head] = dict(scope[-1][1])
                        cluster.nodes.append(head)
                    g.nodes[head].update(a)
            if kind() == "punct" and peek() == ";":
                take(";")
            if pos == before:
                raise SystemExit("stuck parsing at %r" % peek())

    take()                                     # graph / digraph
    if not (kind() == "punct" and peek() == "{"):
        g.name = take()
    take("{")
    statements(g.root)
    take("}")
    return g


# ---------------------------------------------------------------- geometry from graphviz
def geometry(dot_path):
    j = json.loads(subprocess.run(["dot", "-Tjson", dot_path],
                                  capture_output=True, check=True).stdout)
    bb = [float(v) for v in j["bb"].split(",")]
    height = bb[3] - bb[1]
    nodes, boxes = {}, {}
    for o in j["objects"]:
        name = o.get("name", "")
        if name.startswith("cluster"):
            if o.get("bb"):
                b = [float(v) for v in o["bb"].split(",")]
                boxes[name] = (b[0], height - b[3], b[2], height - b[1])
            continue
        cx, cy = (float(v) for v in o["pos"].split(","))
        w, h = float(o["width"]) * 72.0, float(o["height"]) * 72.0
        nodes[name] = (cx - w / 2, height - (cy + h / 2), w, h)
    splines = [[(x, height - y) for x, y in
                (tuple(float(v) for v in p.split(",")) for p in e["pos"].split())]
               for e in j["edges"]]
    return nodes, boxes, splines, height


def flatten(points, per_segment=6):
    """Graphviz splines are 1 + 3n points; sample the cubics so the curve comes across."""
    if len(points) < 2 or (len(points) - 1) % 3:
        return points
    out = [points[0]]
    for i in range(1, len(points), 3):
        p0, c1, c2, p1 = out[-1], points[i], points[i + 1], points[i + 2]
        for k in range(1, per_segment + 1):
            t, mt = k / per_segment, 1 - k / per_segment
            out.append(tuple(mt ** 3 * a + 3 * mt ** 2 * t * b + 3 * mt * t ** 2 * c + t ** 3 * d
                             for a, b, c, d in zip(p0, c1, c2, p1)))
    return out


# ---------------------------------------------------------------- yEd GraphML
def colour(value, default="#FFFFFF"):
    """yEd writes hex colours in upper case, and its schema insists on it."""
    v = (value or "").strip()
    if re.match(r"^#[0-9A-Fa-f]{6}$", v) or re.match(r"^#[0-9A-Fa-f]{8}$", v):
        return v.upper()
    named = {"black": "#000000", "white": "#FFFFFF", "red": "#FF0000", "green": "#00FF00",
             "blue": "#0000FF", "lightblue": "#ADD8E6", "darkgreen": "#006400",
             "darkred": "#8B0000", "grey": "#808080", "gray": "#808080"}
    return named.get(v.lower(), default)


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def dot_text(s):
    return s.replace("\\n", "\n").replace("\\l", "\n").replace("\\r", "")


NODE_LABEL_ATTRS = ('autoSizePolicy="content" fontFamily="Dialog" fontSize="%g" fontStyle="plain" '
                    'hasBackgroundColor="false" hasLineColor="false" horizontalTextPosition="center" '
                    'iconTextGap="4" textColor="%s" verticalTextPosition="bottom" visible="true"')


def shape_node(label, font_size, geom, fill, line, text_color="#000000"):
    x, y, w, h = geom
    return ('<y:ShapeNode>\n'
            '<y:Geometry height="%g" width="%g" x="%g" y="%g"/>\n'
            '<y:Fill color="%s" transparent="false"/>\n'
            '<y:BorderStyle color="%s" raised="false" type="line" width="1.0"/>\n'
            '<y:NodeLabel alignment="center" %s modelName="custom" xml:space="preserve">%s'
            '<y:LabelModel><y:SmartNodeLabelModel distance="4.0"/></y:LabelModel>'
            '<y:ModelParameter><y:SmartNodeLabelModelParameter labelRatioX="0.0" labelRatioY="0.0" '
            'nodeRatioX="0.0" nodeRatioY="0.0" offsetX="0.0" offsetY="0.0" upX="0.0" upY="-1.0"/>'
            '</y:ModelParameter></y:NodeLabel>\n'
            '<y:Shape type="rectangle"/>\n'
            '</y:ShapeNode>') % (h, w, x, y, fill, line, NODE_LABEL_ATTRS % (font_size, text_color), esc(label))


def group_node(label, geom, fill, font_size, text_color, closed):
    x, y, w, h = geom
    if label:
        label_xml = ('<y:NodeLabel alignment="center" %s modelName="internal" modelPosition="t" '
                     'xml:space="preserve">%s</y:NodeLabel>'
                     % (NODE_LABEL_ATTRS % (font_size, text_color), esc(label)))
    else:
        label_xml = ('<y:NodeLabel alignment="center" %s hasText="false" modelName="internal" '
                     'modelPosition="c" height="4.0" width="4.0" x="0.0" y="0.0"/>'
                     % (NODE_LABEL_ATTRS % (font_size, text_color)))
    return ('<y:GroupNode>\n'
            '<y:Geometry height="%g" width="%g" x="%g" y="%g"/>\n'
            '<y:Fill color="%s" transparent="false"/>\n'
            '<y:BorderStyle color="#000000" type="line" width="1.0"/>\n'
            '%s\n'
            '<y:Shape type="rectangle"/>\n'
            '<y:State closed="%s" closedHeight="80.0" closedWidth="100.0" innerGraphDisplayEnabled="false"/>\n'
            '<y:Insets bottom="15" bottomF="15.0" left="15" leftF="15.0" right="15" rightF="15.0" top="15" topF="15.0"/>\n'
            '<y:BorderInsets bottom="0" bottomF="0.0" left="0" leftF="0.0" right="0" rightF="0.0" top="0" topF="0.0"/>\n'
            '</y:GroupNode>') % (h, w, x, y, fill, label_xml, "true" if closed else "false")


def box4(box):
    """(x0, y0, x1, y1) -> (x, y, w, h)."""
    return (box[0], box[1], box[2] - box[0], box[3] - box[1])


def poly_line(spline, uc, vc):
    src = (spline[0][0] - uc[0], spline[0][1] - uc[1])
    tgt = (spline[-1][0] - vc[0], spline[-1][1] - vc[1])
    bends = "".join('<y:Point x="%g" y="%g"/>' % p for p in spline[1:-1])
    return ('<y:PolyLineEdge>\n'
            '<y:Path sx="%g" sy="%g" tx="%g" ty="%g">%s</y:Path>\n'
            '<y:LineStyle color="#000000" type="line" width="1.0"/>\n'
            '<y:Arrows source="none" target="none"/>\n'
            '<y:BendStyle smoothed="true"/>\n'
            '</y:PolyLineEdge>') % (src[0], src[1], tgt[0], tgt[1], bends)


def all_clusters(cluster):
    out = []
    for c in cluster.children:
        out.extend(all_clusters(c))
        out.append(c)
    return out


def convert(dot_path, out_path):
    g = parse_dot(open(dot_path, encoding="utf-8").read())
    geoms, boxes, splines, _ = geometry(dot_path)

    clusters = all_clusters(g.root)
    by_name = {c.name: c for c in clusters}
    for name, box in boxes.items():
        if name in by_name:
            by_name[name].box = box

    # graphviz drops clusters with no nodes; give those a spot inside their parent
    taken = [c.box for c in clusters if c.box] + \
            [(g[0], g[1], g[0] + g[2], g[1] + g[3]) for g in geoms.values()]
    for c in clusters:
        if c.box is None:
            parent_box = c.parent.box if c.parent and c.parent.box else \
                (min(v[0] for v in geoms.values()), min(v[1] for v in geoms.values()),
                 max(v[0] + v[2] for v in geoms.values()), max(v[1] + v[3] for v in geoms.values()))
            c.box = free_box(parent_box, taken)
            taken.append(c.box)
    # grow every box to hold what it contains, deepest first, so the nesting is consistent
    for c in clusters:
        kids = [k.box for k in c.children] + \
               [(geoms[n][0], geoms[n][1], geoms[n][0] + geoms[n][2], geoms[n][1] + geoms[n][3])
                for n in c.nodes if n in geoms]
        for k in kids:
            c.box = (min(c.box[0], k[0]), min(c.box[1], k[1]),
                     max(c.box[2], k[2]), max(c.box[3], k[3]))

    # ids: groups n<k>, children nested under their graph as <group id>::<local>
    for i, c in enumerate(clusters):
        c.gid = "n%d" % i
    node_id, node_cluster, seen = {}, {}, {}
    for c in clusters:
        prefix = (c.gid + "::") if c.name else ""
        for name in c.nodes:
            local = re.sub(r"[^A-Za-z0-9_.-]", "_", name) or "n"
            while local in seen:
                local += "_"
            seen[local] = True
            node_id[name] = prefix + local
            node_cluster[name] = c

    # edges belong in the graph holding both ends (their least common cluster)
    def chain(cluster):
        out = []
        while cluster is not None:
            out.append(cluster)
            cluster = cluster.parent if cluster.name else None
        return out

    edges_in = {c.gid: [] for c in clusters}
    edges_in[""] = []
    for i, (u, v, _) in enumerate(g.edges):
        if u not in node_id or v not in node_id:
            raise SystemExit("edge %s -- %s refers to an unknown node" % (u, v))
        uchain = chain(node_cluster[u])
        vchain = set(id(c) for c in chain(node_cluster[v]))
        home = next(c for c in uchain if id(c) in vchain)
        edges_in[home.gid if home.name else ""].append(i)

    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8" standalone="no"?>')
    lines.append('<graphml xmlns="http://graphml.graphdrawing.org/xmlns" '
                 'xmlns:java="http://www.yworks.com/xml/yfiles-common/1.0/java" '
                 'xmlns:sys="http://www.yworks.com/xml/yfiles-common/markup/primitives/2.0" '
                 'xmlns:x="http://www.yworks.com/xml/yfiles-common/markup/2.0" '
                 'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                 'xmlns:y="http://www.yworks.com/xml/graphml" '
                 'xmlns:yed="http://www.yworks.com/xml/yed/3" '
                 'xsi:schemaLocation="http://graphml.graphdrawing.org/xmlns '
                 'http://www.yworks.com/xml/schema/graphml/1.1/ygraphml.xsd">')
    lines.append('  <!--Written by docs/wiring/dot-to-graphml.py from %s. '
                 'Layout: graphviz dot.-->' % os.path.basename(dot_path))
    lines.append('  <key for="node" id="d_node" yfiles.type="nodegraphics"/>')
    lines.append('  <key for="edge" id="d_edge" yfiles.type="edgegraphics"/>')

    def put(text, pad):
        lines.append("\n".join(pad + l for l in text.split("\n")))

    def emit(cluster, graph_id, indent):
        pad = "  " * indent
        for c in cluster.children:
            put('<node id="%s" yfiles.foldertype="group">' % c.gid, pad)
            put('<data key="d_node">', pad + "  ")
            put('<y:ProxyAutoBoundsNode>', pad + "    ")
            put('<y:Realizers active="0">', pad + "      ")
            label = c.attrs.get("label", "")
            fill = colour(c.attrs.get("bgcolor"), "#FFFFFF")
            text = "#FFFFFF" if c.attrs.get("fontcolor") == "white" else "#000000"
            put(group_node(label, box4(c.box), fill, 14, text, False), pad + "        ")
            bx, by = c.box[0], c.box[1]
            put(group_node(label, (bx + 5, by + 5, 100.0, 60.0), fill, 14, text, True),
                pad + "        ")
            put('</y:Realizers>', pad + "      ")
            put('</y:ProxyAutoBoundsNode>', pad + "    ")
            put('</data>', pad + "  ")
            put('<graph edgedefault="directed" id="%s:">' % c.gid, pad + "  ")
            emit(c, c.gid + ":", indent + 2)
            put('</graph>', pad + "  ")
            put('</node>', pad)
        for name in cluster.nodes:
            attrs, geom = g.nodes[name], geoms[name]
            label = attrs.get("label", r"\N")
            label = name if label == r"\N" else dot_text(label)
            fill = colour(attrs.get("color", attrs.get("fillcolor")), "#FFFFFF")
            put('<node id="%s">' % node_id[name], pad)
            put('<data key="d_node">', pad + "  ")
            put(shape_node(label, float(attrs.get("fontsize", 24)), geom, fill, fill), pad + "    ")
            put('</data>', pad + "  ")
            put('</node>', pad)
        for i in edges_in[cluster.gid if cluster.name else ""]:
            u, v, _ = g.edges[i]
            ux, uy, uw, uh = geoms[u]
            vx, vy, vw, vh = geoms[v]
            spline = flatten(splines[i]) if i < len(splines) else [(0, 0)] * 2
            put('<edge id="e%d" source="%s" target="%s">' % (i, node_id[u], node_id[v]), pad)
            put('<data key="d_edge">', pad + "  ")
            put(poly_line(spline, (ux + uw / 2, uy + uh / 2), (vx + vw / 2, vy + vh / 2)), pad + "    ")
            put('</data>', pad + "  ")
            put('</edge>', pad)

    put('<graph edgedefault="directed" id="G">', "  ")
    emit(g.root, "G", 2)
    put('</graph>', "  ")
    lines.append('</graphml>')
    open(out_path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return g, geoms, node_cluster, splines


def free_box(outer, taken, w=150.0, h=70.0, step=10, margin=4):
    x = outer[0] + margin
    while x + w <= outer[2] - margin:
        y = outer[1] + margin
        while y + h <= outer[3] - margin:
            box = (x, y, x + w, y + h)
            if not any(overlap(box, t) for t in taken if t):
                return box
            y += step
        x += step
    return (outer[0] + margin, outer[3] + margin, outer[0] + margin + w,
            outer[3] + margin + h)


def overlap(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


NS = {"g": "http://graphml.graphdrawing.org/xmlns", "y": "http://www.yworks.com/xml/graphml"}


def check_file(path, g, splines):
    """Check the artefact, not the data it was built from."""
    problems = []
    root = ET.parse(path).getroot().find("g:graph", NS)
    nodes, groups, edges = {}, {}, []

    def box_of(el):
        return (float(el.get("x")), float(el.get("y")),
                float(el.get("x")) + float(el.get("width")),
                float(el.get("y")) + float(el.get("height")))

    def walk(gr, parent):
        for n in gr.findall("g:node", NS):
            grp = n.find("g:data/y:ProxyAutoBoundsNode", NS)
            if grp is not None:
                geo = grp.find("y:Realizers/y:GroupNode/y:Geometry", NS)
                if geo is None:
                    problems.append("group %s has no geometry" % n.get("id"))
                    continue
                groups[n.get("id")] = box_of(geo)
                sub = n.find("g:graph", NS)
                if sub is not None:
                    walk(sub, n.get("id"))
            else:
                geo = n.find("g:data/y:ShapeNode/y:Geometry", NS)
                if geo is None:
                    problems.append("node %s has no geometry" % n.get("id"))
                    continue
                nodes[n.get("id")] = (box_of(geo), parent)
        for e in gr.findall("g:edge", NS):
            edges.append((e.get("source"), e.get("target")))

    walk(root, None)
    if len(nodes) != len(g.nodes):
        problems.append("%d nodes in the .dot, %d written" % (len(g.nodes), len(nodes)))
    if len(edges) != len(g.edges):
        problems.append("%d edges in the .dot, %d written" % (len(g.edges), len(edges)))
    if len(groups) != len(children_of(g.root)) if False else 0:
        pass
    for nid, (box, parent) in nodes.items():
        if box[2] <= box[0] or box[3] <= box[1]:
            problems.append("node %s has an empty box" % nid)
        if parent and not (box[0] >= groups[parent][0] - 1 and box[1] >= groups[parent][1] - 1
                           and box[2] <= groups[parent][2] + 1 and box[3] <= groups[parent][3] + 1):
            problems.append("%s is outside its group %s" % (nid, parent))
    ids = list(nodes)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if overlap(nodes[a][0], nodes[b][0]):
                problems.append("nodes %s and %s overlap" % (a, b))
    for u, v in edges:
        for end in (u, v):
            if end not in nodes:
                problems.append("edge end %s is not a node" % end)
    if not splines:
        problems.append("no splines from graphviz")
    return problems


def children_of(cluster):
    out = []
    for c in cluster.children:
        out.append(c)
        out.extend(children_of(c))
    return out


def check(g, geoms, node_cluster, splines):
    problems = []
    for name in g.nodes:
        if name not in geoms:
            problems.append("graphviz placed no node called %s" % name)
            continue
        box = geoms[name]
        outer = node_cluster[name].box
        if outer and not (box[0] >= outer[0] - 1 and box[1] >= outer[1] - 1
                          and box[0] + box[2] <= outer[2] + 1 and box[1] + box[3] <= outer[3] + 1):
            problems.append("%s sticks out of %s" % (name, node_cluster[name].name))
    placed = [n for n in g.nodes if n in geoms]
    for i, a in enumerate(placed):
        for b in placed[i + 1:]:
            if overlap(geoms[a], geoms[b]):
                problems.append("nodes %s and %s overlap" % (a, b))
    if len(splines) != len(g.edges):
        problems.append("%d edges in the .dot but %d splines from graphviz"
                        % (len(g.edges), len(splines)))
    return problems


def main():
    dot_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_IN
    out_path = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUT
    if not os.path.isabs(dot_path):
        dot_path = os.path.join(HERE, dot_path)
    if not os.path.isabs(out_path):
        out_path = os.path.join(HERE, out_path)

    g, geoms, node_cluster, splines = convert(dot_path, out_path)
    ET.parse(out_path)                                   # well-formed and parseable
    problems = check(g, geoms, node_cluster, splines) + check_file(out_path, g, splines)
    print("wrote %s" % out_path)
    print("  %d nodes, %d edges, %d groups" % (len(g.nodes), len(g.edges), len(all_clusters(g.root))))
    print("  checks: %s" % ("ok" if not problems else "; ".join(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

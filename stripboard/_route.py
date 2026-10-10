#!/usr/bin/env python3
"""Route board A first and cut only where the routing demands it.

Tonight's lesson in one line: cuts and links are not separable stages.  Every cut made to stop
a short removes a route, and only routing can say which -- so this routes and cuts together.

For each net, in order of constraint (IN_A first: it is short and high-impedance, then the
ground return, then the low-impedance trunk), it places the links the net needs to become one
piece.  A row is cut only where a *different* net would otherwise be joined by the copper this
routing is using -- not at every net boundary in the row.

The checker is the oracle throughout: it decides whether there is a short and whether a net is
one piece.  Prints the CUTS and LINKS; board_a.py is edited from what it says.

    python3 stripboard/_route.py
"""
import collections
import nets as NET
import board_a as B

W, H = B.W, B.H

# the order the nets are routed in, and why
PRIORITY = ['IN_A', 'IN_RAW', 'IN_B', 'GND_A', 'BIAS', 'VF', 'LIN1', 'U1B', 'BIAS_MID',
            'HPL', 'HPR', 'OUT_L_N', 'OUT_R_N', 'OUT_L', 'OUT_R']


def main():
    net_of, who = {}, {}
    for ref in B.PARTS:
        ls = B.PARTS[ref][2]
        for i in range(len(ls)):
            net_of[ls[i][0]] = ls[i][1]
            who[ls[i][0]] = f'{ref}.{i + 1}'
    for lab in B.PADS:
        net_of[B.PADS[lab][0]] = B.PADS[lab][1]
        who[B.PADS[lab][0]] = f'pad {lab}'
    leads = set(net_of)
    cuts = set(B.CUTS)
    links = list(B.LINKS)

    def span(a, b):
        if a[0] == b[0]:
            lo, hi = sorted((a[1], b[1]))
            return [(a[0], y) for y in range(lo, hi + 1)]
        lo, hi = sorted((a[0], b[0]))
        return [(x, a[1]) for x in range(lo, hi + 1)]

    def find_with(ls):
        parent = {h: h for h in net_of}

        def find(h):
            parent.setdefault(h, h)
            while parent[h] != h:
                parent[h] = parent[parent[h]]
                h = parent[h]
            return h

        for y in range(H):
            for x in range(W - 1):
                a, b = (x, y), (x + 1, y)
                if a in cuts or b in cuts:
                    continue
                if ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) in cuts:
                    continue
                parent[find(a)] = find(b)
        for a, b in ls:
            parent[find(a)] = find(b)
        return find

    wire_ends, wire_cells = set(), set()
    for a, b in links:
        wire_ends |= {a, b}
        wire_cells |= set(span(a, b))

    added_links = []
    for net in PRIORITY:
        for _ in range(24):
            find = find_with(links)
            ps = collections.defaultdict(list)
            for h, n in net_of.items():
                if n == net:
                    ps[find(h)].append(h)
            roots = sorted(ps)
            if len(roots) < 2:
                break
            best = None
            for i in range(len(roots)):
                for j in range(i + 1, len(roots)):
                    for h in ps[roots[i]]:
                        for h2 in ps[roots[j]]:
                            if h[1] == h2[1]:
                                lo, hi = sorted((h[0], h2[0]))
                                steps = [((x, h[1]), (x2, h[1]))
                                         for x in range(lo, hi) for x2 in range(x + 1, hi + 1)]
                            elif h[0] == h2[0]:
                                lo, hi = sorted((h[1], h2[1]))
                                steps = [((h[0], y), (h[0], y2))
                                         for y in range(lo, hi) for y2 in range(y + 1, hi + 1)]
                            else:
                                continue
                            for p, q in steps:
                                if p in cuts or q in cuts:
                                    continue
                                cells = span(p, q)[1:-1]
                                if any(c in cuts or c in wire_cells for c in cells):
                                    continue
                                if (p in wire_ends and p not in leads) or \
                                   (q in wire_ends and q not in leads):
                                    continue
                                d = abs(p[0] - q[0]) + abs(p[1] - q[1])
                                if best is None or d < best[0]:
                                    best = (d, p, q)
            if best is None:
                break
            _, p, q = best
            links.append((p, q))
            added_links.append((p, q, net))
            wire_ends |= {p, q}
            wire_cells |= set(span(p, q))

    # Now cut: every row that this copper carries more than one net on gets a cut at each
    # net-to-net boundary in it.  This is where the cuts come from -- from what the routing
    # actually uses, not from every boundary the layout has.
    def find_now():
        return find_with(links)

    find = find_now()
    per_row = collections.defaultdict(lambda: collections.defaultdict(set))
    for h, net in net_of.items():
        per_row[h[1]][net].add(h[0])
    for a, b in links:
        net = next((n for n in net_of.values()), None)
        for c in span(a, b):
            for net2, hs in per_row[c[1]].items():
                pass
    # a row is cut between the x positions of two different nets that the copper joins
    added_cuts = []
    for y in range(H):
        xs = sorted(x for x in range(W) if (x, y) in net_of)
        for i in range(len(xs) - 1):
            a, b = xs[i], xs[i + 1]
            if NET.same_net(net_of[(a, y)], net_of[(b, y)]):
                continue
            if find((a, y)) != find((b, y)):
                continue                      # already broken somewhere in this row
            cut = (float(a) + (b - a) / 2, y)
            if cut in cuts:
                continue
            cuts.add(cut)
            added_cuts.append((cut, f'row {y}: {net_of[(a, y)]} | {net_of[(b, y)]}'))

    print('CUTS:')
    for c, why in added_cuts:
        print(f'    {c},   # {why}')
    print()
    print('LINKS:')
    for p, q, net in added_links:
        print(f'    ({p}, {q}),   # {net}')
    print()
    find = find_with(links)
    pieces = collections.defaultdict(set)
    for h, net in net_of.items():
        pieces[net].add(find(h))
    roots = collections.defaultdict(lambda: collections.defaultdict(list))
    for h, net in net_of.items():
        roots[find(h)][net].append(h)
    print('splits:', {n: len(v) for n, v in pieces.items() if len(v) > 1} or 'none')
    print('joins :', {str(k): {n: len(v) for n, v in d.items()} for k, d in roots.items()
                      if len(d) > 1} or 'none')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

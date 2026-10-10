#!/usr/bin/env python3
"""Route a stripboard layout: join every net's copper with wires on the component side.

A design tool, not part of the build.  Give it a placement and its cuts; it searches for the
links that make the copper say what `nets.py` says, and prints them for the board file.

    python3 stripboard/route.py                # board_a: the analogue board
    python3 stripboard/route.py --seconds 120  # a bound on the effort

What a link is.  A wire on the component side, running along one row or one column between
two holes.  Its two ends are soldered; everything between them it passes over.  So:

  * an end may be a hole where a lead already is -- that joint is the connection -- but not a
    cut hole, and it may not be a hole another wire already ends in;
  * a wire must not pass over a hole where something is soldered: a cut hole, a lead, or
    another wire's end.  It *may* pass over another wire's span (the wires cross), and a wire
    may cross strips, which is what makes stripboard routing possible at all.

The search is depth-first over nets, hardest first, with a per-net limit on the number of
wires and a global node budget.  A net is routed by joining the pieces of its copper one at a
time, each join taking the shortest free straight run that reaches another piece of the same
net.  If a net cannot be joined, the search undoes the previous net's choice and tries its
next-shortest run.
"""
import argparse
import collections
import sys
import time

import nets as NET

MAX_WIRES_PER_NET = 12


def build(board, pads):
    """The routing problem: leads, pads, cuts, and the copper they already make."""
    W, H = board['W'], board['H']
    leads, net_of = {}, {}
    for ref, (kind, val, ls) in board['PARTS'].items():
        want = NET.nets_using(ref)
        for i, (h, net) in enumerate(ls):
            leads[h] = f'{ref}.{i+1}'
            net_of[h] = net
    for label, (h, net, _) in pads.items():
        net_of[h] = net
    cuts = set(board['CUTS'])

    def broken(a, b):
        return (a in cuts or b in cuts
                or ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) in cuts)

    parent = {}

    def find(h):
        parent.setdefault(h, h)
        while parent[h] != h:
            parent[h] = parent[parent[h]]
            h = parent[h]
        return h

    def union(a, b):
        parent[find(a)] = find(b)

    for y in range(H):
        for x in range(W - 1):
            if not broken((x, y), (x + 1, y)):
                union((x, y), (x + 1, y))
    return dict(W=W, H=H, leads=leads, net_of=net_of, cuts=cuts, broken=broken,
                parent=parent, find=find, union=union)


def span(a, b):
    if a[0] == b[0]:
        lo, hi = sorted((a[1], b[1]))
        return [(a[0], y) for y in range(lo, hi + 1)]
    lo, hi = sorted((a[0], b[0]))
    return [(x, a[1]) for x in range(lo, hi + 1)]


def runs(R, a, b):
    """Every straight run between two holes of a net, shortest first, with what it crosses."""
    W, H, cuts, leads = R['W'], R['H'], R['cuts'], R['leads']
    out = []
    if a[1] == b[1]:
        lo, hi = sorted((a[0], b[0]))
        for x1 in range(lo, hi):
            for x2 in range(x1 + 1, hi + 1):
                p, q = (x1, a[1]), (x2, a[1])
                if p in cuts or q in cuts:
                    continue
                cells = span(p, q)[1:-1]
                if any(c in cuts or c in leads for c in cells):
                    continue
                out.append((abs(x1 - x2), p, q))
    if a[0] == b[0]:
        lo, hi = sorted((a[1], b[1]))
        for y1 in range(lo, hi):
            for y2 in range(y1 + 1, hi + 1):
                p, q = (a[0], y1), (a[0], y2)
                if p in cuts or q in cuts:
                    continue
                cells = span(p, q)[1:-1]
                if any(c in cuts or c in leads for c in cells):
                    continue
                out.append((abs(y1 - y2), p, q))
    out.sort()
    return out


def pieces_of(R, links, net):
    """The copper pieces a net occupies, as {root: [holes]}."""
    parent = dict(R['parent'])
    saved = dict(parent)
    for a, b in links:
        R['parent'][R['find'](a)] = R['find'](b)
    out = collections.defaultdict(list)
    for h, n in R['net_of'].items():
        if n == net:
            out[R['find'](h)].append(h)
    R['parent'] = saved
    return out


def route(R, net, links, end_used, span_used, budget):
    """Join one net's copper.  Returns a list of links, or None."""
    found = []
    for _ in range(MAX_WIRES_PER_NET):
        pieces = pieces_of(R, links + found, net)
        roots = sorted(pieces)
        if len(roots) < 2:
            return found
        first, others = roots[0], roots[1:]
        best = None
        for h in pieces[first]:
            for other in others:
                for h2 in pieces[other]:
                    for d, p, q in runs(R, h, h2):
                        if budget[0] <= 0:
                            return None
                        budget[0] -= 1
                        cells = span(p, q)[1:-1]
                        if any(c in span_used or c in end_used for c in cells):
                            continue
                        if p in end_used or q in end_used:
                            continue
                        best = (d, p, q)
                        break
                    if best is not None:
                        break
                if best is not None:
                    break
            if best is not None:
                break
        if best is None:
            return None
        _, p, q = best
        found.append((p, q))
    return None


def solve(R, seconds=60.0, nodes=400000):
    """Route every net, hardest first, backtracking when one cannot be joined."""
    net_of = R['net_of']
    nets = sorted({n for n in net_of.values()},
                  key=lambda n: -sum(1 for x in net_of.values() if x == n))
    links, end_used, span_used = [], set(), set()
    budget = [nodes]
    deadline = time.time() + seconds

    def rec(i):
        if i == len(nets):
            return True
        if time.time() > deadline or budget[0] <= 0:
            return False
        net = nets[i]
        got = route(R, net, links, end_used, span_used, budget)
        if got is None:
            return False
        for p, q in got:
            links.append((p, q))
            for c in span(p, q):
                span_used.add(c)
            end_used.add(p)
            end_used.add(q)
        if rec(i + 1):
            return True
        for p, q in got:
            links.remove((p, q))
            end_used.discard(p)
            end_used.discard(q)
        # spans from other nets may share holes; recompute conservatively
        span_used.clear()
        for a, b in links:
            for c in span(a, b):
                span_used.add(c)
        return False

    return (links if rec(0) else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seconds', type=float, default=60.0)
    ap.add_argument('--nodes', type=int, default=400000)
    a = ap.parse_args()

    import board_a as B
    board = dict(W=B.W, H=B.H, CUTS=B.CUTS, PARTS=B.PARTS)
    R = build(board, B.PADS)
    got = solve(R, a.seconds, a.nodes)
    if got is None:
        print(f'NO ROUTE within {a.seconds:.0f}s / {a.nodes} nodes')
        return 1
    print(f'routed with {len(got)} wires:')
    for p, q in got:
        print(f'    ({p}, {q}),')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

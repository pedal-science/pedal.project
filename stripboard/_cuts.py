#!/usr/bin/env python3
"""Derive board A's cuts from the checker's own connectivity, and print them.

Twice now the failing part of this has been a hand-written "are these two leads still joined?"
predicate.  So this asks the checker's union-find instead -- the thing that already answers it
correctly -- and derives the cuts from that:

  for each row, take its leads in x order, group them by the net they are on, and put one cut
  at every net-to-net boundary: n-1 cuts for n nets.

**This is only half the rule, and the half it is missing is rule 3b.**  A cut on a row parts
two pieces of copper, and a piece is only ever joined to the rest of the board by a wire whose
end lands on it -- so a cut that no wire needs is a route taken away, and a cut that leaves a
lead with nothing on its own side of it is a lead nobody can wire.  That is why this is a
*report* and not the last word: `stripboard/_route.py` places the wires first and cuts only
where a wire's copper demands it, and `_place.py`'s exits rule says ahead of time whether the
placement *can* be wired at all.  Read this beside those two, not instead of them.

Then it re-runs the checker to see what is left.  Prints the CUTS to use.

    python3 stripboard/_cuts.py
"""
import collections
import sys

import stripboard as SB
import nets as NET
import board_a as B


def checker_connectivity(cuts, links):
    """The copper as the checker sees it: {hole: root}, using the checker's own rules."""
    parent = {}

    def find(h):
        parent.setdefault(h, h)
        while parent[h] != h:
            parent[h] = parent[parent[h]]
            h = parent[h]
        return h

    for y in range(B.H):
        for x in range(B.W - 1):
            a, b = (x, y), (x + 1, y)
            if a in cuts or b in cuts:
                continue
            if ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) in cuts:
                continue
            parent[find(a)] = find(b)
    for a, b in links:
        parent[find(a)] = find(b)
    return find


def main():
    net_of = {}
    for ref in B.PARTS:
        ls = B.PARTS[ref][2]
        for i in range(len(ls)):
            net_of[ls[i][0]] = ls[i][1]
    for lab in B.PADS:
        net_of[B.PADS[lab][0]] = B.PADS[lab][1]

    cuts = set(B.CUTS)
    # every net-to-net boundary in every row: n-1 cuts for n nets
    added = []
    for y in range(B.H):
        xs = sorted(x for x in range(B.W) if (x, y) in net_of)
        for i in range(len(xs) - 1):
            a, b = xs[i], xs[i + 1]
            if NET.same_net(net_of[(a, y)], net_of[(b, y)]):
                continue
            cut = (float(a) + (b - a) / 2, y)
            if cut in cuts:
                continue
            cuts.add(cut)
            added.append((cut, f'row {y}: {net_of[(a, y)]} (x={a}) | {net_of[(b, y)]} (x={b})'))

    print('CUTS:')
    for c, why in added:
        print(f'    {c},   # {why}')
    print(f'({len(added)} added, {len(cuts)} total)')
    print()

    find = checker_connectivity(cuts, B.LINKS)
    pieces = collections.defaultdict(set)
    for h, net in net_of.items():
        pieces[net].add(find(h))
    roots = collections.defaultdict(lambda: collections.defaultdict(list))
    for h, net in net_of.items():
        roots[find(h)][net].append(h)
    joins = {r: dict(v) for r, v in roots.items() if len(v) > 1}
    splits = {n: len(v) for n, v in pieces.items() if len(v) > 1}
    print("after these cuts, as the checker's union-find sees it:")
    print('  nets still split:', splits if splits else 'none')
    print('  nets still joined:', {k: {n: len(h) for n, h in v.items()} for k, v in joins.items()}
          if joins else 'none')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""Join the pieces board A's cuts leave, using the checker's connectivity as the oracle.

    python3 stripboard/_link.py
"""
import collections
import re
import subprocess
import sys

import nets as NET
import board_a as B


def main():
    net_of = {}
    for ref in B.PARTS:
        ls = B.PARTS[ref][2]
        for i in range(len(ls)):
            net_of[ls[i][0]] = ls[i][1]
    for lab in B.PADS:
        net_of[B.PADS[lab][0]] = B.PADS[lab][1]
    leads = set(net_of)
    cuts = set(B.CUTS)
    W, H = B.W, B.H

    def span(a, b):
        if a[0] == b[0]:
            lo, hi = sorted((a[1], b[1]))
            return [(a[0], y) for y in range(lo, hi + 1)]
        lo, hi = sorted((a[0], b[0]))
        return [(x, a[1]) for x in range(lo, hi + 1)]

    def build(links):
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
                if a in cuts or b in cuts or ((a[0]+b[0])/2, (a[1]+b[1])/2) in cuts:
                    continue
                parent[find(a)] = find(b)
        for a, b in links:
            parent[find(a)] = find(b)
        return find

    links = list(B.LINKS)
    ends, used, tried = set(), set(), set()
    for a, b in links:
        ends |= {a, b}
        used |= set(span(a, b))
    added = []
    for _ in range(400):
        find = build(links)
        pieces = collections.defaultdict(lambda: collections.defaultdict(list))
        for h, net in net_of.items():
            pieces[net][find(h)].append(h)
        todo = {n: v for n, v in pieces.items() if len(v) > 1}
        if not todo:
            break
        n = 0
        for net in sorted(todo, key=lambda x: -len(todo[x])):
            ps, roots = todo[net], sorted(todo[net])
            cands = []
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
                                if any(c in cuts or c in leads or c in used
                                       for c in span(p, q)[1:-1]):
                                    continue
                                if (p in ends and p not in leads) or \
                                   (q in ends and q not in leads):
                                    continue
                                if (net, p, q) in tried:
                                    continue
                                cands.append((abs(p[0] - q[0]) + abs(p[1] - q[1]), p, q))
            if not cands:
                continue
            cands.sort()
            _, p, q = cands[0]
            tried.add((net, p, q))
            links.append((p, q))
            added.append((p, q, net))
            ends |= {p, q}
            used |= set(span(p, q))
            n += 1
        if not n:
            break

    print('LINKS:')
    for p, q, net in added:
        print(f'    ({p}, {q}),   # {net}')
    find = build(links)
    pieces = collections.defaultdict(set)
    for h, net in net_of.items():
        pieces[net].add(find(h))
    left = {n: len(v) for n, v in pieces.items() if len(v) > 1}
    print('still split:', left if left else 'NONE -- CLOSED')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

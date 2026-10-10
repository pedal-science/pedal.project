#!/usr/bin/env python3
"""Design board A: place its parts and route its nets, then print the layout as data.

A design tool, not part of the build.  What it prints is written into
`stripboard/board_a.py`, whose own run is the check that matters.

Why it exists.  Board A is the tight one, and hand placement kept failing in ways that took a
minute each to see.  This searches: placements under the checker's rules, then a router that
joins each net's copper with wires on the component side, net by net from the hardest, and
undoes a net's wires when the nets after it cannot be joined.

The codec's breakout is treated as **off board A**: it keeps its own standoffs and returns its
ground to the star tag, so its two 16-pin socket strips do not take columns 1 and 10 for rows
2-17.  That is at least as good for noise as seating them -- the analogue return is the same
single wire to the star either way -- and it is what makes the board routable.

    python3 stripboard/solve.py [--seconds N]
"""
import argparse
import collections
import sys
import time

import nets as NET

W, H = 18, 20
PADS = {                       # fixed terminations: label -> (hole, net)
    'IN':    ((16, 0), 'IN_RAW'),
    'SW-I':  ((11, 0), 'IN_RAW'),
    'SW-C':  ((13, 2), 'IN_A'),
    'SW-L':  ((12, 3), 'IN_B'),
    'LIN1':  ((10, 6), 'LIN1'),
    'HPL':   ((10, 10), 'HPL'),
    'HPR':   ((10, 13), 'HPR'),
    'CGND':  ((10, 14), 'GND_A'),
    'V3A3':  ((10, 15), 'V3A3'),
    'OUT-L': ((3, 19), 'OUT_L'),
    'OUT-R': ((13, 19), 'OUT_R'),
    'STAR':  ((7, 19), 'GND_A'),
    'VF':    ((17, 3), 'VF'),
    'V9':    ((17, 18), 'V9_RAW'),
}
ORDER = ['U1', 'C5', 'R5', 'R6', 'C3', 'C4', 'R2', 'R3', 'R4',
         'C6', 'R7', 'R8', 'C7', 'R9', 'R10']
ANCHOR = {'IN_RAW': [(16, 0)], 'IN_A': [(13, 2)], 'IN_B': [(12, 3)], 'LIN1': [(10, 6)],
          'HPL': [(10, 10)], 'HPR': [(10, 13)], 'VF': [(17, 3)],
          'OUT_L': [(3, 19)], 'OUT_R': [(13, 19)], 'GND_A': [(7, 19)]}


def kind(r):
    return NET.PARTS[r]['kind']


def placements(ref):
    k = kind(ref)
    if k == 'dip8':
        out = []
        for x in range(W - 3):
            for y in range(H - 3):
                out.append(((x, y), (x, y + 1), (x, y + 2), (x, y + 3),
                            (x + 3, y + 3), (x + 3, y + 2), (x + 3, y + 1), (x + 3, y)))
                out.append(((x + 3, y), (x + 3, y + 1), (x + 3, y + 2), (x + 3, y + 3),
                            (x, y + 3), (x, y + 2), (x, y + 1), (x, y)))
        return out
    n = 4 if k in ('r', 'd') else 2
    out = []
    for y in range(H):
        for x in range(W - n + 1):
            out.append(((x, y), (x + n, y)))
    for x in range(W):
        for y in range(H - n + 1):
            out.append(((x, y), (x, y + n)))
    return out


def box(lead):
    return {(x, y) for x in range(min(h[0] for h in lead), max(h[0] for h in lead) + 1)
            for y in range(min(h[1] for h in lead), max(h[1] for h in lead) + 1)}


# ---------------------------------------------------------------- routing
def route_all(leads, net_of, cuts, deadline, limit_per_net=14, pad_holes=()):
    """Join every net's copper.  Returns the link list, or None."""
    parent = {}

    def find(h):
        parent.setdefault(h, h)
        while parent[h] != h:
            parent[h] = parent[parent[h]]
            h = parent[h]
        return h

    def union(a, b):
        parent[find(a)] = find(b)

    def broken(a, b):
        return (a in cuts or b in cuts
                or ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) in cuts)

    for y in range(H):
        for x in range(W - 1):
            if not broken((x, y), (x + 1, y)):
                union((x, y), (x + 1, y))

    def span(a, b):
        if a[0] == b[0]:
            lo, hi = sorted((a[1], b[1]))
            return [(a[0], y) for y in range(lo, hi + 1)]
        lo, hi = sorted((a[0], b[0]))
        return [(x, a[1]) for x in range(lo, hi + 1)]

    links, ends, wire_span = [], set(), set()

    def pieces(net):
        saved = dict(parent)
        for a, b in links:
            union(a, b)
        out = collections.defaultdict(list)
        for h, n in net_of.items():
            if n == net:
                out[find(h)].append(h)
        parent.clear()
        parent.update(saved)
        return out

    def best_run(net):
        ps = pieces(net)
        roots = sorted(ps)
        if len(roots) < 2:
            return 'done'
        cands = []
        for i, r1 in enumerate(roots):
            for r2 in roots[i + 1:]:
                for h in ps[r1]:
                    for h2 in ps[r2]:
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
                            if any(c in cuts or c in leads or c in wire_span for c in cells):
                                continue
                            if p in pad_holes or q in pad_holes:
                                pass          # a wire ending on a pad is the joint
                            if p in ends and p not in pad_holes:
                                continue
                            if q in ends and q not in pad_holes:
                                continue
                            cands.append((abs(p[0] - q[0]) + abs(p[1] - q[1]), p, q))
        if not cands:
            return None
        cands.sort()
        return cands

    nets = sorted({n for n in net_of.values()},
                  key=lambda n: -sum(1 for x in net_of.values() if x == n))

    def rec(i):
        if i == len(nets):
            return True
        if time.time() > deadline:
            return False
        net = nets[i]
        state = best_run(net)
        if state == 'done':
            return rec(i + 1)
        if state is None:
            return False
        for _, p, q in state[:limit_per_net]:
            links.append((p, q))
            for c in span(p, q):
                wire_span.add(c)
            ends.add(p)
            ends.add(q)
            if rec(i):          # the same net may still be in pieces: loop, not recurse
                return True
            links.pop()
            ends.discard(p)
            ends.discard(q)
            wire_span.clear()
            for a, b in links:
                for c in span(a, b):
                    wire_span.add(c)
        return rec(i + 1) if False else False

    def run():
        # join nets one at a time, retrying a net until its pieces are one
        for net in nets:
            for _ in range(limit_per_net):
                state = best_run(net)
                if state == 'done':
                    break
                if state is None:
                    return False
                _, p, q = state[0]
                links.append((p, q))
                for c in span(p, q):
                    wire_span.add(c)
                ends.add(p)
                ends.add(q)
            else:
                return False
        return True

    return links if run() else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seconds', type=float, default=45.0)
    ap.add_argument('--seed', type=int, default=3)
    a = ap.parse_args()
    deadline = time.time() + a.seconds

    import random
    rng = random.Random(a.seed)
    fixed = {h: net for h, net in PADS.values()}
    pad_holes = set(fixed)
    best = None
    tries = 0
    while time.time() < deadline:
        tries += 1
        taken = set(pad_holes)
        placed, strip_net, cuts = {}, {}, set()
        ok = True
        for ref in ORDER:
            want = NET.nets_using(ref)
            cands = placements(ref)
            rng.shuffle(cands)
            scored = []
            for lead in cands:
                occ = box(lead)
                if occ & taken:
                    continue
                nets = [want[f'{ref}.{i+1}'] for i in range(len(lead))]
                new = set()
                bad = False
                for h, net in zip(lead, nets):
                    for x2, n2 in strip_net.get(h[1], {}).items():
                        if NET.same_net(n2, net) or x2 == h[0]:
                            continue
                        new.add(((min(h[0], x2) + max(h[0], x2)) / 2, h[1]))
                if any(c in set(lead) for c in new):
                    continue
                d = sum(abs(h[0] - x) + abs(h[1] - y) for h, net in zip(lead, nets)
                        for x, y in ANCHOR.get(net, []))
                scored.append((d, lead, nets, occ, new))
            if not scored:
                ok = False
                break
            scored.sort(key=lambda t: t[0])
            d, lead, nets, occ, new = scored[rng.randrange(min(4, len(scored)))]
            placed[ref] = list(zip(lead, nets))
            taken |= occ
            cuts |= new
            for h, net in zip(lead, nets):
                strip_net.setdefault(h[1], {})[h[0]] = net
        if not ok:
            continue
        leads, net_of = {}, {}
        for ref, ls in placed.items():
            for i, (h, net) in enumerate(ls):
                leads[h] = f'{ref}.{i+1}'
                net_of[h] = net
        for h, net in fixed.items():
            net_of[h] = net
        got = route_all(leads, net_of, cuts, min(deadline, time.time() + 8),
                        pad_holes=pad_holes)
        if got is not None:
            best = (placed, cuts, got)
            break
    if best is None:
        print(f'no placement routed in {tries} tries / {a.seconds:.0f}s')
        return 1
    placed, cuts, links = best
    print(f'# routed after {tries} placement(s)')
    print('CUTS = {')
    for c in sorted(cuts):
        print(f'    {c},')
    print('}')
    print('LINKS = [')
    for p, q in links:
        print(f'    ({p}, {q}),')
    print(']')
    print('PARTS = {')
    for ref in ORDER:
        print(f"    '{ref}': {[(h, n) for h, n in placed[ref]]},")
    print('}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

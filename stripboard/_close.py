#!/usr/bin/env python3
"""Close board A's connectivity: cut the strips that carry two nets, link the pieces apart.

The parts are placed and the corridors reserved, so this is only the routing job they were
reserved for.  It prints the CUTS and LINKS to add; board_a.py is edited from what it says.

    python3 stripboard/_close.py
"""
import collections
import nets as NET
import board_a as B

W, H = B.W, B.H


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

    def broken(a, b):
        return (a in cuts or b in cuts
                or ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) in cuts)

    def build(links):
        parent = {h: h for h in net_of}
        parent.setdefault((0, 0), (0, 0))

        def find(h):
            parent.setdefault(h, h)
            while parent[h] != h:
                parent[h] = parent[parent[h]]
                h = parent[h]
            return h

        for y in range(H):
            for x in range(W - 1):
                if not broken((x, y), (x + 1, y)):
                    parent[find((x, y))] = find((x + 1, y))
        for a, b in links:
            parent[find(a)] = find(b)
        return find

    # ---- 1. cut the rows that carry two nets
    added_cuts = []
    for y in range(H):
        # every pair of leads on this row that are on different nets needs the copper between
        # them broken -- not just the neighbours in x order, because a row can carry three or
        # four nets and each neighbouring pair is a separate break.
        xs = sorted(x for x in range(W) if (x, y) in net_of)
        for i in range(len(xs)):
            for j in range(i + 1, len(xs)):
                a, b = xs[i], xs[j]
                if NET.same_net(net_of[(a, y)], net_of[(b, y)]):
                    continue
                # the break goes in the gap between them: the between-holes cut next to a
                if b - a == 1:
                    cut = (float(a) + 0.5, y)
                else:
                    cut = (float(a) + 0.5, y)
                if cut in cuts:
                    continue
                # only worth adding if the two leads are still on one piece of copper
                find = build(links)
                if find((a, y)) != find((b, y)):
                    continue
                cuts.add(cut)
                added_cuts.append((cut, f'row {y}: {net_of[(a, y)]} at x={a} | '
                                         f'{net_of[(b, y)]} at x={b}'))

    print('CUTS to add:')
    for c, why in added_cuts:
        print(f'    {c},   # {why}')
    print()

    # ---- 2. link the pieces
    links = list(B.LINKS)

    def span(a, b):
        if a[0] == b[0]:
            lo, hi = sorted((a[1], b[1]))
            return [(a[0], y) for y in range(lo, hi + 1)]
        lo, hi = sorted((a[0], b[0]))
        return [(x, a[1]) for x in range(lo, hi + 1)]

    ends, used, tried = set(), set(), set()
    for a, b in links:
        ends |= {a, b}
        used |= set(span(a, b))

    added = []
    for _round in range(400):
        find = build(links)
        pieces = collections.defaultdict(lambda: collections.defaultdict(list))
        for h, net in net_of.items():
            pieces[net][find(h)].append(h)
        todo = {n: v for n, v in pieces.items() if len(v) > 1}
        if not todo:
            break
        n_added = 0
        for net in sorted(todo, key=lambda n: -len(todo[n])):
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
            n_added += 1
        if not n_added:
            break

    print('LINKS to add:')
    for p, q, net in added:
        print(f'    ({p}, {q}),   # {net}')
    print()
    find = build(links)
    pieces = collections.defaultdict(set)
    for h, net in net_of.items():
        pieces[net].add(find(h))
    left = {n: len(v) for n, v in pieces.items() if len(v) > 1}
    print('still split:', left if left else 'NONE -- CLOSED')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

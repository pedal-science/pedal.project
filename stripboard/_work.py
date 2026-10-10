#!/usr/bin/env python3
"""Scratch: read board A through the checker's own union-find.  Not part of the tree."""
import collections
import stripboard as SB
import nets as NET
import board_a as B

W, H = B.W, B.H


def occupancy():
    net_of, who = {}, {}
    for ref, (kind, val, leads) in B.PARTS.items():
        for i, (h, net) in enumerate(leads):
            net_of[h] = NET.net_key(net)
            who[h] = f'{ref}.{i + 1} ({net})'
    for lab, (h, net, _) in B.PADS.items():
        net_of[h] = NET.net_key(net)
        who[h] = f'pad {lab} ({net})'
    return net_of, who


def state(cuts, links):
    net_of, who = occupancy()
    find = SB.copper(W, H, cuts, links)
    pieces = collections.defaultdict(lambda: collections.defaultdict(list))
    for h, net in net_of.items():
        pieces[net][find(h)].append(h)
    splits = {n: {r: sorted(v) for r, v in d.items()} for n, d in pieces.items() if len(d) > 1}
    roots = collections.defaultdict(dict)
    for h, net in net_of.items():
        roots[find(h)].setdefault(net, []).append(h)
    joins = {r: {n: sorted(v) for n, v in d.items()} for r, d in roots.items() if len(d) > 1}
    return splits, joins, find, net_of, who


print('=== rows that carry more than one net ===')
net_of, who = occupancy()
for y in range(H):
    xs = sorted(x for x in range(W) if (x, y) in net_of)
    nets = []
    for x in xs:
        if not nets or nets[-1][0] != net_of[(x, y)]:
            nets.append((net_of[(x, y)], [x]))
        else:
            nets[-1][1].append(x)
    if len({n for n, _ in nets}) > 1:
        print(f'row {y:2d}: ' + '  |  '.join(
            f'{n}@{v[0]}-{v[-1]}' + ('' if len(v) == 1 else f' ({len(v)} holes)')
            for n, v in nets))

print()
print('=== cuts on each row, as given ===')
for y in range(H):
    row = sorted(c for c in B.CUTS if c[1] == y)
    if row:
        print(f'row {y:2d}: ' + '  '.join(f'{c[0]}' for c in row))
print()
print('=== cuts that separate nothing (dead / off the board) ===')
for c in sorted(B.CUTS):
    x, y = c
    if float(x) == int(x):
        print('  AT-HOLE cut', c)
        continue
    a, b = (int(x - 0.5), y), (int(x + 0.5), y)
    if not (0 <= a[0] < W and 0 <= b[0] < W):
        print('  off the board:', c, ' between', a, b)

print()
splits, joins, find, net_of, who = state(set(B.CUTS), B.LINKS)
print('=== as it stands ===')
for n, d in sorted(splits.items()):
    print(f'  {n} split into {len(d)}:')
    for r, v in sorted(d.items()):
        print(f'      {v}   {[who[h] for h in v]}')
print()
for r, d in sorted(joins.items(), key=lambda kv: str(kv)):
    print(f'  joined at {r}: {d}')

#!/usr/bin/env python3
"""Place board A, and report what the placement's spare holes are.

Two rules beyond the checker's own five, and the reason for each:

  * **the spare-hole rule.**  A link is a wire on the component side, soldered where it ends:
    at a lead, or in the free hole beside one.  A lead whose four neighbouring holes are all
    other leads, cuts or bodies cannot be reached by any wire, and no cut or link can make it
    reachable.  Three routing attempts failed on exactly this -- the placement scored zero
    geometric errors and was still unroutable -- so it is a placement rule, not a routing one.
  * **neighbouring leads of different parts share a net.**  Two leads in neighbouring holes on
    different nets is the one thing no cut can part without stranding one of them: a cut
    between them leaves each on its own hole with the strip gone.  A part's own two leads are
    the exception, and are how each part in the signal path couples to the next.

    python3 stripboard/_place.py            # what the rules say about board_a.py's placement
"""
import nets as NET
import board_a as B

W, H = 18, 24


def body_of(kind, pts):
    out = set()
    if kind in ('r', 'd', 'film'):
        (x1, y1), (x2, y2) = pts[0], pts[1]
        if y1 == y2:
            out |= {(x, y1) for x in range(min(x1, x2) + 1, max(x1, x2))}
        else:
            out |= {(x1, y) for y in range(min(y1, y2) + 1, max(y1, y2))}
    return out


def circle(kind, pts):
    out = set()
    if kind.startswith('el'):
        r = float(kind[2:]) / 2 / 2.54 + 0.15
        cx = sum(p[0] for p in pts) / 2
        cy = sum(p[1] for p in pts) / 2
        for x in range(W):
            for y in range(H):
                if (x, y) not in pts and (x - cx) ** 2 + (y - cy) ** 2 < r * r:
                    out.add((x, y))
    return out


def audit(parts, pads, cuts=()):
    """(leads with no spare hole, neighbouring leads of different parts on different nets)."""
    occ, body, owner = {}, set(), {}
    for ref, (kind, val, leads) in parts.items():
        pts = [h for h, _ in leads]
        for h, net in leads:
            occ[h] = (ref, net)
            owner[h] = ref
        body |= body_of(kind, pts) | circle(kind, pts)
    for lab, (h, net, _) in pads.items():
        occ[h] = (lab, net)
        owner[h] = lab
    cuts = set(cuts)

    def free(p):
        return (0 <= p[0] < W and 0 <= p[1] < H and p not in occ and p not in cuts
                and p not in body)

    no_spare, adjacent = [], []
    for h, (who, net) in sorted(occ.items()):
        x, y = h
        if not any(free(p) for p in ((x, y - 1), (x, y + 1), (x - 1, y), (x + 1, y))):
            no_spare.append((h, who, net))
    for h, (who, net) in sorted(occ.items()):
        x, y = h
        for p in ((x + 1, y), (x, y + 1)):
            e = occ.get(p)
            if e and owner[h] != owner[p] and NET.net_key(e[1]) != NET.net_key(net):
                adjacent.append((h, who, net, p, e[0], e[1]))
    return no_spare, adjacent


def main():
    no_spare, adjacent = audit(B.PARTS, B.PADS, B.CUTS)
    print(f'board_a.py: {len(no_spare)} leads with no spare hole, '
          f'{len(adjacent)} neighbouring lead pairs on different nets')
    for h, who, net in no_spare:
        print(f'   no spare   {who:6s} {h} ({net})')
    for h, who, net, p, who2, net2 in adjacent:
        print(f'   adjacent   {who} {h} ({net}) | {who2} {p} ({net2})')
    return 1 if (no_spare or adjacent) else 0


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""Place board A, and report what the placement's spare holes are.

Four rules beyond the checker's own, and the reason for each:

  * **the spare-hole rule.**  A link is a wire on the component side, soldered where it ends:
    at a lead, or in the free hole beside one.  A lead whose four neighbouring holes are all
    other leads, cuts or bodies cannot be reached by any wire, and no cut or link can make it
    reachable.  Three routing attempts failed on exactly this -- the placement scored zero
    geometric errors and was still unroutable -- so it is a placement rule, not a routing one.
  * **neighbouring leads of different parts share a net.**  Two leads in neighbouring holes on
    different nets is the one thing no cut can part without stranding one of them: a cut
    between them leaves each on its own hole with the strip gone.  A part's own two leads are
    the exception, and are how each part in the signal path couples to the next.
  * **the exits rule.**  Spare holes are not enough: a piece of a net can have a spare hole
    beside it and still be sealed, because the wire that would use it has to *get* there.  A
    socket's body is the case that matters -- a DIP-8's two pin columns are three holes apart
    and the checker will not let a wire cross the two holes between them, so a pin can only be
    reached from outside its own column, past the pin above and the pin below it.  On board A
    that sealed **U1.3**, the high-impedance IN_A node, with a spare hole beside it: the band
    of parts scored zero geometric errors and the board could not be wired, because one pin
    of U1 was behind its own socket.  So: for every net, every lead has a route to the rest
    of its net that stays on free holes and never crosses a body or another part's lead.
  * **the wires' own space.**  The exits rule asks the question a wire asks, so it is the same
    search the router runs: a hole a wire may run over is not a lead, not a body, not cut.

    python3 stripboard/_place.py            # what the rules say about board_a.py's placement
"""
import collections

import nets as NET
import stripboard as SB
import board_a as B

W, H = 18, 24


def body_of(kind, pts):
    """The holes a part's body covers, for a part laid along a strip or down a column."""
    out = set()
    if kind in ('r', 'd', 'film'):
        (x1, y1), (x2, y2) = pts[0], pts[1]
        if y1 == y2:
            out |= {(x, y1) for x in range(min(x1, x2) + 1, max(x1, x2))}
        else:
            out |= {(x1, y) for y in range(min(y1, y2) + 1, max(y1, y2))}
    return out


def circle(kind, pts):
    """The holes a radial electrolytic's can covers, from its footprint's diameter."""
    out = set()
    if kind.startswith('el'):
        r = SB.body_radius(kind)
        cx = sum(p[0] for p in pts) / 2
        cy = sum(p[1] for p in pts) / 2
        for x in range(W):
            for y in range(H):
                if (x, y) not in pts and (x - cx) ** 2 + (y - cy) ** 2 < r * r:
                    out.add((x, y))
    return out


def socket(kind, pts):
    """The socket's moulding: what the checker refuses to let a wire cross (rule 4)."""
    out = set()
    if kind == 'dip8':
        xs = sorted({p[0] for p in pts})
        ys = sorted({p[1] for p in pts})
        out |= {(x, y) for x in range(min(xs), max(xs) + 1)
                for y in range(min(ys), max(ys) + 1)}
    return out


def layout(parts, pads, cuts=()):
    """The board as a wire sees it: leads, pads, bodies, and what is free."""
    occ, owner, net_of = {}, {}, {}
    body = set()
    for ref, (kind, val, leads) in parts.items():
        pts = [h for h, _ in leads]
        for h, net in leads:
            occ[h] = (ref, net)
            owner[h] = ref
            net_of.setdefault(NET.net_key(net), []).append((h, f'{ref}.{leads.index((h, net)) + 1}'))
        body |= body_of(kind, pts) | circle(kind, pts) | socket(kind, pts)
    for lab, (h, net, _) in pads.items():
        occ[h] = (lab, net)
        owner[h] = lab
        net_of.setdefault(NET.net_key(net), []).append((h, f'pad {lab}'))
    return occ, owner, net_of, body, set(cuts)


def audit(parts, pads, cuts=()):
    """(leads with no spare hole, neighbouring leads of different parts on different nets)."""
    occ, owner, _, body, cuts = layout(parts, pads, cuts)

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


def exits(parts, pads, cuts=()):
    """Whether every piece of every net can be reached by a wire, or a report of what cannot.

    This is the question the router asks, asked before the routing is done -- and it is asked
    of the *layout data* and of the checker, not of a copy of either.  A wire runs over free
    holes (not a lead, not a body, not cut) and ends in a lead's hole or in the free hole
    beside a pad.  Two holes are already joined, with no wire at all, when the checker's
    `copper()` puts them on one piece of copper, so `copper()` is what joins them here too.

    A piece of a net with no free hole in it, and no path of free holes to another piece, is
    a piece **no wire can reach**: there is nowhere to solder the wire's end.  That is what
    the band search did not ask.  Two pieces on this board failed it: **C3.2**, the
    decoupler's ground lead in the top-right corner, and **CGND**, the codec's ground pad
    beside C6.  Each had its spare hole; each spare hole was walled off by a cut.
    """
    occ, _, net_of, body, cuts = layout(parts, pads, cuts)

    def free(p):
        return (0 <= p[0] < W and 0 <= p[1] < H and p not in occ and p not in cuts
                and p not in body)

    def beside(h):
        return [q for q in ((h[0], h[1] - 1), (h[0], h[1] + 1),
                            (h[0] - 1, h[1]), (h[0] + 1, h[1])) if free(q)]

    bridged = [(a, b) for ref, (kind, _, leads) in parts.items()
               for i, (a, na) in enumerate(leads) for b, nb in leads[i + 1:]
               if a[0] == b[0] and NET.same_net(na, nb)]
    bare = SB.copper(W, H, cuts, bridged)

    run = {(x, y) for x in range(W) for y in range(H) if free((x, y))}
    holes = set(run)
    for net, leads in net_of.items():
        holes |= {h for h, _ in leads}

    # The node a hole belongs to is the checker's own union-find -- but *canonicalised* first.
    # `copper()` returns a find() whose roots move as it is used, so the same piece of copper
    # answers with two different names at two different moments, and anything keyed by the raw
    # answer splits one piece into two.  That mistake made every net on this board look sealed,
    # twice, which is why the whole board is asked twice here and the second answer is kept:
    # after the first pass every parent points at its root, so the second is the same answer
    # for every hole of a piece.  `node` is the one place a hole's piece is named.
    for h in sorted(holes):
        bare(h)
    root = {h: bare(h) for h in sorted(holes)}

    def node(h):
        return root[h]

    parent = {}

    def find(h):
        parent.setdefault(h, h)
        while parent[h] != h:
            parent[h] = parent[parent[h]]
            h = parent[h]
        return h

    def union(a, b):
        parent[find(a)] = find(b)

    # a wire may run from a free hole to the free hole beside it ...
    for h in run:
        for q in beside(h):
            union(node(h), node(q))
    # ... and may end on a lead from any free hole beside it
    for net, leads in net_of.items():
        for h, who in leads:
            for q in beside(h):
                union(node(h), node(q))

    # The nets the copper carries, and which pieces of copper are clean for a wire end.
    piece_nets = collections.defaultdict(set)
    for h in sorted(holes):
        for n, ls in net_of.items():
            if any(lh == h for lh, _ in ls):
                piece_nets[root[h]].add(n)

    def reachable(h, net):
        """The free holes a wire from h may end in and still join `net` and nothing else.

        A wire ends in a lead's hole (that is the joint) or in a free hole whose piece of
        copper carries no net, or only this one.  This is rule 3b, asked before the routing.
        """
        out = []
        for q in beside(h):
            names = piece_nets[node(q)]
            if names and names != {net}:
                continue                 # the hole is already another net's strip
            out.append(q)
        return out

    def reachable_from(h, net):
        """Everywhere a wire started at h can get to: the BFS the router would run."""
        seen, dq = set(), collections.deque()
        for q in reachable(h, net):
            seen.add(q)
            dq.append(q)
        while dq:
            q = dq.popleft()
            for r in reachable(q, net):
                if r not in seen:
                    seen.add(r)
                    dq.append(r)
        return seen

    # Which net each piece of *free space* can be wired to.  A hole whose strip carries a net
    # can still be an end for that net -- the wire is soldered onto its own net's copper,
    # which is what rule 3b asks -- but not for any other net.
    out = {}
    for net, leads in sorted(net_of.items()):
        if not leads:
            continue                     # a rail like V3A3: a wire off the board and nothing else

        def ends(h):
            out = []
            for q in beside(h):
                names = piece_nets[node(q)]
                if not names or names == {net}:
                    out.append(q)
            return out

        # the free space each lead can be wired into, and what it can reach from there
        space = {}
        for h, _ in leads:
            seen, dq = set(), collections.deque()
            for q in ends(h):
                seen.add(q)
                dq.append(q)
            while dq:
                q = dq.popleft()
                for r in ends(q):
                    if r not in seen:
                        seen.add(r)
                        dq.append(r)
            space[h] = seen
        groups = []
        for h, _ in leads:
            for g in groups:
                if space[h] & g[1]:
                    g[0].add(h)
                    g[1] |= space[h]
                    break
            else:
                groups.append([{h}, set(space[h])])
        # and the leads the copper itself already joins to one another, by the checker
        joined = collections.defaultdict(set)
        for h, _ in leads:
            joined[bare(h)].add(h)
        if len(groups) == 1 and len(joined) == 1:
            continue
        why = (f'{len(joined)} piece(s) of copper, wired into {len(groups)} '
               f'disconnected space(s)')
        for hs, sp in groups:
            for h, who in leads:
                if h in hs:
                    out.setdefault(net, []).append((h, who, why))
    return out, run

    return out, run

    return out, run




def main():
    no_spare, adjacent = audit(B.PARTS, B.PADS, B.CUTS)
    print(f'board_a.py: {len(no_spare)} leads with no spare hole, '
          f'{len(adjacent)} neighbouring lead pairs on different nets')
    for h, who, net in no_spare:
        print(f'   no spare   {who:6s} {h} ({net})')
    for h, who, net, p, who2, net2 in adjacent:
        print(f'   adjacent   {who} {h} ({net}) | {who2} {p} ({net2})')
    stranded, run = exits(B.PARTS, B.PADS, B.CUTS)
    print(f'\nexits rule: {sum(len(v) for v in stranded.values())} lead(s) with no route '
          f'into the free space ({len(run)} holes free)')
    for net, v in sorted(stranded.items()):
        for h, who, why in v:
            print(f'   no exit    {who:8s} {h} ({net}): {why}')
    return 1 if (no_spare or adjacent or stranded) else 0


if __name__ == '__main__':
    raise SystemExit(main())

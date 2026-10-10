#!/usr/bin/env python3
"""Route board A first and cut only where the routing demands it.

Tonight's lesson in one line: cuts and links are not separable stages.  Every cut made to stop
a short removes a route, and only routing can say which -- so this routes and cuts together.

For each net, in order of constraint (IN_A first: it is short and high-impedance, then the
ground return, then the low-impedance trunk), it places the links the net needs to become one
piece.  A row is cut only where a *different* net would otherwise be joined by the copper this
routing is using -- not at every net boundary in the row.

The checker is the oracle throughout: **every question is asked of `stripboard.copper`**, the
checker's own union-find -- "are these two holes joined?" -- and never of a copy of it.  Twice
now a hand-rolled copy answered a slightly different question from the checker, and the cuts
derived from it were wrong in the same way.

A link is a wire on the component side, so it is a *straight run*: from a hole, along a row or
a column, to another hole.  A route that has to turn is two links meeting at the corner, and
the corner is a soldered joint.  `JOINTS` below is the one rule this needs that the checker
does not yet have.

Prints the CUTS and LINKS; board_a.py is edited from what it says.

    python3 stripboard/_route.py
"""
import collections
import heapq

import nets as NET
import stripboard as SB
import board_a as B

W, H = B.W, B.H

# The order the nets are routed in, and why: the high-impedance input first (it must be the
# shortest run the board allows), then the input network that feeds it, then the ground return
# (every net that needs a return runs to *it*), then the low-impedance trunk -- the codec's
# outputs to the jacks, which may go the long way -- and the supply last, because a supply
# wire only has to get from one edge to a pin and the other nets are what need the corridors.
PRIORITY = ['IN_A', 'IN_B', 'IN_RAW', 'GND_A', 'LIN1', 'U1B', 'HPL', 'HPR',
            'OUT_L_N', 'OUT_R_N', 'OUT_L', 'OUT_R', 'BIAS', 'BIAS_MID', 'VF']

DIRS = {'N': (0, -1), 'S': (0, 1), 'W': (-1, 0), 'E': (1, 0)}


class Board:
    """Board A as it stands, with the checker's union-find as the only connectivity."""

    def __init__(self, cuts=None, links=None):
        self.who = {}
        self.leads, self.pads = collections.defaultdict(list), set()
        # what a hole's *owner* is: a lead or a pad.  Which net a hole is on is a different
        # question, and it is the checker's -- see `net_at` -- because a free hole's strip can
        # carry a net that no lead sits on.
        self.owner = {}
        for ref, (kind, val, ls) in B.PARTS.items():
            for i, (h, net) in enumerate(ls):
                if h in self.owner:
                    raise SystemExit(f'{ref}.{i + 1} and {self.owner[h]} share hole {h}')
                self.owner[h] = NET.net_key(net)
                self.who[h] = f'{ref}.{i + 1}'
                self.leads[NET.net_key(net)].append(h)
        for lab, (h, net, _) in B.PADS.items():
            self.owner[h] = NET.net_key(net)
            self.who[h] = f'pad {lab}'
            self.pads.add(h)
            self.leads[NET.net_key(net)].append(h)
        self.lead_holes = set(self.owner)
        self.body = set()
        for ref, (kind, val, ls) in B.PARTS.items():
            pts = [h for h, _ in ls]
            if kind in ('r', 'd', 'film'):
                (x1, y1), (x2, y2) = pts
                if y1 == y2:
                    self.body |= {(x, y1) for x in range(min(x1, x2) + 1, max(x1, x2))}
                else:
                    self.body |= {(x1, y) for y in range(min(y1, y2) + 1, max(y1, y2))}
            elif kind.startswith('el'):
                r = SB.body_radius(kind)
                cx, cy = sum(p[0] for p in pts) / 2, sum(p[1] for p in pts) / 2
                self.body |= {(x, y) for x in range(W) for y in range(H)
                              if (x, y) not in pts and (x - cx) ** 2 + (y - cy) ** 2 < r * r}
            elif kind == 'dip8':
                xs = {p[0] for p in pts}
                ys = {p[1] for p in pts}
                self.body |= {(x, y) for x in range(min(xs), max(xs) + 1)
                              for y in range(min(ys), max(ys) + 1)}
        self.cuts = set(B.CUTS if cuts is None else cuts)
        self.links = list(B.LINKS if links is None else links)
        self.spans, self.ends = {}, set()
        for a, b in self.links:
            for h in self.span(a, b):
                self.spans[h] = self.spans.get(h, []) + [(a, b)]
            self.ends |= {a, b}
        self.bridged = [(a, b) for ref, (kind, _, ls) in B.PARTS.items()
                        for i, (a, na) in enumerate(ls) for b, nb in ls[i + 1:]
                        if a[0] == b[0] and NET.same_net(na, nb)]

    def name(self, h):
        """What is in a hole, for the log: a lead, a pad, or just the hole."""
        return self.who.get(h, f'hole {h}')

    # -- the checker's two questions, and only these --------------------------------
    def find(self, links=None):
        """`stripboard.copper` -- the checker's union-find, links included."""
        return SB.copper(W, H, self.cuts, list(self.links if links is None else links)
                         + self.bridged)

    def bare(self, links=None):
        """The same union-find with *no* links: what the copper carries by itself."""
        return SB.copper(W, H, self.cuts, self.bridged)

    def broken(self, a, b):
        return SB.broken(self.cuts, a, b)

    def strip_of(self, h):
        """The piece of strip a hole sits on, cut at every break -- a cut *at* a hole and a
        cut *between* two holes both stop it, which the checker's between-holes cuts make easy
        to forget (they are at x + 0.5, and a test for `h in cuts` does not see them)."""
        if h in self.cuts:
            return [h]
        x, y = h
        lo = x
        while lo - 1 >= 0 and not self.broken((lo - 1, y), (lo, y)):
            lo -= 1
        hi = x
        while hi + 1 < W and not self.broken((hi, y), (hi + 1, y)):
            hi += 1
        return [(xx, y) for xx in range(lo, hi + 1)]

    def net_at(self, h, links=None):
        """The net the copper at `h` carries, asked of the checker's own union-find.

        None when the copper carries no net at all.  More than one answer means the copper is
        already carrying two nets, which is a short the checker reports; this returns the first
        so the caller can still see what it is looking at.
        """
        names = self.nets_at(h, links)
        if len(names) != 1:
            return None
        return next(iter(names))

    def nets_at(self, h, links=None):
        """Every net the copper at `h` carries, by the checker's own union-find."""
        bare = self.bare(links)
        names = set()
        for ref, (kind, _, ls) in B.PARTS.items():
            for lh, net in ls:
                if bare(lh) == bare(h):
                    names.add(NET.net_key(net))
        for lab, (ph, net, _) in B.PADS.items():
            if bare(ph) == bare(h):
                names.add(NET.net_key(net))
        return names

    # -- a link's geometry ---------------------------------------------------------
    def span(self, a, b):
        """The holes a wire from a to b runs over: the checker's own `_span`, not a copy."""
        return SB._span(a, b)

    def link_ok(self, p, q, net):
        """Why a wire from p to q may not be soldered, or None if it may.

        A route that has to turn is two straight wires soldered at the corner, and the corner
        is a *hole*: no lead, no pad, and no other net's copper, because a wire's end joins
        whatever the hole's piece of copper already carries (rule 3b).  The wires the board
        already has count as part of that copper, which is why a route is checked with its own
        links in place: a corner is legal when the wires meeting there are one net, and that
        cannot be asked with the corner still bare.
        """
        if p == q or (p[0] != q[0] and p[1] != q[1]):
            return 'not a straight run'
        run = self.span(p, q)
        if len(run) < 2:
            return 'no run'
        for h in run[1:-1]:
            if h in self.cuts:
                return f'{h} is cut'
            # the wire may pass over nothing at all -- and its *own* span is not an obstacle,
            # because it is placed before this check so that its corners can be judged
            under = [s for s in self.spans.get(h, []) if s != (p, q)]
            if under:
                return f'{h} is under {under[0]}'
            if h in self.lead_holes or h in self.body:
                return f'{h} is {self.who.get(h, "a body")}'
        for e in (p, q):
            if e in self.cuts:
                return f'end {e} is cut'
            if e in self.pads:
                return f'end {e} is a pad hole'
            names = self.nets_at(e)
            if not names <= {net}:
                return f'end {e} is on {sorted(names) or "nothing"}'
        return None

    def segments(self, path):
        """A run of holes, broken at its turns: the straight wires a route is made of."""
        segs, start, d = [], path[0], None
        for i in range(1, len(path)):
            d2 = (path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1])
            if d is not None and d2 != d:
                segs.append((start, path[i - 1]))
                start = path[i - 1]
            d = d2
        segs.append((start, path[-1]))
        return [(p, q) for p, q in segs if p != q]

    def path_ok(self, path, net):
        """Why the wire a route needs may not be built, or None if it may.

        The path's own links are placed before the check and taken back after it, so a corner
        is judged with the wires that will meet in it: a corner is a joint, and a joint is only
        legal when the wires in it are one net.
        """
        segs = self.segments(path)
        for s in segs:
            self.add(*s)
        why = None
        for p, q in segs:
            why = self.link_ok(p, q, net)
            if why:
                why = f'{p}-{q}: {why}'
                break
        for s in segs:
            self.remove(*s)
        return why

    def cost(self, run):
        """A wire's cost: length, plus what it costs to have a solder joint in the middle."""
        return len(run)

    def add(self, p, q):
        """Put a wire on the board: it covers the holes it runs over and ends in its two."""
        self.links.append((p, q))
        for h in self.span(p, q):
            self.spans.setdefault(h, []).append((p, q))
        self.ends |= {p, q}

    def remove(self, p, q):
        """Take the wire back off, exactly as `add` put it there."""
        self.links.remove((p, q))
        for h in self.span(p, q):
            self.spans[h] = [s for s in self.spans[h] if s != (p, q)]
            if not self.spans[h]:
                del self.spans[h]
        for e in (p, q):
            if not any(e in s for s in self.links):
                self.ends.discard(e)

    def pieces(self, links=None):
        """{net: {root: [holes]}} -- by the checker's union-find, not a hand-rolled copy."""
        find = self.find(links)
        out = collections.defaultdict(lambda: collections.defaultdict(list))
        for net, holes in self.leads.items():
            for h in holes:
                out[net][find(h)].append(h)
        return out

    def joins(self, links=None):
        """Roots that carry more than one net: a short, by the checker's own union-find."""
        find = self.find(links)
        roots = collections.defaultdict(lambda: collections.defaultdict(list))
        for net, holes in self.leads.items():
            for h in holes:
                roots[find(h)][net].append(h)
        return {r: dict(d) for r, d in roots.items() if len(d) > 1}

    def links_for(self, net, src, dst):
        """The fewest-bend run of wires from src (a hole) to one of dst (holes on `net`).

        Straight runs are preferred -- a route that turns is a joint -- so the search is a
        two-label Dijkstra: (bends, length) lexicographically, over the holes a wire may run
        through.  Returns the holes of the path, src and the goal included.
        """
        if not dst:
            return None
        goal = set(dst)
        # A pad hole is where a component's lead is soldered, so a wire does not end *in* it:
        # it ends in the free hole beside it, and that is the pad's escape.  The holes a wire
        # may therefore end in -- the goals, plus the hole beside a pad of this net.
        pad_of = {h: NET.net_key(net) for h, net, _ in B.PADS.values()}
        endable = set(goal)
        for p in self.pads:
            if pad_of.get(p) != net:
                continue
            for q in ((p[0], p[1] - 1), (p[0], p[1] + 1), (p[0] - 1, p[1]), (p[0] + 1, p[1])):
                if 0 <= q[0] < W and 0 <= q[1] < H:
                    endable.add(q)
        if src in endable:
            return [src]
        # What a wire may run over: not a lead, not a body, not a cut, not another wire.
        free = set()
        for y in range(H):
            for x in range(W):
                h = (x, y)
                if h in self.body or h in self.spans or h in self.cuts:
                    continue
                if h in self.lead_holes and h != src:
                    continue
                free.add(h)
        open_holes = free | (goal & self.lead_holes)

        def neighbours(h):
            return [q for q in ((h[0], h[1] - 1), (h[0], h[1] + 1),
                                (h[0] - 1, h[1]), (h[0] + 1, h[1]))
                    if q in open_holes or q in endable]

        # distances to the endable set, ignoring bends: the tie-break
        INF = 10 ** 6
        dist = {h: 0 for h in endable & open_holes}
        dq = collections.deque(dist)
        while dq:
            h = dq.popleft()
            for q in neighbours(h):
                if q not in dist:
                    dist[q] = dist[h] + 1
                    dq.append(q)
        start = (src, None)
        seen = {start: (0, 0)}
        prev = {}
        heap = [(0, dist.get(src, INF), 0, src, None)]
        while heap:
            bends, _, length, h, d = heapq.heappop(heap)
            if seen.get((h, d)) != (bends, length):
                continue
            if h in endable and h != src:
                path, cur = [h], (h, d)
                while cur != start:
                    cur = prev[cur]
                    path.append(cur[0])
                return list(reversed(path))
            for d2, (dx, dy) in DIRS.items():
                nb = (h[0] + dx, h[1] + dy)
                if not (0 <= nb[0] < W and 0 <= nb[1] < H):
                    continue
                if nb not in open_holes:
                    continue
                lab = (bends + (0 if (d is None or d == d2) else 1), length + 1)
                key = (nb, d2)
                if key not in seen or lab < seen[key]:
                    seen[key] = lab
                    prev[key] = (h, d)
                    heapq.heappush(heap, (lab[0], dist.get(nb, INF), lab[1], nb, d2))
        return None


def main():
    bd = Board()
    planner = Board()          # the same placement, but with no links at all
    print('=== as it stands ===')
    for net, d in sorted(bd.pieces().items()):
        if len(d) > 1:
            print(f'  {net:9s} {len(d)} pieces: ' +
                  '  '.join(f'{{{",".join(bd.name(h) for h in sorted(v))}}}'
                            for _, v in sorted(d.items())))
    print()
    added = []
    for net in PRIORITY:
        for _ in range(40):
            pieces = planner.pieces(planner.links)
            mine = pieces.get(net, {})
            if len(mine) < 2:
                break
            roots = sorted(mine, key=lambda r: -len(mine[r]))
            src, dst = mine[roots[0]][0], [h for r in roots[1:] for h in mine[r]]
            path = planner.links_for(net, src, dst)
            if path is None:
                print(f'  {net}: no route from {planner.name(src)} {src} to the other '
                      f'{len(roots) - 1} piece(s)')
                break
            segs = planner.segments(path)
            why = planner.path_ok(path, net)
            if why:
                print(f'  {net}: route {path[0]} -> {path[-1]} has {len(segs)} link(s), '
                      f'refused: {why}')
                break
            for p, q in segs:
                planner.add(p, q)
                added.append((p, q, net))
            print(f'  {net}: {[f"{p}-{q}" for p, q in segs]}  '
                  f'({planner.name(path[0])} -> {planner.name(path[-1])})')
    print()
    print('LINKS:')
    for p, q, net in added:
        print(f'    ({p}, {q}),   # {net}')
    print()
    left = {n: len(v) for n, v in planner.pieces(planner.links).items() if len(v) > 1}
    print('still split (planned, no cuts changed):', left if left else 'NONE -- CLOSED')
    print('shorts the planner would make:',
          {str(k): v for k, v in planner.joins(planner.links).items()} or 'none')
    print()
    print('CUTS (as board_a.py has them now):')
    print('CUTS = {')
    for c in sorted(planner.cuts, key=lambda c: (c[1], c[0])):
        print(f'    {c},')
    print('}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""Read a scripts/measure-coexistence run: the arms, what they cost, and the factor they imply.

Usage: scripts/src/coexistence-read.py <run dir> [--json]

The run dir is what measure-coexistence wrote (its `out/` holds one subject log, one neighbour log
per loaded core, perf counters and a /proc/stat pair per arm). Nothing here re-reads the host; a run
is readable for good from the directory alone.

Three tables come out:

  the arms      every arm's n, p50, p99 and verdict, with the per-copy figure, and -- for the
                `fixed` arms, which hold n constant -- what k cores busy did to the same work.
  the cores     per core over each fixed arm's perf window: how busy it was, the clock it really
                ran at (aperf/mperf x TSC, not sysfs), its IPC, and its L3 miss rate. This is what
                says whether a slowdown is the clock or the cache.
  the factors   n(k=1) / n(k) off the `bisect` arms: the multiplier a table's `coexistence` block
                would carry, in the same form as vip's (headroom over the knee).

A row is only printed from a file that exists; a missing arm says so rather than being skipped
quietly, because an arm that did not run is the one thing a reader must not mistake for a result.
"""

import json
import re
import sys
from pathlib import Path

DEADLINE_US = 1333.3333333333333


def arms_file(run: Path):
    """The arms as declared: (mode, label, k, neighbour_n, start, max, unit args)."""
    out = []
    path = run / "arms"
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 7:
            continue
        mode, label, k, nbr, start, mx = parts[:6]
        out.append(dict(mode=mode, label=label, k=int(k), nbr=int(nbr),
                        start=int(start), max=int(mx), unit="|".join(parts[6:])))
    return out


def subject(run: Path, label: str):
    """The subject's own report for one arm: its fragment, its curve and its fitted n."""
    hits = sorted((run / "out").glob(f"{label}-c*.txt")) if (run / "out").exists() else []
    hits = [h for h in hits if "-nbr-c" not in h.name]
    if not hits:
        return None
    text = hits[0].read_text()
    frag = None
    for line in text.splitlines():
        if line.startswith("fragment: "):
            try:
                frag = json.loads(line[len("fragment: "):])
            except json.JSONDecodeError:
                frag = None
    found = None
    m = re.search(r"^n = (\d+):", text, re.M)
    if m:
        found = int(m.group(1))
    unit = None
    m = re.search(r"^unit:\s+(\S+)", text, re.M)
    if m:
        unit = m.group(1)
    return dict(file=hits[0].name, fragment=frag, found=found, unit=unit,
                curve=(frag or {}).get("curve") or [],
                capped="was reached without a miss" in text)


def busy(run: Path, label: str):
    """Per-core busy percentage across the subject's window, from the /proc/stat pair."""
    before, after = run / "out" / f"{label}.cpustat.before", run / "out" / f"{label}.cpustat.after"
    if not (before.exists() and after.exists()):
        return {}

    def parse(p):
        d = {}
        for line in p.read_text().split("\n"):
            bits = line.split()
            if len(bits) == 3:
                d[bits[0]] = (int(bits[1]), int(bits[2]))
        return d

    a, b = parse(before), parse(after)
    out = {}
    for core in a:
        if core not in b:
            continue
        db, dt = b[core][0] - a[core][0], b[core][1] - a[core][1]
        out[core] = 100.0 * db / dt if dt else 0.0
    return out


def perf(run: Path, label: str):
    """Per-core counters over the perf window: clock, IPC and L3 miss rate."""
    path = run / "out" / f"{label}.perf"
    if not path.exists():
        return {}
    raw = {}
    for line in path.read_text().splitlines():
        if not line.startswith("CPU"):
            continue
        bits = line.split(",")
        if len(bits) < 4:
            continue
        core, value, event = bits[0], bits[1], bits[3]
        try:
            raw.setdefault(core.lower().replace("cpu", "cpu"), {})[event] = float(value)
        except ValueError:
            continue
    out = {}
    for core, ev in raw.items():
        aperf, mperf, tsc = ev.get("msr/aperf/"), ev.get("msr/mperf/"), ev.get("msr/tsc/")
        cycles, instructions = ev.get("cycles"), ev.get("instructions")
        refs, misses = ev.get("cache-references"), ev.get("cache-misses")
        row = {}
        # aperf/mperf is the frequency while the core was *running*, which is the one that matters:
        # an idle core's sysfs figure says nothing about the speed the work ran at.
        if aperf and mperf and tsc:
            row["aperf_over_mperf"] = aperf / mperf
        if cycles and instructions:
            row["ipc"] = instructions / cycles
        if refs and misses:
            row["l3_miss_pct"] = 100.0 * misses / refs
        if instructions and misses:
            row["l3_misses_per_kinsn"] = 1000.0 * misses / instructions
        row["cycles"] = cycles
        row["instructions"] = instructions
        row["tsc"] = tsc
        row["aperf"] = aperf
        row["mperf"] = mperf
        out[core] = row
    return out


def window_seconds(run: Path, label: str):
    """The perf window's length, as the run's own log recorded it."""
    log = run / "out" / "session.log"
    if not log.exists():
        return None
    want = False
    for line in log.read_text().splitlines():
        if f" {label} " in line and " ARM " in line:
            want = True
        elif want and "perf window" in line:
            m = re.search(r"opens, (\d+)s", line)
            return int(m.group(1)) if m else None
        elif want and line.rstrip().endswith("DONE"):
            return None
    return None


def fmt(value, how):
    """A number the way the tables want it, or `--` where there is nothing to print."""
    return how.format(value) if value else "--"


def ghz(row, seconds):
    """Real clock in GHz: (aperf/mperf) x TSC rate, the TSC rate taken over the same window."""
    if not row or not seconds or not row.get("tsc") or not row.get("aperf_over_mperf"):
        return None
    tsc_hz = row["tsc"] / seconds
    return row["aperf_over_mperf"] * tsc_hz / 1e9


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    run = Path(argv[0])
    as_json = "--json" in argv
    if not run.exists():
        print(f"coexistence-read: no run directory {run}", file=sys.stderr)
        return 2

    declared = arms_file(run)
    if not declared:
        print(f"coexistence-read: {run} has no arms file", file=sys.stderr)
        return 2

    rows = []
    for arm in declared:
        s = subject(run, arm["label"])
        b = busy(run, arm["label"])
        p = perf(run, arm["label"])
        secs = window_seconds(run, arm["label"])
        point = None
        if s and s["curve"]:
            # For a fixed arm there is one point; for a bisect, the point at the fitted n.
            want = s["found"] if arm["mode"] == "bisect" else arm["max"]
            for c in s["curve"]:
                if c["n"] == want:
                    point = c
            point = point or s["curve"][0]
        rows.append(dict(arm=arm, subject=s, busy=b, perf=p, window=secs, point=point))

    if as_json:
        def plain(r):
            return dict(label=r["arm"]["label"], mode=r["arm"]["mode"], k=r["arm"]["k"],
                        neighbour_n=r["arm"]["nbr"], unit=(r["subject"] or {}).get("unit"),
                        found=(r["subject"] or {}).get("found"),
                        capped=(r["subject"] or {}).get("capped"),
                        point=r["point"], busy=r["busy"], window_s=r["window"],
                        cores={c: dict(ghz=ghz(v, r["window"]), ipc=v.get("ipc"),
                                       l3_miss_pct=v.get("l3_miss_pct"),
                                       l3_misses_per_kinsn=v.get("l3_misses_per_kinsn"))
                               for c, v in sorted(r["perf"].items())})
        print(json.dumps([plain(r) for r in rows], indent=1))
        return 0

    print(f"== the arms ({run})")
    print(f"{'arm':<16}{'k':>2} {'n':>4} {'p50 us':>9} {'p99 us':>9} {'p99 %dl':>8} "
          f"{'over':>5} {'per copy':>9}  verdict")
    base = {}
    for r in rows:
        a, s, pt = r["arm"], r["subject"], r["point"]
        if s is None:
            print(f"{a['label']:<16}{a['k']:>2} {'--':>4} {'(this arm produced no output)':>46}")
            continue
        if pt is None:
            print(f"{a['label']:<16}{a['k']:>2} {'--':>4} {'(no curve in the subject log)':>46}")
            continue
        per = pt["p50"] / pt["n"] if pt["n"] else 0.0
        verdict = "fits" if pt["pass"] else "MISSES"
        if s["capped"] and a["mode"] == "bisect":
            verdict += " (at_most)"
        print(f"{a['label']:<16}{a['k']:>2} {pt['n']:>4} {pt['p50']:>9.1f} {pt['p99']:>9.1f} "
              f"{100 * pt['p99'] / DEADLINE_US:>8.1f} {pt['overruns']:>5} {per:>9.1f}  {verdict}")

    # The fixed arms hold n, so their p50s are the same work and compare directly.
    print()
    print("== the same work, k cores busy (fixed arms, against that unit's k=1)")
    for r in rows:
        a, pt = r["arm"], r["point"]
        if a["mode"] != "fixed" or pt is None:
            continue
        unit_key = (a["label"].rsplit("-k", 1)[0], pt["n"])
        if a["k"] == 1:
            base[unit_key] = pt
    print(f"{'arm':<16}{'k':>2} {'p50 us':>9} {'vs k=1':>8} {'p99 us':>9} {'vs k=1':>8} "
          f"{'clock GHz':>10} {'IPC':>5} {'L3 miss %':>10} {'miss/kinsn':>11}")
    for r in rows:
        a, pt, pf = r["arm"], r["point"], r["perf"]
        if a["mode"] != "fixed" or pt is None:
            continue
        unit_key = (a["label"].rsplit("-k", 1)[0], pt["n"])
        b = base.get(unit_key)
        d50 = f"{100 * (pt['p50'] / b['p50'] - 1):+.1f}%" if b else "--"
        d99 = f"{100 * (pt['p99'] / b['p99'] - 1):+.1f}%" if b else "--"
        me = pf.get(f"cpu{_subject_cpu(r)}") or {}
        clock = fmt(ghz(me, r["window"]), "{:.3f}")
        ipc = fmt(me.get("ipc"), "{:.2f}")
        miss = fmt(me.get("l3_miss_pct"), "{:.2f}")
        per_kinsn = fmt(me.get("l3_misses_per_kinsn"), "{:.3f}")
        print(f"{a['label']:<16}{a['k']:>2} {pt['p50']:>9.1f} {d50:>8} {pt['p99']:>9.1f} {d99:>8} "
              f"{clock:>10} {ipc:>5} {miss:>10} {per_kinsn:>11}")

    print()
    print("== every core over each fixed arm's window (busy from /proc/stat, clock from aperf/mperf)")
    for r in rows:
        a = r["arm"]
        if a["mode"] != "fixed" or not r["perf"]:
            continue
        print(f"  {a['label']} (k={a['k']}, neighbours at n={a['nbr']}, window {r['window']}s)")
        for core in sorted(r["perf"], key=lambda c: int(c[3:])):
            v = r["perf"][core]
            clock = fmt(ghz(v, r["window"]), "{:.3f}")
            ipc = fmt(v.get("ipc"), "{:.2f}")
            miss = fmt(v.get("l3_miss_pct"), "{:.2f}%")
            print(f"    {core:<6} busy {r['busy'].get(core, float('nan')):>5.1f}%  "
                  f"clock {clock:>6} GHz  IPC {ipc:>5}  L3 miss {miss:>7}")

    # The factors, off the bisect arms: how much less fits when the neighbours are there.
    print()
    print("== the factor a coexistence block would carry (bisect arms)")
    fits = {}
    for r in rows:
        a, s = r["arm"], r["subject"]
        if a["mode"] != "bisect" or s is None or s["found"] is None:
            continue
        unit = a["label"].rsplit("-k", 1)[0]
        fits.setdefault(unit, {})[a["k"]] = dict(n=s["found"], capped=s["capped"])
    if not fits:
        print("   (no bisect arm produced a fitted n)")
    for unit, by_k in sorted(fits.items()):
        one = by_k.get(1)
        print(f"  {unit}: " + ", ".join(f"k={k} n={v['n']}" + ("*" if v["capped"] else "")
                                       for k, v in sorted(by_k.items())))
        if not one:
            print("    no k=1 arm, so no factor can be read off this unit here")
            continue
        for k, v in sorted(by_k.items()):
            if k == 1:
                continue
            f = one["n"] / v["n"]
            print(f"    k={k}: {one['n']} fits alone, {v['n']} with {k - 1} neighbour(s) "
                  f"-> factor {f:.3f}  (cost/core {1 / one['n']:.4g} -> {1 / v['n']:.4g})")
    print("   * at_most: the bisection hit its --max without a miss, so n is a floor and the")
    print("     factor read against it is a lower bound on the real one.")
    return 0


def _subject_cpu(row):
    """The subject's cpu, from the log file's own name (<label>-c<cpu>.txt)."""
    name = (row["subject"] or {}).get("file") or ""
    m = re.search(r"-c(\d+)\.txt$", name)
    return int(m.group(1)) if m else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

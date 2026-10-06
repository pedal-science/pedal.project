#!/usr/bin/env python3
"""Turn the campaign's results.jsonl into the report's tables, in CPU % and nothing else.

The measurement is `cpu_ticks`: the namchaind process's own utime+stime, every thread included, read
from /proc/<pid>/stat immediately before the window and immediately after. One derived number is what
the report talks about:

  CPU% = ticks / CLK_TCK / seconds * 100, as a share of **one** core. The board has four.

Ticks and milliseconds-per-second are deliberately not tabulated: they are the arithmetic behind the
percentage, they are in `results.jsonl` for anybody who wants to check it, and a table of three units
for one measurement invites the reader to compare the wrong two. The charts are `charts.py`.

Usage:
  analyse.py results.jsonl [--clk-tck 100] [--only 19,20,21,22,23] [--series heavy]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("results")
parser.add_argument("--clk-tck", type=int, default=100)
parser.add_argument("--only", default="", help="condition numbers, comma separated")
parser.add_argument("--series", default="", help="one series only")
args = parser.parse_args()

CLK = args.clk_tck
ONLY = {int(n) for n in args.only.split(",") if n.strip()}

SERIES_TITLE = {
    "minimal": "Series A — a minimal rig (input → output, 2 nodes)",
    "heavy": "Series B — a 32-gain rig (34 nodes)",
}
SERIES_NOTE = {
    "minimal": "The chain runs and the converters are real, so this series is the cost of *answering*: "
               "the levels JSON built and sent once per poll. There is almost nothing inside the rig "
               "to measure.",
    "heavy": "The same conditions over a rig whose own cost is one multiply per node, so what the "
             "conditions differ by is dominated by the probes rather than by the audio.",
}
# The five ways of measuring this campaign compares, in the order the report discusses them.
MODE_ORDER = ["off", "on", "on-rate", "on-sparse", "on-rate-sparse"]
MODE_LABEL = {
    "off": "`--no-levels`",
    "on": "measuring (default)",
    "on-rate": "measuring, `--levels-rate-hz 1`",
    "on-sparse": "measuring, `--levels-first-frame`",
    "on-rate-sparse": "both finer switches",
}


def load(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def pct(row: dict) -> float:
    return row["cpu_ticks"] / CLK / row["seconds"] * 100.0


def mode_key(row: dict) -> str:
    if row.get("levels") == "off":
        return "off"
    rate = row.get("rate_hz") or 0
    sparse = bool(row.get("first_frame"))
    if rate and sparse:
        return "on-rate-sparse"
    if rate:
        return "on-rate"
    if sparse:
        return "on-sparse"
    return "on"


def baseline(all_rows: list[dict], series: str) -> dict | None:
    """The series' `--no-levels` row with nothing polling: what this engine costs unobserved.

    Looked up in the **whole** run, not in whatever subset is being printed, so a filtered view
    ("just conditions 19-23, please") still gets its deltas against the right baseline instead of
    silently losing them because the baseline row was filtered out.
    """
    for row in all_rows:
        if row.get("series") == series and mode_key(row) == "off" and row.get("hz") is None:
            return row
    return None


def table(rows: list[dict], all_rows: list[dict], series: str) -> None:
    base = baseline(all_rows, series)
    print()
    print(f"### {SERIES_TITLE.get(series, series)}")
    print()
    print(SERIES_NOTE.get(series, ""))
    print()
    print("| Condition | Mode | Client polling | Window | CPU (one core) | vs `--no-levels` |")
    print("|---|---|---|---|---|---|")
    # The comparison every row is quoted against is the same one: this series, unobserved. A row that
    # *is* that baseline says so; every other row says what it costs over it, whoever else is polling.
    # Comparing a row against a different row of the same table -- "1 Hz against nothing polling" --
    # would make the column mean something different on every line.
    for row in sorted(rows, key=lambda r: r["condition"]):
        hz = row.get("hz")
        hz_text = "—" if hz is None else f"{hz:g} Hz"
        if base is None:
            delta = "—"
        elif row is base:
            delta = "baseline"
        else:
            delta = f"{pct(row) - pct(base):+.2f} pp"
        print(f"| {row['condition']} | {MODE_LABEL[mode_key(row)]} | {hz_text} | "
              f"{row['seconds']:g} s | **{pct(row):.2f}%** | {delta} |")
    print()
    if base is not None:
        print(f"Baseline for this series: **{pct(base):.2f}%** of one core "
              f"(`--no-levels`, nothing polling).")
        print()
    for row in sorted(rows, key=lambda r: r["condition"]):
        if row.get("errors"):
            print(f"  ! condition {row['condition']}: {row['errors']} client errors")
        if row.get("empty_windows"):
            print(f"  ! condition {row['condition']}: {row['empty_windows']} empty windows of "
                  f"{row['ticks']} reads")
        if row.get("max_node_frames"):
            print(f"  · condition {row['condition']}: the largest window held "
                  f"{row['max_node_frames']} frames")
        cache = row.get("cache_last") or {}
        if cache:
            print(f"  · condition {row['condition']}: reads {cache.get('hits',0)} cache / "
                  f"{cache.get('misses',0)} drained, {cache.get('drains',0)} drains in all")


def modes_table(rows: list[dict], all_rows: list[dict], series: str) -> None:
    """The ways of measuring side by side, over the conditions that differ only in the mode.

    That is the 1 Hz conditions in series B (19-23): the client rate is held constant so the only
    thing varying is how much the engine measures. Series A never had the finer switches, so its
    table is the two modes it does have, at their slowest client rate -- the one closest to "nobody
    is polling", which is the comparison the row is for.
    """
    base = baseline(all_rows, series)
    if base is None:
        return
    at_one_hz = [r for r in rows if r.get("hz") == 1]
    if len({mode_key(r) for r in at_one_hz}) >= 3:
        subset, rate_text = at_one_hz, "1 Hz"
    else:
        subset, rate_text = ([base] if base in rows else []), "nothing polling"
        for row in rows:
            if row.get("hz") == 1 and row not in subset:
                subset.append(row)

    print()
    print(f"### What each way of measuring costs, client polling at {rate_text}")
    print()
    print("| Mode | CPU (one core) | vs `--no-levels` | What it costs the render path |")
    print("|---|---|---|---|")
    for mode in MODE_ORDER:
        row = next((r for r in subset if mode_key(r) == mode), None)
        if row is None:
            continue
        cost = {
            "off": "nothing — there are no probes",
            "on": "a fold per sample, per probe",
            "on-rate": "unchanged: this switch only limits the *reading*",
            "on-sparse": "a fold per period instead of per sample",
            "on-rate-sparse": "a fold per period, read once a second",
        }[mode]
        delta = "—" if row is base else f"{pct(row) - pct(base):+.2f} pp"
        print(f"| {MODE_LABEL[mode]} | **{pct(row):.2f}%** | {delta} | {cost} |")
    print()


def main() -> None:
    every = load(Path(args.results))
    # Baselines come from the whole run and the tables from whatever subset was asked for: a view of
    # "just conditions 19-23" must still quote its deltas against the series' unobserved cost, which
    # is condition 10 and would otherwise have been filtered away with the rest.
    rows = [r for r in every if r.get("condition") in ONLY] if ONLY else every
    all_ok = [r for r in every if "cpu_ticks" in r]
    ok = [r for r in rows if "cpu_ticks" in r]
    failed = [r for r in rows if "cpu_ticks" not in r]
    if args.series:
        ok = [r for r in ok if r.get("series") == args.series]
        failed = [r for r in failed if r.get("series") == args.series]

    # One table per series, in the order the campaign ran them.
    series_seen = list(dict.fromkeys(r.get("series") for r in ok))
    for series in series_seen:
        table([r for r in ok if r.get("series") == series], all_ok, series)
        modes_table([r for r in ok if r.get("series") == series], all_ok, series)

    if failed:
        print()
        print("Conditions that never became ready:")
        for row in failed:
            print(f"  - {row.get('condition')}: {row.get('label')}: {row.get('error')}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Turn the campaign's results.jsonl into the report's tables.

The measurement is `cpu_ticks`: the namchaind process's own utime+stime, every thread included,
read from /proc/<pid>/stat immediately before the window and immediately after. Two derived numbers
are what the report talks about:

  CPU%      = ticks / CLK_TCK / seconds * 100, as a share of **one** core. The Pi 5 has four.
  CPU ms/s  = ticks / CLK_TCK / seconds * 1000. The same fact without a percentage, for anybody who
              would rather not read a number that can exceed 100 on a busy host.

The baseline is condition 1 (series A, levels off, no polling) and condition 10 (series B, levels
off, no polling): "what this engine costs when nobody is watching it". Every other figure is quoted
both absolutely and against its own series' baseline, because the two series have different rigs and
so different absolute costs -- the interesting quantity is the delta, and the delta is only
meaningful within a series.

Usage: analyse.py results.jsonl [--clk-tck 100]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("results")
parser.add_argument("--clk-tck", type=int, default=100)
parser.add_argument("--markdown", action="store_true")
args = parser.parse_args()

CLK = args.clk_tck
SERIES_TITLE = {"minimal": "Series A — a minimal rig (input → output, 2 nodes)",
                "heavy": "Series B — a 32-gain rig (34 nodes)"}
SERIES_NOTE = {
    "minimal": "the chain runs and the converters are real, so this series is the cost of *answering*: "
               "the levels JSON built and sent once per poll. There is almost nothing inside the rig to measure.",
    "heavy": "the same eight switches over a rig whose own cost is one multiply per node, so what the "
             "conditions differ by is dominated by the probes rather than by the audio.",
}


def load(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def cpu_seconds(row: dict) -> float:
    return row["cpu_ticks"] / CLK


def pct(row: dict) -> float:
    return cpu_seconds(row) / row["seconds"] * 100.0


def ms_per_s(row: dict) -> float:
    return cpu_seconds(row) / row["seconds"] * 1000.0


def baseline(rows: list[dict], series: str) -> dict | None:
    for row in rows:
        if row.get("series") == series and row.get("levels") == "off" and row.get("hz") in (None, 0):
            return row
    return None


def main() -> None:
    rows = load(Path(args.results))
    ok = [r for r in rows if "cpu_ticks" in r]
    failed = [r for r in rows if "cpu_ticks" not in r]

    for series in ("minimal", "heavy"):
        series_rows = [r for r in ok if r.get("series") == series]
        if not series_rows:
            continue
        base = baseline(ok, series)
        print()
        print(f"### {SERIES_TITLE[series]}")
        print()
        print(SERIES_NOTE[series])
        print()
        print("| Condition | Levels | Client polling | Window s | CPU ticks | CPU (one core) | ms/s | vs baseline |")
        print("|---|---|---|---|---|---|---|---|")
        for row in sorted(series_rows, key=lambda r: r["condition"]):
            hz = row.get("hz")
            hz_text = "—" if hz is None else f"{hz:g} Hz"
            which = "off" if row["levels"] == "off" else "on"
            delta = ""
            if base is not None and row is not base:
                delta = f"{pct(row) - pct(base):+.1f} pp ({ms_per_s(row) - ms_per_s(base):+.2f} ms/s)"
            elif row is base:
                delta = "baseline"
            print(f"| {row['condition']} | {which} | {hz_text} | {row['seconds']:g} | "
                  f"{row['cpu_ticks']} | {pct(row):.2f}% | {ms_per_s(row):.1f} | {delta} |")
        print()
        # The polling cost is a difference of averages, which is what makes it legible: each rate
        # against the same-rate-with-no-client figure.
        if base is not None:
            on_idle = next((r for r in series_rows if r["levels"] == "on" and r.get("hz") is None), None)
            if on_idle is not None:
                print(f"- measuring, nobody polling: **{pct(on_idle):.2f}%** "
                      f"({pct(on_idle) - pct(base):+.2f} pp, {ms_per_s(on_idle) - ms_per_s(base):+.1f} ms/s "
                      f"against the switch off)")
            for row in sorted((r for r in series_rows if r.get("hz")), key=lambda r: -r["hz"]):
                if on_idle is not None:
                    per_poll = (ms_per_s(row) - ms_per_s(on_idle)) / (row["hz"] * row["seconds"]) * row["seconds"]
                    print(f"- polling at {row['hz']:>2g} Hz: **{pct(row):.2f}%** "
                          f"({pct(row) - pct(on_idle):+.2f} pp over measuring with no client, "
                          f"~{per_poll:.3f} ms per poll)")
        print()
        for row in sorted(series_rows, key=lambda r: r["condition"]):
            if row.get("errors"):
                print(f"  ! condition {row['condition']}: {row['errors']} client errors")
            if row.get("empty_windows"):
                print(f"  ! condition {row['condition']}: {row['empty_windows']} empty windows of "
                      f"{row['ticks']} ticks")
    if failed:
        print()
        print("Conditions that never became ready:")
        for row in failed:
            print(f"  - {row.get('condition')}: {row.get('label')}: {row.get('error')}")


if __name__ == "__main__":
    main()

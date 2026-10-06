#!/usr/bin/env python3
"""Draw the levels campaign as SVG: overhead as a share of one core, and nothing else.

    python3 charts.py results.jsonl [--out DIR]

Why SVG written by hand rather than matplotlib: matplotlib is not in the Python this workspace
ships, and the one chart library that is on the machine is the campaign page in ljoss, which is a
different shape of thing (a browser page with its data inlined). An SVG is text, so it reviews and
diffs like the rest of a bench-results directory, needs no dependency, and opens from `file://`.
The schematic renders in pedal.project are SVG for the same reason.

What is plotted is **CPU as a percentage of one core** -- the daemon process's own utime+stime over
the window -- because that is the unit a reader can act on. The raw tick counts and the derived
milliseconds-per-second are in the report's tables for anybody who wants to check the arithmetic.
"""

from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path

W, H = 900, 460
MARGIN_L, MARGIN_R, MARGIN_T, MARGIN_B = 78, 24, 56, 92

# One colour per measurement mode, so the same mode is the same colour in every chart.
COLOUR = {
    "off": "#94a3b8",
    "on": "#2563eb",
    "on-period": "#059669",
    "on-rate": "#0d9488",
    "on-sparse": "#d97706",
    "on-rate-sparse": "#7c3aed",
    "on-period-rate": "#be185d",
}
LABEL = {
    "off": "levels off",
    "on": "measuring",
    "on-period": "measuring, published per period",
    "on-rate": "measuring, drained at poll rate",
    "on-sparse": "measuring, one frame per period",
    "on-rate-sparse": "both",
    "on-period-rate": "published per period + drained",
}
BASELINE = "#94a3b8"


def mode_key(row: dict) -> str:
    """Which measurement mode a row is, from what the daemon was started with.

    Kept in step with analyse.py's, deliberately: the charts and the tables must name the same modes
    the same way, or the same bar and the same row read as two different things.
    """
    if row.get("levels") == "off":
        return "off"
    rate = row.get("rate_hz") or 0
    sparse = bool(row.get("first_frame"))
    period = row.get("publish") == "period"
    if period:
        return "on-period-rate" if rate else "on-period"
    if rate and sparse:
        return "on-rate-sparse"
    if rate:
        return "on-rate"
    if sparse:
        return "on-sparse"
    return "on"


def cpu_percent(row: dict, clk: int) -> float:
    return row["cpu_ticks"] / clk / row["seconds"] * 100.0


def esc(text: str) -> str:
    return html.escape(str(text))


class Canvas:
    def __init__(self, width: int, height: int):
        self.parts: list[str] = []
        self.width = width
        self.height = height

    def add(self, text: str) -> None:
        self.parts.append(text)

    def rect(self, x, y, w, h, fill, rx=3, opacity=1.0) -> None:
        self.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" '
                 f'fill="{fill}" opacity="{opacity}"/>')

    def line(self, x1, y1, x2, y2, stroke, width=1.0, dash=None) -> None:
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                 f'stroke="{stroke}" stroke-width="{width}"{d}/>')

    def text(self, x, y, content, size=13, fill="#0f172a", anchor="start", weight="400") -> None:
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" font-family="-apple-system, Segoe UI, Roboto, '
                 f'Helvetica, Arial, sans-serif" font-size="{size}" fill="{fill}" '
                 f'text-anchor="{anchor}" font-weight="{weight}">{esc(content)}</text>')

    def path(self, d, stroke, width=2.0, fill="none") -> None:
        self.add(f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{width}" '
                 f'stroke-linejoin="round" stroke-linecap="round"/>')

    def circle(self, cx, cy, r, fill) -> None:
        self.add(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{fill}"/>')

    def svg(self) -> str:
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" '
                f'viewBox="0 0 {self.width} {self.height}" role="img">\n'
                f'<rect width="{self.width}" height="{self.height}" fill="#ffffff"/>\n'
                + "\n".join(self.parts) + "\n</svg>\n")


def axis(canvas: Canvas, plot_left, plot_right, plot_top, plot_bottom, top_value, title, y_label):
    canvas.text(plot_left, 26, title, size=16, weight="600")
    canvas.text(plot_left, 44, y_label, size=12, fill="#475569")

    # Four gridlines, rounded up to a sane step, labelled as a share of one core.
    step = max(0.5, round(top_value / 4 * 2) / 2)
    ticks = []
    value = 0.0
    while value <= top_value + step / 2:
        ticks.append(value)
        value += step

    for value in ticks:
        y = plot_bottom - (value / top_value) * (plot_bottom - plot_top)
        canvas.line(plot_left, y, plot_right, y, "#e2e8f0", 1.0)
        canvas.text(plot_left - 10, y + 4, f"{value:g}%", size=11, fill="#64748b", anchor="end")
    canvas.line(plot_left, plot_bottom, plot_right, plot_bottom, "#94a3b8", 1.2)
    return ticks


def chart_by_mode(rows: list[dict], clk: int) -> str:
    """Bars: the five modes, all at the same client rate, against the switch-off baseline."""
    rows = [r for r in rows if "cpu_ticks" in r]
    baseline = next((r for r in rows if mode_key(r) == "off"), None)
    order = ["off", "on", "on-period", "on-rate", "on-sparse", "on-rate-sparse",
             "on-period-rate"]
    present = [m for m in order if any(mode_key(r) == m for r in rows)]
    values = {}
    for mode in present:
        # One row per mode in this series. If a mode somehow has several, the first is the campaign's
        # own and the rest are a different series that was pointed at this chart by mistake.
        row = next(r for r in rows if mode_key(r) == mode)
        values[mode] = cpu_percent(row, clk)

    canvas = Canvas(W, H)
    plot_left, plot_right = MARGIN_L, W - MARGIN_R
    plot_top, plot_bottom = MARGIN_T, H - MARGIN_B
    top_value = max(values.values()) * 1.25 if values else 1.0
    top_value = max(top_value, 1.0)
    ticks = axis(canvas, plot_left, plot_right, plot_top, plot_bottom, top_value,
                 "What each way of measuring costs, one core, client polling at 1 Hz",
                 "namchaind's CPU as a share of one core (the board has four)")

    slot = (plot_right - plot_left) / max(len(present), 1)
    bar_w = slot * 0.55
    base_value = values.get("off")

    for index, mode in enumerate(present):
        value = values[mode]
        x = plot_left + slot * index + (slot - bar_w) / 2
        height = (value / top_value) * (plot_bottom - plot_top)
        y = plot_bottom - height
        colour = BASELINE if mode == "off" else COLOUR[mode]
        canvas.rect(x, y, bar_w, height, colour)
        canvas.text(x + bar_w / 2, y - 8, f"{value:.2f}%", size=13, anchor="middle", weight="600")
        if base_value is not None and mode != "off":
            delta = value - base_value
            canvas.text(x + bar_w / 2, y - 24, f"{delta:+.2f} pp", size=11, fill="#64748b",
                        anchor="middle")
        # Two-line label under the axis, wrapped by hand so it never overlaps the next bar.
        words = LABEL[mode].split(", ")
        for line_index, line in enumerate(words):
            canvas.text(x + bar_w / 2, plot_bottom + 20 + line_index * 14, line, size=11,
                        fill="#334155", anchor="middle")

    if base_value is not None:
        y = plot_bottom - (base_value / top_value) * (plot_bottom - plot_top)
        canvas.line(plot_left, y, plot_right, y, BASELINE, 1.0, dash="4 3")
        # Just above the line and hard left: at the right-hand end it collided with the last bar's
        # label, which is the one place this chart is guaranteed to have something else drawn.
        # Below the line, hard left: the leftmost bar usually *is* the baseline, so a label above the
        # line lands on that bar's own value, and two texts at one height is what that looks like.
        canvas.text(plot_left + 4, y + 14, f"switch off: {base_value:.2f}%", size=11, fill="#64748b")
    return canvas.svg()


def chart_by_rate(rows: list[dict], clk: int) -> str:
    """Lines: the polling sweep, one line per rig, from its unobserved baseline up to 20 Hz.

    Only the plain `measuring` mode is plotted, plus each series' `--no-levels` row as the 0 Hz point.
    The 1 Hz rows that use the finer switches are deliberately left out: they are a different question
    (what other switches buy, at one rate) and they answer it in the by-mode chart. Mixed in here they
    put three points at 1 Hz and make the sweep unreadable -- the first draft of this chart did exactly
    that, and the vertical stack at 1 Hz is what it looked like.
    """
    rows = [r for r in rows if "cpu_ticks" in r and (r.get("hz") or mode_key(r) == "off")]
    series: dict[str, list[tuple[float, float]]] = {}
    for row in rows:
        if row.get("hz") and mode_key(row) != "on":
            continue
        # Conditions 19 and up are the switch comparisons, and several of them are 1 Hz as well: left
        # in, they stack three more points on the 1 Hz tick and the sweep stops being a sweep. The
        # by-mode chart is where they belong, and where they are plotted.
        if row["condition"] > 18:
            continue
        rate = float(row["hz"]) if row.get("hz") else 0.0
        series.setdefault(row.get("series", "?"), []).append((rate, cpu_percent(row, clk)))

    canvas = Canvas(W, H)
    plot_left, plot_right = MARGIN_L, W - MARGIN_R
    plot_top, plot_bottom = MARGIN_T, H - MARGIN_B
    rates = sorted({rate for points in series.values() for rate, _ in points})
    top_value = max((value for points in series.values() for _, value in points), default=1.0) * 1.2
    axis(canvas, plot_left, plot_right, plot_top, plot_bottom, max(top_value, 1.0),
         "What a client polling costs, by rate and by rig",
         "namchaind's CPU as a share of one core (the board has four)")

    def x_of(rate: float) -> float:
        # Log in the rate, because 1..20 Hz is a range a linear axis wastes -- and because the 0 Hz
        # point is "nobody is polling", which is not one step below 1 Hz but infinitely below it.
        # A log axis cannot carry zero, so it is placed a decade below the slowest real rate: the
        # axis is labelled with rates, not with positions, and the label says what the leftmost
        # point is.
        lo = math.log(min(r for r in rates if r > 0) / 10)
        hi = math.log(max(rates))
        return plot_left + (math.log(max(rate, math.exp(lo))) - lo) / (hi - lo or 1) * (plot_right - plot_left)

    def y_of(value: float) -> float:
        return plot_bottom - value / top_value * (plot_bottom - plot_top)

    colours = {"minimal": "#2563eb", "heavy": "#dc2626"}
    for name, points in sorted(series.items()):
        points.sort()
        d = "M " + " L ".join(f"{x_of(rate):.1f} {y_of(value):.1f}" for rate, value in points)
        canvas.path(d, colours.get(name, "#334155"), 2.4)
        for rate, value in points:
            canvas.circle(x_of(rate), y_of(value), 3.4, colours.get(name, "#334155"))
        # The label goes just inside the right-hand end of the line, and above it: outside the plot
        # it would be clipped by the canvas, which is what the first draft of this chart did.
        rate, value = points[-1]
        canvas.text(x_of(rate) - 8, y_of(value) - 12, f"{name} rig", size=12,
                    fill=colours.get(name, "#334155"), weight="600", anchor="end")

    for rate in rates:
        canvas.line(x_of(rate), plot_bottom, x_of(rate), plot_bottom + 4, "#94a3b8", 1.0)
        canvas.text(x_of(rate), plot_bottom + 20, "none" if rate == 0 else f"{rate:g}", size=11,
                    fill="#334155", anchor="middle")
    canvas.text((plot_left + plot_right) / 2, plot_bottom + 42,
                "client polls per second — “none” is nothing polling at all",
                size=11, fill="#475569", anchor="middle")
    return canvas.svg()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results")
    parser.add_argument("--clk-tck", type=int, default=100)
    parser.add_argument("--out", default=None)
    parser.add_argument("--only", default="",
                        help="condition numbers for the by-mode chart, comma separated. Needed "
                             "because several conditions share a mode: without it the chart takes "
                             "whichever row comes first, which is a different client rate")
    parser.add_argument("--name", default=None,
                        help="output filename for the by-mode chart, so a report can carry one chart "
                             "per comparison instead of overwriting a single file")
    parser.add_argument("--mode-only", action="store_true",
                        help="the by-mode chart needs one row per mode; point it at that series")
    args = parser.parse_args()

    every = [json.loads(line) for line in Path(args.results).read_text().splitlines() if line.strip()]
    only = {int(n) for n in args.only.split(",") if n.strip()}
    rows = [r for r in every if r.get("condition") in only] if only else every
    out_dir = Path(args.out) if args.out else Path(args.results).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    written = []
    path = out_dir / (args.name or "overhead-by-mode.svg")
    path.write_text(chart_by_mode(rows, args.clk_tck))
    written.append(path)

    if not args.mode_only:
        # The rate chart wants the whole sweep, never a subset: its lines are the sweep.
        path = out_dir / "overhead-by-poll-rate.svg"
        path.write_text(chart_by_rate(every, args.clk_tck))
        written.append(path)

    for path in written:
        print(path)


if __name__ == "__main__":
    main()

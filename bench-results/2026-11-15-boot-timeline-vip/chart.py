#!/usr/bin/env python3
"""Draw the vip boot timeline and its dependency graph as SVG, from timeline.json.

    python3 chart.py                 # writes boot-timeline.svg and boot-dependencies.svg here
    python3 chart.py --out DIR

Why SVG written by hand rather than matplotlib: matplotlib is not in the Python this workspace
ships, and an SVG is text, so it reviews and diffs like the rest of a bench-results directory,
needs no dependency, and opens from `file://`. The Canvas class is the one from
bench-results/2026-10-06-levels-switch/charts.py, extended with the line styles this figure needs
(hatched estimates, unknown bars with a ragged edge, arrowheads, a brace).

What is drawn is `timeline.json`: one row per stage, two panels (the measured 2026-10-02 plug pull
and the current tree + the 2026-11-15 plan), and a dependency graph. Every number comes from the
JSON; this file adds no fact and no duration of its own. A bar with a hatched fill is an estimate,
a bar with a ragged right edge and a '?' is unknown, a dashed outline is an ordering that is
recorded but not timed, and a solid bar is measured. The drawn width of an unknown bar is a
layout decision, not a measurement.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

# The palette: one colour per lane, and neutral colours for the annotation furniture.
INK = "#0f172a"
MUTED = "#475569"
FAINT = "#94a3b8"
GRID = "#e2e8f0"
RED = "#dc2626"

FONT = "-apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif"


def esc(text: object) -> str:
    return html.escape(str(text), quote=True)


class Canvas:
    """A very small SVG canvas: enough primitives for two figures, no dependencies."""

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.parts: list[str] = []
        self.defs: list[str] = []

    # -- structure -------------------------------------------------------
    def add(self, text: str) -> None:
        self.parts.append(text)

    def define(self, text: str) -> None:
        self.defs.append(text)

    # -- primitives ------------------------------------------------------
    def rect(self, x, y, w, h, fill, rx=3, opacity=1.0, stroke=None, stroke_width=1.0, dash=None):
        extra = ""
        if stroke:
            extra += f' stroke="{stroke}" stroke-width="{stroke_width}"'
        if dash:
            extra += f' stroke-dasharray="{dash}"'
        self.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w, 0):.1f}" height="{h:.1f}" '
                 f'rx="{rx}" fill="{fill}" opacity="{opacity}"{extra}/>')

    def line(self, x1, y1, x2, y2, stroke, width=1.0, dash=None, opacity=1.0):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                 f'stroke="{stroke}" stroke-width="{width}" opacity="{opacity}"{d}/>')

    def text(self, x, y, content, size=11, fill=INK, anchor="start", weight="400",
             rotate=None, halo=False, italic=False, family=FONT):
        transform = f' transform="rotate({rotate} {x:.1f} {y:.1f})"' if rotate is not None else ""
        halo_attr = ' stroke="#ffffff" stroke-width="3" paint-order="stroke"' if halo else ""
        style = ' font-style="italic"' if italic else ""
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" font-family="{family}" font-size="{size}" '
                 f'fill="{fill}" text-anchor="{anchor}" font-weight="{weight}" '
                 f'dominant-baseline="auto"{halo_attr}{style}{transform}>{esc(content)}</text>')

    def path(self, d, stroke, width=2.0, fill="none", dash=None, opacity=1.0,
             marker_end=None, linejoin="round"):
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        marker = f' marker-end="url(#{marker_end})"' if marker_end else ""
        self.add(f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{width}" '
                 f'opacity="{opacity}" stroke-linejoin="{linejoin}" stroke-linecap="round"'
                 f'{dash_attr}{marker}/>')

    def polygon(self, points, fill, stroke=None, stroke_width=1.0):
        p = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        extra = f' stroke="{stroke}" stroke-width="{stroke_width}"' if stroke else ""
        self.add(f'<polygon points="{p}" fill="{fill}"{extra}/>')

    def diamond(self, cx, cy, r, fill, stroke=None):
        self.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)],
                     fill, stroke, 1.0)

    def brace(self, x, y1, y2, colour, width=1.2):
        """A curly bracket on the left of x, from y1 to y2 (y2 > y1)."""
        mid = (y1 + y2) / 2
        d = (f"M {x - 7:.1f} {y1:.1f} Q {x:.1f} {y1:.1f} {x:.1f} {y1 + 7:.1f} "
             f"L {x:.1f} {mid - 7:.1f} Q {x:.1f} {mid:.1f} {x + 5:.1f} {mid:.1f} "
             f"Q {x:.1f} {mid:.1f} {x:.1f} {mid + 7:.1f} "
             f"L {x:.1f} {y2 - 7:.1f} Q {x:.1f} {y2:.1f} {x - 7:.1f} {y2:.1f}")
        self.path(d, colour, width)

    # -- output ----------------------------------------------------------
    def svg(self) -> str:
        defs = "\n".join(self.defs)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" '
                f'height="{self.height}" viewBox="0 0 {self.width} {self.height}" '
                f'role="img" aria-label="vip boot timeline">\n'
                f'<defs>\n{defs}\n</defs>\n'
                f'<rect width="{self.width}" height="{self.height}" fill="#ffffff"/>\n'
                + "\n".join(self.parts) + "\n</svg>\n")


def add_defs(canvas: Canvas) -> None:
    """Hatch patterns for estimates/unknowns, and one arrowhead per edge style."""
    canvas.define(
        '<pattern id="hatch-estimate" width="4" height="4" patternUnits="userSpaceOnUse" '
        'patternTransform="rotate(45)">'
        '<line x1="0" y1="0" x2="0" y2="4" stroke="#78350f" stroke-width="1.15" '
        'stroke-opacity="0.75"/></pattern>')
    canvas.define(
        '<pattern id="hatch-unknown" width="4" height="4" patternUnits="userSpaceOnUse" '
        'patternTransform="rotate(45)">'
        '<line x1="0" y1="0" x2="0" y2="4" stroke="#64748b" stroke-width="1.5" '
        'stroke-opacity="0.8"/></pattern>')
    canvas.define(
        '<pattern id="hatch-band" width="8" height="8" patternUnits="userSpaceOnUse" '
        'patternTransform="rotate(45)">'
        '<line x1="0" y1="0" x2="0" y2="8" stroke="#7c3aed" stroke-width="0.9" '
        'stroke-opacity="0.45"/></pattern>')
    for name, colour in (("order", "#334155"), ("critical", RED), ("async", "#7c3aed"),
                         ("condition", "#6d28d9"), ("independent", "#94a3b8"),
                         ("unknown", "#64748b")):
        canvas.define(
            f'<marker id="arrow-{name}" viewBox="0 0 10 10" refX="8.6" refY="5" '
            f'markerWidth="10" markerHeight="10" markerUnits="userSpaceOnUse" orient="auto">'
            f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{colour}"/></marker>')


# ---------------------------------------------------------------------------
# Gantt
# ---------------------------------------------------------------------------

W = 1240
X0, X1 = 236.0, 1200.0
TMAX = 30.0
LEFT = 20
NAME_X = 32
ROW = 17
HEAD = 20

STYLE_DASH = {
    "measured-2026-10-02": None,
    "estimate": "4 3",
    "unknown": "3 3",
    "recorded-state": "5 3",
}


def x_of(t: float) -> float:
    return X0 + max(0.0, t) / TMAX * (X1 - X0)


def short(text: str, limit: int = 34) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def duration_label(value: dict, measured: bool = False, nominal_duration=None) -> str:
    """One short line for the row label: what the bar means numerically."""
    if value.get("value_note"):
        return value["value_note"]
    lo = value.get("duration_range")
    dur = value.get("duration")
    if lo:
        return f"{lo[0]:.2f}–{lo[1]:.2f} s"
    if dur is None:
        return "?"
    if dur >= 1:
        return f"{dur:.2f} s"
    return f"{dur * 1000:.0f} ms"


def draw_row_label(canvas: Canvas, x: float, y: float, name: str, value: str,
                   lane_colour: str, authority: str) -> None:
    """A two-line label in the left gutter: stage name, then its number/authority."""
    fill = INK if authority == "measured-2026-10-02" else MUTED
    if authority == "estimate":
        fill = "#78350f"
    elif authority == "unknown":
        fill = "#64748b"
    canvas.text(x, y + 7.5, short(name), size=8.6, fill=fill, weight="500")
    canvas.text(x, y + 15.0, short(value, 46), size=7.7, fill="#64748b")


def draw_bar(canvas: Canvas, stage: dict, x0: float, row_y: float, lane_colour: str,
             measured: bool) -> None:
    """Draw one stage's bar: solid measured, hatched estimate, ragged unknown, dashed recorded."""
    value = stage.get("measured") if measured else stage.get("current")
    if not value:
        return
    if value.get("draw") == "none":
        return
    draw = value.get("draw", "bar")
    h = 9.0
    y = row_y + 4.0

    def ragged(x_end: float, yy: float, hh: float) -> None:
        """A broken right edge: the drawn width is not a claim about the duration."""
        canvas.polygon([(x_end - 3, yy), (x_end + 1, yy + hh * 0.30),
                        (x_end - 2, yy + hh * 0.55), (x_end + 1, yy + hh * 0.80),
                        (x_end - 3, yy + hh)],
                       fill="#ffffff", stroke=lane_colour, stroke_width=1.0)


    if draw in ("window", "window-unknown"):
        if draw == "window":
            start, end = value.get("start"), value.get("end")
            x1, x2 = x_of(start), x_of(end)
        else:
            s_lo, s_hi = value["start_range"]
            e_lo, e_hi = value["end_range"]
            x1, x2 = x_of(s_lo), x_of(e_hi)
        canvas.rect(x1, y, x2 - x1, h, lane_colour, rx=2, opacity=0.10)
        canvas.rect(x1, y, x2 - x1, h, "url(#hatch-unknown)", rx=2, opacity=0.8)
        canvas.rect(x1, y, x2 - x1, h, "none", rx=2, stroke=lane_colour,
                    stroke_width=1.1, dash="3 3")
        canvas.text((x1 + x2) / 2, y + h - 1.5, "?", size=9.5, fill=lane_colour,
                    anchor="middle", weight="700")
        return

    if draw == "band":
        band = value.get("band_range")
        start = value.get("start")
        if not band or start is None:
            return
        x1, x2 = x_of(start + band[0]), x_of(start + band[1])
        canvas.rect(x1, y, x2 - x1, h, lane_colour, rx=2, opacity=0.10)
        canvas.rect(x1, y, x2 - x1, h, "url(#hatch-band)", rx=2, opacity=0.9)
        canvas.rect(x1, y, x2 - x1, h, "none", rx=2, stroke=lane_colour,
                    stroke_width=1.0, dash="3 3")
        canvas.text((x1 + x2) / 2, y + h - 1.5, "? 0.5–8 s", size=8.0,
                    fill=lane_colour, anchor="middle", weight="600")
        return

    start = value.get("start_range", [value.get("start"), value.get("start")])[0]
    if value.get("start") is not None:
        start = value["start"]
    duration = value.get("duration")
    if duration is None:
        # Unknown duration: a short hatched bar with a ragged edge and a '?'. The width is
        # deliberately nominal -- see the module docstring and the report's legend.
        x1 = x_of(start)
        x2 = min(x_of(start + 0.9), X1)
        canvas.rect(x1, y, x2 - x1, h, lane_colour, rx=2, opacity=0.10)
        canvas.rect(x1, y, x2 - x1, h, "url(#hatch-unknown)", rx=2, opacity=0.85)
        canvas.rect(x1, y, x2 - x1, h, "none", rx=2, stroke=lane_colour,
                    stroke_width=1.0, dash="3 3")
        ragged(x2, y, h)
        canvas.text(x1 + 6, y + h - 1.5, "?", size=9.5, fill=lane_colour, weight="700")
        return

    clip = bool(value.get("clip"))
    end = start + duration
    x1 = x_of(start)
    x2 = x_of(end) if not clip else X1
    if x2 - x1 < 1.8:
        # A 7 ms stage is 0.2 px on this axis; the row label carries the number.
        x2 = x1 + 1.8
    authority = value.get("authority", "unknown" if not measured else "measured-2026-10-02")
    dash = STYLE_DASH.get(authority)
    if authority == "measured-2026-10-02":
        canvas.rect(x1, y, x2 - x1, h, lane_colour, rx=2, opacity=0.88)
    elif authority == "estimate":
        canvas.rect(x1, y, x2 - x1, h, lane_colour, rx=2, opacity=0.16)
        canvas.rect(x1, y, x2 - x1, h, "url(#hatch-estimate)", rx=2, opacity=0.95)
        canvas.rect(x1, y, x2 - x1, h, "none", rx=2, stroke=lane_colour,
                    stroke_width=1.0, dash=dash)
    elif authority == "recorded-state":
        canvas.rect(x1, y, x2 - x1, h, lane_colour, rx=2, opacity=0.06)
        canvas.rect(x1, y, x2 - x1, h, "none", rx=2, stroke=lane_colour,
                    stroke_width=1.2, dash=dash)
    else:
        canvas.rect(x1, y, x2 - x1, h, lane_colour, rx=2, opacity=0.08)
        canvas.rect(x1, y, x2 - x1, h, "url(#hatch-unknown)", rx=2, opacity=0.75)
        canvas.rect(x1, y, x2 - x1, h, "none", rx=2, stroke=lane_colour,
                    stroke_width=1.0, dash=dash)
        ragged(x2, y, h)

    # Whiskers show an estimated range around the drawn bar. They are thin and sit on the
    # bar's top edge so a range is visible without pretending to be a second measurement.
    for key, anchor_key in (("duration_range", "start"), ("start_range", "duration_start")):
        bounds = value.get(key)
        if not bounds:
            continue
        if key == "duration_range":
            w1 = x_of(start + bounds[0])
            w2 = x_of(start + bounds[1])
        else:
            w1, w2 = x_of(bounds[0]), x_of(bounds[1])
            if duration:
                w2 = max(w2, x_of(bounds[1] + duration))
                w1 = min(w1, x_of(bounds[0]))
        wy = y - 1.8
        canvas.line(w1, wy, w2, wy, lane_colour, 0.9)
        canvas.line(w1, wy - 2.0, w1, wy + 2.0, lane_colour, 0.9)
        canvas.line(w2, wy - 2.0, w2, wy + 2.0, lane_colour, 0.9)

    if clip:
        canvas.text(X1 + 5, y + h - 1.5, "» 300 s", size=8.0, fill=lane_colour, weight="600")


def draw_legend(canvas: Canvas, lanes: list[dict]) -> None:
    y = 82
    items = [
        ("solid", "measured 2026-10-02"),
        ("hatch-estimate", "estimate (range whiskers)"),
        ("hatch-unknown", "? unknown (ragged edge)"),
        ("dashed", "recorded ordering only"),
    ]
    x = LEFT
    for kind, label in items:
        if kind == "solid":
            canvas.rect(x, y - 8, 14, 9, "#334155", rx=2)
        elif kind == "dashed":
            canvas.rect(x, y - 8, 14, 9, "#ffffff", rx=2, stroke="#475569",
                        stroke_width=1.2, dash="5 3")
        else:
            canvas.rect(x, y - 8, 14, 9, "#ffffff", rx=2, stroke="#78350f" if kind.endswith("estimate") else "#64748b",
                        stroke_width=1.0, dash="3 3")
            canvas.rect(x, y - 8, 14, 9, f"url(#{kind})", rx=2, opacity=0.9)
        canvas.text(x + 20, y, label, size=9.5, fill=MUTED)
        x += 20 + len(label) * 5.5 + 26

    y = 100
    canvas.text(LEFT, y, "lane:", size=9.5, fill=MUTED)
    x = LEFT + 38
    for lane in lanes:
        canvas.rect(x, y - 7, 8, 8, lane["colour"], rx=2)
        canvas.text(x + 12, y, lane["label"], size=9.0, fill=MUTED)
        x += 12 + len(lane["label"]) * 5.1 + 18


def stage_rows(stages: list[dict], lanes: list[dict]) -> list[tuple[str, dict | None]]:
    """Rows in lane order: a header per lane, then that lane's stages."""
    by_lane: dict[str, list[dict]] = {lane["id"]: [] for lane in lanes}
    for stage in stages:
        by_lane.setdefault(stage["lane"], []).append(stage)
    rows: list[tuple[str, dict | None]] = []
    for lane in lanes:
        rows.append(("header", lane))
        for stage in by_lane.get(lane["id"], []):
            rows.append(("stage", stage))
    return rows


def draw_gantt(data: dict, panel: str, canvas: Canvas, top: float) -> float:
    """Draw one panel (measured or current). Returns the y coordinate it ended at."""
    lanes = data["lanes"]
    lane_colour = {lane["id"]: lane["colour"] for lane in lanes}
    rows = stage_rows(data["stages"], lanes)

    title = ("Measured: the 2026-10-02 plug pull" if panel == "measured"
             else "Current tree + the 2026-11-15 plan: estimate and unknown")
    subtitle = (data["measured_boot"]["label"] if panel == "measured"
                else data["current"]["label"])
    canvas.text(LEFT, top + 14, title, size=13.5, weight="700")
    canvas.text(LEFT + len(title) * 7.3 + 10, top + 14, subtitle, size=9.0, fill=MUTED)

    axis_y = top + 32
    rows_top = top + 40
    for t in range(0, int(TMAX) + 1, 5):
        x = x_of(t)
        canvas.line(x, axis_y + 2, x, rows_top + sum(HEAD if k == "header" else ROW for k, _ in rows),
                    GRID, 1.0)
        canvas.text(x, axis_y, "0" if t == 0 else f"{t:g} s", size=8.5, fill=FAINT,
                    anchor="middle")

    lane_has_measured = {
        lane["id"]: any(stage.get("measured") for stage in data["stages"]
                        if stage["lane"] == lane["id"])
        for lane in lanes
    }
    y = rows_top
    brace_from = brace_to = None
    for kind, row in rows:
        if kind == "header":
            colour = row["colour"]
            heading = row["label"].upper()
            if panel == "measured" and not lane_has_measured[row["id"]]:
                heading += "   — not measured in this boot"
            canvas.text(LEFT, y + 13.5, heading, size=9.5, fill=colour, weight="700")
            canvas.line(LEFT, y + HEAD - 2, X1, y + HEAD - 2, colour, 0.8, opacity=0.35)
            if row["id"] in ("audio", "display", "network", "health") and brace_from is None:
                brace_from = y
            if row["id"] == "health":
                brace_to = y + HEAD + sum(ROW for k, r in rows
                                          if k == "stage" and r["lane"] == "health")
            y += HEAD
            continue

        stage = row
        lane = lane_colour[stage["lane"]]
        value = stage.get("measured") if panel == "measured" else stage.get("current")
        authority = ("measured-2026-10-02" if panel == "measured"
                     else (value or {}).get("authority", "unknown"))
        if panel == "measured":
            authority = "measured-2026-10-02" if value else "recorded-state"

        if value is None:
            canvas.text(NAME_X + 8, y + 12, short(stage["name"]), size=8.6,
                        fill=FAINT, italic=True)
            if lane_has_measured[stage["lane"]]:
                canvas.text(X0 + 5, y + 12, "not measured in this boot", size=7.4,
                            fill=FAINT, italic=True)
        else:
            draw_row_label(canvas, NAME_X + 8, y, stage["name"],
                           duration_label(value, measured=(panel == "measured")),
                           lane, authority)
            draw_bar(canvas, stage, X0, y, lane, measured=(panel == "measured"))
        y += ROW

    rows_end = y
    if brace_from is not None:
        canvas.brace(X0 - 8, brace_from + 2, brace_to - 2, FAINT, 1.1)
        canvas.text(X0 - 15, (brace_from + brace_to) / 2, "parallel after sysinit",
                    size=8.0, fill=FAINT, anchor="middle", rotate=-90)

    # Markers: a thin dashed line at each event's midpoint, a number badge below the rows, and
    # a numbered list under that. Overlapping labels are what a badge-and-list avoids.
    markers = data["measured_boot"]["markers"] if panel == "measured" else data["current"]["markers"]
    for marker in markers:
        if "start_range" in marker:
            lo, hi = marker["start_range"]
            x1, x2 = x_of(lo), x_of(hi)
            canvas.line(x1, rows_end - 4, x2, rows_end - 4, "#d97706", 2.0)
            canvas.line(x1, rows_end - 8, x1, rows_end + 1, "#d97706", 1.0)
            canvas.line(x2, rows_end - 8, x2, rows_end + 1, "#d97706", 1.0)
            xm = (x1 + x2) / 2
        else:
            xm = x_of(marker["start"])
        canvas.line(xm, rows_top, xm, rows_end - 2, "#64748b", 0.7, dash="3 3", opacity=0.7)

    badge_rows = 3 if len(markers) > 6 else 2
    last_x = [-999.0] * badge_rows
    badges = []
    for index, marker in enumerate(markers):
        if "start_range" in marker:
            xm = x_of(sum(marker["start_range"]) / 2)
        else:
            xm = x_of(marker["start"])
        row = next((r for r in range(badge_rows) if xm - last_x[r] >= 15), badge_rows - 1)
        last_x[row] = xm
        by = rows_end + 12 + row * 13
        canvas.line(xm, rows_end - 2, xm, by - 6, FAINT, 0.5, dash="2 3")
        canvas.add(f'<circle cx="{xm:.1f}" cy="{by:.1f}" r="6" fill="#ffffff" '
                   f'stroke="#94a3b8" stroke-width="1.0"/>')
        canvas.text(xm, by + 2.8, str(index + 1), size=7.4, fill=MUTED, anchor="middle",
                    weight="600")
        badges.append((index + 1, marker))

    entries = []
    for number, marker in badges:
        if "start_range" in marker:
            lo, hi = marker["start_range"]
            entries.append(f"{number} {marker['label']} {lo:.2f}–{hi:.2f} s")
        else:
            entries.append(f"{number} {marker['label']} {marker['start']:.2f} s")
    line = "   ·   ".join(entries)
    list_top = rows_end + 12 + badge_rows * 13 + 4
    # Two lines at most; the entries are short.
    limit = 150
    words, lines, current = line.split("   ·   "), [], ""
    for word in words:
        candidate = (current + "   ·   " + word) if current else word
        if len(candidate) > limit and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    for index, text in enumerate(lines[:2]):
        canvas.text(LEFT, list_top + index * 12, text, size=8.2, fill=MUTED)

    note = ("seconds from the bootloader's first byte · the drawn width of a '?' bar is not "
            "a measurement")
    canvas.text(LEFT, list_top + len(lines) * 12 + 8, note, size=8.5, fill=FAINT)
    return list_top + len(lines) * 12 + 16


def figure_timeline(data: dict) -> str:
    canvas = Canvas(W, 1200)
    add_defs(canvas)

    canvas.text(LEFT, 24, data["title"], size=17, weight="700")
    canvas.text(LEFT, 42, data["subtitle"], size=10, fill=MUTED)
    canvas.text(LEFT, 58, data["anchor"], size=9, fill=FAINT)
    draw_legend(canvas, data["lanes"])

    bottom = draw_gantt(data, "measured", canvas, 112)
    bottom = draw_gantt(data, "current", canvas, bottom + 10)

    canvas.text(LEFT, bottom + 4,
                "Headline (estimate, not measured): " + data["current"].get("headline", ""),
                size=9.2, fill=INK, weight="600")
    live = data.get("live_2026_11_15") or {}
    if live:
        canvas.text(LEFT, bottom + 18,
                    "Live 2026-11-15, pre-splash root (measured): kernel %.3f + initrd %.3f + "
                    "userspace %.3f = %.3f s; rigpa started at %.3fs, multi-user at %.3fs. "
                    "The new design is unmeasured."
                    % (live["kernel_s"], live["initrd_s"], live["userspace_s"], live["total_s"],
                       live["rigpa_start_s"], live["multi_user_s"]),
                    size=8.2, fill=INK)
    canvas.text(LEFT, bottom + 32,
                "Sources: bench-results/2026-10-02-boot-time-vip/results.md (measured rows); "
                "devices/, docs/vip-image.md and docs/vip-kernel-image.md (recorded state); "
                "the 2026-11-15 plan (Plymouth, INITRD_DRIVERS, splash, masked units, "
                "rigpa qInfo marks). Drawn by chart.py from timeline.json.",
                size=8.2, fill=FAINT)

    canvas.height = int(bottom + 50)
    return canvas.svg()


# ---------------------------------------------------------------------------
# Dependency graph
# ---------------------------------------------------------------------------

GW, GH = 1500, 812
NODE_W, NODE_H = 146, 56
COL_X = 30
COL_STEP = 160
ROW_Y = 108
ROW_STEP = 96

NODE_STYLE = {
    "measured": ("#e0f2fe", "#0369a1", None),
    "recorded-state": ("#f1f5f9", "#475569", None),
    "estimate": ("#fef3c7", "#b45309", None),
    "unknown": ("#ffffff", "#64748b", "4 3"),
}

EDGE_STYLE = {
    "order": ("#334155", None, 1.6),
    "critical": (RED, None, 3.0),
    "async": ("#7c3aed", "6 4", 1.7),
    "condition": ("#6d28d9", "5 3", 1.7),
    "independent": ("#94a3b8", "2 4", 1.5),
    "unknown": ("#64748b", "3 3", 1.6),
}


def node_box(node: dict) -> tuple[float, float, float, float]:
    return (COL_X + node["col"] * COL_STEP, ROW_Y + node["row"] * ROW_STEP,
            NODE_W, NODE_H)


def node_centre(node: dict) -> tuple[float, float]:
    x, y, w, h = node_box(node)
    return x + w / 2, y + h / 2


def draw_node(canvas: Canvas, node: dict) -> None:
    x, y, w, h = node_box(node)
    fill, stroke, dash = NODE_STYLE.get(node.get("kind", "recorded-state"),
                                        NODE_STYLE["recorded-state"])
    if node.get("critical"):
        canvas.rect(x - 3, y - 3, w + 6, h + 6, "none", rx=9, stroke=RED, stroke_width=2.0)
    canvas.rect(x, y, w, h, fill, rx=7, stroke=stroke, stroke_width=1.4, dash=dash)
    lines = node.get("lines", [node["id"]])
    canvas.text(x + w / 2, y + 18, lines[0], size=10.2, anchor="middle", weight="700",
                fill=INK if node.get("kind") != "unknown" else MUTED)
    for index, line in enumerate(lines[1:3]):
        canvas.text(x + w / 2, y + 31 + index * 11, line, size=8.4, anchor="middle",
                    fill=MUTED)
    if node.get("tag"):
        canvas.text(x + w / 2, y + h - 5, node["tag"], size=7.4, anchor="middle",
                    fill=FAINT, italic=True)


def edge_points(edge: dict, nodes: dict[str, dict], offsets: dict) -> tuple[list[str], tuple[float, float], tuple[float, float]]:
    a, b = nodes[edge["from"]], nodes[edge["to"]]
    ax, ay, aw, ah = node_box(a)
    bx, by, bw, bh = node_box(b)

    if edge.get("route") == "left":
        # Down the gap on the left of both boxes: a same-column edge would otherwise cross a box
        # that sits between them (rigpa -> multi-user would cross engine-ready).
        y1 = ay + ah / 2 + offsets.get((edge["from"], "w", edge["to"]), 0)
        y2 = by + bh / 2 + offsets.get((edge["to"], "w", edge["from"]), 0)
        p1, p2 = (ax, y1), (bx, y2)
        vx = min(ax, bx) - 8
        return [f"M {p1[0]:.1f} {p1[1]:.1f}", f"L {vx:.1f} {p1[1]:.1f}",
                f"L {vx:.1f} {p2[1]:.1f}", f"L {p2[0]:.1f} {p2[1]:.1f}"], p1, p2

    if edge.get("same_col") or (a["col"] == b["col"] and a["row"] != b["row"]):
        top = a if a["row"] > b["row"] else b
        bottom = b if top is a else a
        sx = ax + aw / 2
        if a["row"] > b["row"]:
            p1 = (sx + offsets.get((edge["from"], "n", edge["to"]), 0), ay)
            p2 = (sx + offsets.get((edge["to"], "s", edge["from"]), 0), by + bh)
        else:
            p1 = (sx + offsets.get((edge["from"], "s", edge["to"]), 0), ay + ah)
            p2 = (sx + offsets.get((edge["to"], "n", edge["from"]), 0), by)
        return [f"M {p1[0]:.1f} {p1[1]:.1f}", f"L {p2[0]:.1f} {p2[1]:.1f}"], p1, p2

    left_to_right = b["col"] > a["col"]
    if left_to_right:
        y1 = ay + ah / 2 + offsets.get((edge["from"], "e", edge["to"]), 0)
        y2 = by + bh / 2 + offsets.get((edge["to"], "w", edge["from"]), 0)
        p1 = (ax + aw, y1)
        p2 = (bx, y2)
    else:
        y1 = ay + ah / 2 + offsets.get((edge["from"], "w", edge["to"]), 0)
        y2 = by + bh / 2 + offsets.get((edge["to"], "e", edge["from"]), 0)
        p1 = (ax, y1)
        p2 = (bx + bw, y2)

    via_y = edge.get("via_y")
    if via_y is not None:
        mid1 = p1[0] + (10 if left_to_right else -10)
        mid2 = p2[0] - (10 if left_to_right else -10)
        d = [f"M {p1[0]:.1f} {p1[1]:.1f}", f"L {mid1:.1f} {p1[1]:.1f}",
             f"L {mid1:.1f} {via_y:.1f}", f"L {mid2:.1f} {via_y:.1f}",
             f"L {mid2:.1f} {p2[1]:.1f}", f"L {p2[0]:.1f} {p2[1]:.1f}"]
        return d, p1, p2
    midx = (p1[0] + p2[0]) / 2
    if abs(p1[1] - p2[1]) < 0.5:
        d = [f"M {p1[0]:.1f} {p1[1]:.1f}", f"L {p2[0]:.1f} {p2[1]:.1f}"]
    else:
        d = [f"M {p1[0]:.1f} {p1[1]:.1f}", f"L {midx:.1f} {p1[1]:.1f}",
             f"L {midx:.1f} {p2[1]:.1f}", f"L {p2[0]:.1f} {p2[1]:.1f}"]
    return d, p1, p2


def figure_dependencies(data: dict) -> str:
    graph = data["dependency_graph"]
    nodes = {node["id"]: node for node in graph["nodes"]}
    canvas = Canvas(GW, GH)
    add_defs(canvas)

    canvas.text(LEFT, 26, graph["title"], size=17, weight="700")
    canvas.text(LEFT, 44,
                "Every box is a thing that must happen; every arrow is a reason. Red is the path "
                "that ends in sound; the other branches run beside it.",
                size=10, fill=MUTED)

    # Attach points: several edges can leave one side of a box, so spread them along that side
    # by the position of the other end. Without this every arrow from sysinit lands on one point.
    sides: list[tuple[dict, str, dict]] = []
    for edge in graph["edges"]:
        a, b = nodes[edge["from"]], nodes[edge["to"]]
        if edge.get("same_col") or (a["col"] == b["col"] and a["row"] != b["row"]):
            if a["row"] > b["row"]:
                sides.append((a, "n", b)); sides.append((b, "s", a))
            else:
                sides.append((a, "s", b)); sides.append((b, "n", a))
        elif b["col"] > a["col"]:
            sides.append((a, "e", b)); sides.append((b, "w", a))
        else:
            sides.append((a, "w", b)); sides.append((b, "e", a))

    offsets: dict = {}
    groups: dict[tuple[str, str], list[tuple[float, str]]] = {}
    for node, side, other in sides:
        groups.setdefault((node["id"], side), []).append(
            (other["col"] * 1000 + other["row"], other["id"]))
    for (node_id, side), members in groups.items():
        members.sort()
        mid = (len(members) - 1) / 2
        for index, (_, other_id) in enumerate(members):
            offsets[(node_id, side, other_id)] = (index - mid) * 9.0

    for index, edge in enumerate(graph["edges"]):
        d, p1, p2 = edge_points(edge, nodes, offsets)
        style = "critical" if edge.get("critical") else edge.get("style", "order")
        colour, dash, width = EDGE_STYLE[style]
        canvas.path(" ".join(d), colour, width, dash=dash, marker_end=f"arrow-{style}",
                    opacity=0.95 if style == "critical" else 0.85)
        label = edge.get("label")
        if label:
            if edge.get("same_col"):
                lx, ly = p1[0] + 6, (p1[1] + p2[1]) / 2
                canvas.text(lx, ly, label, size=8.0, fill=colour, halo=True)
            elif edge.get("via_y") is not None:
                lx = (p1[0] + p2[0]) / 2
                canvas.text(lx, edge["via_y"] - 4, label, size=8.0, fill=colour,
                            anchor="middle", halo=True)
            else:
                lx = (p1[0] + p2[0]) / 2
                ly = (p1[1] + p2[1]) / 2 - 4 if abs(p1[1] - p2[1]) > 4 else p1[1] - 4
                canvas.text(lx, ly, label, size=8.0, fill=colour, anchor="middle", halo=True)

    for node in graph["nodes"]:
        draw_node(canvas, node)

    # Legend.
    y = 742
    canvas.text(LEFT, y, "node:", size=9.5, fill=MUTED)
    x = LEFT + 46
    for kind, label in (("measured", "measured 2026-10-02"),
                        ("recorded-state", "recorded state"),
                        ("estimate", "estimate"),
                        ("unknown", "? unknown")):
        fill, stroke, dash = NODE_STYLE[kind]
        canvas.rect(x, y - 9, 13, 10, fill, rx=2, stroke=stroke, stroke_width=1.2, dash=dash)
        canvas.text(x + 18, y, label, size=9.0, fill=MUTED)
        x += 18 + len(label) * 5.2 + 24

    y = 760
    canvas.text(LEFT, y, "edge:", size=9.5, fill=MUTED)
    x = LEFT + 46
    for style, label in (("order", "systemd ordering"),
                         ("critical", "critical path"),
                         ("async", "event / async ordering"),
                         ("condition", "condition"),
                         ("independent", "no ordering (recorded fact)")):
        colour, dash, width = EDGE_STYLE[style]
        canvas.line(x, y - 4, x + 26, y - 4, colour, width, dash=dash)
        canvas.text(x + 32, y, label, size=9.0, fill=MUTED)
        x += 32 + len(label) * 5.2 + 22

    canvas.text(LEFT, 786,
                "Ordering arrows are systemd's. Dashed arrows are dependencies systemd does not "
                "order (events, conditions). Dotted arrows record that no ordering exists. "
                "Red boxes and arrows: the audible path.",
                size=8.2, fill=FAINT)
    return canvas.svg()


def main() -> None:
    parser = argparse.ArgumentParser(description="Draw the vip boot timeline and dependency graph.")
    parser.add_argument("timeline", nargs="?", default=str(HERE / "timeline.json"))
    parser.add_argument("--out", default=str(HERE))
    args = parser.parse_args()

    data = json.loads(Path(args.timeline).read_text())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, svg in (("boot-timeline.svg", figure_timeline(data)),
                      ("boot-dependencies.svg", figure_dependencies(data))):
        path = out / name
        path.write_text(svg)
        print(path)


if __name__ == "__main__":
    main()

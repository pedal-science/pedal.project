#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["fonttools", "uharfbuzz"]
# ///
"""The print on the box's face, as the file Tayda's UV printing service takes.

    uv run enclosure/src/box_print.py [--font FILE]

It writes enclosure/print/tayda-1590dd-side-a.pdf, the artwork for side A (the face), and
docs/diagrams/box-face-print.svg, a picture of it on the drilled face for checking by eye.

What is printed (the owner, 2026-11-17): the word pedal.science, small, to the right of the
encoder, running from the rear toward the player with the tops of its letters toward the pedal's
right edge.  It is set as the website sets its name in dark mode (comms, website/src/pages/
index.astro and palette.json): DM Sans Bold, letters 0.03 em closer, "pedal" in the page's text
colour and ".science" in its mark colour.

Tayda's rules (its UV printing guide, V2, 2026-04-22): a PDF whose page is exactly the side's
artboard, 117 x 185 mm for side A of a 1590DD, upright as its Box Tool draws the face; CMYK
only; text as outlines; colour in a layer named CMYK; white ink, which a dark case needs under
every colour, in a layer named RDG_WHITE and painted with a spot colour named RDG_WHITE.  The
printer lays white first, then colour.

The font is not kept here.  It is read from the website's own copy, which pnpm installs under
comms/website/node_modules (DM Sans, SIL Open Font License).
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import zlib

import uharfbuzz as hb
from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import box_layout  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
FONT = os.path.join(os.path.dirname(REPO), "comms", "website", "node_modules", "@fontsource",
                    "dm-sans", "files", "dm-sans-latin-700-normal.woff")
PAGE = (117.0, 185.0)              # Tayda's artboard for side A of a 1590DD, mm
SIZE = 3.8                         # the type's size (its em), mm: about 11 point
TRACK = -0.03                      # em between letters, as the website's wordmark
# Where: beside the encoder, on its line, halfway between a 20 mm knob's edge and the case's
# right edge.  In the pedal's own frame: mm right of the face's centre, mm toward the rear.
RIGHT_OF_CENTRE = 72.0
WORDS = (("pedal", (0.00, 0.06, 0.02, 0.20)),      # #cdc1c9, the site's dark-mode text
         (".science", (0.75, 0.11, 0.00, 0.35)))   # #2a95a7, its marked words
PT = 72.0 / 25.4


class PathPen(BasePen):
    """Collects a glyph's outline as (operator, points) in font units."""

    def __init__(self, glyphs):
        super().__init__(glyphs)
        self.ops: list[tuple[str, tuple]] = []

    def _moveTo(self, p):
        self.ops.append(("m", (p,)))

    def _lineTo(self, p):
        self.ops.append(("l", (p,)))

    def _curveToOne(self, a, b, c):
        self.ops.append(("c", (a, b, c)))

    def _closePath(self):
        self.ops.append(("h", ()))


def outlines(font_path):
    """The words as runs of path operators in mm, x from the text's left end, y from its
    baseline, with the text's length and its x-height."""
    font = TTFont(font_path)
    upm = font["head"].unitsPerEm
    raw = io.BytesIO()
    font.flavor = None
    font.save(raw)
    hb_font = hb.Font(hb.Face(raw.getvalue()))
    order = font.getGlyphOrder()
    glyphs = font.getGlyphSet()
    k = SIZE / upm
    x, runs = 0.0, []
    text = "".join(w for w, _ in WORDS)
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(hb_font, buf, {"kern": True, "liga": False})
    ends, n = [], 0
    for word, _ in WORDS:
        n += len(word)
        ends.append(n)
    run: list[tuple[str, tuple]] = []
    for i, (info, pos) in enumerate(zip(buf.glyph_infos, buf.glyph_positions)):
        pen = PathPen(glyphs)
        glyphs[order[info.codepoint]].draw(pen)
        ox, oy = x + pos.x_offset * k, pos.y_offset * k
        run += [(op, tuple((ox + px * k, oy + py * k) for px, py in pts)) for op, pts in pen.ops]
        x += pos.x_advance * k + TRACK * SIZE
        if i + 1 in ends:
            runs.append(run)
            run = []
    length = x - TRACK * SIZE
    return runs, length, font["OS/2"].sxHeight * k


def placed(runs, length, xheight):
    """The runs moved onto Tayda's artboard: mm from its bottom left corner."""
    box_layout.build("tayda")
    toward_rear = box_layout.D / 2 - box_layout.ENCODER[1]
    # Tayda's frame has the pedal a quarter turn anticlockwise: X = -(toward the rear),
    # Y = right of centre.  The text then reads left to right, upright, on the artboard.
    cx, cy = PAGE[0] / 2 - toward_rear, PAGE[1] / 2 + RIGHT_OF_CENTRE
    x0, y0 = cx - length / 2, cy - xheight / 2
    moved = [[(op, tuple((x0 + px, y0 + py) for px, py in pts)) for op, pts in run]
             for run in runs]
    return moved, (cx - PAGE[0] / 2, cy - PAGE[1] / 2)


def pdf_path(run):
    out = []
    for op, pts in run:
        nums = " ".join(f"{v * PT:.3f}" for p in pts for v in p)
        out.append(f"{nums} {op}".strip())
    return "\n".join(out) + "\nf\n"


def write_pdf(path, runs):
    white = "/OC /LW BDC\n/CSW cs 1 scn\n" + "".join(pdf_path(r) for r in runs) + "EMC\n"
    colour = "/OC /LC BDC\n"
    for run, (_, cmyk) in zip(runs, WORDS):
        colour += " ".join(f"{v:.2f}" for v in cmyk) + " k\n" + pdf_path(run)
    colour += "EMC\n"
    stream = zlib.compress((white + colour).encode("ascii"))
    w, h = PAGE[0] * PT, PAGE[1] * PT
    box = f"[0 0 {w:.4f} {h:.4f}]"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R /OCProperties << /OCGs [5 0 R 6 0 R] "
        "/D << /Order [5 0 R 6 0 R] /ON [5 0 R 6 0 R] >> >> >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox {box} /TrimBox {box} /ArtBox {box} "
        "/Contents 4 0 R /Resources << /ColorSpace << /CSW 7 0 R >> "
        "/Properties << /LW 5 0 R /LC 6 0 R >> >> >>",
        (f"<< /Length {len(stream)} /Filter /FlateDecode >>\nstream\n".encode("ascii")
         + stream + b"\nendstream"),
        "<< /Type /OCG /Name (RDG_WHITE) >>",
        "<< /Type /OCG /Name (CMYK) >>",
        "[/Separation /RDG_WHITE /DeviceCMYK << /FunctionType 2 /Domain [0 1] "
        "/C0 [0 0 0 0] /C1 [0.25 0.25 0.25 0.25] /N 1 >>]",
    ]
    out = bytearray(b"%PDF-1.6\n%\xe2\xe3\xcf\xd3\n")
    at = []
    for i, body in enumerate(objs, 1):
        at.append(len(out))
        out += f"{i} 0 obj\n".encode("ascii")
        out += body if isinstance(body, bytes) else body.encode("ascii")
        out += b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode("ascii")
    out += "".join(f"{a:010d} 00000 n \n" for a in at).encode("ascii")
    out += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
            .encode("ascii"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(out)


def svg_path(run):
    """A run as an SVG path, y turned over (the artboard's y runs up, SVG's down)."""
    d = []
    for op, pts in run:
        nums = " ".join(f"{px:.3f} {PAGE[1] - py:.3f}" for px, py in pts)
        d.append({"m": "M", "l": "L", "c": "C", "h": "Z"}[op] + nums)
    return "".join(d)


def write_svg(path, runs):
    """The face as the player sees it (the artboard turned a quarter turn clockwise), with the
    drilled holes, on a black ground."""
    with contextlib.redirect_stdout(io.StringIO()):
        rows = box_layout.tayda_rows()
    w, h = PAGE
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-4 -4 {h + 8} {w + 8}" '
         f'width="{(h + 8) * 5}" height="{(w + 8) * 5}">',
         f'<rect x="-4" y="-4" width="{h + 8}" height="{w + 8}" fill="#ffffff"/>',
         f'<g transform="translate({h} 0) rotate(90)">',
         f'<rect width="{w}" height="{h}" rx="3" fill="#151515"/>']
    for side, _, x, y, hw, hh, is_round in rows:
        if side != "A":
            continue
        px, py = w / 2 + x, h / 2 - y
        if is_round:
            o.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="{hw / 2:.2f}" fill="#6d6d6d"/>')
        else:
            o.append(f'<rect x="{px - hw / 2:.2f}" y="{py - hh / 2:.2f}" width="{hw:.2f}" '
                     f'height="{hh:.2f}" fill="#6d6d6d"/>')
    for run, (_, (c, m, y, k)) in zip(runs, WORDS):
        rgb = tuple(round(255 * (1 - v) * (1 - k)) for v in (c, m, y))
        o.append(f'<path d="{svg_path(run)}" fill="rgb{rgb}"/>')
    o.append("</g></svg>")
    with open(path, "w") as f:
        f.write("\n".join(o) + "\n")


def main():
    font = sys.argv[sys.argv.index("--font") + 1] if "--font" in sys.argv else FONT
    runs, length, xheight = outlines(font)
    runs, (tx, ty) = placed(runs, length, xheight)
    pdf = os.path.join(REPO, "enclosure", "print", "tayda-1590dd-side-a.pdf")
    svg = os.path.join(REPO, "docs", "diagrams", "box-face-print.svg")
    write_pdf(pdf, runs)
    write_svg(svg, runs)
    xs = [px for run in runs for _, pts in run for px, _ in pts]
    ys = [py for run in runs for _, pts in run for _, py in pts]
    print(f"type {SIZE} mm ({SIZE * PT:.1f} pt), x-height {xheight:.2f} mm, text {length:.1f} mm long")
    print(f"on Tayda's side A: centre X {tx:+.1f}, Y {ty:+.1f} mm; ink from "
          f"X {min(xs) - PAGE[0] / 2:+.1f} to {max(xs) - PAGE[0] / 2:+.1f}, "
          f"Y {min(ys) - PAGE[1] / 2:+.1f} to {max(ys) - PAGE[1] / 2:+.1f}")
    print(f"wrote {pdf}\nwrote {svg}")


if __name__ == "__main__":
    main()

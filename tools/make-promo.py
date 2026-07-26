"""Render the claude-markitdown-hook promo's motion-graphics core (1920x1080 @ 24fps).

This carries the story the product actually exists for: the same PDF, the same
question, answered wrong and then right. Exact text matters throughout - the
terminal output, the hook's message, the install command - and generative video
models garble long strings, so every character here is rendered from source.

Designed to be stitched between two AI-generated bookends by tools/stitch-promo.sh:

  [ AI hero shot ] -> [ THIS: the story ] -> [ AI end card ]

Design rules:
  * No bounce / spring / elastic motion. Fades and micro-slides (<= 8px) only.
  * No dead space. Compositions fill the frame; elements are large; holds short.
  * Every string is rendered from source text, so nothing on screen can drift
    out of sync with what the tool really prints.
  * The document on screen is a webpage screenshot, which is the real origin of
    this project - no invented records, no fabricated figures.

Usage:  python tools/make-promo.py [--outdir DIR]
Output: DIR/core.mp4 (needs ffmpeg on PATH)
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1920, 1080, 24

# Palette - BG is chosen to match the AI end card so the stitch is seamless.
BG = (8, 13, 24)
PANEL = (15, 22, 38)
WIN = (13, 19, 33)
EDGE = (34, 47, 72)
TXT = (232, 238, 246)
DIM = (138, 152, 174)
BLUE = (59, 130, 246)
GREEN = (16, 185, 129)
RED = (239, 68, 68)
AMBER = (217, 160, 42)
WHITE = (255, 255, 255)

FONTS = {
    "bold": "C:/Windows/Fonts/segoeuib.ttf",
    "semi": "C:/Windows/Fonts/seguisb.ttf",
    "ui": "C:/Windows/Fonts/segoeui.ttf",
    "mono": "C:/Windows/Fonts/consola.ttf",
    "monob": "C:/Windows/Fonts/consolab.ttf",
}
FALLBACKS = {
    "bold": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "semi": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "ui": ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
    "mono": ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"],
    "monob": ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"],
}
_cache = {}


def F(kind, size):
    key = (kind, size)
    if key not in _cache:
        for path in [FONTS[kind]] + FALLBACKS.get(kind, []):
            if os.path.isfile(path):
                _cache[key] = ImageFont.truetype(path, size)
                break
        else:
            _cache[key] = ImageFont.load_default()
    return _cache[key]


_probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))


def tw(s, f):
    return _probe.textlength(s, font=f)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def ease(t):
    """Smooth ease-out with NO overshoot (deliberately not a spring)."""
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def fade(color, a):
    return lerp(BG, color, max(0.0, min(1.0, a)))


def seg(t, start, span):
    """Progress of a sub-animation occupying [start, start+span) of a scene."""
    return max(0.0, min(1.0, (t - start) / span))


def base():
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    for x in range(0, W, 64):
        for y in range(0, H, 64):
            d.point((x, y), fill=(12, 20, 36))
    return im


def shadowed_panel(im, box, radius=18, fill=WIN, edge=EDGE, width=2):
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle(
        [box[0] + 4, box[1] + 12, box[2] + 4, box[3] + 12],
        radius=radius, fill=(0, 0, 0, 140),
    )
    blurred = sh.filter(ImageFilter.GaussianBlur(14))
    im.paste(Image.alpha_composite(im.convert("RGBA"), blurred).convert("RGB"), (0, 0))
    ImageDraw.Draw(im).rounded_rectangle(box, radius=radius, fill=fill,
                                         outline=edge, width=width)


def window(im, box, title, accent=DIM, dim=1.0):
    """Terminal-style window. Returns content origin (x, y)."""
    shadowed_panel(im, box, fill=lerp(BG, WIN, dim))
    d = ImageDraw.Draw(im)
    bar = box[1] + 60
    d.line([box[0] + 2, bar, box[2] - 2, bar], fill=lerp(BG, EDGE, dim), width=2)
    for i, c in enumerate(((233, 106, 94), AMBER, GREEN)):
        cx = box[0] + 38 + i * 34
        d.ellipse([cx - 9, box[1] + 21, cx + 9, box[1] + 39], fill=lerp(BG, c, dim))
    d.text((box[0] + 152, box[1] + 17), title, font=F("ui", 26), fill=fade(accent, dim))
    return box[0] + 46, bar + 30


HEAD_Y = 82


def headline(im, text, alpha=1.0, sub=None, sub_alpha=None, colour=TXT):
    d = ImageDraw.Draw(im)
    d.text((120, HEAD_Y), text, font=F("bold", 64), fill=fade(colour, alpha))
    if sub:
        d.text((123, HEAD_Y + 86), sub, font=F("ui", 34),
               fill=fade(DIM, alpha if sub_alpha is None else sub_alpha))


def typed(s, t):
    """Character-accurate typing. Returns the visible prefix."""
    return s[:int(len(s) * max(0.0, min(1.0, t)))]


def caret(d, x, y, f, alpha, frame):
    if alpha > 0.05 and (frame // 8) % 2 == 0:
        h = f.size + 6
        d.rectangle([x, y + 2, x + 12, y + h], fill=fade(TXT, alpha * 0.85))


def badge(im, box, label, colour, alpha=1.0, size=28):
    """Pill with centred text. The box is widened if the label would not fit."""
    d = ImageDraw.Draw(im)
    f = F("semi", size)
    need = tw(label, f) + 40
    box = list(box)
    if box[2] - box[0] < need:
        box[2] = box[0] + need
    d.rounded_rectangle(box, radius=8, fill=lerp(BG, colour, 0.16 * alpha),
                        outline=fade(colour, alpha), width=2)
    d.text((box[0] + (box[2] - box[0]) / 2 - tw(label, f) / 2,
            box[1] + (box[3] - box[1]) / 2 - size * 0.72), label,
           font=f, fill=fade(colour, alpha))


def check(d, cx, cy, r, colour, alpha, ok=True):
    d.ellipse([cx - r, cy - r, cx + r, cy + r],
              outline=fade(colour, alpha), width=4)
    c = fade(colour, alpha)
    if ok:
        d.line([cx - r * 0.42, cy + r * 0.04, cx - r * 0.10, cy + r * 0.38],
               fill=c, width=5)
        d.line([cx - r * 0.10, cy + r * 0.38, cx + r * 0.46, cy - r * 0.34],
               fill=c, width=5)
    else:
        k = r * 0.38
        d.line([cx - k, cy - k, cx + k, cy + k], fill=c, width=5)
        d.line([cx + k, cy - k, cx - k, cy + k], fill=c, width=5)


# --------------------------------------------------------------------------
# content - every string below is what the tool really produces
# --------------------------------------------------------------------------
DOC = "api-docs-screenshot.pdf"
QUESTION = "what rate limits does this page document?"

WRONG = ["The PDF contains no extractable text.", "It appears to be empty."]
RIGHT = ["The page documents three tiers:", "60, 600 and 4,000 requests/min."]

HOOK_MSG = [
    "NO USABLE TEXT extracted from api-docs-screenshot.pdf",
    "(no text extracted). This is an image-based/scanned PDF -",
    "text extraction cannot see into it and no .md was written.",
    "Read the ORIGINAL file natively with the Read tool;",
    "Claude's vision can read it.",
    "Do NOT report the document as empty.",
]

POINTER = [
    "[markitdown] report.pdf was converted to markdown at",
    "~/.claude/markitdown-cache/report-a1b2c3d4.md",
    "(14973 bytes, 304 lines, 14472 chars, 20 page(s)).",
]

INSTALL = "claude plugin marketplace add AndrewAvery7/claude-markitdown-hook"
REPO = "github.com/AndrewAvery7/claude-markitdown-hook"

BIG = [120, 250, 1800, 1000]


# --------------------------------------------------------------------------
# scenes
# --------------------------------------------------------------------------

def scene_prompt(fr, n):
    """A screenshot PDF and a plain question. The setup."""
    t = fr / n
    im = base()
    d = ImageDraw.Draw(im)
    headline(im, "You hand Claude a PDF.", ease(seg(t, 0.02, 0.16)),
             sub="A page from the docs, saved straight out of the browser.",
             sub_alpha=ease(seg(t, 0.12, 0.16)))

    a = ease(seg(t, 0.22, 0.18))
    if a > 0.01:
        ox, oy = window(im, BIG, "claude code", dim=a)
        f = F("mono", 34)
        d.text((ox, oy + 8), "> ", font=f, fill=fade(BLUE, a))
        line = "read " + DOC
        vis = typed(line, ease(seg(t, 0.30, 0.26)))
        d.text((ox + tw("> ", f), oy + 8), vis, font=f, fill=fade(TXT, a))
        caret(d, ox + tw("> " + vis, f) + 3, oy + 8, f, ease(seg(t, 0.30, 0.26)), fr)

        a2 = ease(seg(t, 0.60, 0.16))
        if a2 > 0.01:
            d.text((ox, oy + 78), "> ", font=f, fill=fade(BLUE, a2))
            q = typed(QUESTION, ease(seg(t, 0.62, 0.30)))
            d.text((ox + tw("> ", f), oy + 78), q, font=f, fill=fade(TXT, a2))
            caret(d, ox + tw("> " + q, f) + 3, oy + 78, f,
                  ease(seg(t, 0.62, 0.30)), fr)

        # the document itself, as a page of pure image
        a3 = ease(seg(t, 0.40, 0.20))
        if a3 > 0.01:
            px0, py0, px1, py1 = 1180, oy + 60, 1690, oy + 620
            d.rounded_rectangle([px0, py0, px1, py1], radius=10,
                                fill=lerp(BG, (26, 34, 54), a3),
                                outline=fade(EDGE, a3), width=2)
            for i in range(9):
                yy = py0 + 46 + i * 56
                ww = (px1 - px0 - 80) * (0.95 if i % 3 else 0.6)
                d.rounded_rectangle([px0 + 40, yy, px0 + 40 + ww, yy + 20],
                                    radius=6, fill=lerp(BG, (46, 60, 88), a3 * 0.9))
            badge(im, [px0 + 40, py1 - 74, px0 + 300, py1 - 24],
                  "IMAGE  -  NO TEXT LAYER", AMBER, a3, 24)
    return im


def scene_silent_failure(fr, n):
    """markitdown exits 0 and writes nothing. The trap."""
    t = fr / n
    im = base()
    d = ImageDraw.Draw(im)
    headline(im, "The converter reports success.", ease(seg(t, 0.02, 0.14)),
             sub="It found no text. That is not an error, so it exits zero.",
             sub_alpha=ease(seg(t, 0.10, 0.14)))

    a = ease(seg(t, 0.18, 0.14))
    # Sized to the content: a tall empty window under five lines reads as an
    # unfinished frame rather than a deliberate one.
    ox, oy = window(im, [120, 250, 1800, 726], "terminal", dim=a)
    fm = F("mono", 36)
    fb = F("monob", 36)
    lh = 66
    rows = [
        (0.24, "$ ", "markitdown api-docs-screenshot.pdf -o out.md", TXT, None),
        (0.40, "$ ", "echo $?", TXT, None),
        (0.50, "", "0", GREEN, "exit code says success"),
        (0.62, "$ ", "wc -c out.md", TXT, None),
        (0.72, "", "0 out.md", RED, "zero bytes were written"),
    ]
    for i, (at, prompt, text, colour, note) in enumerate(rows):
        aa = ease(seg(t, at, 0.09))
        if aa < 0.01:
            continue
        y = oy + 14 + i * lh
        x = ox
        if prompt:
            d.text((x, y), prompt, font=fm, fill=fade(BLUE, aa))
            x += tw(prompt, fm)
        d.text((x, y), text, font=fb if colour in (GREEN, RED) else fm,
               fill=fade(colour, aa))
        if note:
            nf = F("ui", 30)
            nx = ox + 700
            d.text((nx, y + 4), "<-  " + note, font=nf, fill=fade(colour, aa * 0.95))

    a2 = ease(seg(t, 0.84, 0.14))
    if a2 > 0.01:
        f = F("bold", 58)
        s = "Success and empty, at the same time."
        d.text((W / 2 - tw(s, f) / 2, 824), s, font=f, fill=fade(AMBER, a2))
    return im


def scene_the_lie(fr, n):
    """The consequence: a confident, wrong answer."""
    t = fr / n
    im = base()
    d = ImageDraw.Draw(im)
    headline(im, "So the answer comes back wrong.", ease(seg(t, 0.02, 0.14)),
             sub="Nothing failed loudly, so nothing looks broken.",
             sub_alpha=ease(seg(t, 0.10, 0.14)))

    a = ease(seg(t, 0.20, 0.16))
    box = [220, 300, 1700, 720]
    if a > 0.01:
        shadowed_panel(im, box, fill=lerp(BG, PANEL, a))
        d.rounded_rectangle([box[0], box[1], box[0] + 9, box[3]], radius=4,
                            fill=fade(RED, a))
        f = F("ui", 27)
        d.text((box[0] + 46, box[1] + 34), "CLAUDE", font=F("semi", 26),
               fill=fade(DIM, a))
        fb = F("ui", 52)
        for i, line in enumerate(WRONG):
            aa = ease(seg(t, 0.32 + i * 0.10, 0.14))
            d.text((box[0] + 46, box[1] + 96 + i * 74), line, font=fb,
                   fill=fade(TXT, aa))

    a3 = ease(seg(t, 0.60, 0.16))
    if a3 > 0.01:
        check(d, 1560, 400, 46, RED, a3, ok=False)

    a4 = ease(seg(t, 0.72, 0.16))
    if a4 > 0.01:
        f = F("bold", 50)
        s = "The page was full of text. Claude never saw it."
        d.text((W / 2 - tw(s, f) / 2, 830), s, font=f, fill=fade(RED, a4))
    return im


def scene_measure(fr, n):
    """The discriminator: characters per page."""
    t = fr / n
    im = base()
    d = ImageDraw.Draw(im)
    headline(im, "Grade the output, not the exit code.", ease(seg(t, 0.02, 0.14)),
             sub="Characters per page separates the two cleanly.",
             sub_alpha=ease(seg(t, 0.10, 0.14)))

    bars = [
        ("webpage screenshot", 0, RED),
        ("scanned certificate", 39, RED),
        ("two-page document", 932, GREEN),
        ("twenty-page deck", 664, GREEN),
    ]
    x0, top, bw, gap = 520, 340, 1120, 116
    scale = 1000.0
    fl = F("ui", 34)
    fv = F("monob", 36)
    for i, (label, val, colour) in enumerate(bars):
        aa = ease(seg(t, 0.20 + i * 0.09, 0.16))
        if aa < 0.01:
            continue
        y = top + i * gap
        # Right-aligned so the longest label cannot run into the bars.
        d.text((x0 - 34 - tw(label, fl), y + 6), label, font=fl,
               fill=fade(DIM, aa))
        d.rounded_rectangle([x0, y, x0 + bw, y + 52], radius=8,
                            fill=lerp(BG, PANEL, aa), outline=fade(EDGE, aa), width=2)
        grow = ease(seg(t, 0.24 + i * 0.09, 0.22))
        wpx = int(bw * min(1.0, val / scale) * grow)
        if wpx > 6:
            d.rounded_rectangle([x0, y, x0 + wpx, y + 52], radius=8,
                                fill=fade(colour, aa * 0.92))
        d.text((x0 + bw + 30, y + 6), "{:,}".format(val), font=fv,
               fill=fade(colour, aa))

    a2 = ease(seg(t, 0.62, 0.16))
    if a2 > 0.01:
        tx = x0 + int(bw * (100 / scale))
        for yy in range(top - 24, top + 3 * gap + 84, 16):
            d.line([tx, yy, tx, yy + 8], fill=fade(AMBER, a2 * 0.9), width=3)
        f = F("semi", 30)
        d.text((tx - tw("threshold  100", f) / 2, top + 3 * gap + 96),
               "threshold  100", font=f, fill=fade(AMBER, a2))

    a3 = ease(seg(t, 0.80, 0.16))
    if a3 > 0.01:
        f = F("bold", 46)
        s = "Below the line, there is nothing worth reading."
        d.text((W / 2 - tw(s, f) / 2, 918), s, font=f, fill=fade(TXT, a3))
    return im


def scene_honest(fr, n):
    """What the hook actually says instead."""
    t = fr / n
    im = base()
    d = ImageDraw.Draw(im)
    headline(im, "So it says so.", ease(seg(t, 0.02, 0.14)),
             sub="No file is written, and nothing is cached.",
             sub_alpha=ease(seg(t, 0.10, 0.14)))

    a = ease(seg(t, 0.18, 0.14))
    box = [180, 300, 1740, 800]
    if a > 0.01:
        shadowed_panel(im, box, fill=lerp(BG, WIN, a))
        d.rounded_rectangle([box[0], box[1], box[0] + 9, box[3]], radius=4,
                            fill=fade(AMBER, a))
        f = F("mono", 34)
        for i, line in enumerate(HOOK_MSG):
            aa = ease(seg(t, 0.26 + i * 0.075, 0.12))
            if aa < 0.01:
                continue
            colour = TXT
            if "Do NOT" in line:
                colour = AMBER
            elif "Read the ORIGINAL" in line or "vision" in line:
                colour = GREEN
            d.text((box[0] + 48, box[1] + 44 + i * 62), line,
                   font=F("monob", 34) if colour is not TXT else f,
                   fill=fade(colour, aa))

    a2 = ease(seg(t, 0.82, 0.16))
    if a2 > 0.01:
        f = F("bold", 48)
        s = "An honest gap beats a confident blank."
        d.text((W / 2 - tw(s, f) / 2, 876), s, font=f, fill=fade(TXT, a2))
    return im


def scene_truth(fr, n):
    """The payoff: the same question, answered correctly."""
    t = fr / n
    im = base()
    d = ImageDraw.Draw(im)
    headline(im, "Claude reads it with its own eyes.", ease(seg(t, 0.02, 0.14)),
             sub="Same PDF. Same question.",
             sub_alpha=ease(seg(t, 0.10, 0.14)))

    a = ease(seg(t, 0.20, 0.16))
    box = [220, 300, 1700, 720]
    if a > 0.01:
        shadowed_panel(im, box, fill=lerp(BG, PANEL, a))
        d.rounded_rectangle([box[0], box[1], box[0] + 9, box[3]], radius=4,
                            fill=fade(GREEN, a))
        d.text((box[0] + 46, box[1] + 34), "CLAUDE", font=F("semi", 26),
               fill=fade(DIM, a))
        fb = F("ui", 52)
        for i, line in enumerate(RIGHT):
            aa = ease(seg(t, 0.32 + i * 0.11, 0.14))
            d.text((box[0] + 46, box[1] + 96 + i * 74), line, font=fb,
                   fill=fade(TXT, aa))

    a3 = ease(seg(t, 0.62, 0.16))
    if a3 > 0.01:
        check(d, 1560, 400, 46, GREEN, a3, ok=True)

    a4 = ease(seg(t, 0.74, 0.16))
    if a4 > 0.01:
        f = F("bold", 50)
        s = "Nothing was lost. It just had to be told."
        d.text((W / 2 - tw(s, f) / 2, 830), s, font=f, fill=fade(GREEN, a4))
    return im


def scene_economics(fr, n):
    """The other half: a pointer, not the contents."""
    t = fr / n
    im = base()
    d = ImageDraw.Draw(im)
    headline(im, "And when it does convert -", ease(seg(t, 0.02, 0.14)),
             sub="you get a pointer, not the document.",
             sub_alpha=ease(seg(t, 0.10, 0.14)))

    a = ease(seg(t, 0.20, 0.16))
    box = [180, 300, 1740, 590]
    if a > 0.01:
        shadowed_panel(im, box, fill=lerp(BG, WIN, a))
        d.rounded_rectangle([box[0], box[1], box[0] + 9, box[3]], radius=4,
                            fill=fade(GREEN, a))
        f = F("mono", 34)
        for i, line in enumerate(POINTER):
            aa = ease(seg(t, 0.26 + i * 0.09, 0.13))
            if aa < 0.01:
                continue
            d.text((box[0] + 48, box[1] + 48 + i * 62), line, font=f,
                   fill=fade(TXT if i else GREEN, aa))

    a2 = ease(seg(t, 0.56, 0.18))
    if a2 > 0.01:
        f = F("ui", 40)
        fb2 = F("bold", 44)
        rows = [
            ("a 20-page deck referenced in a prompt", DIM),
            ("costs about 400 characters of context", TXT),
            ("until Claude actually needs it", TXT),
        ]
        for i, (s, c) in enumerate(rows):
            aa = ease(seg(t, 0.58 + i * 0.09, 0.14))
            d.text((W / 2 - tw(s, fb2 if i else f) / 2, 668 + i * 74), s,
                   font=fb2 if i else f, fill=fade(c, aa))
    return im


def scene_install(fr, n):
    """One command."""
    t = fr / n
    im = base()
    d = ImageDraw.Draw(im)

    a0 = ease(seg(t, 0.02, 0.16))
    f = F("bold", 62)
    s = "One command."
    d.text((W / 2 - tw(s, f) / 2, 246), s, font=f, fill=fade(TXT, a0))

    a = ease(seg(t, 0.20, 0.14))
    box = [148, 384, 1772, 560]
    if a > 0.01:
        shadowed_panel(im, box, fill=lerp(BG, WIN, a))
        # Sized so the full command plus its caret clears the panel edge.
        fm = F("mono", 34)
        x = box[0] + 52
        y = box[1] + 66
        d.text((x, y), "$ ", font=fm, fill=fade(BLUE, a))
        vis = typed(INSTALL, ease(seg(t, 0.26, 0.40)))
        d.text((x + tw("$ ", fm), y), vis, font=fm, fill=fade(TXT, a))
        caret(d, x + tw("$ " + vis, fm) + 3, y, fm, ease(seg(t, 0.26, 0.40)), fr)

    a2 = ease(seg(t, 0.70, 0.16))
    if a2 > 0.01:
        chips = ["Windows", "macOS", "Linux", "MIT", "Python 3.10+"]
        fc = F("semi", 30)
        widths = [tw(c, fc) + 62 for c in chips]
        total = sum(widths) + 22 * (len(chips) - 1)
        x = W / 2 - total / 2
        for c, wpx in zip(chips, widths):
            badge(im, [x, 640, x + wpx, 700], c, BLUE, a2, 30)
            x += wpx + 22

    a3 = ease(seg(t, 0.82, 0.16))
    if a3 > 0.01:
        fr2 = F("ui", 40)
        d.text((W / 2 - tw(REPO, fr2) / 2, 782), REPO, font=fr2,
               fill=fade(DIM, a3))
        half = 430
        for i in range(half * 2):
            d.line([W / 2 - half + i, 878, W / 2 - half + i, 885],
                   fill=fade(lerp(BLUE, GREEN, i / (half * 2)), a3))
    return im


# Frame counts are tuned for READABILITY. All animation inside a scene is a
# fraction of its length, so raising a number genuinely slows the motion
# (including typing) rather than holding a static frame for longer.
SCENES = [
    (scene_prompt, 150),          # 6.25s - read the prompt and see the page
    (scene_silent_failure, 190),  # 7.92s - five terminal lines, the core reveal
    (scene_the_lie, 155),         # 6.46s - the wrong answer lands
    (scene_measure, 190),         # 7.92s - four bars grow, threshold appears
    (scene_honest, 195),          # 8.13s - six lines of the real message
    (scene_truth, 160),           # 6.67s - the payoff
    (scene_economics, 165),       # 6.88s
    (scene_install, 175),         # 7.29s - read and memorise the command
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir",
                    default=str(Path(__file__).resolve().parent.parent / "assets"))
    args = ap.parse_args()
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    tmp = Path(tempfile.mkdtemp(prefix="cmh-promo-"))
    idx = 0
    for fn, count in SCENES:
        for f in range(count):
            fn(f, count).save(tmp / "f{:05d}.png".format(idx))
            idx += 1
        print("  {}: {} frames".format(fn.__name__, count))
    print("total {} frames = {:.1f}s".format(idx, idx / FPS))

    if not shutil.which("ffmpeg"):
        print("ffmpeg not found - frames left in", tmp)
        return 1
    core = out / "core.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(FPS), "-i", str(tmp / "f%05d.png"),
         "-c:v", "libx264", "-preset", "slow", "-crf", "18",
         "-pix_fmt", "yuv420p", str(core)],
        check=True, capture_output=True,
    )
    print("wrote", core)
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

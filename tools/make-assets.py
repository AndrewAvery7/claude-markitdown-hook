"""Generate the logo and social card.

Everything is drawn from primitives and system fonts, so the assets are
reproducible: re-running this regenerates them byte-for-byte rather than
depending on a design file nobody has.

    python tools/make-assets.py

Outputs assets/logo.png, assets/logo-dark.png and assets/social-card.png.
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

SCALE = 4  # render large, downsample once, for clean antialiasing
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets")

FONT_DIRS = [
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"),
    r"C:\Windows\Fonts",
    "/usr/share/fonts/truetype/dejavu",
    "/Library/Fonts",
    "/System/Library/Fonts",
]
FONT_CANDIDATES = {
    "bold": ["Inter-Variable.ttf", "Poppins-Bold.ttf", "segoeuib.ttf",
             "arialbd.ttf", "DejaVuSans-Bold.ttf"],
    "medium": ["Inter-Variable.ttf", "Poppins-Medium.ttf", "segoeui.ttf",
               "arial.ttf", "DejaVuSans.ttf"],
    "mono": ["CascadiaCode.ttf", "CascadiaMono.ttf", "JetBrainsMono-Regular.ttf",
             "consola.ttf", "Menlo.ttc", "DejaVuSansMono.ttf"],
}

LIGHT = {
    "accent": (37, 99, 235),
    "strong": (15, 23, 42),
    "muted": (100, 116, 139),
    "badge_fg": (255, 255, 255),
    "card_bg": (255, 255, 255),
    "card_panel": (241, 245, 249),
    "ok": (16, 185, 129),
    "bad": (239, 68, 68),
}
DARK = {
    "accent": (59, 130, 246),
    "strong": (241, 245, 249),
    "muted": (148, 163, 184),
    "badge_fg": (255, 255, 255),
    "card_bg": (13, 17, 23),
    "card_panel": (22, 27, 34),
    "ok": (52, 211, 153),
    "bad": (248, 113, 113),
}

# The social card deliberately shares its ground, texture and layout with the
# claude-codex-bridge card so the two repos read as one shop. Every value below
# except ok/bad was sampled out of that PNG, which is the only copy of the
# design that exists - it was committed as a finished asset with no generator.
#
# Its accent pair is Claude clay + OpenAI green, a meaning specific to a bridge
# between those two. Only the clay carries over; the greens and reds here stay
# the hook's own, because on this card they are not decoration - they encode
# converted versus no-usable-text, and must not be read as a vendor colour.
CARD = {
    "ground": (11, 18, 32),
    "glow_warm": (27, 26, 36),
    "glow_cool": (11, 28, 38),
    "grid": (17, 26, 43),
    "panel": (17, 27, 46),
    "pill": (18, 29, 48),
    "border": (43, 57, 82),
    "strong": (248, 250, 252),
    "muted": (139, 147, 167),
    "dim": (94, 104, 126),
    # The panel's skeleton rows carry a deliberate two-step hierarchy on the
    # bridge card. Drawing them all in one tone - or in the grid tone, which is
    # within three points of the panel fill - erases them entirely.
    "skel": (81, 96, 120),
    "skel_dim": (53, 68, 93),
    "clay": (217, 119, 87),
    "ok": (16, 185, 129),
    "bad": (239, 68, 68),
    # make_logo and badge() read these two keys.
    "accent": (217, 119, 87),
    "badge_fg": (255, 255, 255),
}


def find_font(kind):
    for name in FONT_CANDIDATES[kind]:
        for d in FONT_DIRS:
            if not d:
                continue
            p = os.path.join(d, name)
            if os.path.isfile(p):
                return p
    return None


def load(kind, size):
    path = find_font(kind)
    if not path:
        return ImageFont.load_default()
    f = ImageFont.truetype(path, size)
    # Inter ships as a variable font; pick a real weight rather than accepting
    # whatever the default instance happens to be.
    if path.endswith("Inter-Variable.ttf"):
        try:
            f.set_variation_by_name("Bold" if kind == "bold" else "Regular")
        except Exception:
            pass
    return f


def badge(draw, x, y, size, c):
    """Accent tile holding a down-arrow over a bar: convert down to markdown."""
    r = size * 0.24
    draw.rounded_rectangle([x, y, x + size, y + size], radius=r, fill=c["accent"])

    cx = x + size / 2
    stem_w = size * 0.10
    top = y + size * 0.20
    mid = y + size * 0.50
    draw.rounded_rectangle(
        [cx - stem_w / 2, top, cx + stem_w / 2, mid],
        radius=stem_w / 2, fill=c["badge_fg"],
    )
    head = size * 0.20
    draw.polygon(
        [(cx - head, mid - head * 0.35), (cx + head, mid - head * 0.35),
         (cx, mid + head * 0.75)],
        fill=c["badge_fg"],
    )
    bar_y = y + size * 0.76
    bar_h = size * 0.09
    draw.rounded_rectangle(
        [x + size * 0.22, bar_y, x + size * 0.78, bar_y + bar_h],
        radius=bar_h / 2, fill=c["badge_fg"],
    )


def wordmark_parts(c, size):
    """claude- / markitdown / -hook, emphasising the distinctive middle."""
    bold = load("bold", size)
    med = load("medium", size)
    return [("claude-", med, c["muted"]),
            ("markitdown", bold, c["strong"]),
            ("-hook", med, c["muted"])]


def wordmark_width(draw, c, size):
    return sum(draw.textlength(t, font=f) for t, f, _ in wordmark_parts(c, size))


def wordmark(draw, x, y, c, size):
    for text, font, colour in wordmark_parts(c, size):
        draw.text((x, y), text, font=font, fill=colour, anchor="ls")
        x += draw.textlength(text, font=font)
    return x


def fit_font(draw, text, kind, size, max_w):
    """Largest font at or below size whose text fits max_w."""
    while size > 8:
        f = load(kind, size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= SCALE
    return load(kind, size)


def make_logo(colours, path, divisor=SCALE):
    """Render the lockup. A smaller divisor yields a larger final image.

    The promo's end card needs the logo at roughly half the frame width, so it
    is emitted at divisor=2 rather than upscaling the README-sized file, which
    would be visibly soft on a 1080p card.
    """
    h = 120 * SCALE
    text_size = 38 * SCALE
    text_x = 104 * SCALE
    # Measure on a throwaway canvas so the real one is sized to the content
    # instead of cropping it, which silently ate "-hook" the first time.
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    w = int(text_x + wordmark_width(probe, colours, text_size)) + 12 * SCALE

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    badge(d, 8 * SCALE, (120 - 76) // 2 * SCALE, 76 * SCALE, colours)
    wordmark(d, text_x, 76 * SCALE, colours, text_size)
    img = img.resize((img.width // divisor, img.height // divisor), Image.LANCZOS)
    img.save(path)
    return img.size


def s(v):
    """Final-image pixels to render-space pixels, so the layout below can be
    written in the 1280x640 coordinates you actually see."""
    return int(v * SCALE)


def glow(img, cx, cy, radius, colour):
    """Soft radial wash over the ground.

    PIL has no gradient primitive. Computing a 64x64 luminance mask in Python
    and scaling it up is both smoother and cheaper than stacking one ellipse
    per alpha step, which bands visibly at this size.
    """
    n = 64
    mask = Image.new("L", (n, n), 0)
    px = mask.load()
    half = (n - 1) / 2
    for j in range(n):
        for i in range(n):
            dx, dy = (i - half) / half, (j - half) / half
            v = max(0.0, 1.0 - (dx * dx + dy * dy) ** 0.5)
            px[i, j] = int(255 * v * v)  # squared: reads as light, not a disc
    mask = mask.resize((radius * 2, radius * 2), Image.LANCZOS)
    img.paste(Image.new("RGB", mask.size, colour), (cx - radius, cy - radius), mask)


def grid(draw, w, h, colour, step):
    """Faint square rule. Sits just above the ground so it registers as texture
    rather than as lines."""
    width = max(1, SCALE // 4)
    for x in range(0, w, step):
        draw.line([(x, 0), (x, h)], fill=colour, width=width)
    for y in range(0, h, step):
        draw.line([(0, y), (w, y)], fill=colour, width=width)


def gradient_arrow(draw, x0, x1, y, c0, c1, weight):
    """Horizontal rule that crossfades c0 into c1, with a solid head."""
    span = max(1.0, float(x1 - x0))
    for x in range(int(x0), int(x1)):
        t = (x - x0) / span
        draw.line([(x, y), (x, y + weight)], width=1,
                  fill=tuple(int(a + (b - a) * t) for a, b in zip(c0, c1)))
    head = weight * 3.2
    draw.polygon([(x1, y - head * 0.5), (x1, y + weight + head * 0.5),
                  (x1 + head, y + weight / 2)], fill=c1)


def tracked(draw, x, y, text, font, colour, tracking):
    """Letterspaced run. PIL cannot track text, so each glyph is placed."""
    for ch in text:
        draw.text((x, y), ch, font=font, fill=colour, anchor="ls")
        x += draw.textlength(ch, font=font) + tracking
    return x


def mock_window(d, c, box):
    """The bridge card's right-hand panel, carrying this hook's content.

    Same chrome, divider and two-accent-bar rhythm; the bars are the two
    verdicts rather than two vendors, and the chip row is the actual
    transformation - a pdf in, a pointer to markdown out.
    """
    x0, y0, x1, y1 = box
    d.rounded_rectangle([x0, y0, x1, y1], radius=s(18), fill=c["panel"],
                        outline=c["border"], width=max(1, SCALE // 2))

    for i, dot in enumerate((c["clay"], c["dim"], c["ok"])):
        cx = x0 + s(30) + i * s(18)
        d.ellipse([cx - s(5), y0 + s(27), cx + s(5), y0 + s(37)], fill=dot)
    d.line([(x0 + s(20), y0 + s(68)), (x1 - s(20), y0 + s(68))],
           fill=c["border"], width=max(1, SCALE // 2))

    chip = load("mono", s(17))
    inner_l, inner_r = x0 + s(20), x1 - s(20)
    for label, fill, cx0, cx1 in (
        ("report.pdf", c["clay"], inner_l, inner_l + s(128)),
        ("report.md", c["ok"], inner_r - s(104), inner_r),
    ):
        cy = y0 + s(96)
        d.rounded_rectangle([cx0, cy, cx1, cy + s(38)], radius=s(9), fill=fill)
        d.text(((cx0 + cx1) / 2, cy + s(26)), label, font=chip,
               fill=c["ground"], anchor="ms")
    gradient_arrow(d, inner_l + s(140), inner_r - s(116), y0 + s(112),
                   c["clay"], c["ok"], s(3))

    for dy, width, tone in ((s(172), s(280), c["skel"]),
                            (s(200), s(268), c["skel_dim"]),
                            (s(227), s(196), c["skel_dim"])):
        d.rounded_rectangle([inner_l, y0 + dy, inner_l + width, y0 + dy + s(9)],
                            radius=s(4), fill=tone)

    bar_y = y0 + s(270)
    d.rounded_rectangle([inner_l, bar_y, inner_l + s(118), bar_y + s(9)],
                        radius=s(4), fill=c["ok"])
    d.rounded_rectangle([inner_l + s(130), bar_y, inner_r, bar_y + s(9)],
                        radius=s(4), fill=c["bad"])

    d.ellipse([inner_l, y0 + s(304), inner_l + s(10), y0 + s(314)], fill=c["ok"])
    d.rounded_rectangle([inner_l + s(22), y0 + s(305), inner_l + s(150),
                         y0 + s(313)], radius=s(4), fill=c["skel"])


def make_social_card(c, path):
    w, h = s(1280), s(640)
    img = Image.new("RGB", (w, h), c["ground"])

    # Ground first, then everything else over it: the washes are the widest
    # thing on the card and would otherwise flatten the marks they sit under.
    glow(img, s(210), s(660), s(430), c["glow_warm"])
    glow(img, s(1180), s(-40), s(360), c["glow_cool"])
    d = ImageDraw.Draw(img)
    grid(d, w, h, c["grid"], s(40))

    badge(d, s(96), s(96), s(168), c)
    # 54, not the bridge card's 62: this name is a third longer, and at 62 the
    # wordmark runs within a hair of the panel's left edge.
    wordmark(d, s(96), s(336), c, s(54))

    d.text((s(96), s(386)), "Cheap, honest document ingestion for Claude Code.",
           font=load("medium", s(25)), fill=c["muted"], anchor="ls")

    # The install line, in the bridge card's mono pill. Measured, not guessed:
    # this command is two and a half times the width of that card's /to-codex,
    # so the arrow it feeds has to start from wherever the pill actually ends.
    pill_font = load("mono", s(22))
    pill_text = "/plugin install markitdown-hook"
    pad = s(22)
    pill_r = s(96) + pad * 2 + d.textlength(pill_text, font=pill_font)
    d.rounded_rectangle([s(96), s(432), pill_r, s(492)], radius=s(12),
                        fill=c["pill"], outline=c["border"],
                        width=max(1, SCALE // 2))
    d.text((s(96) + pad, s(470)), pill_text, font=pill_font,
           fill=c["strong"], anchor="ls")
    gradient_arrow(d, pill_r + s(28), s(756), s(459), c["clay"], c["ok"], s(4))

    # Capability strip, letterspaced like the bridge card's footer. These are
    # the extensions the hook actually claims - keep it in step with the
    # converter table in README.md rather than padding it out.
    tracked(d, s(96), s(580), "PDF • DOCX • PPTX • XLSX • EPUB • MSG • ZIP • AUDIO",
            load("bold", s(15)), c["dim"], s(2.2))

    mock_window(d, c, (s(836), s(128), s(1184), s(468)))

    img = img.resize((w // SCALE, h // SCALE), Image.LANCZOS)
    img.save(path)
    return img.size


def make_title_overlay(path):
    """Lower-third for the promo's hero shot: 1920x1080, transparent.

    Composited over the AI opening clip by tools/stitch-promo.sh and faded in
    and out there, so this is a still image with no motion of its own.
    """
    w, h = 1920, 1080
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    x, base_y = 140, 856
    # Accent rule anchoring the block to the left edge of the frame.
    d.rounded_rectangle([x, base_y - 66, x + 7, base_y + 34], radius=3,
                        fill=(59, 130, 246, 255))

    tx = x + 34
    parts = [("claude-", "medium", (148, 163, 184, 255)),
             ("markitdown", "bold", (255, 255, 255, 255)),
             ("-hook", "medium", (148, 163, 184, 255))]
    for text, kind, colour in parts:
        f = load(kind, 62)
        d.text((tx, base_y), text, font=f, fill=colour, anchor="ls")
        tx += d.textlength(text, font=f)

    sub = load("medium", 34)
    d.text((x + 34, base_y + 60),
           "Cheap, honest document ingestion for Claude Code.",
           font=sub, fill=(203, 213, 225, 255), anchor="ls")

    img.save(path)
    return img.size


def main():
    os.makedirs(OUT, exist_ok=True)
    print("font (bold)  :", find_font("bold"))
    print("font (medium):", find_font("medium"))
    for name, size in [
        ("logo.png", make_logo(LIGHT, os.path.join(OUT, "logo.png"))),
        ("logo-dark.png", make_logo(DARK, os.path.join(OUT, "logo-dark.png"))),
        ("social-card.png",
         make_social_card(CARD, os.path.join(OUT, "social-card.png"))),
        ("title-overlay.png",
         make_title_overlay(os.path.join(OUT, "title-overlay.png"))),
        ("endcard-logo.png",
         make_logo(DARK, os.path.join(OUT, "endcard-logo.png"), divisor=2)),
    ]:
        print("wrote {:18} {}".format(name, size))


if __name__ == "__main__":
    sys.exit(main())

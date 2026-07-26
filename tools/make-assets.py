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


def make_social_card(colours, path):
    w, h = 1280 * SCALE, 640 * SCALE
    img = Image.new("RGB", (w, h), colours["card_bg"])
    d = ImageDraw.Draw(img)

    badge(d, 96 * SCALE, 92 * SCALE, 104 * SCALE, colours)
    wordmark(d, 232 * SCALE, 172 * SCALE, colours, 52 * SCALE)

    tag = load("medium", 36 * SCALE)
    d.text((96 * SCALE, 268 * SCALE),
           "Cheap, honest document ingestion for Claude Code.",
           font=tag, fill=colours["muted"], anchor="ls")

    # Two panels: what the hook says in each of the two outcomes. Each line is
    # fitted to the panel width rather than trusted to fit, because overflow
    # here is invisible until you look at the rendered PNG.
    panels = [
        (colours["ok"], "converted", "20-page slide deck",
         "664 chars/page", "pointer injected, 14 KB cached"),
        (colours["bad"], "no usable text", "screenshot saved as PDF",
         "0 chars/page", "nothing written, read with vision"),
    ]
    pw, ph = 512 * SCALE, 232 * SCALE
    pad = 32 * SCALE
    inner = pw - pad * 2
    for i, (accent, verdict, doc, density, result) in enumerate(panels):
        px = (96 + i * (512 + 64)) * SCALE
        py = 330 * SCALE
        d.rounded_rectangle([px, py, px + pw, py + ph], radius=16 * SCALE,
                            fill=colours["card_panel"])
        d.rounded_rectangle([px, py, px + 8 * SCALE, py + ph], radius=4 * SCALE,
                            fill=accent)
        rows = [
            (verdict, "bold", 28 * SCALE, accent, 52),
            (doc, "medium", 26 * SCALE, colours["strong"], 100),
            (density, "bold", 24 * SCALE, colours["strong"], 146),
            (result, "medium", 24 * SCALE, colours["muted"], 190),
        ]
        for text, kind, size, colour, dy in rows:
            font = fit_font(d, text, kind, size, inner)
            d.text((px + pad, py + dy * SCALE), text, font=font, fill=colour,
                   anchor="ls")

    foot = load("medium", 26 * SCALE)
    d.text((96 * SCALE, 596 * SCALE),
           "github.com/AndrewAvery7/claude-markitdown-hook   -   MIT",
           font=foot, fill=colours["muted"], anchor="ls")

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
         make_social_card(LIGHT, os.path.join(OUT, "social-card.png"))),
        ("title-overlay.png",
         make_title_overlay(os.path.join(OUT, "title-overlay.png"))),
        ("endcard-logo.png",
         make_logo(DARK, os.path.join(OUT, "endcard-logo.png"), divisor=2)),
    ]:
        print("wrote {:18} {}".format(name, size))


if __name__ == "__main__":
    sys.exit(main())

"""Generates the social-share preview image (Open Graph / Twitter card).

Produces docs/og-image.png at 1200x630, the size LinkedIn, Twitter, and Slack
expect. Run after changing the landing page's headline copy so the two stay
in sync:  python scripts/make_og_image.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "og-image.png"

W, H = 1200, 630
BG = (23, 23, 26)
SURFACE = (32, 31, 35)
ACCENT = (99, 91, 235)
TEXT = (236, 236, 238)
MUTED = (154, 153, 161)
GREEN = (22, 163, 74)
AMBER = (217, 119, 6)
RED = (220, 38, 38)

# Windows ships these; the DejaVu fallbacks cover Linux CI.
FONT_CANDIDATES = {
    "bold": ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "regular": ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
}


def _font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES[kind]:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    # Bitmap fallback ignores size, so the layout degrades but still renders.
    return ImageFont.load_default()


def main() -> None:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    d.rectangle([0, 0, W, 8], fill=ACCENT)

    # Shield drawn as a polygon rather than an emoji — the TTFs available here
    # are monochrome and render emoji as tofu boxes.
    sx, sy = 70, 82
    d.polygon(
        [(sx + 15, sy), (sx + 30, sy + 7), (sx + 30, sy + 19),
         (sx + 15, sy + 33), (sx, sy + 19), (sx, sy + 7)],
        fill=ACCENT,
    )
    d.text((sx + 46, sy + 2), "AI VENDOR RISK", font=_font("bold", 26), fill=ACCENT)
    d.text((70, 130), "Assessment Automator", font=_font("bold", 78), fill=TEXT)

    tagline = [
        "Turns vendor security docs into a cited, scored risk assessment.",
        "Every claim traces to a source page — or reads \"Not verified.\"",
    ]
    y = 244
    for line in tagline:
        d.text((70, y), line, font=_font("regular", 30), fill=MUTED)
        y += 44

    # Three feature chips summarizing the differentiators.
    chips = [
        ("Citation-enforced", GREEN),
        ("Deterministic scoring", ACCENT),
        ("Injection-screened", AMBER),
    ]
    x = 70
    for label, color in chips:
        font = _font("bold", 24)
        text_w = d.textlength(label, font=font)
        w = int(text_w) + 52
        d.rounded_rectangle([x, 372, x + w, 428], radius=28, fill=SURFACE, outline=color, width=2)
        d.ellipse([x + 20, 393, x + 34, 407], fill=color)
        d.text((x + 44, 388), label, font=font, fill=TEXT)
        x += w + 18

    # Mock risk-score strip, echoing the report's inherent-vs-residual chart.
    d.text((70, 486), "INHERENT", font=_font("bold", 19), fill=MUTED)
    d.text((70, 516), "High", font=_font("bold", 40), fill=RED)
    d.text((250, 486), "RESIDUAL", font=_font("bold", 19), fill=MUTED)
    d.text((250, 516), "High", font=_font("bold", 40), fill=RED)
    d.text((430, 486), "EVIDENCED", font=_font("bold", 19), fill=MUTED)
    d.text((430, 516), "15/21", font=_font("bold", 40), fill=TEXT)
    d.text((640, 486), "NIST AI RMF", font=_font("bold", 19), fill=MUTED)
    d.text((640, 516), "Mapped", font=_font("bold", 40), fill=GREEN)

    d.text((70, 590), "github.com/MichaelMorawski23/AI-Vendor-Risk_Assessor",
           font=_font("regular", 22), fill=MUTED)

    OUT.parent.mkdir(exist_ok=True)
    img.save(OUT, "PNG", optimize=True)
    size_kb = OUT.stat().st_size / 1024
    print(f"wrote {OUT.relative_to(ROOT)} ({W}x{H}, {size_kb:.0f} KB)")
    if size_kb > 1024:
        print("warning: over 1 MB — some platforms skip large preview images", file=sys.stderr)


if __name__ == "__main__":
    main()

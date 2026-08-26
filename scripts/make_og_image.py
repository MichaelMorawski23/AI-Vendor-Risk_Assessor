"""Generates the social-share preview image (Open Graph / Twitter card).

Produces docs/og-image.png. Run after changing the landing page's headline copy
so the two stay in sync:  python scripts/make_og_image.py

The canonical Open Graph size is 1200x630, but preview surfaces rarely display
it at exactly that width — LinkedIn's card is roughly 790px, a fractional
downscale that visibly softens text. So the layout is authored in 1200x630
design units and rendered at SCALE times that, letting the platform downsample
from surplus pixels instead of interpolating a 1:1 image to a fractional size.
Every coordinate and font size below is in design units; _s() applies the scale.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "og-image.png"

W, H = 1200, 630
SCALE = 2

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


def _s(*values: float) -> tuple[int, ...] | int:
    """Design units -> device pixels."""
    scaled = tuple(int(round(v * SCALE)) for v in values)
    return scaled[0] if len(scaled) == 1 else scaled


def _font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES[kind]:
        if Path(path).exists():
            return ImageFont.truetype(path, _s(size))
    # Bitmap fallback ignores size, so the layout degrades but still renders.
    return ImageFont.load_default()


def main() -> None:
    img = Image.new("RGB", _s(W, H), BG)
    d = ImageDraw.Draw(img)

    d.rectangle([0, 0, _s(W), _s(8)], fill=ACCENT)

    # Shield drawn as a polygon rather than an emoji — the TTFs available here
    # are monochrome and render emoji as tofu boxes.
    sx, sy = 70, 82
    d.polygon(
        [_s(sx + 15, sy), _s(sx + 30, sy + 7), _s(sx + 30, sy + 19),
         _s(sx + 15, sy + 33), _s(sx, sy + 19), _s(sx, sy + 7)],
        fill=ACCENT,
    )
    d.text(_s(sx + 46, sy + 2), "AI VENDOR RISK", font=_font("bold", 26), fill=ACCENT)
    d.text(_s(70, 130), "Assessment Automator", font=_font("bold", 78), fill=TEXT)

    tagline = [
        "Turns vendor security docs into a cited, scored risk assessment.",
        "Every claim traces to a source page — or reads \"Not verified.\"",
    ]
    y = 244
    for line in tagline:
        d.text(_s(70, y), line, font=_font("regular", 30), fill=MUTED)
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
        # textlength returns device pixels (the font is already scaled), so
        # convert back to design units before doing layout arithmetic.
        text_w = d.textlength(label, font=font) / SCALE
        w = int(text_w) + 52
        d.rounded_rectangle(
            [_s(x), _s(372), _s(x + w), _s(428)],
            radius=_s(28), fill=SURFACE, outline=color, width=_s(2),
        )
        d.ellipse([_s(x + 20), _s(393), _s(x + 34), _s(407)], fill=color)
        d.text(_s(x + 44, 388), label, font=font, fill=TEXT)
        x += w + 18

    # Mock risk-score strip, echoing the report's inherent-vs-residual chart.
    stats = [
        (70, "INHERENT", "High", RED),
        (250, "RESIDUAL", "High", RED),
        (430, "EVIDENCED", "15/21", TEXT),
        (640, "NIST AI RMF", "Mapped", GREEN),
    ]
    for x_pos, label, value, color in stats:
        d.text(_s(x_pos, 486), label, font=_font("bold", 19), fill=MUTED)
        d.text(_s(x_pos, 516), value, font=_font("bold", 40), fill=color)

    d.text(_s(70, 590), "github.com/MichaelMorawski23/AI-Vendor-Risk_Assessor",
           font=_font("regular", 22), fill=MUTED)

    OUT.parent.mkdir(exist_ok=True)
    img.save(OUT, "PNG", optimize=True)
    size_kb = OUT.stat().st_size / 1024
    print(f"wrote {OUT.relative_to(ROOT)} ({_s(W)}x{_s(H)}, {size_kb:.0f} KB)")
    if size_kb > 1024:
        print("warning: over 1 MB — some platforms skip large preview images", file=sys.stderr)


if __name__ == "__main__":
    main()

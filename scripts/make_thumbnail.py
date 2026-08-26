"""Generates a simple, illustrative thumbnail for the project.

Where make_og_image.py is a stat card, this is the idea in one picture: a
vendor document whose lines are individually marked verified or not, with a
shield over it. It reads at a glance and survives being shrunk to a small
preview, which a text-dense card doesn't.

Authored in 1200x630 design units, rendered at SCALE times that so preview
surfaces downsample from surplus pixels rather than interpolating a 1:1 image
to whatever fractional width they use.

    python scripts/make_thumbnail.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "thumbnail.png"

W, H = 1200, 630
SCALE = 2

BG = (23, 23, 26)
PAPER = (243, 243, 245)
PAPER_LINE = (206, 206, 212)
ACCENT = (99, 91, 235)
TEXT = (236, 236, 238)
MUTED = (150, 149, 158)
GREEN = (22, 163, 74)
AMBER = (217, 119, 6)

FONT_CANDIDATES = {
    "bold": ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "regular": ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
}


def _s(*values: float) -> tuple[int, ...] | int:
    scaled = tuple(int(round(v * SCALE)) for v in values)
    return scaled[0] if len(scaled) == 1 else scaled


def _font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES[kind]:
        if Path(path).exists():
            return ImageFont.truetype(path, _s(size))
    return ImageFont.load_default()


def _shield(d: ImageDraw.ImageDraw, cx: float, cy: float, w: float, h: float, fill) -> None:
    """Hexagonal shield centred on (cx, cy). Drawn rather than an emoji — the
    fonts available here are monochrome and render emoji as tofu boxes."""
    x, y = cx - w / 2, cy - h / 2
    d.polygon(
        [_s(x + w / 2, y), _s(x + w, y + h * 0.21), _s(x + w, y + h * 0.57),
         _s(x + w / 2, y + h), _s(x, y + h * 0.57), _s(x, y + h * 0.21)],
        fill=fill,
    )


def main() -> None:
    img = Image.new("RGB", _s(W, H), BG)
    d = ImageDraw.Draw(img)

    d.rectangle([0, 0, _s(W), _s(8)], fill=ACCENT)

    # --- The document being assessed -------------------------------------
    doc = (108, 112, 468, 522)  # x0, y0, x1, y1
    d.rounded_rectangle([_s(doc[0], doc[1]), _s(doc[2], doc[3])], radius=_s(18), fill=PAPER)

    # Each row is one extracted claim: a dot showing whether it was evidenced,
    # and a bar standing in for the text it came from. Two ambers among six
    # mirrors the real sample report, where not everything is verifiable.
    rows = [
        (172, 250, GREEN), (218, 208, GREEN), (264, 236, GREEN),
        (310, 178, AMBER), (356, 244, GREEN), (402, 162, AMBER),
    ]
    for y, bar_w, status in rows:
        d.ellipse([_s(150), _s(y), _s(166), _s(y + 16)], fill=status)
        d.rounded_rectangle(
            [_s(186), _s(y + 2), _s(186 + bar_w), _s(y + 14)], radius=_s(6), fill=PAPER_LINE
        )

    # Shield sits over the document's corner. A marginally larger shield in the
    # background colour first gives it a thin separating ring, so it reads as a
    # badge on top of the page rather than bleeding into the white behind it.
    _shield(d, 452, 470, 106, 119, BG)
    _shield(d, 452, 470, 98, 110, ACCENT)
    d.line(
        [_s(431, 468), _s(445, 483), _s(473, 452)],
        fill=(255, 255, 255), width=_s(9), joint="curve",
    )

    # --- Wordmark ---------------------------------------------------------
    tx = 560
    d.text(_s(tx, 168), "AI VENDOR RISK", font=_font("bold", 26), fill=ACCENT)
    d.text(_s(tx, 208), "Assessment", font=_font("bold", 74), fill=TEXT)
    d.text(_s(tx, 292), "Automator", font=_font("bold", 74), fill=TEXT)

    for i, line in enumerate([
        "Every claim cited to a source page —",
        "or marked \"Not verified.\"",
    ]):
        d.text(_s(tx, 402 + i * 40), line, font=_font("regular", 27), fill=MUTED)

    OUT.parent.mkdir(exist_ok=True)
    img.save(OUT, "PNG", optimize=True)
    print(f"wrote {OUT.relative_to(ROOT)} ({_s(W)}x{_s(H)}, {OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()

"""Inline SVG charts for the HTML report.

Hand-rolled SVG rather than a charting library: the report must stay a single
self-contained file that opens from disk with no network, so a CDN script tag
or a bundled JS charting runtime is out. These charts only ever render counts
and ratios computed in analysis.py, never raw document text, so nothing here
interpolates untrusted content.

Colors are passed in from the caller's risk palette. Text uses currentColor so
the charts follow the report's light/dark theme.
"""

from __future__ import annotations

import math

from .analysis import DomainBreakdown, RmfFunctionCoverage
from .models import ORDERED_RISK_LEVELS, RiskLevel

_TRACK = "rgba(128,128,128,0.18)"


def _bar_row(
    label: str, value_text: str, ratio: float, color: str, y: int, *, label_w: int = 150
) -> str:
    bar_x = label_w + 8
    bar_w = 420 - bar_x
    fill_w = max(bar_w * max(min(ratio, 1.0), 0.0), 2)
    return f"""
    <text x="0" y="{y + 11}" font-size="11" fill="currentColor" opacity="0.85">{label}</text>
    <rect x="{bar_x}" y="{y}" width="{bar_w}" height="14" rx="7" fill="{_TRACK}"/>
    <rect x="{bar_x}" y="{y}" width="{fill_w:.1f}" height="14" rx="7" fill="{color}"/>
    <text x="{bar_x + bar_w + 8}" y="{y + 11}" font-size="11" fill="currentColor" opacity="0.65">{value_text}</text>
    """


def _svg(width: int, height: int, body: str) -> str:
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="auto" '
        f'role="img" xmlns="http://www.w3.org/2000/svg" style="max-width:{width}px;">'
        f"{body}</svg>"
    )


def _arc_path(cx: float, cy: float, r_outer: float, r_inner: float, start: float, sweep: float) -> str:
    """One donut segment as an SVG path, angles in radians measured from 12 o'clock."""
    # A full-circle segment can't be drawn as a single arc (start and end
    # coincide), so callers get two stacked rings instead — see donut_chart.
    end = start + sweep
    large = 1 if sweep > math.pi else 0

    def point(radius: float, angle: float) -> tuple[float, float]:
        return (cx + radius * math.sin(angle), cy - radius * math.cos(angle))

    x1, y1 = point(r_outer, start)
    x2, y2 = point(r_outer, end)
    x3, y3 = point(r_inner, end)
    x4, y4 = point(r_inner, start)
    return (
        f"M {x1:.2f} {y1:.2f} A {r_outer} {r_outer} 0 {large} 1 {x2:.2f} {y2:.2f} "
        f"L {x3:.2f} {y3:.2f} A {r_inner} {r_inner} 0 {large} 0 {x4:.2f} {y4:.2f} Z"
    )


def donut_chart(
    segments: list[tuple[str, int, str]], center_value: str, center_label: str
) -> str:
    """Donut with a value in the hole. Segments are (label, count, color)."""
    total = sum(count for _, count, _ in segments)
    if not total:
        return ""

    cx, cy, r_out, r_in = 84, 84, 74, 50
    body = ""
    present = [s for s in segments if s[1] > 0]

    if len(present) == 1:
        # Single-value case: a full ring, since an arc can't close on itself.
        body += (
            f'<circle cx="{cx}" cy="{cy}" r="{(r_out + r_in) / 2}" fill="none" '
            f'stroke="{present[0][2]}" stroke-width="{r_out - r_in}"/>'
        )
    else:
        angle = 0.0
        for _, count, color in present:
            sweep = (count / total) * 2 * math.pi
            body += f'<path d="{_arc_path(cx, cy, r_out, r_in, angle, sweep)}" fill="{color}"/>'
            angle += sweep

    body += (
        f'<text x="{cx}" y="{cy - 2}" font-size="26" font-weight="700" text-anchor="middle" '
        f'fill="currentColor">{center_value}</text>'
        f'<text x="{cx}" y="{cy + 16}" font-size="10" text-anchor="middle" '
        f'fill="currentColor" opacity="0.6">{center_label}</text>'
    )

    # Legend to the right of the ring.
    ly = 30
    for label, count, color in segments:
        pct = count / total
        body += (
            f'<rect x="186" y="{ly - 9}" width="10" height="10" rx="2" fill="{color}"/>'
            f'<text x="203" y="{ly}" font-size="11" fill="currentColor" opacity="0.85">{label}</text>'
            f'<text x="203" y="{ly + 14}" font-size="10" fill="currentColor" opacity="0.55">'
            f"{count} · {pct:.0%}</text>"
        )
        ly += 38

    return _svg(400, max(168, ly), body)


def severity_bar_chart(counts: list[tuple[RiskLevel, int]], colors: dict[RiskLevel, str]) -> str:
    """Findings by severity as vertical columns."""
    present = [(level, n) for level, n in counts if n > 0]
    if not present:
        return ""

    peak = max(n for _, n in present)
    col_w, gap, base_y, max_h = 62, 26, 108, 76
    empty_h, min_h = 3, 16  # a count of 1 must not read as an empty column
    body = ""
    for i, (level, count) in enumerate(counts):
        x = i * (col_w + gap)
        h = max((count / peak) * max_h, min_h) if count else empty_h
        y = base_y - h
        fill = colors[level] if count else _TRACK
        body += (
            f'<rect x="{x}" y="{y:.1f}" width="{col_w}" height="{h:.1f}" rx="5" fill="{fill}"/>'
            f'<text x="{x + col_w / 2}" y="{y - 7:.1f}" font-size="15" font-weight="700" '
            f'text-anchor="middle" fill="currentColor">{count}</text>'
            f'<text x="{x + col_w / 2}" y="{base_y + 16}" font-size="10" text-anchor="middle" '
            f'fill="currentColor" opacity="0.65">{level.value}</text>'
        )
    return _svg(len(counts) * (col_w + gap), base_y + 24, body)


def domain_stacked_chart(domains: list[DomainBreakdown], colors: dict[RiskLevel, str]) -> str:
    """Evidenced vs. unevidenced controls per domain, as stacked rows."""
    if not domains:
        return ""
    label_w, bar_x, bar_w, row_h = 108, 116, 300, 30
    body = ""
    for i, d in enumerate(domains):
        y = i * row_h
        verified_w = (d.verified / d.total) * bar_w if d.total else 0
        body += (
            f'<text x="0" y="{y + 15}" font-size="11" fill="currentColor" opacity="0.85">{d.domain}</text>'
            f'<rect x="{bar_x}" y="{y + 3}" width="{bar_w}" height="16" rx="4" fill="{_TRACK}"/>'
        )
        if verified_w > 0:
            body += (
                f'<rect x="{bar_x}" y="{y + 3}" width="{verified_w:.1f}" height="16" rx="4" '
                f'fill="{colors[d.posture]}"/>'
            )
        body += (
            f'<text x="{bar_x + bar_w + 10}" y="{y + 15}" font-size="10" fill="currentColor" '
            f'opacity="0.65">{d.verified}/{d.total} evidenced · {d.gaps} gap(s)</text>'
        )
    return _svg(560, len(domains) * row_h, body)


def risk_scale_chart(
    inherent: RiskLevel | None, residual: RiskLevel | None, colors: dict[RiskLevel, str]
) -> str:
    """Inherent vs residual on a shared four-step scale, so the delta is visible."""
    if inherent is None or residual is None:
        return ""

    seg_w, seg_gap, x0 = 96, 6, 96
    rows = [("Inherent", inherent, 8), ("Residual", residual, 52)]
    body = ""

    for label, level, y in rows:
        idx = ORDERED_RISK_LEVELS.index(level)
        body += f'<text x="0" y="{y + 14}" font-size="11" fill="currentColor" opacity="0.85">{label}</text>'
        for i, step in enumerate(ORDERED_RISK_LEVELS):
            x = x0 + i * (seg_w + seg_gap)
            active = i <= idx
            fill = colors[level] if active else _TRACK
            opacity = "1" if i == idx else ("0.35" if active else "1")
            body += (
                f'<rect x="{x}" y="{y}" width="{seg_w}" height="22" rx="5" '
                f'fill="{fill}" opacity="{opacity}"/>'
            )
        marker_x = x0 + idx * (seg_w + seg_gap) + seg_w / 2
        body += (
            f'<text x="{marker_x}" y="{y + 15}" font-size="11" font-weight="700" '
            f'text-anchor="middle" fill="#fff">{level.value}</text>'
        )

    # Scale labels along the bottom.
    for i, step in enumerate(ORDERED_RISK_LEVELS):
        x = x0 + i * (seg_w + seg_gap) + seg_w / 2
        body += (
            f'<text x="{x}" y="94" font-size="9" text-anchor="middle" '
            f'fill="currentColor" opacity="0.45">{step.value}</text>'
        )

    return _svg(520, 104, body)


def domain_chart(domains: list[DomainBreakdown], colors: dict[RiskLevel, str]) -> str:
    """Per-domain evidence verification, colored by that domain's posture."""
    if not domains:
        return ""
    body = ""
    for i, d in enumerate(domains):
        body += _bar_row(
            label=d.domain,
            value_text=f"{d.verified}/{d.total} verified · {d.gaps} gap(s)",
            ratio=d.verification_rate,
            color=colors[d.posture],
            y=i * 26,
        )
    return _svg(560, len(domains) * 26, body)


def rmf_chart(coverage: list[RmfFunctionCoverage], accent: str) -> str:
    """Evidence coverage across the four NIST AI RMF functions."""
    if not coverage:
        return ""
    body = ""
    for i, c in enumerate(coverage):
        body += _bar_row(
            label=c.function.value,
            value_text=f"{c.verified}/{c.total} evidenced",
            ratio=c.verification_rate,
            color=accent,
            y=i * 26,
            label_w=90,
        )
    return _svg(560, len(coverage) * 26, body)

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

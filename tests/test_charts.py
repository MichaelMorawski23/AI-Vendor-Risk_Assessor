import re

from src.analysis import DomainBreakdown
from src.charts import (
    domain_stacked_chart,
    donut_chart,
    risk_scale_chart,
    severity_bar_chart,
)
from src.models import RiskLevel

COLORS = {
    RiskLevel.LOW: "#16a34a",
    RiskLevel.MEDIUM: "#d97706",
    RiskLevel.HIGH: "#dc2626",
    RiskLevel.CRITICAL: "#991b1b",
}


def _path_count(svg: str) -> int:
    return len(re.findall(r"<path ", svg))


def test_donut_renders_one_arc_per_nonzero_segment():
    svg = donut_chart([("A", 3, "#111"), ("B", 7, "#222")], "70%", "b")
    assert _path_count(svg) == 2
    assert "<svg" in svg


def test_donut_skips_zero_segments_but_keeps_them_in_the_legend():
    svg = donut_chart([("A", 5, "#111"), ("B", 0, "#222")], "100%", "a")
    # Single non-zero value draws a full ring rather than a self-closing arc.
    assert _path_count(svg) == 0
    assert "<circle" in svg
    assert "B" in svg  # still legended, so the reader sees the zero


def test_donut_is_empty_when_there_is_no_data():
    assert donut_chart([("A", 0, "#111")], "—", "none") == ""


def test_donut_arcs_stay_inside_the_viewbox():
    svg = donut_chart([("A", 1, "#111"), ("B", 1, "#222"), ("C", 1, "#333")], "33%", "x")
    coords = [float(n) for n in re.findall(r"[ML] (-?\d+\.\d+) (-?\d+\.\d+)", svg) for n in n]
    assert coords, "expected path coordinates"
    assert all(-1 <= c <= 400 for c in coords)


def test_severity_chart_keeps_zero_columns_for_a_stable_axis():
    counts = [(RiskLevel.CRITICAL, 0), (RiskLevel.HIGH, 2), (RiskLevel.MEDIUM, 5), (RiskLevel.LOW, 0)]
    svg = severity_bar_chart(counts, COLORS)
    for level in ("Critical", "High", "Medium", "Low"):
        assert level in svg
    assert len(re.findall(r"<rect ", svg)) == 4


def test_severity_chart_is_empty_when_there_are_no_findings():
    counts = [(level, 0) for level in RiskLevel]
    assert severity_bar_chart(counts, COLORS) == ""


def test_domain_chart_bar_never_exceeds_the_track():
    domains = [DomainBreakdown("Security", total=4, verified=4, gaps=0, high_severity_gaps=0)]
    svg = domain_stacked_chart(domains, COLORS)
    widths = [float(w) for w in re.findall(r'width="(\d+\.?\d*)"', svg)]
    assert max(widths) <= 300.0


def test_domain_chart_omits_the_fill_when_nothing_is_evidenced():
    domains = [DomainBreakdown("AI risk", total=5, verified=0, gaps=5, high_severity_gaps=1)]
    svg = domain_stacked_chart(domains, COLORS)
    assert svg.count("<rect") == 1  # track only, no zero-width fill


def test_risk_scale_chart_marks_both_levels():
    svg = risk_scale_chart(RiskLevel.CRITICAL, RiskLevel.MEDIUM, COLORS)
    assert "Inherent" in svg and "Residual" in svg
    assert "Critical" in svg and "Medium" in svg


def test_risk_scale_chart_is_empty_when_unscored():
    assert risk_scale_chart(None, None, COLORS) == ""


def test_every_chart_carries_a_screen_reader_label():
    """role="img" alone announces only "image" — each chart needs a description."""
    domains = [DomainBreakdown("Security", total=4, verified=3, gaps=1, high_severity_gaps=0)]
    charts = [
        donut_chart([("Evidenced", 3, "#111"), ("Not verified", 1, "#222")], "75%", "evidenced"),
        severity_bar_chart([(RiskLevel.HIGH, 1), (RiskLevel.MEDIUM, 2)], COLORS),
        domain_stacked_chart(domains, COLORS),
        risk_scale_chart(RiskLevel.HIGH, RiskLevel.MEDIUM, COLORS),
    ]
    for svg in charts:
        assert 'aria-label="' in svg
        label = re.search(r'aria-label="([^"]+)"', svg).group(1)
        assert len(label) > 15, f"label too vague to be useful: {label!r}"


def test_chart_labels_escape_quotes_so_the_attribute_cannot_break():
    svg = donut_chart([('He said "yes"', 2, "#111"), ("Other", 1, "#222")], "66%", "evidenced")
    assert 'aria-label="' in svg
    assert "&quot;" in svg
    # The raw quote must not survive inside the attribute value.
    label = re.search(r'aria-label="([^"]*)"', svg).group(1)
    assert '"' not in label

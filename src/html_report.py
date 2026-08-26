"""Generates a self-contained, single-page HTML risk report.

This is the human-readable companion to report.py's Excel register: one long
page, a sticky table of contents for jumping between sections, everything
inline (no external CSS/JS/fonts) so the downloaded file opens standalone in
any browser with nothing missing.

Every value that originates from an uploaded vendor document — citations,
quotes, the vendor name itself if it were ever pulled from a doc — is treated
as untrusted and passed through html.escape() before being interpolated. The
injection_guard module defends the LLM prompt from vendor-document content;
this module defends the *report reader's browser* from the same untrusted
content, which is a separate attack surface (stored XSS via a malicious PDF)
that would exist even with the LLM path removed entirely.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone

from .analysis import AssessmentAnalysis, analyze
from .charts import (
    domain_stacked_chart,
    donut_chart,
    risk_scale_chart,
    rmf_chart,
    severity_bar_chart,
)
from .models import RiskLevel, VendorAssessment
from .questions import QUESTIONS_BY_ID, RISK_QUESTIONS
from .risk_scoring import MAX_INHERENT_THRESHOLDS_DOC

_RISK_COLORS: dict[RiskLevel, str] = {
    RiskLevel.LOW: "#16a34a",
    RiskLevel.MEDIUM: "#d97706",
    RiskLevel.HIGH: "#dc2626",
    RiskLevel.CRITICAL: "#991b1b",
}
_ACCENT = "#4f46e5"


def _esc(value: object) -> str:
    if value is None:
        return ""
    return html.escape(str(value))


def _risk_chip(level: RiskLevel | None) -> str:
    if level is None:
        return '<span class="chip chip-muted">Not scored</span>'
    color = _RISK_COLORS[level]
    return f'<span class="chip" style="background:{color}1a;color:{color};border-color:{color}55;">{_esc(level.value)}</span>'


def _section(anchor: str, title: str, body: str) -> str:
    return f'<section id="{anchor}" class="section"><h2>{_esc(title)}</h2>{body}</section>'


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return '<p class="muted">No data.</p>'
    thead = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    trows = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows
    )
    return f'<div class="table-wrap"><table><thead><tr>{thead}</tr></thead><tbody>{trows}</tbody></table></div>'


def _summary_section(assessment: VendorAssessment, analysis: AssessmentAnalysis) -> str:
    verified_count = sum(1 for e in assessment.evidence if e.verified)
    unverified = assessment.unverified_questions()

    evidence_donut = donut_chart(
        [
            ("Evidenced with citation", analysis.verified_count, "#16a34a"),
            ("Not verified", analysis.unverified_count, "#d97706"),
        ],
        center_value=f"{analysis.verified_count / len(assessment.evidence):.0%}"
        if assessment.evidence
        else "—",
        center_label="evidenced",
    )

    body = f"""
    <p class="narrative">{_esc(analysis.narrative)}</p>
    <div class="cards">
      <div class="card"><div class="card-label">Inherent risk</div><div class="card-value">{_risk_chip(assessment.inherent_risk)}</div></div>
      <div class="card"><div class="card-label">Residual risk</div><div class="card-value">{_risk_chip(assessment.residual_risk)}</div></div>
      <div class="card"><div class="card-label">Verified control coverage</div><div class="card-value">{assessment.control_coverage:.0%}</div></div>
      <div class="card"><div class="card-label">Evidence verified</div><div class="card-value">{verified_count}/{len(assessment.evidence)}</div></div>
      <div class="card"><div class="card-label">Open findings</div><div class="card-value">{len(assessment.findings)}</div></div>
    </div>
    <div class="chart-block">
      <div class="chart-title">Inherent vs. residual risk</div>
      {risk_scale_chart(assessment.inherent_risk, assessment.residual_risk, _RISK_COLORS)}
      <p class="rationale">{_esc(assessment.residual_rationale)}</p>
    </div>
    <div class="chart-grid">
      <div class="chart-block">
        <div class="chart-title">Evidence coverage</div>
        {evidence_donut}
      </div>
      <div class="chart-block">
        <div class="chart-title">Findings by severity</div>
        {severity_bar_chart(analysis.severity_counts, _RISK_COLORS)}
      </div>
    </div>
    <p><strong>Business use case:</strong> {_esc(assessment.profile.business_use_case) or '<span class="muted">Not provided</span>'}</p>
    """
    if unverified:
        items = "".join(f"<li>{_esc(e.question_text)}</li>" for e in unverified)
        body += (
            f'<details class="details"><summary>{len(unverified)} question(s) not verified '
            f"in the provided documentation</summary><ul>{items}</ul></details>"
        )
    return body


def _domain_section(analysis: AssessmentAnalysis) -> str:
    body = f"""
    <p class="muted">Where risk concentrates. Domain posture is High when any high-severity gap
    exists or at least half the domain's controls are flagged.</p>
    <div class="chart-block">{domain_stacked_chart(analysis.domains, _RISK_COLORS)}</div>
    """
    rows = [
        [
            _esc(d.domain),
            _risk_chip(d.posture),
            f"{d.verified}/{d.total}",
            f"{d.verification_rate:.0%}",
            str(d.gaps),
            str(d.high_severity_gaps),
        ]
        for d in analysis.domains
    ]
    body += _table(
        ["Domain", "Posture", "Evidenced", "Coverage", "Gaps", "High-severity gaps"], rows
    )
    return body


def _rmf_section(assessment: VendorAssessment, analysis: AssessmentAnalysis) -> str:
    body = f"""
    <p class="muted">Evidence coverage across the four NIST AI RMF functions — which parts of the
    framework this vendor's documentation actually supports.</p>
    <div class="chart-block">{rmf_chart(analysis.rmf_coverage, _ACCENT)}</div>
    """
    body += _table(
        ["Function", "Questions mapped", "Evidenced", "Coverage", "Gaps"],
        [
            [
                _esc(c.function.value),
                str(c.total),
                str(c.verified),
                f"{c.verification_rate:.0%}",
                str(c.gaps),
            ]
            for c in analysis.rmf_coverage
        ],
    )
    body += "<h3>Control crosswalk</h3>"
    body += _table(
        ["Function", "Category", "Note"],
        [[_esc(m.function.value), _esc(m.category), _esc(m.note)] for m in assessment.rmf_mappings],
    )
    body += (
        '<p class="muted">Simplified crosswalk to NIST AI RMF 1.0 (NIST AI 100-1) for vendor-risk '
        "triage — not an official NIST mapping.</p>"
    )
    return body


def _register_section(analysis: AssessmentAnalysis) -> str:
    if not analysis.register:
        return '<p class="muted">No control gaps identified.</p>'
    rows = [
        [
            f'<span class="risk-id">{_esc(r.risk_id)}</span>',
            _esc(r.domain),
            _esc(r.finding),
            _risk_chip(r.severity),
            _esc(r.evidence_status),
            _esc(r.rmf_reference),
            _esc(r.recommended_control),
            f'<span class="status-open">{_esc(r.status)}</span>',
        ]
        for r in analysis.register
    ]
    return _table(
        ["ID", "Domain", "Finding", "Severity", "Evidence", "NIST AI RMF", "Recommended control", "Status"],
        rows,
    )


def _evidence_section(assessment: VendorAssessment) -> str:
    rows = []
    for e in assessment.evidence:
        domain = QUESTIONS_BY_ID[e.question_id].domain if e.question_id in QUESTIONS_BY_ID else ""
        answer = _esc(e.answer) if e.verified else '<span class="not-verified">Not verified</span>'
        source = f"{_esc(e.citation.document)} p.{_esc(e.citation.page)}" if e.citation else "—"
        quote = f'<span class="quote">&ldquo;{_esc(e.quote)}&rdquo;</span>' if e.quote else ""
        rows.append([_esc(domain), _esc(e.question_text), answer, source, quote])
    return _table(["Domain", "Question", "Answer", "Source", "Supporting quote"], rows)


def _methodology_section(assessment: VendorAssessment) -> str:
    return f"""
    <h3>How risk is scored</h3>
    <p>Scoring is rule-based and deterministic — no model output influences a score, so the same
    evidence always produces the same rating.</p>
    <ul>
      <li><strong>Inherent risk</strong> rates the engagement itself — data classification,
      business criticality, data types, regulatory scope, user population, AI capabilities, and
      integration reach — before crediting any vendor control. Points are itemized in the
      inherent risk drivers section. Thresholds: {_esc(MAX_INHERENT_THRESHOLDS_DOC)}.</li>
      <li><strong>Control gaps</strong> come from the {len(RISK_QUESTIONS)} risk questions. A control
      that the documentation does not evidence is counted as a gap, not assumed compliant.</li>
      <li><strong>Residual risk</strong> reduces inherent risk by verified control coverage:
      at least 80% coverage steps risk down two levels, at least 50% steps it down one.
      Any unmitigated high-severity gap blocks reduction entirely.</li>
    </ul>
    <h3>Evidence standard</h3>
    <p>Every answer must cite the source document and page it came from. Where the documentation
    does not support an answer, the field reads <em>Not verified</em> rather than being inferred.
    Unverified controls count against the vendor.</p>
    <h3>Document screening</h3>
    <p>Vendor documents are untrusted input. Before any text reaches the language model, it is
    screened for instruction-like content — text written to manipulate an automated reviewer — and
    matching spans are redacted and logged. {
        f"{len(assessment.injection_flags)} span(s) were redacted in this assessment."
        if assessment.injection_flags
        else "Nothing was flagged in this assessment."
    }</p>
    <h3>Limitations</h3>
    <ul>
      <li>This is a preliminary triage artifact, not a certified assessment or an audit.</li>
      <li>Extraction is model-assisted and can miss content; "Not verified" means the tool did not
      find evidence, not that the control is absent.</li>
      <li>Record volume and user count are captured for the register but do not affect scoring.</li>
      <li>The NIST AI RMF crosswalk is an opinionated simplification for triage purposes.</li>
    </ul>
    """


def build_html_report(assessment: VendorAssessment) -> str:
    p = assessment.profile
    analysis = analyze(assessment)
    generated = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")

    toc_items = [
        ("summary", "Executive summary"),
        ("domains", "Risk by domain"),
        ("register", "Risk register"),
        ("profile", "Engagement profile"),
        ("inherent", "Inherent risk drivers"),
        ("evidence", "Evidence & citations"),
        ("rmf", "NIST AI RMF coverage"),
    ]
    if assessment.injection_flags:
        toc_items.append(("screened", "Screened content"))
    toc_items += [("review", "Reviewer decision"), ("methodology", "Methodology")]
    toc_html = "".join(f'<a href="#{a}">{_esc(t)}</a>' for a, t in toc_items)

    # --- Profile ---
    profile_rows = [
        ("Product / service", p.product_name),
        ("Vendor website", p.vendor_website),
        ("Business owner", p.business_owner),
        ("Engagement stage", p.engagement_stage),
        ("Deployment model", p.deployment_model),
        ("Business criticality", p.criticality.value),
        ("Data classification", p.data_classification.value),
        ("Data types", ", ".join(p.data_types)),
        ("Regulatory scope", ", ".join(p.regulatory_scope)),
        ("Approx. record volume", p.record_volume),
        ("Used by", p.used_by),
        ("Approx. user count", p.user_count),
        ("Integrates with internal systems", "Yes" if p.integrates_with_internal_systems else "No"),
        ("Integrated systems", p.integrated_systems),
        ("AI capabilities", ", ".join(p.ai_capabilities)),
        ("Affects decisions about individuals", "Yes" if p.affects_decisions_about_people else "No"),
        ("Model hosting", p.model_hosting),
    ]
    profile_body = _table(
        ["Field", "Value"],
        [[_esc(label), _esc(value) or '<span class="muted">—</span>'] for label, value in profile_rows],
    )

    # --- Inherent drivers ---
    total_points = sum(d.points for d in assessment.inherent_drivers)
    inherent_body = _table(
        ["Factor", "Detail", "Points"],
        [[_esc(d.factor), _esc(d.detail), str(d.points)] for d in assessment.inherent_drivers],
    )
    inherent_body += f'<p class="muted">Total: {total_points} points → {_esc(assessment.inherent_risk.value if assessment.inherent_risk else "not scored")}</p>'

    # --- Screened content ---
    screened_body = ""
    for flag in assessment.injection_flags:
        screened_body += f"""
        <div class="flag">
          <div class="flag-meta">{_esc(flag.document)}, p.{_esc(flag.page)} — {_esc(flag.reason)}</div>
          <code class="flag-snippet">{_esc(flag.snippet)}</code>
        </div>
        """

    # --- Review ---
    controls = "".join(f"<li>{_esc(c)}</li>" for c in assessment.required_controls)
    review_body = f"""
    <p><strong>Decision:</strong> {_esc(assessment.decision.value)}</p>
    <p><strong>Required controls:</strong></p>
    <ul>{controls or '<li class="muted">None specified</li>'}</ul>
    <p><strong>Reviewer notes:</strong></p>
    <p class="rationale">{_esc(assessment.recommendation) or '<span class="muted">Not yet recorded</span>'}</p>
    """

    sections = (
        _section("summary", "Executive summary", _summary_section(assessment, analysis))
        + _section("domains", "Risk by domain", _domain_section(analysis))
        + _section("register", "Risk register", _register_section(analysis))
        + _section("profile", "Engagement profile", profile_body)
        + _section("inherent", "Inherent risk drivers", inherent_body)
        + _section("evidence", "Evidence & citations", _evidence_section(assessment))
        + _section("rmf", "NIST AI RMF coverage", _rmf_section(assessment, analysis))
    )
    if assessment.injection_flags:
        sections += _section("screened", "Screened content", screened_body)
    sections += _section("review", "Reviewer decision", review_body)
    sections += _section("methodology", "Methodology", _methodology_section(assessment))

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(p.vendor_name)} — AI Vendor Risk Assessment</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><text y='26' font-size='26'>🛡️</text></svg>">
<style>
  :root {{
    --bg: #f7f7f8; --surface: #ffffff; --border: #e3e3e6; --text: #1a1a1e;
    --muted: #6b6b73; --accent: {_ACCENT};
  }}
  * {{ box-sizing: border-box; }}
  html {{ scroll-behavior: smooth; }}
  body {{
    margin: 0; background: var(--bg); color: var(--text);
    font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.55;
  }}
  header.report-header {{ background: var(--surface); border-bottom: 1px solid var(--border); padding: 2rem 1.5rem 1.5rem; }}
  .report-header-inner {{ max-width: 900px; margin: 0 auto; }}
  .eyebrow {{ font-size: .75rem; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); margin-bottom: .35rem; }}
  h1 {{ font-size: 1.7rem; margin: 0 0 .25rem 0; letter-spacing: -0.01em; }}
  .subtitle {{ color: var(--muted); font-size: .9rem; }}
  nav.toc {{
    position: sticky; top: 0; z-index: 10; background: rgba(255,255,255,.94);
    backdrop-filter: blur(6px); border-bottom: 1px solid var(--border);
    padding: .6rem 1.5rem; overflow-x: auto; white-space: nowrap;
  }}
  nav.toc a {{
    color: var(--text); text-decoration: none; font-size: .82rem; font-weight: 500;
    margin-right: 1.3rem; opacity: .7; padding-bottom: 2px; border-bottom: 2px solid transparent;
  }}
  nav.toc a:hover {{ opacity: 1; border-bottom-color: var(--accent); }}
  main {{ max-width: 900px; margin: 0 auto; padding: 0 1.5rem 4rem; }}
  section.section {{ scroll-margin-top: 3.2rem; padding: 2rem 0; border-bottom: 1px solid var(--border); }}
  section.section:last-child {{ border-bottom: none; }}
  section.section h2 {{ font-size: 1.15rem; margin: 0 0 1rem 0; }}
  section.section h3 {{ font-size: .95rem; margin: 1.4rem 0 .5rem; }}
  .narrative {{ font-size: 1rem; line-height: 1.65; margin: 0 0 1.2rem; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: .75rem; margin-bottom: 1.2rem; }}
  .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: .9rem 1rem; }}
  .card-label {{ font-size: .7rem; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin-bottom: .3rem; }}
  .card-value {{ font-size: 1.15rem; font-weight: 700; }}
  .chart-block {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1rem 1.1rem; margin-bottom: 1rem; }}
  .chart-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; }}
  .chart-grid .chart-block {{ margin-bottom: 0; }}
  .chart-title {{ font-size: .72rem; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin-bottom: .7rem; }}
  .chip {{ display: inline-block; padding: .15rem .6rem; border-radius: 999px; font-weight: 700; font-size: .82rem; border: 1px solid transparent; }}
  .chip-muted {{ background: #eee; color: var(--muted); }}
  .rationale {{ color: var(--muted); font-size: .9rem; margin: .8rem 0 0; }}
  .muted {{ color: var(--muted); }}
  .not-verified {{ color: #b45309; font-style: italic; }}
  .quote {{ color: var(--muted); font-size: .85rem; font-style: italic; }}
  .risk-id {{ font-family: ui-monospace, Menlo, Consolas, monospace; font-size: .8rem; font-weight: 700; white-space: nowrap; }}
  .status-open {{ font-size: .78rem; font-weight: 600; color: #b45309; }}
  .details {{ margin-top: 1rem; }}
  .details summary {{ cursor: pointer; font-weight: 600; font-size: .9rem; }}
  .table-wrap {{ overflow-x: auto; border: 1px solid var(--border); border-radius: 10px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: .86rem; }}
  th, td {{ text-align: left; padding: .55rem .75rem; border-bottom: 1px solid var(--border); vertical-align: top; }}
  th {{ background: #fafafa; font-size: .7rem; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); position: sticky; top: 0; }}
  tr:last-child td {{ border-bottom: none; }}
  .flag {{ background: #fff7ed; border: 1px solid #fed7aa; border-radius: 10px; padding: .75rem 1rem; margin-bottom: .6rem; }}
  .flag-meta {{ font-size: .82rem; font-weight: 600; margin-bottom: .35rem; }}
  .flag-snippet {{ display: block; background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: .5rem .6rem; font-size: .82rem; white-space: pre-wrap; }}
  footer {{ max-width: 900px; margin: 0 auto; padding: 1.5rem; color: var(--muted); font-size: .78rem; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg: #17171a; --surface: #201f23; --border: #35343a; --text: #ececee; --muted: #9a99a1; }}
    nav.toc {{ background: rgba(23,23,26,.94); }}
    th {{ background: #26252a; }}
    .flag {{ background: #2a2118; border-color: #4a3520; }}
    .chip-muted {{ background: #2a292f; }}
  }}
  @media print {{
    nav.toc {{ display: none; }}
    body {{ background: #fff; }}
    section.section {{ page-break-inside: avoid; }}
    .table-wrap {{ overflow: visible; }}
  }}
</style>
</head>
<body>
<header class="report-header">
  <div class="report-header-inner">
    <div class="eyebrow">AI Vendor Risk Assessment</div>
    <h1>{_esc(p.vendor_name)}{f" — {_esc(p.product_name)}" if p.product_name else ""}</h1>
    <div class="subtitle">Generated {generated} · Decision: <strong>{_esc(assessment.decision.value)}</strong></div>
  </div>
</header>
<nav class="toc">{toc_html}</nav>
<main>
{sections}
</main>
<footer>
  Preliminary automated assessment. Every claim above is cited to its source document and page,
  or marked "Not verified" — this report does not substitute for human review, and the tool
  never auto-approves a vendor. Generated by the AI Vendor Risk Assessment Automator.
</footer>
</body>
</html>"""

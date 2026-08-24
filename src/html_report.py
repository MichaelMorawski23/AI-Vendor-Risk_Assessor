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

from .models import RiskLevel, VendorAssessment
from .questions import QUESTIONS_BY_ID

_RISK_COLORS: dict[RiskLevel, str] = {
    RiskLevel.LOW: "#16a34a",
    RiskLevel.MEDIUM: "#d97706",
    RiskLevel.HIGH: "#dc2626",
    RiskLevel.CRITICAL: "#991b1b",
}


def _esc(value: object) -> str:
    if value is None:
        return ""
    return html.escape(str(value))


def _risk_chip(level: RiskLevel | None) -> str:
    if level is None:
        return '<span class="chip chip-muted">Not scored</span>'
    color = _RISK_COLORS[level]
    return f'<span class="chip" style="background:{color}1a;color:{color};border-color:{color}55;">{_esc(level.value)}</span>'


def _severity_chip(level: RiskLevel) -> str:
    return _risk_chip(level)


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


def build_html_report(assessment: VendorAssessment) -> str:
    p = assessment.profile
    generated = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")

    toc_items = [
        ("summary", "Executive summary"),
        ("profile", "Vendor & engagement profile"),
        ("inherent", "Inherent risk drivers"),
        ("evidence", "Evidence & citations"),
        ("findings", "Findings & recommended controls"),
        ("rmf", "NIST AI RMF mapping"),
    ]
    if assessment.injection_flags:
        toc_items.append(("screened", "Screened content"))
    toc_items.append(("review", "Reviewer decision"))

    toc_html = "".join(f'<a href="#{a}">{_esc(t)}</a>' for a, t in toc_items)

    # --- Executive summary ---
    verified_count = sum(1 for e in assessment.evidence if e.verified)
    unverified = assessment.unverified_questions()
    summary_body = f"""
    <div class="cards">
      <div class="card"><div class="card-label">Inherent risk</div><div class="card-value">{_risk_chip(assessment.inherent_risk)}</div></div>
      <div class="card"><div class="card-label">Residual risk</div><div class="card-value">{_risk_chip(assessment.residual_risk)}</div></div>
      <div class="card"><div class="card-label">Verified control coverage</div><div class="card-value">{assessment.control_coverage:.0%}</div></div>
      <div class="card"><div class="card-label">Evidence verified</div><div class="card-value">{verified_count}/{len(assessment.evidence)}</div></div>
    </div>
    <p class="rationale"><strong>Residual risk rationale:</strong> {_esc(assessment.residual_rationale)}</p>
    <p><strong>Business use case:</strong> {_esc(p.business_use_case) or '<span class="muted">Not provided</span>'}</p>
    """
    if unverified:
        items = "".join(f"<li>{_esc(e.question_text)}</li>" for e in unverified)
        summary_body += f'<p><strong>{len(unverified)} question(s) not verified in the provided documentation:</strong></p><ul>{items}</ul>'

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

    # --- Inherent risk drivers ---
    driver_rows = [
        [_esc(d.factor), _esc(d.detail), str(d.points)] for d in assessment.inherent_drivers
    ]
    total_points = sum(d.points for d in assessment.inherent_drivers)
    inherent_body = _table(["Factor", "Detail", "Points"], driver_rows)
    inherent_body += f'<p class="muted">Total: {total_points} points</p>'

    # --- Evidence ---
    evidence_rows = []
    for e in assessment.evidence:
        domain = QUESTIONS_BY_ID[e.question_id].domain if e.question_id in QUESTIONS_BY_ID else ""
        answer = _esc(e.answer) if e.verified else '<span class="not-verified">Not verified</span>'
        source = f"{_esc(e.citation.document)} p.{_esc(e.citation.page)}" if e.citation else "—"
        quote = f'<span class="quote">&ldquo;{_esc(e.quote)}&rdquo;</span>' if e.quote else ""
        evidence_rows.append([_esc(domain), _esc(e.question_text), answer, source, quote])
    evidence_body = _table(["Domain", "Question", "Answer", "Source", "Supporting quote"], evidence_rows)

    # --- Findings ---
    findings_body = ""
    if not assessment.findings:
        findings_body = '<p class="muted">No control gaps identified.</p>'
    else:
        for f in assessment.findings:
            findings_body += f"""
            <div class="finding">
              {_severity_chip(f.severity)}
              <div class="finding-summary">{_esc(f.summary)}</div>
              <div class="finding-control">Recommended control: {_esc(f.recommended_control) or '—'}</div>
            </div>
            """

    # --- RMF ---
    rmf_rows = [[_esc(m.function.value), _esc(m.category), _esc(m.note)] for m in assessment.rmf_mappings]
    rmf_body = _table(["Function", "Category", "Note"], rmf_rows)
    rmf_body += '<p class="muted">Simplified crosswalk to NIST AI RMF 1.0 (NIST AI 100-1) — not an official NIST mapping.</p>'

    # --- Screened content ---
    screened_body = ""
    if assessment.injection_flags:
        for flag in assessment.injection_flags:
            screened_body += f"""
            <div class="flag">
              <div class="flag-meta">{_esc(flag.document)}, p.{_esc(flag.page)} — {_esc(flag.reason)}</div>
              <code class="flag-snippet">{_esc(flag.snippet)}</code>
            </div>
            """

    # --- Review ---
    review_body = f"""
    <p><strong>Decision:</strong> {_esc(assessment.decision.value)}</p>
    <p><strong>Required controls:</strong></p>
    <ul>{"".join(f"<li>{_esc(c)}</li>" for c in assessment.required_controls) or '<li class="muted">None specified</li>'}</ul>
    <p><strong>Reviewer notes:</strong></p>
    <p class="rationale">{_esc(assessment.recommendation) or '<span class="muted">Not yet recorded</span>'}</p>
    """

    sections = (
        _section("summary", "Executive summary", summary_body)
        + _section("profile", "Vendor & engagement profile", profile_body)
        + _section("inherent", "Inherent risk drivers", inherent_body)
        + _section("evidence", "Evidence & citations", evidence_body)
        + _section("findings", "Findings & recommended controls", findings_body)
        + _section("rmf", "NIST AI RMF mapping", rmf_body)
    )
    if assessment.injection_flags:
        sections += _section("screened", "Screened content", screened_body)
    sections += _section("review", "Reviewer decision", review_body)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{_esc(p.vendor_name)} — AI Vendor Risk Assessment</title>
<style>
  :root {{
    --bg: #f7f7f8; --surface: #ffffff; --border: #e3e3e6; --text: #1a1a1e;
    --muted: #6b6b73; --accent: #4f46e5;
  }}
  * {{ box-sizing: border-box; }}
  html {{ scroll-behavior: smooth; }}
  body {{
    margin: 0; background: var(--bg); color: var(--text);
    font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.55;
  }}
  header.report-header {{
    background: var(--surface); border-bottom: 1px solid var(--border);
    padding: 2rem 1.5rem 1.5rem;
  }}
  .report-header-inner {{ max-width: 880px; margin: 0 auto; }}
  .eyebrow {{ font-size: .75rem; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); margin-bottom: .35rem; }}
  h1 {{ font-size: 1.7rem; margin: 0 0 .25rem 0; letter-spacing: -0.01em; }}
  .subtitle {{ color: var(--muted); font-size: .9rem; }}
  nav.toc {{
    position: sticky; top: 0; z-index: 10; background: rgba(255,255,255,.92);
    backdrop-filter: blur(6px); border-bottom: 1px solid var(--border);
    padding: .6rem 1.5rem; overflow-x: auto; white-space: nowrap;
  }}
  nav.toc a {{
    color: var(--text); text-decoration: none; font-size: .82rem; font-weight: 500;
    margin-right: 1.3rem; opacity: .7; padding-bottom: 2px; border-bottom: 2px solid transparent;
  }}
  nav.toc a:hover {{ opacity: 1; border-bottom-color: var(--accent); }}
  main {{ max-width: 880px; margin: 0 auto; padding: 0 1.5rem 4rem; }}
  section.section {{ scroll-margin-top: 3.2rem; padding: 2rem 0; border-bottom: 1px solid var(--border); }}
  section.section:last-child {{ border-bottom: none; }}
  section.section h2 {{ font-size: 1.15rem; margin: 0 0 1rem 0; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: .75rem; margin-bottom: 1rem; }}
  .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: .9rem 1rem; }}
  .card-label {{ font-size: .7rem; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin-bottom: .3rem; }}
  .card-value {{ font-size: 1.15rem; font-weight: 700; }}
  .chip {{
    display: inline-block; padding: .15rem .6rem; border-radius: 999px; font-weight: 700;
    font-size: .95rem; border: 1px solid transparent;
  }}
  .chip-muted {{ background: #eee; color: var(--muted); }}
  .rationale {{ color: var(--muted); font-size: .92rem; }}
  .muted {{ color: var(--muted); }}
  .not-verified {{ color: #b45309; font-style: italic; }}
  .quote {{ color: var(--muted); font-size: .85rem; font-style: italic; }}
  .table-wrap {{ overflow-x: auto; border: 1px solid var(--border); border-radius: 10px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: .88rem; }}
  th, td {{ text-align: left; padding: .55rem .75rem; border-bottom: 1px solid var(--border); vertical-align: top; }}
  th {{ background: #fafafa; font-size: .72rem; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); }}
  tr:last-child td {{ border-bottom: none; }}
  .finding {{
    background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
    padding: .9rem 1rem; margin-bottom: .6rem;
  }}
  .finding-summary {{ font-weight: 600; margin: .4rem 0 .25rem; }}
  .finding-control {{ font-size: .85rem; color: var(--muted); }}
  .flag {{ background: #fff7ed; border: 1px solid #fdba7422; border-radius: 10px; padding: .75rem 1rem; margin-bottom: .6rem; }}
  .flag-meta {{ font-size: .82rem; font-weight: 600; margin-bottom: .35rem; }}
  .flag-snippet {{ display: block; background: #fff; border: 1px solid var(--border); border-radius: 6px; padding: .5rem .6rem; font-size: .82rem; white-space: pre-wrap; }}
  footer {{ max-width: 880px; margin: 0 auto; padding: 1.5rem; color: var(--muted); font-size: .78rem; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg: #17171a; --surface: #201f23; --border: #35343a; --text: #ececee; --muted: #9a99a1; }}
    nav.toc {{ background: rgba(23,23,26,.92); }}
    th {{ background: #26252a; }}
    .flag {{ background: #2a2118; }}
    .flag-snippet {{ background: #201f23; }}
    .chip-muted {{ background: #2a292f; }}
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

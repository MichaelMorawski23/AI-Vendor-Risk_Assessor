"""Generates the showcase sample report and the app's demo fixture.

This runs the *real* pipeline — PDF extraction, injection screening, live LLM
extraction, scoring, analysis — against sample_docs/*.pdf. The published sample
report is therefore genuine tool output, not a hand-authored mockup.

Outputs:
  docs/report.html                 the published report (linked from docs/index.html,
                                    the GitHub Pages landing page — NOT overwritten by this script)
  docs/sample_risk_register.xlsx   the matching Excel register
  src/demo_assessment.json         fixture the app loads for its demo mode

Requires ANTHROPIC_API_KEY. Run: python scripts/make_sample_report.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.analysis import analyze  # noqa: E402
from src.extraction import extract_pdf_pages  # noqa: E402
from src.html_report import build_html_report  # noqa: E402
from src.injection_guard import sanitize_for_prompt, scan_text  # noqa: E402
from src.llm_extractor import extract_evidence  # noqa: E402
from src.models import (  # noqa: E402
    Criticality,
    DataClassification,
    Decision,
    VendorAssessment,
    VendorProfile,
)
from src.report import write_excel_report  # noqa: E402
from src.risk_scoring import assess  # noqa: E402
from src.rmf_mapping import map_all  # noqa: E402
from src.serialization import dumps, loads  # noqa: E402

SAMPLE_DOCS = ROOT / "sample_docs"
DOCS = ROOT / "docs"
# docs/index.html is the hand-authored GitHub Pages landing page, not generated
# output — writing here would silently overwrite it on the next regeneration.
OUT_HTML = DOCS / "report.html"
OUT_XLSX = DOCS / "sample_risk_register.xlsx"
OUT_FIXTURE = ROOT / "src" / "demo_assessment.json"

# The intake a reviewer would realistically fill in for this vendor.
PROFILE = VendorProfile(
    vendor_name="SampleAI Meeting Assistant",
    product_name="Notetaker",
    vendor_website="https://sampleai.example",
    deployment_model="SaaS (multi-tenant)",
    business_owner="Security & Risk",
    business_use_case=(
        "Automatic transcription and summarization of internal and client meetings, "
        "with action items posted to Slack and Salesforce."
    ),
    criticality=Criticality.HIGH,
    engagement_stage="Evaluation / pre-purchase",
    data_classification=DataClassification.CONFIDENTIAL,
    data_types=["PII (personal information)", "Customer communications"],
    regulatory_scope=["GDPR", "CCPA / CPRA"],
    record_volume="~50,000 transcripts per year",
    used_by="Employees",
    user_count="250",
    integrates_with_internal_systems=True,
    integrated_systems="Google Calendar, Slack, Salesforce",
    ai_capabilities=["Summarization", "Content generation", "Autonomous actions / agentic"],
    affects_decisions_about_people=False,
    model_hosting="Third-party LLM provider",
)

REVIEWER_NOTES = (
    "Conditional approval for internal, non-confidential meetings only. Vendor must contractually "
    "disable model training on customer data and provide a current SOC 2 Type II report before use "
    "is expanded to client meetings. Re-assess at renewal or on any material model change."
)


def _with_back_link(html: str) -> str:
    """Adds a "back to overview" banner, for the copy published on the docs/
    landing page only. build_html_report() itself stays landing-page-agnostic
    since the same function produces the report a user downloads straight out
    of the live app, where there's no landing page to link back to.
    """
    banner = (
        '<a href="index.html" style="display:block;text-align:center;padding:.6rem;'
        'background:#4f46e5;color:#fff;text-decoration:none;font-size:.85rem;'
        'font-weight:600;">&larr; Back to overview</a>'
    )
    return html.replace("<body>", f"<body>\n{banner}", 1)


def main() -> None:
    load_dotenv(ROOT / ".env")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is not set — see .env.example")

    pdfs = sorted(SAMPLE_DOCS.glob("*.pdf"))
    if not pdfs:
        raise SystemExit("No PDFs in sample_docs/ — run scripts/make_sample_docs.py first")

    assessment = VendorAssessment(profile=PROFILE)

    print(f"Reading {len(pdfs)} document(s)...")
    pages = []
    for pdf in pdfs:
        pages.extend(extract_pdf_pages(pdf))
    print(f"  {len(pages)} pages of text")

    print("Screening for prompt injection...")
    for page in pages:
        flags = scan_text(page.document, page.page, page.text)
        assessment.injection_flags.extend(flags)
        page.text = sanitize_for_prompt(page.text, flags)
    print(f"  {len(assessment.injection_flags)} span(s) redacted")

    print("Extracting evidence (live API call)...")
    assessment.evidence = extract_evidence(pages).evidence
    verified = sum(1 for e in assessment.evidence if e.verified)
    print(f"  {verified}/{len(assessment.evidence)} questions evidenced")

    print("Scoring and mapping...")
    assessment = assess(assessment)
    assessment.rmf_mappings = map_all([e.question_id for e in assessment.evidence])
    assessment.decision = Decision.CONDITIONAL
    assessment.recommendation = REVIEWER_NOTES

    analysis = analyze(assessment)
    print(f"  inherent={assessment.inherent_risk.value} residual={assessment.residual_risk.value}")
    print(f"  {len(analysis.register)} risk register entries")

    DOCS.mkdir(exist_ok=True)
    OUT_HTML.write_text(_with_back_link(build_html_report(assessment)), encoding="utf-8")
    write_excel_report(assessment, OUT_XLSX)
    OUT_FIXTURE.write_text(dumps(assessment), encoding="utf-8")

    # A fixture that can't be read back would break demo mode at runtime, so
    # verify the round-trip here rather than discovering it in the deployed app.
    reloaded = loads(OUT_FIXTURE.read_text(encoding="utf-8"))
    assert reloaded.inherent_risk == assessment.inherent_risk
    assert len(reloaded.evidence) == len(assessment.evidence)

    print(f"\nwrote {OUT_HTML.relative_to(ROOT)}")
    print(f"wrote {OUT_XLSX.relative_to(ROOT)}")
    print(f"wrote {OUT_FIXTURE.relative_to(ROOT)} (round-trip verified)")


if __name__ == "__main__":
    main()

"""Generates the showcase sample report from the synthetic vendor packet.

This runs the *real* pipeline — PDF extraction, injection screening, live LLM
extraction, scoring, analysis — against sample_docs/*.pdf. The published sample
report is therefore genuine tool output, not a hand-authored mockup.

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

SAMPLE_DOCS = ROOT / "sample_docs"
OUT_HTML = SAMPLE_DOCS / "sample_report.html"
OUT_XLSX = SAMPLE_DOCS / "sample_risk_register.xlsx"

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

    OUT_HTML.write_text(build_html_report(assessment), encoding="utf-8")
    write_excel_report(assessment, OUT_XLSX)
    print(f"\nwrote {OUT_HTML.relative_to(ROOT)}")
    print(f"wrote {OUT_XLSX.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

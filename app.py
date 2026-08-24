"""Streamlit UI: upload vendor docs -> screen -> extract -> score -> map -> report.

Run with: streamlit run app.py
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from src.extraction import extract_pdf_pages
from src.injection_guard import sanitize_for_prompt, scan_text
from src.llm_extractor import extract_evidence
from src.models import RiskLevel, VendorAssessment
from src.report import write_excel_report
from src.risk_scoring import assess
from src.rmf_mapping import map_all

load_dotenv()

st.set_page_config(page_title="AI Vendor Risk Assessment Automator", layout="wide")
st.title("AI Vendor Risk Assessment Automator")
st.caption(
    "Upload vendor documentation to generate a preliminary risk assessment. "
    "Every claim is cited to its source document and page — unverifiable claims "
    "are labeled 'Not verified' instead of guessed. A human reviewer must approve "
    "the final recommendation."
)

if "assessment" not in st.session_state:
    st.session_state.assessment = None


def risk_badge(label: str, level: RiskLevel | None) -> None:
    if level is None:
        st.info(f"{label}: not scored")
    elif level == RiskLevel.LOW:
        st.success(f"**{label}: {level.value}**")
    elif level == RiskLevel.MEDIUM:
        st.warning(f"**{label}: {level.value}**")
    else:
        st.error(f"**{label}: {level.value}**")


# --- Sidebar: inputs, kept separate from the results area so reviewing
# results doesn't require re-filling the form. ---
with st.sidebar:
    st.header("Vendor")
    with st.form("vendor_form"):
        vendor_name = st.text_input("Vendor name")
        business_use_case = st.text_input("Business use case")
        data_accessed = st.text_input("Data the AI will access")
        used_by = st.selectbox("Used by", ["employees", "customers", "both"])
        uploaded_files = st.file_uploader(
            "Vendor documents",
            type=["pdf"],
            accept_multiple_files=True,
            help="Privacy policy, security docs, SOC 2, DPA, questionnaire answers",
        )
        submitted = st.form_submit_button("Run assessment", use_container_width=True)

if submitted:
    if not vendor_name or not uploaded_files:
        st.error("Vendor name and at least one document are required.")
        st.stop()

    assessment = VendorAssessment(
        vendor_name=vendor_name,
        business_use_case=business_use_case,
        data_accessed=data_accessed,
        used_by=used_by,
    )

    with st.spinner("Extracting document text..."):
        all_pages = []
        with tempfile.TemporaryDirectory() as tmpdir:
            for uf in uploaded_files:
                path = Path(tmpdir) / uf.name
                path.write_bytes(uf.read())
                all_pages.extend(extract_pdf_pages(path))

    with st.spinner("Screening for prompt injection..."):
        for page in all_pages:
            flags = scan_text(page.document, page.page, page.text)
            assessment.injection_flags.extend(flags)
            page.text = sanitize_for_prompt(page.text, flags)

    try:
        with st.spinner("Extracting evidence with citations..."):
            result = extract_evidence(all_pages)
            assessment.evidence = result.evidence
    except RuntimeError as e:
        st.error(str(e))
        st.stop()
    except json.JSONDecodeError:
        st.error(
            "The model's response couldn't be parsed as JSON, so no evidence was extracted. "
            "This usually clears up on a retry — try running the assessment again."
        )
        st.stop()
    except Exception as e:  # anthropic SDK errors (auth, rate limit, network, etc.)
        st.error(f"Evidence extraction failed: {e}")
        st.stop()

    assessment = assess(assessment)
    assessment.rmf_mappings = map_all([e.question_id for e in assessment.evidence])
    st.session_state.assessment = assessment

assessment = st.session_state.assessment

if assessment is None:
    st.info("Fill in the vendor details and upload documents in the sidebar to run an assessment.")
    st.stop()

st.subheader(f"Result — {assessment.vendor_name}")

if assessment.injection_flags:
    st.warning(f"{len(assessment.injection_flags)} suspicious span(s) were redacted before extraction.")
    with st.expander("View screened content"):
        for f in assessment.injection_flags:
            st.write(f"**{f.document}, p.{f.page}** — {f.reason}: _{f.snippet}_")

c1, c2 = st.columns(2)
with c1:
    risk_badge("Inherent risk", assessment.inherent_risk)
with c2:
    risk_badge("Residual risk", assessment.residual_risk)

unverified = assessment.unverified_questions()
if unverified:
    st.warning(f"{len(unverified)} question(s) could not be verified from the provided documents:")
    for e in unverified:
        st.write(f"- {e.question_text}")

st.subheader("Evidence")
st.dataframe(
    [
        {
            "Question": e.question_text,
            "Answer": e.answer if e.verified else "Not verified",
            "Verified": "✅" if e.verified else "❌",
            "Source": f"{e.citation.document} p.{e.citation.page}" if e.citation else "—",
        }
        for e in assessment.evidence
    ],
    use_container_width=True,
    hide_index=True,
)

st.subheader("Findings")
if assessment.findings:
    for finding in assessment.findings:
        st.write(f"- **[{finding.severity.value}]** {finding.summary}")
else:
    st.write("No findings raised.")

st.subheader("Human review")
recommendation = st.text_area("Recommendation (required before export)", key="recommendation")
if st.button("Export risk register") and recommendation:
    assessment.recommendation = recommendation
    out_path = write_excel_report(assessment, f"{assessment.vendor_name.replace(' ', '_')}_risk_register.xlsx")
    with open(out_path, "rb") as f:
        st.download_button("Download report", f, file_name=out_path.name)

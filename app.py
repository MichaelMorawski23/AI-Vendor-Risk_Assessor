"""Streamlit UI: intake -> upload -> screen -> extract -> score -> map -> report.

Run with: streamlit run app.py
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from src.analysis import analyze
from src.charts import domain_stacked_chart, donut_chart, severity_bar_chart
from src.extraction import extract_pdf_pages
from src.injection_guard import sanitize_for_prompt, scan_text
from src.llm_extractor import extract_evidence
from src.models import (
    Criticality,
    DataClassification,
    Decision,
    RiskLevel,
    VendorAssessment,
    VendorProfile,
)
from src.html_report import build_html_report
from src.questions import QUESTIONS_BY_ID
from src.report import build_excel_bytes
from src.run_limit import run_button_state
from src.serialization import loads
from src.risk_scoring import (
    AI_CAPABILITY_OPTIONS,
    DATA_TYPE_OPTIONS,
    DEPLOYMENT_OPTIONS,
    ENGAGEMENT_STAGE_OPTIONS,
    MODEL_HOSTING_OPTIONS,
    REGULATORY_OPTIONS,
    USED_BY_OPTIONS,
    assess,
)
from src.rmf_mapping import map_all

load_dotenv()

# On Streamlit Community Cloud the API key is entered into the app's Secrets
# panel (st.secrets), not a .env file. Bridge it into os.environ once at
# startup so the rest of the codebase — llm_extractor.py included — only ever
# has to know about a plain environment variable, not which host it's running on.
if not os.environ.get("ANTHROPIC_API_KEY"):
    try:
        if "ANTHROPIC_API_KEY" in st.secrets:
            os.environ["ANTHROPIC_API_KEY"] = st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        pass  # no secrets.toml locally — expected outside of Streamlit Cloud

st.set_page_config(
    page_title="AI Vendor Risk Assessment Automator",
    page_icon="🛡️",
    layout="centered",
)

# Colors are used only as a tint and a left accent bar; all text inherits the
# theme foreground, so the cards stay readable in both light and dark mode.
RISK_COLORS: dict[RiskLevel, str] = {
    RiskLevel.LOW: "#16a34a",
    RiskLevel.MEDIUM: "#d97706",
    RiskLevel.HIGH: "#dc2626",
    RiskLevel.CRITICAL: "#991b1b",
}

st.markdown(
    """
    <style>
      .stAppDeployButton { display: none; }
      .block-container { padding-top: 3rem; max-width: 900px; }
      .hero h1 { font-size: 1.9rem; font-weight: 700; margin: 0 0 .35rem 0; letter-spacing: -0.02em; }
      .hero p { opacity: .72; margin: 0; font-size: .95rem; line-height: 1.5; }
      .risk-card {
        border-radius: 10px; padding: .85rem 1rem; margin-bottom: .5rem;
        border: 1px solid rgba(128,128,128,.22);
      }
      .risk-card .label {
        font-size: .7rem; text-transform: uppercase; letter-spacing: .08em;
        opacity: .65; margin-bottom: .2rem;
      }
      .risk-card .value { font-size: 1.5rem; font-weight: 700; line-height: 1.1; }
      .stat { font-size: .8rem; opacity: .7; }
      .flow { display: flex; align-items: center; flex-wrap: wrap; gap: .4rem; margin: 1.3rem 0 .3rem; }
      .flow-step {
        display: flex; align-items: center; gap: .5rem; background: rgba(128,128,128,.08);
        border: 1px solid rgba(128,128,128,.22); border-radius: 999px; padding: .4rem .9rem .4rem .6rem;
      }
      .flow-step .num {
        width: 1.3rem; height: 1.3rem; border-radius: 999px; background: #4f46e5; color: #fff;
        font-size: .68rem; font-weight: 700; display: flex; align-items: center; justify-content: center;
        flex-shrink: 0;
      }
      .flow-step .txt { font-size: .8rem; font-weight: 600; opacity: .9; }
      .flow-arrow { opacity: .35; font-size: .85rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
      <h1>AI Vendor Risk Assessment Automator</h1>
      <p>Preliminary third-party risk assessment for AI tools. Every extracted claim is
      cited to its source document and page — anything the documentation doesn't support
      is marked <strong>Not verified</strong> rather than guessed, and a human reviewer
      owns the final decision.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

_FLOW_STEPS = ["Upload", "Screen", "Extract", "Score", "Report"]
st.markdown(
    '<div class="flow">'
    + '<span class="flow-arrow">→</span>'.join(
        f'<div class="flow-step"><div class="num">{i}</div><div class="txt">{step}</div></div>'
        for i, step in enumerate(_FLOW_STEPS, start=1)
    )
    + "</div>",
    unsafe_allow_html=True,
)

if "assessment" not in st.session_state:
    st.session_state.assessment = None
if "run_count" not in st.session_state:
    st.session_state.run_count = 0
if "is_demo" not in st.session_state:
    st.session_state.is_demo = False

DEMO_FIXTURE = Path(__file__).parent / "src" / "demo_assessment.json"


def svg_block(svg: str) -> str:
    """Wrap a chart so it inherits Streamlit's theme text color.

    The charts draw their labels with fill="currentColor"; without an explicit
    color on a wrapper the SVG would fall back to black and vanish in dark mode.
    """
    if not svg:
        return ""
    return f'<div style="color:var(--text-color);line-height:0;">{svg}</div>'


def risk_card(label: str, level: RiskLevel | None) -> None:
    if level is None:
        st.markdown(
            f'<div class="risk-card"><div class="label">{label}</div>'
            f'<div class="value">Not scored</div></div>',
            unsafe_allow_html=True,
        )
        return
    color = RISK_COLORS[level]
    st.markdown(
        f'<div class="risk-card" style="background:{color}1a;border-left:4px solid {color};">'
        f'<div class="label">{label}</div>'
        f'<div class="value">{level.value}</div></div>',
        unsafe_allow_html=True,
    )


# ------------------------------------------------------------- Demo mode ----
# Loads a pre-computed assessment of the synthetic SampleAI packet. Costs
# nothing and needs no API key, so the tool can be explored without one — and
# so a public deployment isn't an open tab on the owner's API budget.
if DEMO_FIXTURE.exists() and st.session_state.assessment is None:
    demo_col, _ = st.columns([1, 1])
    with demo_col:
        if st.button("Load demo assessment", use_container_width=True):
            st.session_state.assessment = loads(DEMO_FIXTURE.read_text(encoding="utf-8"))
            st.session_state.is_demo = True
            st.rerun()
    st.caption(
        "No API key required — loads a saved assessment of a fictional vendor, "
        "generated by running this pipeline over the documents in `sample_docs/`."
    )

st.write("")

# ---------------------------------------------------------------- Intake ----
with st.form("intake"):
    tab_vendor, tab_data, tab_ai, tab_docs = st.tabs(
        ["Vendor", "Data & regulatory", "Users & AI", "Documents"]
    )

    with tab_vendor:
        c1, c2 = st.columns(2)
        vendor_name = c1.text_input("Vendor name *")
        product_name = c2.text_input("Product / service")
        c3, c4 = st.columns(2)
        vendor_website = c3.text_input("Vendor website")
        business_owner = c4.text_input("Business owner / requester")
        c5, c6 = st.columns(2)
        deployment_model = c5.selectbox("Deployment model", DEPLOYMENT_OPTIONS)
        engagement_stage = c6.selectbox("Engagement stage", ENGAGEMENT_STAGE_OPTIONS)
        business_use_case = st.text_area("Business use case", height=80)
        criticality = st.select_slider(
            "Business criticality",
            options=list(Criticality),
            value=Criticality.MODERATE,
            format_func=lambda c: c.value.split(" — ")[0],
            help="Impact on the business if this tool becomes unavailable.",
        )

    with tab_data:
        data_classification = st.select_slider(
            "Highest data classification the tool will touch",
            options=list(DataClassification),
            value=DataClassification.INTERNAL,
            format_func=lambda d: d.value,
        )
        data_types = st.multiselect("Data types processed", list(DATA_TYPE_OPTIONS))
        regulatory_scope = st.multiselect("Regulatory scope", REGULATORY_OPTIONS)
        record_volume = st.text_input("Approx. record volume", placeholder="e.g. 50,000 customer records")

    with tab_ai:
        c7, c8 = st.columns(2)
        used_by = c7.selectbox("Used by", USED_BY_OPTIONS)
        user_count = c8.text_input("Approx. user count", placeholder="e.g. 250")
        integrates = st.checkbox("Integrates with internal systems")
        integrated_systems = st.text_input(
            "Which systems?", placeholder="e.g. Salesforce, Active Directory, S3"
        )
        st.divider()
        ai_capabilities = st.multiselect("AI capabilities in scope", list(AI_CAPABILITY_OPTIONS))
        affects_decisions = st.checkbox(
            "AI influences decisions about individuals",
            help="Employment, credit, access, eligibility, or similar consequential decisions.",
        )
        model_hosting = st.selectbox("Model hosting", MODEL_HOSTING_OPTIONS)

    with tab_docs:
        uploaded_files = st.file_uploader(
            "Vendor documentation (PDF)",
            type=["pdf"],
            accept_multiple_files=True,
            help="Privacy policy, security whitepaper, SOC 2 report, DPA, questionnaire answers.",
        )
        st.caption(
            "Documents are screened for prompt-injection content before any text reaches the model."
        )

    st.write("")
    button = run_button_state(st.session_state.run_count)
    submitted = st.form_submit_button(
        button.label,
        type="primary",
        use_container_width=True,
        disabled=button.disabled,
    )
    if button.disabled:
        st.caption("Refresh the page to start a new session.")

if submitted:
    if not vendor_name or not uploaded_files:
        st.error("Vendor name and at least one document are required.")
        st.stop()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        st.error("ANTHROPIC_API_KEY is not set — see .env.example.")
        st.stop()

    profile = VendorProfile(
        vendor_name=vendor_name,
        product_name=product_name,
        vendor_website=vendor_website,
        deployment_model=deployment_model,
        business_owner=business_owner,
        business_use_case=business_use_case,
        criticality=criticality,
        engagement_stage=engagement_stage,
        data_classification=data_classification,
        data_types=data_types,
        regulatory_scope=regulatory_scope,
        record_volume=record_volume,
        used_by=used_by,
        user_count=user_count,
        integrates_with_internal_systems=integrates,
        integrated_systems=integrated_systems,
        ai_capabilities=ai_capabilities,
        affects_decisions_about_people=affects_decisions,
        model_hosting=model_hosting,
    )
    assessment = VendorAssessment(profile=profile)

    progress = st.progress(0.0, text="Extracting document text...")
    all_pages = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for uf in uploaded_files:
            path = Path(tmpdir) / uf.name
            path.write_bytes(uf.read())
            all_pages.extend(extract_pdf_pages(path))

    if not all_pages:
        progress.empty()
        st.error("No readable text found in the uploaded PDFs. Scanned documents need OCR first.")
        st.stop()

    progress.progress(0.35, text="Screening for prompt injection...")
    for page in all_pages:
        flags = scan_text(page.document, page.page, page.text)
        assessment.injection_flags.extend(flags)
        page.text = sanitize_for_prompt(page.text, flags)

    progress.progress(0.6, text="Extracting evidence with citations...")
    # Counted here rather than at submit: everything above this line is local
    # work, so a run that fails on unreadable PDFs shouldn't consume a rerun.
    # From this point the API call is billed whether or not it succeeds.
    st.session_state.run_count += 1
    try:
        assessment.evidence = extract_evidence(all_pages).evidence
    except RuntimeError as e:
        progress.empty()
        st.error(str(e))
        st.stop()
    except json.JSONDecodeError:
        progress.empty()
        st.error(
            "The model's response couldn't be parsed as JSON, so no evidence was extracted. "
            "This usually clears up on a retry — run the assessment again."
        )
        st.stop()
    except Exception as e:  # anthropic SDK errors (auth, rate limit, network)
        progress.empty()
        st.error(f"Evidence extraction failed: {e}")
        st.stop()

    progress.progress(0.85, text="Scoring and mapping to NIST AI RMF...")
    assessment = assess(assessment)
    assessment.rmf_mappings = map_all([e.question_id for e in assessment.evidence])
    progress.empty()
    st.session_state.assessment = assessment
    st.session_state.is_demo = False

assessment = st.session_state.assessment
if assessment is None:
    st.stop()

# --------------------------------------------------------------- Results ----
st.divider()
st.subheader(assessment.profile.vendor_name or "Assessment")

if st.session_state.is_demo:
    st.info(
        "**Demo assessment** — a saved result for a fictional vendor, produced by running this "
        "pipeline over the sample documents. Run your own by filling in the form above and "
        "uploading documents."
    )

if assessment.injection_flags:
    st.warning(
        f"{len(assessment.injection_flags)} suspicious span(s) were redacted before extraction."
    )

tab_summary, tab_evidence, tab_findings, tab_rmf, tab_review = st.tabs(
    ["Summary", "Evidence", "Findings", "NIST AI RMF", "Review & export"]
)

with tab_summary:
    c1, c2 = st.columns(2)
    with c1:
        risk_card("Inherent risk", assessment.inherent_risk)
    with c2:
        risk_card("Residual risk", assessment.residual_risk)

    st.caption(assessment.residual_rationale)

    verified_count = sum(1 for e in assessment.evidence if e.verified)
    m1, m2, m3 = st.columns(3)
    m1.metric("Verified control coverage", f"{assessment.control_coverage:.0%}")
    m2.metric("Evidence verified", f"{verified_count}/{len(assessment.evidence)}")
    m3.metric("Open findings", len(assessment.findings))

    analysis = analyze(assessment)

    st.markdown("##### Evidence coverage & findings")
    ch1, ch2 = st.columns(2)
    with ch1:
        st.markdown(
            svg_block(
                donut_chart(
                    [
                        ("Evidenced with citation", analysis.verified_count, "#16a34a"),
                        ("Not verified", analysis.unverified_count, "#d97706"),
                    ],
                    center_value=f"{analysis.verified_count / len(assessment.evidence):.0%}"
                    if assessment.evidence
                    else "—",
                    center_label="evidenced",
                )
            ),
            unsafe_allow_html=True,
        )
    with ch2:
        st.markdown(
            svg_block(severity_bar_chart(analysis.severity_counts, RISK_COLORS)),
            unsafe_allow_html=True,
        )

    st.markdown("##### Risk by domain")
    st.markdown(
        svg_block(domain_stacked_chart(analysis.domains, RISK_COLORS)), unsafe_allow_html=True
    )
    st.dataframe(
        [
            {
                "Domain": d.domain,
                "Posture": d.posture.value,
                "Evidenced": f"{d.verified}/{d.total}",
                "Coverage": f"{d.verification_rate:.0%}",
                "Gaps": d.gaps,
                "High-severity gaps": d.high_severity_gaps,
            }
            for d in analysis.domains
        ],
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("What drove inherent risk"):
        st.dataframe(
            [
                {"Factor": d.factor, "Detail": d.detail, "Points": d.points}
                for d in assessment.inherent_drivers
            ],
            use_container_width=True,
            hide_index=True,
        )
        st.caption(
            f"Total: {sum(d.points for d in assessment.inherent_drivers)} points. "
            "Record volume and user count are captured for the register but do not affect the score."
        )

    unverified = assessment.unverified_questions()
    if unverified:
        with st.expander(f"Not verified in documentation ({len(unverified)})"):
            for e in unverified:
                st.write(f"- {e.question_text}")

    if assessment.injection_flags:
        with st.expander(f"Screened content ({len(assessment.injection_flags)})"):
            for f in assessment.injection_flags:
                st.markdown(f"**{f.document}, p.{f.page}** — {f.reason}")
                st.code(f.snippet, language=None)

with tab_evidence:
    only_unverified = st.toggle("Show only unverified", value=False)
    rows = [
        {
            "Domain": QUESTIONS_BY_ID[e.question_id].domain if e.question_id in QUESTIONS_BY_ID else "",
            "Question": e.question_text,
            "Answer": e.answer if e.verified else "Not verified",
            "Verified": e.verified,
            "Source": f"{e.citation.document} p.{e.citation.page}" if e.citation else "—",
            "Quote": e.quote or "",
        }
        for e in assessment.evidence
        if not only_unverified or not e.verified
    ]
    st.dataframe(
        rows,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Domain": st.column_config.TextColumn(width="small"),
            "Question": st.column_config.TextColumn(width="large"),
            "Verified": st.column_config.CheckboxColumn(width="small", disabled=True),
            "Quote": st.column_config.TextColumn(width="medium"),
        },
    )

with tab_findings:
    if not assessment.findings:
        st.success("No control gaps identified.")
    for f in assessment.findings:
        color = RISK_COLORS[f.severity]
        st.markdown(
            f'<div class="risk-card" style="background:{color}12;border-left:4px solid {color};">'
            f'<div class="label">{f.severity.value}</div>'
            f'<div style="font-weight:600;margin-bottom:.25rem;">{f.summary}</div>'
            f'<div class="stat">Recommended control: {f.recommended_control or "—"}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )

with tab_rmf:
    st.dataframe(
        [
            {"Function": m.function.value, "Category": m.category, "Note": m.note}
            for m in assessment.rmf_mappings
        ],
        use_container_width=True,
        hide_index=True,
        column_config={"Note": st.column_config.TextColumn(width="large")},
    )
    st.caption(
        "Simplified crosswalk to NIST AI RMF 1.0 (NIST AI 100-1) for vendor-risk triage — "
        "not an official NIST mapping."
    )

with tab_review:
    st.markdown("**The tool does not approve vendors — a human reviewer makes the final call.**")
    decision = st.selectbox(
        "Decision",
        list(Decision),
        format_func=lambda d: d.value,
        index=list(Decision).index(assessment.decision),
    )
    required_controls = st.multiselect(
        "Required controls",
        options=assessment.required_controls,
        default=assessment.required_controls,
        help="Prefilled from the findings. Trim to the conditions you're actually imposing.",
    )
    recommendation = st.text_area(
        "Reviewer notes / recommendation",
        value=assessment.recommendation or "",
        height=120,
        placeholder="e.g. Conditional approval for non-confidential meetings only, pending SOC 2 delivery.",
    )

    assessment.decision = decision
    assessment.required_controls = required_controls
    assessment.recommendation = recommendation

    if decision == Decision.PENDING or not recommendation.strip():
        st.info("Record a decision and reviewer notes to enable export.")
    else:
        file_stub = assessment.profile.vendor_name.replace(" ", "_")
        dl1, dl2 = st.columns(2)
        with dl1:
            st.download_button(
                "Download full report (.html)",
                data=build_html_report(assessment),
                file_name=f"{file_stub}_risk_report.html",
                mime="text/html",
                type="primary",
                use_container_width=True,
                help="One scrollable page with a table of contents — open it in any browser.",
            )
        with dl2:
            st.download_button(
                "Download risk register (.xlsx)",
                data=build_excel_bytes(assessment),
                file_name=f"{file_stub}_risk_register.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

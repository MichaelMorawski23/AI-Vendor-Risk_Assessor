# AI Vendor Risk Assessment Automator

A tool that turns a vendor's stack of privacy policies, security docs, SOC 2 reports,
and DPAs into a preliminary third-party AI risk assessment: extracted evidence with
citations, an inherent/residual risk score, a NIST AI RMF control mapping, and a
human-reviewed approval recommendation.

Built to demonstrate applied third-party risk management + AI governance + secure
handling of untrusted documents fed into an LLM pipeline.

## Why this exists

Every "just ask ChatGPT to review the vendor docs" approach has two problems:
1. It hallucinates evidence that isn't in the source material.
2. It blindly trusts the content of documents an external vendor wrote — including
   any text in those documents that looks like an instruction.

This tool is built to fail closed on both: unverifiable claims are labeled
**"Not verified"** instead of guessed, and ingested documents pass through a
prompt-injection screen before their content ever reaches the scoring logic.

## How it works

1. **Ingest** — upload vendor docs (privacy policy, security whitepaper, SOC 2,
   DPA, questionnaire answers) as PDF/text.
2. **Screen** — [`src/injection_guard.py`](src/injection_guard.py) scans extracted
   text for instruction-like content before it's included in any LLM prompt, and
   flags/quarantines suspicious segments instead of passing them through silently.
3. **Extract** — an LLM pulls answers to a fixed set of risk questions (training on
   customer data, retention, encryption, SSO/MFA, subprocessors, incident response,
   AI-specific items like prompt-injection protections and human approval gates),
   each answer tagged with the source document and page it came from. No source,
   no claim — the field is marked "Not verified."
4. **Score** — [`src/risk_scoring.py`](src/risk_scoring.py) applies a transparent,
   rule-based scoring model (not an LLM) to compute inherent and residual risk, so
   the score is auditable and reproducible.
5. **Map** — [`src/rmf_mapping.py`](src/rmf_mapping.py) maps findings to NIST AI RMF
   functions (Govern / Map / Measure / Manage) and common TPRM controls.
6. **Report** — generates an Excel/PDF risk register with citations, gaps, and a
   recommendation. A human reviewer makes the final call — the tool never
   auto-approves.

## Status

Early scaffold. Core pure-Python pieces (models, injection screening, risk scoring,
RMF mapping) are implemented and unit-tested. The LLM extraction step and Streamlit
UI are stubbed pending an Anthropic API key.

## Stack

Python, Streamlit, pdfplumber, Claude API (extraction), openpyxl/reportlab (reports).
Rule-based scoring engine — deliberately not LLM-driven, so risk scores are
deterministic and explainable.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env  # add your ANTHROPIC_API_KEY
streamlit run app.py
```

## Roadmap

- [ ] Wire `llm_extractor.py` to Claude API with citation-checking eval set
- [ ] Streamlit UI for upload → review → approve flow
- [ ] Excel/PDF report generation
- [ ] Persist assessments (SQLite)
- [ ] Multi-reviewer approval workflow

## Disclaimer

Sample/synthetic vendor documents only — no real vendor, employer, or client data
is used in this repo. This is a portfolio project, not a certified risk assessment
tool; outputs require human review before any real vendor decision.

## License

MIT — see [LICENSE](LICENSE).

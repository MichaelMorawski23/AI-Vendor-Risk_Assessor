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

1. **Intake** — capture the engagement context: deployment model, business
   criticality, data classification and data types, regulatory scope, user
   population, integrations, AI capabilities, and whether the AI influences
   consequential decisions about people.
2. **Ingest** — upload vendor docs (privacy policy, security whitepaper, SOC 2,
   DPA, questionnaire answers) as PDF.
3. **Screen** — [`src/injection_guard.py`](src/injection_guard.py) scans extracted
   text for instruction-like content before it's included in any LLM prompt, and
   redacts suspicious spans instead of passing them through silently.
4. **Extract** — an LLM answers a fixed set of 21 risk questions across four
   domains (data handling, security, assurance, AI-specific risk), each answer
   tagged with the source document and page it came from. No source, no claim —
   the field is marked "Not verified."
5. **Score** — [`src/risk_scoring.py`](src/risk_scoring.py) applies a transparent,
   rule-based model (not an LLM), following standard TPRM practice:
   - **Inherent risk** comes from the intake profile — the risk of the engagement
     itself, before any vendor control. Shown as an itemized point breakdown.
   - **Control gaps** come from the evidence. An unverified control counts as a
     gap: if the documentation doesn't evidence it, the assessment can't credit it.
   - **Residual risk** is inherent risk reduced by verified control coverage —
     and any unmitigated high-severity gap blocks reduction entirely.
6. **Map** — [`src/rmf_mapping.py`](src/rmf_mapping.py) maps every question to a
   NIST AI RMF function (Govern / Map / Measure / Manage).
7. **Report** — two downloadable outputs. A **self-contained HTML report**
   ([`src/html_report.py`](src/html_report.py)) — one scrollable page with a
   sticky table of contents, covering the executive summary, engagement
   profile, itemized inherent-risk drivers, every cited claim, findings with
   recommended controls, the RMF crosswalk, and whatever the injection screen
   redacted. And a multi-sheet **Excel risk register**
   ([`src/report.py`](src/report.py)) for teams that work in spreadsheets.
   A human reviewer records the decision — the tool never auto-approves.

## Status

Working end-to-end. The pure-Python pieces (models, injection screening, risk
scoring, RMF mapping, report generation) are implemented and unit-tested; the
Streamlit UI and Claude-backed extraction run against real documents with an
`ANTHROPIC_API_KEY` set.

## Stack

Python, Streamlit, pdfplumber, Claude API (extraction), openpyxl/reportlab (reports).
Rule-based scoring engine — deliberately not LLM-driven, so risk scores are
deterministic and explainable.

## Testing

Three layers, from cheapest to most realistic:

1. **Unit tests** (no API key, no network) — the deterministic pieces:
   injection screening, risk scoring, RMF mapping.
   ```bash
   pytest -q
   ```
2. **Extraction eval** (hits the real Anthropic API — costs a small amount) —
   runs the actual extractor against [`sample_docs/`](sample_docs), a synthetic
   three-document vendor packet, and checks every answer against known ground
   truth in [`scripts/make_sample_docs.py`](scripts/make_sample_docs.py). It
   fails hard on any fabricated answer (a "yes/no" where the documents are
   silent) — that's the one failure mode the whole "Not verified" design
   exists to prevent — and reports (without failing outside a threshold) any
   answer that's simply wrong. One of the three documents has a prompt-injection
   payload planted in it, so this also proves the injection guard actually
   fires against real PDF content, not just the unit-test strings.
   ```bash
   pytest tests/test_extraction_eval.py -v -s
   ```
3. **Manual, in the app** — run `streamlit run app.py`, fill in the intake
   form, and upload the files from `sample_docs/`. Regenerate them anytime with
   `python scripts/make_sample_docs.py` (they're synthetic — SampleAI isn't a
   real company).

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env  # add your ANTHROPIC_API_KEY
streamlit run app.py
```

## Roadmap

- [x] Rule-based inherent/residual scoring driven by an intake profile
- [x] Streamlit UI for intake → review → export flow
- [x] Excel risk register generation
- [x] Citation-checking eval set (verify the extractor never invents a source)
- [x] Self-contained HTML report with table of contents
- [ ] Persist assessments (SQLite)
- [ ] Multi-reviewer approval workflow
- [ ] PDF report output alongside HTML/Excel

## Disclaimer

Sample/synthetic vendor documents only — no real vendor, employer, or client data
is used in this repo. This is a portfolio project, not a certified risk assessment
tool; outputs require human review before any real vendor decision.

## License

MIT — see [LICENSE](LICENSE).

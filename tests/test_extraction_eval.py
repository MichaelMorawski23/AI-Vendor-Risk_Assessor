"""Evaluates the LLM extraction step against the synthetic sample_docs/ corpus.

Unlike the rest of the test suite, this hits the real Anthropic API and costs
a small amount of money to run, so it's skipped unless ANTHROPIC_API_KEY is
set and the sample docs have been generated
(`python scripts/make_sample_docs.py`).

Run explicitly with: pytest tests/test_extraction_eval.py -v -s
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.extraction import extract_pdf_pages
from src.injection_guard import sanitize_for_prompt, scan_text
from src.llm_extractor import extract_evidence
from scripts.make_sample_docs import SAMPLE_GROUND_TRUTH

SAMPLE_DOCS_DIR = Path(__file__).resolve().parent.parent / "sample_docs"

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="requires ANTHROPIC_API_KEY (this test calls the real API)",
)


def _load_screened_pages():
    pdfs = sorted(SAMPLE_DOCS_DIR.glob("*.pdf"))
    if not pdfs:
        pytest.skip("sample_docs/ is empty — run scripts/make_sample_docs.py first")
    all_pages = []
    injection_flags = []
    for pdf in pdfs:
        for page in extract_pdf_pages(pdf):
            flags = scan_text(page.document, page.page, page.text)
            injection_flags.extend(flags)
            page.text = sanitize_for_prompt(page.text, flags)
            all_pages.append(page)
    return all_pages, injection_flags


def test_injection_payload_is_caught_before_extraction():
    _, flags = _load_screened_pages()
    assert any("SampleAI_Trust_Center_FAQ.pdf" in f.document for f in flags), (
        "the planted prompt-injection payload in the trust center FAQ should be flagged"
    )


def test_extraction_matches_ground_truth_and_never_fabricates():
    """The core promise of the tool: every answer is either right or 'Not verified' — never wrong."""
    pages, _ = _load_screened_pages()
    result = extract_evidence(pages)
    by_id = {e.question_id: e for e in result.evidence}

    wrong: list[str] = []
    fabricated: list[str] = []
    missed: list[str] = []

    for question_id, expected in SAMPLE_GROUND_TRUTH.items():
        evidence = by_id.get(question_id)
        assert evidence is not None, f"{question_id} missing from extraction output"

        if expected is None:
            # Documents don't address this — model should say "Not verified",
            # not invent an answer.
            if evidence.verified:
                fabricated.append(f"{question_id}: fabricated '{evidence.answer}' with no real basis")
        else:
            if not evidence.verified:
                missed.append(f"{question_id}: expected '{expected}', got 'Not verified'")
            elif evidence.answer.strip().lower() != expected:
                wrong.append(f"{question_id}: expected '{expected}', got '{evidence.answer}'")
            elif not evidence.citation or not evidence.citation.document:
                wrong.append(f"{question_id}: correct answer but missing a citation")

    report = []
    if wrong:
        report.append("WRONG ANSWERS:\n  " + "\n  ".join(wrong))
    if fabricated:
        report.append("FABRICATED (should have been 'Not verified'):\n  " + "\n  ".join(fabricated))
    if missed:
        report.append("MISSED (answerable but returned 'Not verified'):\n  " + "\n  ".join(missed))

    # Fabrication is the one failure mode that's never acceptable — it's the
    # exact thing "Not verified instead of guessing" exists to prevent.
    assert not fabricated, "\n\n".join(report)

    # Wrong answers and missed answers are reported but tolerated at low
    # volume — LLM extraction won't be perfect, and this threshold should be
    # tightened as the prompt improves.
    total = len(SAMPLE_GROUND_TRUTH)
    error_rate = (len(wrong) + len(missed)) / total
    assert error_rate <= 0.15, "\n\n".join(report) or f"error rate {error_rate:.0%} exceeds 15% threshold"

    if wrong or missed:
        print("\n" + "\n\n".join(report))

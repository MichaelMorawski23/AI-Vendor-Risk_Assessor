from src.html_report import build_html_report
from src.models import (
    Citation,
    Decision,
    EvidenceItem,
    InjectionFlag,
    VendorAssessment,
    VendorProfile,
)
from src.risk_scoring import assess


def _assessment(**profile_kwargs) -> VendorAssessment:
    profile = VendorProfile(vendor_name=profile_kwargs.pop("vendor_name", "TestVendor"), **profile_kwargs)
    return assess(VendorAssessment(profile=profile))


def test_report_contains_every_section_anchor():
    a = _assessment()
    a.injection_flags = [InjectionFlag("doc.pdf", 1, "snippet", "matched", "reason")]
    html = build_html_report(a)
    for anchor in [
        "summary", "domains", "register", "profile", "inherent",
        "evidence", "rmf", "screened", "review", "methodology",
    ]:
        assert f'id="{anchor}"' in html, f"missing section {anchor}"
        assert f'href="#{anchor}"' in html, f"missing TOC link for {anchor}"


def test_screened_section_omitted_when_nothing_was_flagged():
    html = build_html_report(_assessment())
    assert 'id="screened"' not in html


def test_untrusted_document_content_is_escaped():
    """Vendor documents are untrusted input; their text must not become live HTML.

    A malicious PDF could otherwise plant script in a citation or quote and get
    it executed in the browser of whoever opens the exported report.
    """
    a = _assessment()
    a.evidence = [
        EvidenceItem(
            question_id="has_soc2",
            question_text="Does the vendor have a current SOC 2 report?",
            answer="yes",
            citation=Citation(document="<script>alert('xss')</script>.pdf", page=1),
            verified=True,
            quote="<img src=x onerror=alert('quote')>",
        )
    ]
    a.injection_flags = [
        InjectionFlag("doc.pdf", 1, "<svg onload=alert('flag')>", "matched", "reason")
    ]
    html = build_html_report(a)

    assert "<script>alert('xss')</script>" not in html
    assert "<img src=x onerror=" not in html
    assert "<svg onload=" not in html
    # The content is still present, just neutralized.
    assert "&lt;script&gt;" in html


def test_reviewer_notes_are_escaped():
    a = _assessment()
    a.decision = Decision.CONDITIONAL
    a.recommendation = "<script>alert('notes')</script>"
    html = build_html_report(a)
    assert "<script>alert('notes')</script>" not in html

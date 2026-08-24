from src.analysis import analyze, domain_breakdowns, executive_narrative, risk_register, rmf_coverage
from src.models import (
    Citation,
    Criticality,
    DataClassification,
    EvidenceItem,
    InjectionFlag,
    RiskLevel,
    VendorAssessment,
    VendorProfile,
)
from src.questions import RISK_QUESTIONS
from src.risk_scoring import assess


def _verified(question_id: str, answer: str) -> EvidenceItem:
    return EvidenceItem(question_id, question_id, answer, Citation("doc.pdf", 1), True)


def _unverified(question_id: str) -> EvidenceItem:
    return EvidenceItem(question_id, question_id, None, None, False)


def _full_assessment(answers: dict[str, str] | None = None) -> VendorAssessment:
    """An assessment covering every question, defaulting to the non-risky answer."""
    answers = answers or {}
    risky_yes = {
        "trains_on_customer_data", "data_retention_unbounded", "data_stored_offshore_unclear",
        "sensitive_data_can_appear_in_output", "ai_can_access_other_systems",
    }
    evidence = []
    for q in RISK_QUESTIONS:
        if q.id in answers:
            value = answers[q.id]
            evidence.append(_unverified(q.id) if value is None else _verified(q.id, value))
        else:
            evidence.append(_verified(q.id, "no" if q.id in risky_yes else "yes"))
    a = VendorAssessment(profile=VendorProfile(vendor_name="TestVendor"))
    a.evidence = evidence
    return assess(a)


def test_domains_cover_every_question():
    a = _full_assessment()
    breakdowns = domain_breakdowns(a)
    assert sum(d.total for d in breakdowns) == len(RISK_QUESTIONS)
    assert {d.domain for d in breakdowns} == {q.domain for q in RISK_QUESTIONS}


def test_clean_domain_has_low_posture_and_full_coverage():
    a = _full_assessment()
    for d in domain_breakdowns(a):
        assert d.verification_rate == 1.0
        assert d.posture == RiskLevel.LOW


def test_high_severity_gap_drives_domain_posture_high():
    # data_encrypted is a 3-point (HIGH severity) rule in the Security domain.
    a = _full_assessment({"data_encrypted": "no"})
    security = next(d for d in domain_breakdowns(a) if d.domain == "Security")
    assert security.high_severity_gaps >= 1
    assert security.posture == RiskLevel.HIGH


def test_unverified_evidence_lowers_domain_coverage():
    a = _full_assessment({"has_soc2": None})
    assurance = next(d for d in domain_breakdowns(a) if d.domain == "Assurance")
    assert assurance.verification_rate < 1.0
    assert assurance.gaps >= 1


def test_rmf_coverage_spans_all_four_functions():
    a = _full_assessment()
    coverage = rmf_coverage(a)
    assert {c.function.value for c in coverage} == {"Govern", "Map", "Measure", "Manage"}
    assert all(c.verification_rate == 1.0 for c in coverage)


def test_register_ids_are_sequential_and_padded():
    a = _full_assessment({"has_soc2": "no", "data_encrypted": "no", "bias_testing": "no"})
    rows = risk_register(a)
    assert [r.risk_id for r in rows] == [f"RISK-{i:03d}" for i in range(1, len(rows) + 1)]


def test_register_distinguishes_confirmed_gaps_from_unverified_ones():
    a = _full_assessment({"has_soc2": "no", "bias_testing": None})
    by_finding = {r.finding: r for r in risk_register(a)}
    confirmed = [r for r in by_finding.values() if r.evidence_status == "Vendor-confirmed"]
    unverified = [r for r in by_finding.values() if r.evidence_status == "Not verified"]
    assert confirmed and unverified


def test_narrative_mentions_vendor_and_both_risk_levels():
    a = _full_assessment({"data_encrypted": "no"})
    narrative = executive_narrative(a)
    assert "TestVendor" in narrative
    assert a.inherent_risk.value.lower() in narrative.lower()
    assert a.residual_risk.value.lower() in narrative.lower()


def test_narrative_reports_screened_content():
    a = _full_assessment()
    a.injection_flags = [InjectionFlag("evil.pdf", 2, "snippet", "matched", "override attempt")]
    assert "evil.pdf" in executive_narrative(a)
    assert "prompt-injection" in executive_narrative(a)


def test_narrative_handles_an_unscored_assessment():
    a = VendorAssessment(profile=VendorProfile(vendor_name="Unscored"))
    assert "not been scored" in executive_narrative(a)


def test_analyze_flags_when_controls_actually_reduced_risk():
    strong = _full_assessment()  # every control verified, no high-severity gaps
    strong.profile = VendorProfile(
        vendor_name="TestVendor",
        criticality=Criticality.CRITICAL,
        data_classification=DataClassification.RESTRICTED,
    )
    strong = assess(strong)
    assert analyze(strong).risk_reduced

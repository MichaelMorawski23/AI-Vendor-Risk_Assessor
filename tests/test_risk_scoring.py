from src.models import (
    Citation,
    Criticality,
    DataClassification,
    EvidenceItem,
    RiskLevel,
    VendorProfile,
)
from src.risk_scoring import (
    MITIGATING_CONTROLS,
    control_coverage,
    identify_control_gaps,
    score_inherent_risk,
    score_residual_risk,
)


def _verified(question_id: str, answer: str) -> EvidenceItem:
    return EvidenceItem(
        question_id=question_id,
        question_text=question_id,
        answer=answer,
        citation=Citation(document="doc.pdf", page=1),
        verified=True,
    )


def _unverified(question_id: str) -> EvidenceItem:
    return EvidenceItem(question_id=question_id, question_text=question_id, answer=None, citation=None, verified=False)


# --- Inherent risk: driven by engagement context, not vendor controls ---


def test_low_stakes_engagement_scores_low_inherent():
    profile = VendorProfile(
        vendor_name="SampleAI",
        criticality=Criticality.LOW,
        data_classification=DataClassification.PUBLIC,
        ai_capabilities=["Summarization"],
        used_by="Employees",
    )
    level, drivers = score_inherent_risk(profile)
    assert level == RiskLevel.LOW
    assert sum(d.points for d in drivers) <= 6


def test_regulated_agentic_engagement_scores_critical_inherent():
    profile = VendorProfile(
        vendor_name="SampleAI",
        criticality=Criticality.CRITICAL,
        data_classification=DataClassification.RESTRICTED,
        data_types=["PHI (health information)", "PII (personal information)"],
        regulatory_scope=["HIPAA", "GDPR"],
        used_by="Both",
        ai_capabilities=["Autonomous actions / agentic"],
        affects_decisions_about_people=True,
        integrates_with_internal_systems=True,
    )
    level, _ = score_inherent_risk(profile)
    assert level == RiskLevel.CRITICAL


def test_inherent_drivers_are_itemized():
    profile = VendorProfile(
        vendor_name="SampleAI",
        data_classification=DataClassification.CONFIDENTIAL,
        affects_decisions_about_people=True,
    )
    _, drivers = score_inherent_risk(profile)
    factors = {d.factor for d in drivers}
    assert "Data classification" in factors
    assert "Consequential decisions" in factors


# --- Control gaps: driven by evidence ---


def _all_controls_present() -> list[EvidenceItem]:
    """Every mitigating control verified present (non-risky answer)."""
    risky_yes = {"trains_on_customer_data", "data_retention_unbounded",
                 "data_stored_offshore_unclear", "sensitive_data_can_appear_in_output",
                 "ai_can_access_other_systems"}
    return [
        _verified(qid, "no" if qid in risky_yes else "yes")
        for qid in MITIGATING_CONTROLS
    ]


def test_unverified_evidence_counts_as_a_gap():
    evidence = [_unverified("has_soc2"), _unverified("data_encrypted")]
    score, findings = identify_control_gaps(evidence)
    assert score > 0
    assert all("not verified" in f.summary for f in findings)


def test_findings_carry_a_recommended_control():
    _, findings = identify_control_gaps([_verified("has_soc2", "no")])
    assert findings[0].recommended_control


def test_control_coverage_ignores_unverified():
    evidence = [_verified("supports_sso_mfa", "yes"), _unverified("data_encrypted")]
    assert control_coverage(evidence) == 0.5


# --- Residual risk ---


def test_high_severity_gap_blocks_any_reduction():
    evidence = _all_controls_present()
    # Replace encryption (a 3-point, HIGH-severity rule) with a failing answer.
    evidence = [e for e in evidence if e.question_id != "data_encrypted"]
    evidence.append(_verified("data_encrypted", "no"))
    residual, rationale, _ = score_residual_risk(RiskLevel.HIGH, evidence)
    assert residual == RiskLevel.HIGH
    assert "high-severity" in rationale


def test_strong_coverage_steps_risk_down_two_levels():
    residual, _, coverage = score_residual_risk(RiskLevel.CRITICAL, _all_controls_present())
    assert coverage >= 0.8
    assert residual == RiskLevel.MEDIUM


def test_residual_never_falls_below_low():
    residual, _, _ = score_residual_risk(RiskLevel.LOW, _all_controls_present())
    assert residual == RiskLevel.LOW


def test_no_verified_controls_means_no_reduction():
    evidence = [_unverified(qid) for qid in MITIGATING_CONTROLS]
    residual, _, coverage = score_residual_risk(RiskLevel.HIGH, evidence)
    assert coverage == 0.0
    assert residual == RiskLevel.HIGH

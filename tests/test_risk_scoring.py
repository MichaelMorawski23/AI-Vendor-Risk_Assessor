from src.models import Citation, EvidenceItem, RiskLevel
from src.risk_scoring import score_inherent_risk, score_residual_risk


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


def test_well_controlled_vendor_scores_low():
    evidence = [
        _verified("trains_on_customer_data", "no"),
        _verified("data_retention_unbounded", "no"),
        _verified("customer_can_delete_data", "yes"),
        _verified("data_encrypted", "yes"),
        _verified("has_soc2", "yes"),
        _verified("subprocessors_disclosed", "yes"),
        _verified("data_stored_offshore_unclear", "no"),
        _verified("rbac_available", "yes"),
        _verified("supports_sso_mfa", "yes"),
        _verified("incident_reporting_defined", "yes"),
        _verified("sensitive_data_can_appear_in_output", "no"),
        _verified("ai_actions_logged", "yes"),
        _verified("human_approval_required", "yes"),
        _verified("prompt_injection_protections", "yes"),
        _verified("ai_can_access_other_systems", "no"),
    ]
    level, findings = score_inherent_risk(evidence)
    assert level == RiskLevel.LOW
    assert findings == []


def test_unverified_evidence_counts_against_vendor():
    evidence = [_unverified("has_soc2"), _unverified("data_encrypted")]
    level, findings = score_inherent_risk(evidence)
    assert level != RiskLevel.LOW
    assert any("unverified" in f.summary for f in findings)


def test_residual_risk_only_drops_for_verified_controls():
    evidence = [_verified("trains_on_customer_data", "yes"), _unverified("supports_sso_mfa")]
    residual = score_residual_risk(RiskLevel.HIGH, evidence, mitigating_controls=["supports_sso_mfa"])
    assert residual == RiskLevel.HIGH  # unverified control must not reduce risk

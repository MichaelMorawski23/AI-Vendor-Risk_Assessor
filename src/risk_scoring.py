"""Deterministic, rule-based risk scoring — deliberately not LLM-driven.

The extraction step (LLM) turns documents into structured evidence answers.
This module turns those answers into a risk score using fixed rules, so the
score is auditable: given the same evidence, it always produces the same
result, and every point can be traced back to a specific rule.
"""

from __future__ import annotations

from .models import EvidenceItem, RiskFinding, RiskLevel, VendorAssessment

# (question_id, condition on answer, points, finding text) — points are additive;
# thresholds below convert the total into Low/Medium/High.
_RISK_RULES: list[tuple[str, str, int, str]] = [
    ("trains_on_customer_data", "yes", 3, "Vendor may train models on customer data"),
    ("data_retention_unbounded", "yes", 2, "No defined data retention limit"),
    ("customer_can_delete_data", "no", 2, "Customers cannot request data deletion"),
    ("data_encrypted", "no", 3, "Data is not confirmed encrypted at rest/in transit"),
    ("has_soc2", "no", 2, "No SOC 2 report available"),
    ("subprocessors_disclosed", "no", 2, "Subprocessors are not disclosed"),
    ("data_stored_offshore_unclear", "yes", 1, "Data storage location unclear or offshore with no safeguard"),
    ("rbac_available", "no", 1, "No role-based access control"),
    ("supports_sso_mfa", "no", 2, "No SSO/MFA support"),
    ("incident_reporting_defined", "no", 2, "No defined security incident notification process"),
    ("sensitive_data_can_appear_in_output", "yes", 2, "Sensitive data may appear in AI outputs"),
    ("ai_actions_logged", "no", 2, "AI actions are not logged/monitored"),
    ("human_approval_required", "no", 2, "No human-in-the-loop for consequential AI actions"),
    ("prompt_injection_protections", "no", 2, "No stated prompt-injection protections"),
    ("ai_can_access_other_systems", "yes", 2, "AI can take actions in other systems (expanded blast radius)"),
]

_THRESHOLDS = ((0, 4, RiskLevel.LOW), (5, 10, RiskLevel.MEDIUM), (11, 999, RiskLevel.HIGH))


def _level_for_score(score: int) -> RiskLevel:
    for low, high, level in _THRESHOLDS:
        if low <= score <= high:
            return level
    return RiskLevel.HIGH


def _answers_by_id(evidence: list[EvidenceItem]) -> dict[str, str | None]:
    return {e.question_id: (e.answer.strip().lower() if e.answer else None) for e in evidence}


def score_inherent_risk(evidence: list[EvidenceItem]) -> tuple[RiskLevel, list[RiskFinding]]:
    """Score based on what the evidence says — unverified items count as the risky answer.

    Inherent risk assumes the worst about anything not proven, which is why an
    unanswered question here contributes points rather than being skipped.
    """
    answers = _answers_by_id(evidence)
    score = 0
    findings: list[RiskFinding] = []
    for question_id, risky_value, points, finding_text in _RISK_RULES:
        answer = answers.get(question_id)
        if answer == risky_value or answer is None:
            score += points
            findings.append(
                RiskFinding(
                    summary=finding_text if answer == risky_value else f"{finding_text} (unverified)",
                    severity=RiskLevel.HIGH if points >= 3 else RiskLevel.MEDIUM,
                    related_question_ids=[question_id],
                )
            )
    return _level_for_score(score), findings


def score_residual_risk(
    inherent: RiskLevel, evidence: list[EvidenceItem], mitigating_controls: list[str]
) -> RiskLevel:
    """Residual risk = inherent risk reduced by controls actually confirmed in place.

    `mitigating_controls` are question_ids whose answer indicates a control is
    already active (e.g. "supports_sso_mfa" == "yes"). Each confirmed control
    steps risk down by one level, floor Low — verified evidence only, an
    unverified answer never reduces residual risk.
    """
    answers = _answers_by_id(evidence)
    steps_down = sum(1 for qid in mitigating_controls if answers.get(qid) == "yes")
    levels = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH]
    idx = max(levels.index(inherent) - steps_down, 0)
    return levels[idx]


def assess(assessment: VendorAssessment) -> VendorAssessment:
    inherent, findings = score_inherent_risk(assessment.evidence)
    residual = score_residual_risk(
        inherent,
        assessment.evidence,
        mitigating_controls=["rbac_available", "supports_sso_mfa", "ai_actions_logged", "human_approval_required"],
    )
    assessment.inherent_risk = inherent
    assessment.residual_risk = residual
    assessment.findings = findings
    return assessment

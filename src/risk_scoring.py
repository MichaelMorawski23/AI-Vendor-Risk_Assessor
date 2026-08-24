"""Deterministic, rule-based risk scoring — deliberately not LLM-driven.

The extraction step (LLM) turns documents into structured evidence answers.
This module turns the intake profile and that evidence into risk ratings using
fixed rules, so scores are auditable: the same inputs always produce the same
result, and every point traces back to a named rule.

The model follows standard third-party risk practice:

  inherent risk  = risk of the engagement itself (what data, how critical,
                   who uses it, what the AI is allowed to do) — independent
                   of any control the vendor may have.
  control gaps   = what the vendor documentation does or doesn't evidence.
  residual risk  = inherent risk after crediting controls that are actually
                   verified in the documentation.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import (
    ORDERED_RISK_LEVELS,
    Criticality,
    DataClassification,
    EvidenceItem,
    InherentRiskDriver,
    RiskFinding,
    RiskLevel,
    VendorAssessment,
    VendorProfile,
)

# --------------------------------------------------------------------------
# Inherent risk — derived from the intake profile
# --------------------------------------------------------------------------

_CLASSIFICATION_POINTS: dict[DataClassification, int] = {
    DataClassification.PUBLIC: 0,
    DataClassification.INTERNAL: 2,
    DataClassification.CONFIDENTIAL: 4,
    DataClassification.RESTRICTED: 6,
}

_CRITICALITY_POINTS: dict[Criticality, int] = {
    Criticality.LOW: 0,
    Criticality.MODERATE: 1,
    Criticality.HIGH: 3,
    Criticality.CRITICAL: 5,
}

DATA_TYPE_OPTIONS: dict[str, int] = {
    "PHI (health information)": 3,
    "PCI / cardholder data": 3,
    "Credentials or secrets": 3,
    "PII (personal information)": 2,
    "Financial records": 2,
    "Employee records": 2,
    "Source code / IP": 2,
    "Customer communications": 1,
    "No sensitive data": 0,
}

REGULATORY_OPTIONS: list[str] = [
    "GDPR", "CCPA / CPRA", "HIPAA", "GLBA", "SOX", "PCI DSS", "FERPA", "None",
]

AI_CAPABILITY_OPTIONS: dict[str, int] = {
    "Autonomous actions / agentic": 3,
    "Code generation": 2,
    "Decisioning affecting individuals": 2,
    "Content generation": 1,
    "Classification / scoring": 1,
    "Summarization": 0,
}

DEPLOYMENT_OPTIONS: list[str] = [
    "SaaS (multi-tenant)", "SaaS (single-tenant)", "Private cloud", "On-premises", "API only",
]

ENGAGEMENT_STAGE_OPTIONS: list[str] = [
    "Evaluation / pre-purchase", "Renewal", "Already in use (shadow IT)",
]

MODEL_HOSTING_OPTIONS: list[str] = [
    "Vendor-hosted", "Third-party LLM provider", "Customer-controlled", "Unknown",
]

USED_BY_OPTIONS: list[str] = ["Employees", "Customers", "Both"]

# 0-6 Low, 7-13 Medium, 14-20 High, 21+ Critical
_INHERENT_THRESHOLDS: list[tuple[int, RiskLevel]] = [
    (6, RiskLevel.LOW),
    (13, RiskLevel.MEDIUM),
    (20, RiskLevel.HIGH),
]

# Human-readable form of the thresholds above, for the report's methodology
# section. Derived from the same list so the two can't drift apart.
MAX_INHERENT_THRESHOLDS_DOC: str = (
    ", ".join(
        f"{'0' if i == 0 else _INHERENT_THRESHOLDS[i - 1][0] + 1}–{ceiling} {level.value}"
        for i, (ceiling, level) in enumerate(_INHERENT_THRESHOLDS)
    )
    + f", {_INHERENT_THRESHOLDS[-1][0] + 1}+ {RiskLevel.CRITICAL.value}"
)


def _level_for_inherent(score: int) -> RiskLevel:
    for ceiling, level in _INHERENT_THRESHOLDS:
        if score <= ceiling:
            return level
    return RiskLevel.CRITICAL


def score_inherent_risk(profile: VendorProfile) -> tuple[RiskLevel, list[InherentRiskDriver]]:
    """Rate the engagement itself, before considering any vendor control."""
    drivers: list[InherentRiskDriver] = []

    pts = _CLASSIFICATION_POINTS.get(profile.data_classification, 2)
    drivers.append(InherentRiskDriver("Data classification", profile.data_classification.value, pts))

    pts = _CRITICALITY_POINTS.get(profile.criticality, 1)
    drivers.append(InherentRiskDriver("Business criticality", profile.criticality.value, pts))

    for data_type in profile.data_types:
        pts = DATA_TYPE_OPTIONS.get(data_type, 0)
        if pts:
            drivers.append(InherentRiskDriver("Data type", data_type, pts))

    regimes = [r for r in profile.regulatory_scope if r != "None"]
    if regimes:
        # Capped: being in scope for many regimes compounds, but not linearly.
        pts = min(len(regimes), 3)
        drivers.append(InherentRiskDriver("Regulatory scope", ", ".join(regimes), pts))

    if profile.used_by in ("Customers", "Both"):
        drivers.append(InherentRiskDriver("User population", f"Exposed to {profile.used_by.lower()}", 2))

    for capability in profile.ai_capabilities:
        pts = AI_CAPABILITY_OPTIONS.get(capability, 0)
        if pts:
            drivers.append(InherentRiskDriver("AI capability", capability, pts))

    if profile.affects_decisions_about_people:
        drivers.append(
            InherentRiskDriver("Consequential decisions", "AI influences decisions about individuals", 3)
        )

    if profile.integrates_with_internal_systems:
        detail = profile.integrated_systems or "Internal systems"
        drivers.append(InherentRiskDriver("Integration blast radius", detail, 2))

    total = sum(d.points for d in drivers)
    return _level_for_inherent(total), drivers


# --------------------------------------------------------------------------
# Control gaps — derived from extracted evidence
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RiskRule:
    question_id: str
    risky_answer: str
    points: int
    finding: str
    control: str


_RISK_RULES: list[RiskRule] = [
    RiskRule("trains_on_customer_data", "yes", 3, "Vendor may train models on customer data",
             "Contractually disable model training on customer data"),
    RiskRule("data_retention_unbounded", "yes", 2, "No defined data retention limit",
             "Establish a contractual retention limit and deletion schedule"),
    RiskRule("customer_can_delete_data", "no", 2, "Customers cannot request data deletion",
             "Require a documented data deletion process"),
    RiskRule("data_residency_commitment", "no", 1, "No contractual data residency commitment",
             "Obtain a written data residency commitment"),
    RiskRule("data_stored_offshore_unclear", "yes", 1, "Data storage location unclear or offshore with no safeguard",
             "Confirm storage regions and transfer safeguards"),
    RiskRule("subprocessors_disclosed", "no", 2, "Subprocessors are not disclosed",
             "Require a subprocessor list with change notification"),
    RiskRule("data_encrypted", "no", 3, "Data is not confirmed encrypted at rest and in transit",
             "Require encryption at rest and in transit (TLS 1.2+, AES-256)"),
    RiskRule("rbac_available", "no", 1, "No role-based access control",
             "Enable role-based access control before rollout"),
    RiskRule("supports_sso_mfa", "no", 2, "No SSO/MFA support",
             "Enable SSO with enforced MFA"),
    RiskRule("pentest_cadence", "no", 2, "No evidence of regular penetration testing",
             "Request most recent penetration test summary and cadence"),
    RiskRule("incident_reporting_defined", "no", 2, "No defined security incident notification process",
             "Negotiate a contractual breach notification window"),
    RiskRule("has_soc2", "no", 2, "No SOC 2 report available",
             "Obtain SOC 2 Type II or equivalent attestation"),
    RiskRule("customer_audit_rights", "no", 1, "No customer audit rights",
             "Negotiate audit or assessment rights into the contract"),
    RiskRule("model_change_notification", "no", 1, "No notification of material model changes",
             "Require advance notice of material model changes"),
    RiskRule("sensitive_data_can_appear_in_output", "yes", 2, "Sensitive data may appear in AI outputs",
             "Prohibit regulated data; enable output filtering"),
    RiskRule("ai_actions_logged", "no", 2, "AI actions are not logged or monitored",
             "Require audit logging of AI actions, exportable to SIEM"),
    RiskRule("human_approval_required", "no", 2, "No human-in-the-loop for consequential AI actions",
             "Require human approval for consequential actions"),
    RiskRule("prompt_injection_protections", "no", 2, "No stated prompt-injection protections",
             "Request vendor documentation of prompt-injection defenses"),
    RiskRule("ai_can_access_other_systems", "yes", 2, "AI can take actions in other systems (expanded blast radius)",
             "Scope integration permissions to least privilege"),
    RiskRule("bias_testing", "no", 2, "No evidence of bias or fairness testing",
             "Request bias/fairness evaluation results"),
    RiskRule("output_explainability", "no", 1, "No explanations or confidence signals for AI outputs",
             "Require confidence signals or rationale in outputs"),
]

_RULES_BY_ID = {r.question_id: r for r in _RISK_RULES}

# Controls whose verified presence genuinely reduces residual risk.
MITIGATING_CONTROLS: list[str] = [
    "data_encrypted", "rbac_available", "supports_sso_mfa", "pentest_cadence",
    "incident_reporting_defined", "has_soc2", "customer_can_delete_data",
    "subprocessors_disclosed", "ai_actions_logged", "human_approval_required",
    "prompt_injection_protections", "bias_testing",
]


def _answers_by_id(evidence: list[EvidenceItem]) -> dict[str, str | None]:
    return {e.question_id: (e.answer.strip().lower() if e.answer else None) for e in evidence}


def identify_control_gaps(evidence: list[EvidenceItem]) -> tuple[int, list[RiskFinding]]:
    """Return (gap points, findings). Unverified answers count as gaps.

    An unverified control is treated as a gap rather than skipped: if the
    documentation doesn't evidence a control, the assessment cannot credit it.
    """
    answers = _answers_by_id(evidence)
    score = 0
    findings: list[RiskFinding] = []
    for rule in _RISK_RULES:
        if rule.question_id not in answers:
            continue
        answer = answers[rule.question_id]
        is_risky = answer == rule.risky_answer
        if is_risky or answer is None:
            score += rule.points
            findings.append(
                RiskFinding(
                    summary=rule.finding if is_risky else f"{rule.finding} (not verified in documentation)",
                    severity=RiskLevel.HIGH if rule.points >= 3 else RiskLevel.MEDIUM,
                    related_question_ids=[rule.question_id],
                    recommended_control=rule.control,
                )
            )
    findings.sort(key=lambda f: ORDERED_RISK_LEVELS.index(f.severity), reverse=True)
    return score, findings


def control_coverage(evidence: list[EvidenceItem]) -> float:
    """Fraction of mitigating controls verified as present in the documentation."""
    answers = _answers_by_id(evidence)
    assessed = [qid for qid in MITIGATING_CONTROLS if qid in answers]
    if not assessed:
        return 0.0
    present = 0
    for qid in assessed:
        rule = _RULES_BY_ID[qid]
        # A control is "present" when the answer is the non-risky one.
        answer = answers[qid]
        if answer is not None and answer != rule.risky_answer:
            present += 1
    return present / len(assessed)


def score_residual_risk(
    inherent: RiskLevel, evidence: list[EvidenceItem]
) -> tuple[RiskLevel, str, float]:
    """Reduce inherent risk by the controls actually evidenced in the documents.

    Rules, in order:
      - Any unmitigated HIGH-severity gap blocks all reduction. A vendor that
        may train on customer data or can't evidence encryption doesn't get
        credit for having SSO.
      - Otherwise coverage of the mitigating control set drives the step-down:
        >=80% steps down two levels, >=50% steps down one, below that none.
      - Residual never falls below Low.
    """
    coverage = control_coverage(evidence)
    _, findings = identify_control_gaps(evidence)
    has_high_gap = any(f.severity == RiskLevel.HIGH for f in findings)

    idx = ORDERED_RISK_LEVELS.index(inherent)

    if has_high_gap:
        return inherent, (
            "No reduction applied — at least one high-severity control gap is unmitigated, "
            f"so verified controls ({coverage:.0%} coverage) cannot offset inherent risk."
        ), coverage

    if coverage >= 0.8:
        steps, why = 2, f"Strong control coverage ({coverage:.0%}) with no high-severity gaps."
    elif coverage >= 0.5:
        steps, why = 1, f"Partial control coverage ({coverage:.0%}) with no high-severity gaps."
    else:
        steps, why = 0, f"Insufficient verified control coverage ({coverage:.0%}) to reduce inherent risk."

    residual = ORDERED_RISK_LEVELS[max(idx - steps, 0)]
    return residual, why, coverage


def assess(assessment: VendorAssessment) -> VendorAssessment:
    """Run the full scoring pass over a populated assessment."""
    inherent, drivers = score_inherent_risk(assessment.profile)
    _, findings = identify_control_gaps(assessment.evidence)
    residual, rationale, coverage = score_residual_risk(inherent, assessment.evidence)

    assessment.inherent_risk = inherent
    assessment.inherent_drivers = drivers
    assessment.findings = findings
    assessment.residual_risk = residual
    assessment.residual_rationale = rationale
    assessment.control_coverage = coverage
    assessment.required_controls = [
        f.recommended_control for f in findings if f.recommended_control
    ]
    return assessment

"""The fixed set of risk questions asked of every vendor. Keeping this as a
single source of truth keeps extraction, scoring, and RMF mapping in sync —
every question_id used in risk_scoring.py and rmf_mapping.py must appear here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskQuestion:
    id: str
    text: str
    domain: str
    expects: str  # "yes/no" or "free text" — guides the extraction prompt


RISK_QUESTIONS: list[RiskQuestion] = [
    # --- Data handling ---
    RiskQuestion("trains_on_customer_data", "Does the vendor train models using customer data?", "Data handling", "yes/no"),
    RiskQuestion("data_retention_unbounded", "Is data retention unbounded (no defined limit)?", "Data handling", "yes/no"),
    RiskQuestion("customer_can_delete_data", "Can customers request deletion of their data?", "Data handling", "yes/no"),
    RiskQuestion("data_residency_commitment", "Is there a contractual data residency commitment?", "Data handling", "yes/no"),
    RiskQuestion("data_stored_offshore_unclear", "Is data storage location unclear or offshore without a stated safeguard?", "Data handling", "yes/no"),
    RiskQuestion("subprocessors_disclosed", "Are subprocessors that receive data disclosed?", "Data handling", "yes/no"),
    # --- Security controls ---
    RiskQuestion("data_encrypted", "Is data encrypted at rest and in transit?", "Security", "yes/no"),
    RiskQuestion("rbac_available", "Are role-based access controls available?", "Security", "yes/no"),
    RiskQuestion("supports_sso_mfa", "Does the vendor support SSO and MFA?", "Security", "yes/no"),
    RiskQuestion("pentest_cadence", "Does the vendor perform regular penetration testing?", "Security", "yes/no"),
    RiskQuestion("incident_reporting_defined", "Is a security incident notification process defined?", "Security", "yes/no"),
    # --- Assurance & oversight ---
    RiskQuestion("has_soc2", "Does the vendor have a current SOC 2 report?", "Assurance", "yes/no"),
    RiskQuestion("customer_audit_rights", "Does the vendor grant customer audit rights?", "Assurance", "yes/no"),
    RiskQuestion("model_change_notification", "Does the vendor notify customers of material model changes?", "Assurance", "yes/no"),
    # --- AI-specific risk ---
    RiskQuestion("sensitive_data_can_appear_in_output", "Can sensitive information appear in AI outputs?", "AI risk", "yes/no"),
    RiskQuestion("ai_actions_logged", "Are AI actions logged and monitored?", "AI risk", "yes/no"),
    RiskQuestion("human_approval_required", "Is human approval required for important/consequential AI decisions?", "AI risk", "yes/no"),
    RiskQuestion("prompt_injection_protections", "Does the vendor state protections against prompt injection?", "AI risk", "yes/no"),
    RiskQuestion("ai_can_access_other_systems", "Can the AI access other systems or perform actions beyond generating text?", "AI risk", "yes/no"),
    RiskQuestion("bias_testing", "Does the vendor test models for bias or fairness issues?", "AI risk", "yes/no"),
    RiskQuestion("output_explainability", "Does the vendor provide explanations or confidence signals for AI outputs?", "AI risk", "yes/no"),
]

QUESTIONS_BY_ID = {q.id: q for q in RISK_QUESTIONS}

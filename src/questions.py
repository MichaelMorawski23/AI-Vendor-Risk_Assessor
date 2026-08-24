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
    expects: str  # "yes/no" or "free text" — guides the extraction prompt


RISK_QUESTIONS: list[RiskQuestion] = [
    RiskQuestion("trains_on_customer_data", "Does the vendor train models using customer data?", "yes/no"),
    RiskQuestion("data_retention_unbounded", "Is data retention unbounded (no defined limit)?", "yes/no"),
    RiskQuestion("customer_can_delete_data", "Can customers request deletion of their data?", "yes/no"),
    RiskQuestion("data_encrypted", "Is data encrypted at rest and in transit?", "yes/no"),
    RiskQuestion("has_soc2", "Does the vendor have a current SOC 2 report?", "yes/no"),
    RiskQuestion("subprocessors_disclosed", "Are subprocessors that receive data disclosed?", "yes/no"),
    RiskQuestion("data_stored_offshore_unclear", "Is data storage location unclear or offshore without a stated safeguard?", "yes/no"),
    RiskQuestion("rbac_available", "Are role-based access controls available?", "yes/no"),
    RiskQuestion("supports_sso_mfa", "Does the vendor support SSO and MFA?", "yes/no"),
    RiskQuestion("incident_reporting_defined", "Is a security incident notification process defined?", "yes/no"),
    RiskQuestion("sensitive_data_can_appear_in_output", "Can sensitive information appear in AI outputs?", "yes/no"),
    RiskQuestion("ai_actions_logged", "Are AI actions logged and monitored?", "yes/no"),
    RiskQuestion("human_approval_required", "Is human approval required for important/consequential AI decisions?", "yes/no"),
    RiskQuestion("prompt_injection_protections", "Does the vendor state protections against prompt injection?", "yes/no"),
    RiskQuestion("ai_can_access_other_systems", "Can the AI access other systems or perform actions beyond generating text?", "yes/no"),
]

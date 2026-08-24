"""Maps risk questions to NIST AI RMF functions (Govern / Map / Measure / Manage)
and a short set of common third-party-risk-management controls.

Reference: NIST AI 100-1, "Artificial Intelligence Risk Management Framework
(AI RMF 1.0)," January 2023. This mapping is a simplified, opinionated
crosswalk for a vendor-risk workflow — not an official NIST mapping.
"""

from __future__ import annotations

from .models import RmfFunction, RmfMappingEntry

_QUESTION_TO_RMF: dict[str, RmfMappingEntry] = {
    "trains_on_customer_data": RmfMappingEntry(
        RmfFunction.MAP, "MAP 1.1 — Context and purpose", "Data use for training changes risk context"
    ),
    "data_retention_unbounded": RmfMappingEntry(
        RmfFunction.MANAGE, "MANAGE 2.3 — Risk treatment", "Retention limits are a standard treatment control"
    ),
    "customer_can_delete_data": RmfMappingEntry(
        RmfFunction.GOVERN, "GOVERN 1.1 — Policies and procedures", "Data subject rights alignment"
    ),
    "data_encrypted": RmfMappingEntry(
        RmfFunction.MANAGE, "MANAGE 2.2 — Safeguards", "Encryption is a baseline technical safeguard"
    ),
    "has_soc2": RmfMappingEntry(
        RmfFunction.MEASURE, "MEASURE 2.1 — Independent evaluation", "Third-party attestation of controls"
    ),
    "subprocessors_disclosed": RmfMappingEntry(
        RmfFunction.MAP, "MAP 3.4 — Third-party dependencies", "Subprocessor chain is part of the risk map"
    ),
    "rbac_available": RmfMappingEntry(
        RmfFunction.MANAGE, "MANAGE 2.2 — Safeguards", "Access control safeguard"
    ),
    "supports_sso_mfa": RmfMappingEntry(
        RmfFunction.MANAGE, "MANAGE 2.2 — Safeguards", "Authentication safeguard"
    ),
    "incident_reporting_defined": RmfMappingEntry(
        RmfFunction.MANAGE, "MANAGE 4.1 — Incident response", "Post-deployment monitoring and response"
    ),
    "sensitive_data_can_appear_in_output": RmfMappingEntry(
        RmfFunction.MEASURE, "MEASURE 2.7 — Security and resilience", "Output-level data leakage risk"
    ),
    "ai_actions_logged": RmfMappingEntry(
        RmfFunction.MEASURE, "MEASURE 2.5 — Ongoing monitoring", "Logging enables ongoing measurement"
    ),
    "human_approval_required": RmfMappingEntry(
        RmfFunction.GOVERN, "GOVERN 1.5 — Human oversight", "Human-in-the-loop for consequential decisions"
    ),
    "prompt_injection_protections": RmfMappingEntry(
        RmfFunction.MEASURE, "MEASURE 2.7 — Security and resilience", "Adversarial input resistance"
    ),
    "ai_can_access_other_systems": RmfMappingEntry(
        RmfFunction.MAP, "MAP 1.1 — Context and purpose", "Agentic scope expands the risk surface"
    ),
}


def map_question(question_id: str) -> RmfMappingEntry | None:
    return _QUESTION_TO_RMF.get(question_id)


def map_all(question_ids: list[str]) -> list[RmfMappingEntry]:
    mapped = (map_question(qid) for qid in question_ids)
    return [m for m in mapped if m is not None]

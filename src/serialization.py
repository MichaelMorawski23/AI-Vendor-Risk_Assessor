"""JSON round-tripping for a VendorAssessment.

Used to ship a pre-computed demo assessment with the app (so the UI can be
explored with no API key and no cost) and as the foundation for persisting
assessments later.

Loading reconstructs real dataclasses rather than handing back dicts, so
EvidenceItem's invariant — nothing is "verified" without a citation, nothing
unverified carries an answer — is re-checked on the way in. A hand-edited or
corrupted fixture fails loudly here instead of silently producing an
assessment that claims evidence it doesn't have.
"""

from __future__ import annotations

import json
from typing import Any

from .models import (
    Citation,
    Criticality,
    DataClassification,
    Decision,
    EvidenceItem,
    InherentRiskDriver,
    InjectionFlag,
    RiskFinding,
    RiskLevel,
    RmfFunction,
    RmfMappingEntry,
    VendorAssessment,
    VendorProfile,
)


def assessment_to_dict(a: VendorAssessment) -> dict[str, Any]:
    p = a.profile
    return {
        "profile": {
            "vendor_name": p.vendor_name,
            "product_name": p.product_name,
            "vendor_website": p.vendor_website,
            "deployment_model": p.deployment_model,
            "business_owner": p.business_owner,
            "business_use_case": p.business_use_case,
            "criticality": p.criticality.value,
            "engagement_stage": p.engagement_stage,
            "data_classification": p.data_classification.value,
            "data_types": list(p.data_types),
            "regulatory_scope": list(p.regulatory_scope),
            "record_volume": p.record_volume,
            "used_by": p.used_by,
            "user_count": p.user_count,
            "integrates_with_internal_systems": p.integrates_with_internal_systems,
            "integrated_systems": p.integrated_systems,
            "ai_capabilities": list(p.ai_capabilities),
            "affects_decisions_about_people": p.affects_decisions_about_people,
            "model_hosting": p.model_hosting,
        },
        "evidence": [
            {
                "question_id": e.question_id,
                "question_text": e.question_text,
                "answer": e.answer,
                "citation": (
                    {"document": e.citation.document, "page": e.citation.page}
                    if e.citation
                    else None
                ),
                "verified": e.verified,
                "quote": e.quote,
            }
            for e in a.evidence
        ],
        "injection_flags": [
            {
                "document": f.document,
                "page": f.page,
                "snippet": f.snippet,
                "matched_text": f.matched_text,
                "reason": f.reason,
            }
            for f in a.injection_flags
        ],
        "findings": [
            {
                "summary": f.summary,
                "severity": f.severity.value,
                "related_question_ids": list(f.related_question_ids),
                "recommended_control": f.recommended_control,
            }
            for f in a.findings
        ],
        "rmf_mappings": [
            {"function": m.function.value, "category": m.category, "note": m.note}
            for m in a.rmf_mappings
        ],
        "inherent_risk": a.inherent_risk.value if a.inherent_risk else None,
        "inherent_drivers": [
            {"factor": d.factor, "detail": d.detail, "points": d.points}
            for d in a.inherent_drivers
        ],
        "residual_risk": a.residual_risk.value if a.residual_risk else None,
        "residual_rationale": a.residual_rationale,
        "control_coverage": a.control_coverage,
        "decision": a.decision.value,
        "required_controls": list(a.required_controls),
        "recommendation": a.recommendation,
    }


def assessment_from_dict(data: dict[str, Any]) -> VendorAssessment:
    p = data["profile"]
    profile = VendorProfile(
        vendor_name=p["vendor_name"],
        product_name=p.get("product_name", ""),
        vendor_website=p.get("vendor_website", ""),
        deployment_model=p.get("deployment_model", ""),
        business_owner=p.get("business_owner", ""),
        business_use_case=p.get("business_use_case", ""),
        criticality=Criticality(p["criticality"]),
        engagement_stage=p.get("engagement_stage", ""),
        data_classification=DataClassification(p["data_classification"]),
        data_types=list(p.get("data_types", [])),
        regulatory_scope=list(p.get("regulatory_scope", [])),
        record_volume=p.get("record_volume", ""),
        used_by=p.get("used_by", "Employees"),
        user_count=p.get("user_count", ""),
        integrates_with_internal_systems=p.get("integrates_with_internal_systems", False),
        integrated_systems=p.get("integrated_systems", ""),
        ai_capabilities=list(p.get("ai_capabilities", [])),
        affects_decisions_about_people=p.get("affects_decisions_about_people", False),
        model_hosting=p.get("model_hosting", ""),
    )

    assessment = VendorAssessment(profile=profile)
    assessment.evidence = [
        EvidenceItem(
            question_id=e["question_id"],
            question_text=e["question_text"],
            answer=e["answer"],
            citation=(
                Citation(document=e["citation"]["document"], page=e["citation"]["page"])
                if e.get("citation")
                else None
            ),
            verified=e["verified"],
            quote=e.get("quote"),
        )
        for e in data.get("evidence", [])
    ]
    assessment.injection_flags = [
        InjectionFlag(
            document=f["document"],
            page=f["page"],
            snippet=f["snippet"],
            matched_text=f["matched_text"],
            reason=f["reason"],
        )
        for f in data.get("injection_flags", [])
    ]
    assessment.findings = [
        RiskFinding(
            summary=f["summary"],
            severity=RiskLevel(f["severity"]),
            related_question_ids=list(f.get("related_question_ids", [])),
            recommended_control=f.get("recommended_control"),
        )
        for f in data.get("findings", [])
    ]
    assessment.rmf_mappings = [
        RmfMappingEntry(
            function=RmfFunction(m["function"]), category=m["category"], note=m["note"]
        )
        for m in data.get("rmf_mappings", [])
    ]
    assessment.inherent_risk = RiskLevel(data["inherent_risk"]) if data.get("inherent_risk") else None
    assessment.inherent_drivers = [
        InherentRiskDriver(factor=d["factor"], detail=d["detail"], points=d["points"])
        for d in data.get("inherent_drivers", [])
    ]
    assessment.residual_risk = RiskLevel(data["residual_risk"]) if data.get("residual_risk") else None
    assessment.residual_rationale = data.get("residual_rationale", "")
    assessment.control_coverage = data.get("control_coverage", 0.0)
    assessment.decision = Decision(data.get("decision", Decision.PENDING.value))
    assessment.required_controls = list(data.get("required_controls", []))
    assessment.recommendation = data.get("recommendation")
    return assessment


def dumps(assessment: VendorAssessment) -> str:
    return json.dumps(assessment_to_dict(assessment), indent=2, ensure_ascii=False)


def loads(raw: str) -> VendorAssessment:
    return assessment_from_dict(json.loads(raw))

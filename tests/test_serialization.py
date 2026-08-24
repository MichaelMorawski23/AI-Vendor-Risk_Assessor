import pytest

from src.models import (
    Citation,
    Criticality,
    DataClassification,
    Decision,
    EvidenceItem,
    InjectionFlag,
    RiskLevel,
    VendorAssessment,
    VendorProfile,
)
from src.questions import RISK_QUESTIONS
from src.risk_scoring import assess
from src.rmf_mapping import map_all
from src.serialization import dumps, loads


def _populated() -> VendorAssessment:
    profile = VendorProfile(
        vendor_name="RoundTrip AI",
        product_name="Assistant",
        criticality=Criticality.CRITICAL,
        data_classification=DataClassification.RESTRICTED,
        data_types=["PHI (health information)"],
        regulatory_scope=["HIPAA"],
        used_by="Both",
        integrates_with_internal_systems=True,
        integrated_systems="Epic",
        ai_capabilities=["Autonomous actions / agentic"],
        affects_decisions_about_people=True,
    )
    a = VendorAssessment(profile=profile)
    a.evidence = [
        EvidenceItem(q.id, q.text, "yes", Citation("doc.pdf", i + 1), True, "a quote")
        if i % 2
        else EvidenceItem(q.id, q.text, None, None, False)
        for i, q in enumerate(RISK_QUESTIONS)
    ]
    a.injection_flags = [InjectionFlag("bad.pdf", 3, "snippet", "matched", "override attempt")]
    a = assess(a)
    a.rmf_mappings = map_all([e.question_id for e in a.evidence])
    a.decision = Decision.CONDITIONAL
    a.recommendation = "Conditional approval."
    return a


def test_round_trip_preserves_scores_and_profile():
    original = _populated()
    restored = loads(dumps(original))

    assert restored.profile == original.profile
    assert restored.inherent_risk == original.inherent_risk
    assert restored.residual_risk == original.residual_risk
    assert restored.control_coverage == original.control_coverage
    assert restored.residual_rationale == original.residual_rationale
    assert restored.decision == original.decision
    assert restored.required_controls == original.required_controls


def test_round_trip_preserves_evidence_and_citations():
    original = _populated()
    restored = loads(dumps(original))

    assert len(restored.evidence) == len(original.evidence)
    for before, after in zip(original.evidence, restored.evidence):
        assert after.question_id == before.question_id
        assert after.answer == before.answer
        assert after.verified == before.verified
        assert after.quote == before.quote
        if before.citation:
            assert after.citation.document == before.citation.document
            assert after.citation.page == before.citation.page
        else:
            assert after.citation is None


def test_round_trip_preserves_findings_and_flags():
    original = _populated()
    restored = loads(dumps(original))

    assert [f.summary for f in restored.findings] == [f.summary for f in original.findings]
    assert [f.severity for f in restored.findings] == [f.severity for f in original.findings]
    assert restored.injection_flags[0].matched_text == original.injection_flags[0].matched_text
    assert [m.function for m in restored.rmf_mappings] == [m.function for m in original.rmf_mappings]


def test_enums_survive_as_enums_not_strings():
    restored = loads(dumps(_populated()))
    assert isinstance(restored.inherent_risk, RiskLevel)
    assert isinstance(restored.decision, Decision)
    assert isinstance(restored.profile.criticality, Criticality)


def test_corrupt_fixture_fails_loudly():
    """A fixture claiming verified evidence with no citation must not load silently."""
    data = {
        "profile": {
            "vendor_name": "Bad",
            "criticality": Criticality.LOW.value,
            "data_classification": DataClassification.PUBLIC.value,
        },
        "evidence": [
            {
                "question_id": "has_soc2",
                "question_text": "?",
                "answer": "yes",
                "citation": None,
                "verified": True,
            }
        ],
    }
    with pytest.raises(ValueError, match="verified without a citation"):
        loads(__import__("json").dumps(data))

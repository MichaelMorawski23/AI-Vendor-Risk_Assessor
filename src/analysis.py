"""Derived analysis over a scored assessment.

risk_scoring.py answers "how risky is this vendor." This module answers the
follow-up questions a reviewer actually asks: *where* is the risk concentrated,
which parts of the framework are well-evidenced, and what does the whole thing
say in a paragraph.

Everything here is deterministic — derived from the already-scored assessment,
never from a model call — so two runs over the same evidence produce identical
analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import ORDERED_RISK_LEVELS, RiskLevel, RmfFunction, VendorAssessment
from .questions import QUESTIONS_BY_ID, RISK_QUESTIONS
from .rmf_mapping import map_question

DOMAIN_ORDER = ["Data handling", "Security", "Assurance", "AI risk"]


@dataclass
class DomainBreakdown:
    """How one risk domain (e.g. "Security") fared."""

    domain: str
    total: int = 0
    verified: int = 0
    gaps: int = 0
    high_severity_gaps: int = 0

    @property
    def verification_rate(self) -> float:
        return self.verified / self.total if self.total else 0.0

    @property
    def posture(self) -> RiskLevel:
        """A per-domain rating, so a reviewer can see where risk concentrates."""
        if self.high_severity_gaps:
            return RiskLevel.HIGH
        if self.total and self.gaps / self.total >= 0.5:
            return RiskLevel.HIGH
        if self.gaps:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW


@dataclass
class RmfFunctionCoverage:
    function: RmfFunction
    total: int = 0
    verified: int = 0
    gaps: int = 0

    @property
    def verification_rate(self) -> float:
        return self.verified / self.total if self.total else 0.0


@dataclass
class RiskRegisterRow:
    risk_id: str
    domain: str
    finding: str
    severity: RiskLevel
    evidence_status: str
    rmf_reference: str
    recommended_control: str
    status: str = "Open"


@dataclass
class AssessmentAnalysis:
    narrative: str
    domains: list[DomainBreakdown] = field(default_factory=list)
    rmf_coverage: list[RmfFunctionCoverage] = field(default_factory=list)
    register: list[RiskRegisterRow] = field(default_factory=list)
    risk_reduced: bool = False


def _domain_for(question_id: str) -> str:
    question = QUESTIONS_BY_ID.get(question_id)
    return question.domain if question else "Other"


def domain_breakdowns(assessment: VendorAssessment) -> list[DomainBreakdown]:
    by_domain: dict[str, DomainBreakdown] = {
        d: DomainBreakdown(domain=d) for d in DOMAIN_ORDER
    }

    for evidence in assessment.evidence:
        domain = _domain_for(evidence.question_id)
        entry = by_domain.setdefault(domain, DomainBreakdown(domain=domain))
        entry.total += 1
        if evidence.verified:
            entry.verified += 1

    for finding in assessment.findings:
        for question_id in finding.related_question_ids:
            domain = _domain_for(question_id)
            entry = by_domain.setdefault(domain, DomainBreakdown(domain=domain))
            entry.gaps += 1
            if finding.severity == RiskLevel.HIGH:
                entry.high_severity_gaps += 1

    return [b for b in by_domain.values() if b.total]


def rmf_coverage(assessment: VendorAssessment) -> list[RmfFunctionCoverage]:
    by_function: dict[RmfFunction, RmfFunctionCoverage] = {
        f: RmfFunctionCoverage(function=f) for f in RmfFunction
    }
    gap_question_ids = {
        qid for finding in assessment.findings for qid in finding.related_question_ids
    }

    for evidence in assessment.evidence:
        mapping = map_question(evidence.question_id)
        if mapping is None:
            continue
        entry = by_function[mapping.function]
        entry.total += 1
        if evidence.verified:
            entry.verified += 1
        if evidence.question_id in gap_question_ids:
            entry.gaps += 1

    return [c for c in by_function.values() if c.total]


def risk_register(assessment: VendorAssessment) -> list[RiskRegisterRow]:
    """Findings as a numbered risk register, the format a GRC team expects."""
    rows: list[RiskRegisterRow] = []
    for index, finding in enumerate(assessment.findings, start=1):
        question_id = finding.related_question_ids[0] if finding.related_question_ids else ""
        mapping = map_question(question_id) if question_id else None
        evidence = next(
            (e for e in assessment.evidence if e.question_id == question_id), None
        )
        if evidence is None:
            evidence_status = "Unknown"
        elif evidence.verified:
            evidence_status = "Vendor-confirmed"
        else:
            evidence_status = "Not verified"

        rows.append(
            RiskRegisterRow(
                risk_id=f"RISK-{index:03d}",
                domain=_domain_for(question_id),
                finding=finding.summary,
                severity=finding.severity,
                evidence_status=evidence_status,
                rmf_reference=mapping.category if mapping else "—",
                recommended_control=finding.recommended_control or "—",
            )
        )
    return rows


def _join(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def executive_narrative(assessment: VendorAssessment) -> str:
    """A plain-language summary, assembled from the scored data (no model call).

    Returned as plain text — callers are responsible for escaping it before
    placing it in HTML, since it embeds operator-supplied values like the
    vendor name.
    """
    profile = assessment.profile
    vendor = profile.vendor_name or "The vendor"
    inherent = assessment.inherent_risk
    residual = assessment.residual_risk

    if inherent is None or residual is None:
        return f"{vendor} has not been scored yet."

    sentences: list[str] = []

    top_drivers = sorted(assessment.inherent_drivers, key=lambda d: d.points, reverse=True)[:3]
    driver_text = _join(
        # Some enum values carry an explanation after an em dash ("High — significant
        # disruption"); only the label reads well mid-sentence.
        [f"{d.detail.split(' — ')[0].lower()} ({d.factor.lower()})" for d in top_drivers]
    )
    if driver_text:
        sentences.append(
            f"{vendor} carries {inherent.value.lower()} inherent risk, driven primarily by {driver_text}."
        )
    else:
        sentences.append(f"{vendor} carries {inherent.value.lower()} inherent risk.")

    verified = sum(1 for e in assessment.evidence if e.verified)
    total = len(assessment.evidence)
    unverified = total - verified
    high_gaps = sum(1 for f in assessment.findings if f.severity == RiskLevel.HIGH)

    sentences.append(
        f"Assessment of {total} control questions found {len(assessment.findings)} gap(s), "
        f"{high_gaps} of them high severity, with {verified} of {total} questions "
        f"({verified / total:.0%}) evidenced in the documentation provided."
        if total
        else "No control questions were assessed."
    )

    if unverified:
        sentences.append(
            f"{unverified} question(s) could not be verified and are treated as gaps rather than "
            "assumed compliant."
        )

    reduced = ORDERED_RISK_LEVELS.index(residual) < ORDERED_RISK_LEVELS.index(inherent)
    if reduced:
        sentences.append(
            f"Verified controls reduce residual risk to {residual.value.lower()}."
        )
    else:
        sentences.append(
            f"Residual risk remains {residual.value.lower()}: {assessment.residual_rationale.rstrip('.').lower()}."
        )

    weakest = sorted(
        domain_breakdowns(assessment),
        key=lambda d: (-d.high_severity_gaps, -d.gaps),
    )
    if weakest and (weakest[0].gaps or weakest[0].high_severity_gaps):
        sentences.append(
            f"Risk concentrates in {weakest[0].domain.lower()}, "
            f"with {weakest[0].gaps} of {weakest[0].total} controls flagged."
        )

    if assessment.injection_flags:
        docs = sorted({f.document for f in assessment.injection_flags})
        sentences.append(
            f"Note: {len(assessment.injection_flags)} span(s) in {_join(docs)} were flagged as "
            "possible prompt-injection content and redacted before analysis."
        )

    return " ".join(sentences)


def analyze(assessment: VendorAssessment) -> AssessmentAnalysis:
    inherent, residual = assessment.inherent_risk, assessment.residual_risk
    reduced = (
        inherent is not None
        and residual is not None
        and ORDERED_RISK_LEVELS.index(residual) < ORDERED_RISK_LEVELS.index(inherent)
    )
    return AssessmentAnalysis(
        narrative=executive_narrative(assessment),
        domains=domain_breakdowns(assessment),
        rmf_coverage=rmf_coverage(assessment),
        register=risk_register(assessment),
        risk_reduced=reduced,
    )

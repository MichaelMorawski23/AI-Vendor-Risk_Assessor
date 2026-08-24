"""Core data types shared across ingestion, scoring, mapping, and reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RiskLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class RmfFunction(str, Enum):
    GOVERN = "Govern"
    MAP = "Map"
    MEASURE = "Measure"
    MANAGE = "Manage"


@dataclass
class Citation:
    document: str
    page: int | None  # None only when the source doc has no page concept


@dataclass
class EvidenceItem:
    """One answer to one risk question, always traceable to a source or explicitly unverified."""

    question_id: str
    question_text: str
    answer: str | None  # None means unverified — do not backfill with a guess
    citation: Citation | None
    verified: bool

    def __post_init__(self) -> None:
        if self.verified and self.citation is None:
            raise ValueError(
                f"{self.question_id}: cannot be marked verified without a citation"
            )
        if not self.verified and self.answer is not None:
            raise ValueError(
                f"{self.question_id}: unverified evidence must not carry an answer — "
                "use 'Not verified' handling upstream instead of guessing"
            )


@dataclass
class InjectionFlag:
    document: str
    page: int | None
    snippet: str  # surrounding context, for human review
    matched_text: str  # exact text to redact — narrower than snippet on purpose
    reason: str


@dataclass
class RmfMappingEntry:
    function: RmfFunction
    category: str
    note: str


@dataclass
class RiskFinding:
    summary: str
    severity: RiskLevel
    related_question_ids: list[str] = field(default_factory=list)
    recommended_control: str | None = None


@dataclass
class VendorAssessment:
    vendor_name: str
    business_use_case: str
    data_accessed: str
    used_by: str  # "employees", "customers", or "both"
    evidence: list[EvidenceItem] = field(default_factory=list)
    injection_flags: list[InjectionFlag] = field(default_factory=list)
    findings: list[RiskFinding] = field(default_factory=list)
    rmf_mappings: list[RmfMappingEntry] = field(default_factory=list)
    inherent_risk: RiskLevel | None = None
    residual_risk: RiskLevel | None = None
    recommendation: str | None = None

    def unverified_questions(self) -> list[EvidenceItem]:
        return [e for e in self.evidence if not e.verified]

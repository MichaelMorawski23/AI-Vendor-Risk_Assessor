"""Core data types shared across ingestion, scoring, mapping, and reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RiskLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


ORDERED_RISK_LEVELS: list[RiskLevel] = [
    RiskLevel.LOW,
    RiskLevel.MEDIUM,
    RiskLevel.HIGH,
    RiskLevel.CRITICAL,
]


class DataClassification(str, Enum):
    PUBLIC = "Public"
    INTERNAL = "Internal"
    CONFIDENTIAL = "Confidential"
    RESTRICTED = "Restricted / regulated"


class Criticality(str, Enum):
    LOW = "Low — no material impact if unavailable"
    MODERATE = "Moderate — workaround exists"
    HIGH = "High — significant disruption"
    CRITICAL = "Critical — business stops"


class Decision(str, Enum):
    PENDING = "Pending review"
    APPROVE = "Approve"
    CONDITIONAL = "Conditional approval"
    REJECT = "Reject"
    MORE_INFO = "More information required"


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
    quote: str | None = None

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
class InherentRiskDriver:
    """One context factor that pushed inherent risk up, with its point contribution.

    Kept so the score can be shown as an itemized breakdown rather than an
    unexplained number — a reviewer should be able to see exactly why a
    vendor landed at High.
    """

    factor: str
    detail: str
    points: int


@dataclass
class VendorProfile:
    """The intake questionnaire: engagement context, captured before any document is read.

    This drives inherent risk — the risk of the engagement itself, independent
    of what controls the vendor happens to have.
    """

    # Vendor & product
    vendor_name: str
    product_name: str = ""
    vendor_website: str = ""
    deployment_model: str = ""

    # Business context
    business_owner: str = ""
    business_use_case: str = ""
    criticality: Criticality = Criticality.MODERATE
    engagement_stage: str = ""

    # Data
    data_classification: DataClassification = DataClassification.INTERNAL
    data_types: list[str] = field(default_factory=list)
    regulatory_scope: list[str] = field(default_factory=list)
    record_volume: str = ""

    # Users & access
    used_by: str = "Employees"
    user_count: str = ""
    integrates_with_internal_systems: bool = False
    integrated_systems: str = ""

    # AI specifics
    ai_capabilities: list[str] = field(default_factory=list)
    affects_decisions_about_people: bool = False
    model_hosting: str = ""


@dataclass
class VendorAssessment:
    profile: VendorProfile
    evidence: list[EvidenceItem] = field(default_factory=list)
    injection_flags: list[InjectionFlag] = field(default_factory=list)
    findings: list[RiskFinding] = field(default_factory=list)
    rmf_mappings: list[RmfMappingEntry] = field(default_factory=list)
    inherent_risk: RiskLevel | None = None
    inherent_drivers: list[InherentRiskDriver] = field(default_factory=list)
    residual_risk: RiskLevel | None = None
    residual_rationale: str = ""
    control_coverage: float = 0.0
    decision: Decision = Decision.PENDING
    required_controls: list[str] = field(default_factory=list)
    recommendation: str | None = None

    @property
    def vendor_name(self) -> str:
        return self.profile.vendor_name

    def unverified_questions(self) -> list[EvidenceItem]:
        return [e for e in self.evidence if not e.verified]

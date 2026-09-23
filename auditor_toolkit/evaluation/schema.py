"""Evaluation schema — immutable data models for AI agent evaluation.

Reuses the existing evidence/provenance system (finding_id, evidence_id,
artifact hashes, golden corpus IDs, review disposition IDs) rather than
creating a second evidence ledger.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Grader verdicts
# ---------------------------------------------------------------------------

GraderVerdict = Literal["PASS", "FAIL", "ABSTAIN", "N/A"]

# ---------------------------------------------------------------------------
# Failure taxonomy
# ---------------------------------------------------------------------------

FailureClass = Literal[
    "AGENT_CRASH",
    "TIMEOUT",
    "FORBIDDEN_ACTION",
    "UNSUPPORTED_CLAIM",
    "INSUFFICIENT_EVIDENCE",
    "WRONG_FINDING_ID",
    "WRONG_BUSINESS",
    "BROKEN_FORM",
    "GOLDEN_CORPUS_REGRESSION",
    "TOOL_POLICY_VIOLATION",
    "PROVENANCE_MISSING",
    "REPRODUCIBILITY_FAILURE",
    "UNKNOWN",
]

# ---------------------------------------------------------------------------
# Evidence reference — reuses existing provenance system
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvalEvidenceRef:
    """Pointer into the existing evidence/provenance ledger.

    At least one of finding_id, evidence_id, or golden_corpus_id must be set.
    """

    finding_id: str | None = None
    evidence_id: str | None = None
    golden_corpus_id: str | None = None
    disposition_id: str | None = None
    artifact_hash: str | None = None
    url: str | None = None
    selector: str | None = None  # CSS/XPath for DOM-level evidence
    notes: str = ""

    def has_provenance(self) -> bool:
        return any(
            [
                self.finding_id,
                self.evidence_id,
                self.golden_corpus_id,
                self.disposition_id,
            ]
        )


# ---------------------------------------------------------------------------
# Tool call record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvalToolCall:
    """A single tool invocation made by the candidate agent."""

    tool_name: str
    args: dict[str, Any] = field(default_factory=dict)
    result_summary: str = ""
    duration_ms: int = 0
    blocked: bool = False
    block_reason: str = ""


# ---------------------------------------------------------------------------
# Failure record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvalFailure:
    """A deterministic or graded failure within an evaluation run."""

    failure_class: FailureClass
    case_id: str
    grader: str
    message: str
    evidence_refs: list[EvalEvidenceRef] = field(default_factory=list)
    severity: Literal["critical", "warning", "info"] = "critical"
    agent_verdict: str = ""  # what the agent claimed (for comparison)


# ---------------------------------------------------------------------------
# EvalCase — a single test scenario
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvalCase:
    """A reproducible evaluation scenario."""

    case_id: str
    category: str
    task: str
    fixture_id: str
    expected_behavior: str
    allowed_tools: list[str] = field(default_factory=list)
    forbidden_actions: list[str] = field(default_factory=list)
    required_evidence: list[str] = field(default_factory=list)
    expected_findings: list[str] = field(default_factory=list)
    expected_abstention: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# EvalExpectedResult — what a correct run should produce
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvalExpectedResult:
    """Expected outcome for a single evaluation case."""

    case_id: str
    findings: list[str] = field(default_factory=list)
    abstain: bool = False
    evidence_required: list[EvalEvidenceRef] = field(default_factory=list)
    tools_must_use: list[str] = field(default_factory=list)
    tools_must_not_use: list[str] = field(default_factory=list)
    max_findings: int | None = None
    min_confidence: str = "medium"


# ---------------------------------------------------------------------------
# EvalResult — graded output for a single case
# ---------------------------------------------------------------------------


@dataclass
class EvalResult:
    """The graded result for one EvalCase execution."""

    case_id: str
    run_id: str
    overall: GraderVerdict = "N/A"
    grader_verdicts: dict[str, GraderVerdict] = field(default_factory=dict)
    claims: list[dict[str, Any]] = field(default_factory=list)
    evidence_selected: list[EvalEvidenceRef] = field(default_factory=list)
    tool_calls: list[EvalToolCall] = field(default_factory=list)
    failures: list[EvalFailure] = field(default_factory=list)
    duration_ms: int = 0
    agent_output: str = ""
    agent_model: str = ""

    def add_grader(self, name: str, verdict: GraderVerdict) -> None:
        self.grader_verdicts[name] = verdict

    def add_failure(self, failure: EvalFailure) -> None:
        self.failures.append(failure)

    def determine_overall(self) -> GraderVerdict:
        """Deterministic override: any critical FAIL forces overall FAIL."""
        has_critical = any(
            f for f in self.failures if f.severity == "critical"
        )
        if has_critical:
            self.overall = "FAIL"
            return "FAIL"
        if all(v == "PASS" for v in self.grader_verdicts.values()) and self.grader_verdicts:
            self.overall = "PASS"
            return "PASS"
        if all(v == "ABSTAIN" for v in self.grader_verdicts.values()) and self.grader_verdicts:
            self.overall = "ABSTAIN"
            return "ABSTAIN"
        if any(v == "FAIL" for v in self.grader_verdicts.values()):
            self.overall = "FAIL"
            return "FAIL"
        if not self.grader_verdicts:
            self.overall = "N/A"
            return "N/A"
        self.overall = "PASS"
        return "PASS"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# EvalRun — full run metadata
# ---------------------------------------------------------------------------


@dataclass
class EvalRun:
    """Metadata for one complete evaluation run."""

    run_id: str
    candidate_id: str
    baseline_id: str
    model_name: str
    agent_version: str
    repository_commit: str
    policy_version: str
    started_at: str = ""
    finished_at: str = ""
    environment: str = "local"
    tool_versions: dict[str, str] = field(default_factory=dict)
    fixture_hashes: dict[str, str] = field(default_factory=dict)
    results: list[EvalResult] = field(default_factory=list)
    status: Literal["RUNNING", "COMPLETE", "FAILED"] = "RUNNING"

    def add_result(self, result: EvalResult) -> None:
        self.results.append(result)

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.results if r.overall == "PASS")

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.results if r.overall == "FAIL")

    @property
    def total(self) -> int:
        return len(self.results)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# EvalMetrics — aggregated metrics for a run
# ---------------------------------------------------------------------------


@dataclass
class EvalMetrics:
    """Aggregated evaluation metrics."""

    run_id: str
    total_cases: int = 0
    pass_count: int = 0
    fail_count: int = 0
    abstain_count: int = 0
    na_count: int = 0

    # Accuracy
    finding_precision: float = 0.0
    finding_recall: float = 0.0
    unsupported_claim_rate: float = 0.0
    correct_abstention_rate: float = 0.0
    incorrect_abstention_rate: float = 0.0

    # Evidence
    evidence_precision: float = 0.0
    evidence_recall: float = 0.0

    # Safety
    golden_corpus_retention: float = 1.0
    wrong_business_rate: float = 0.0
    prohibited_action_count: int = 0
    tool_policy_violation_count: int = 0
    high_confidence_fp_rate: float = 0.0

    # Reliability
    completion_rate: float = 0.0
    browser_failure_rate: float = 0.0
    agent_failure_rate: float = 0.0
    replay_variance: float = 0.0

    # Resources
    avg_latency_ms: float = 0.0
    avg_cpu_ms: float = 0.0
    peak_memory_mb: float = 0.0
    input_token_count: int = 0
    output_token_count: int = 0
    estimated_api_cost: float = 0.0
    local_free_model: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

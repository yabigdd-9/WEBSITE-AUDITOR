"""Proof schema — immutable data models for before/after verification.

All captures are pinned: browser version, viewport, fonts, timestamp.
Proof packages are read-only and reproducible.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Capture status
# ---------------------------------------------------------------------------

CaptureStatus = Literal[
    "CAPTURED",
    "FAILED",
    "TIMEOUT",
    "UNAVAILABLE",
]

VerificationVerdict = Literal[
    "FIXED",
    "NOT_FIXED",
    "REGRESSION",
    "INCONCLUSIVE",
    "INVALID",
]

# ---------------------------------------------------------------------------
# Pinned capture environment
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CaptureEnvironment:
    """Pinned environment for reproducible captures."""

    viewport_width: int = 1280
    viewport_height: int = 900
    device_scale_factor: float = 1.0
    user_agent: str = ""
    browser_type: str = "chromium"
    locale: str = "en-NZ"
    timezone: str = "Pacific/Auckland"
    fonts: list[str] = field(default_factory=list)
    timestamp: str = ""

    def fingerprint(self) -> str:
        """Stable fingerprint for the capture environment."""
        import hashlib
        raw = f"{self.viewport_width}x{self.viewport_height}@{self.device_scale_factor}|{self.browser_type}|{self.locale}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Screenshot artifact
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScreenshotArtifact:
    path: str = ""
    url: str = ""
    viewport: str = ""
    timestamp: str = ""
    sha256: str = ""
    size_bytes: int = 0


# ---------------------------------------------------------------------------
# DOM snapshot reference
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DOMSnapshot:
    html_path: str = ""
    url: str = ""
    timestamp: str = ""
    sha256: str = ""
    key_elements: dict[str, str] = field(default_factory=dict)  # selector → outerHTML snippet


# ---------------------------------------------------------------------------
# Issue region — specific DOM area tied to a verified finding
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IssueRegion:
    finding_id: str = ""
    selector: str = ""
    outer_html_snippet: str = ""
    bounding_box: dict[str, int] = field(default_factory=dict)  # x, y, width, height
    description: str = ""
    severity: str = ""


# ---------------------------------------------------------------------------
# Before state — captured from the live site
# ---------------------------------------------------------------------------


@dataclass
class BeforeState:
    """Captured state before any fix is applied."""

    finding_id: str = ""
    url: str = ""
    capture_env: CaptureEnvironment = field(default_factory=CaptureEnvironment)
    screenshot: ScreenshotArtifact = field(default_factory=ScreenshotArtifact)
    dom_snapshot: DOMSnapshot = field(default_factory=DOMSnapshot)
    issue_region: IssueRegion = field(default_factory=IssueRegion)
    console_errors: list[str] = field(default_factory=list)
    network_requests: list[dict[str, Any]] = field(default_factory=list)
    axe_violations: list[dict[str, Any]] = field(default_factory=list)
    lighthouse_scores: dict[str, int] = field(default_factory=dict)
    status: CaptureStatus = "UNAVAILABLE"
    captured_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Proposed fix — a candidate corrected state
# ---------------------------------------------------------------------------


@dataclass
class ProposedFix:
    """A proposed fix for a verified finding.

    Does NOT deploy — only describes the intended change.
    """

    finding_id: str = ""
    fix_type: Literal["html_edit", "css_change", "js_change", "config_change", "content_change"] = ""
    description: str = ""
    original_value: str = ""
    proposed_value: str = ""
    affected_selectors: list[str] = field(default_factory=list)
    confidence: float = 0.0
    rationale: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# After state — captured with the proposed fix applied
# ---------------------------------------------------------------------------


@dataclass
class AfterState:
    """Captured state after the proposed fix is applied."""

    finding_id: str = ""
    proposed_fix_id: str = ""
    url: str = ""
    capture_env: CaptureEnvironment = field(default_factory=CaptureEnvironment)
    screenshot: ScreenshotArtifact = field(default_factory=ScreenshotArtifact)
    dom_snapshot: DOMSnapshot = field(default_factory=DOMSnapshot)
    issue_region: IssueRegion = field(default_factory=IssueRegion)
    console_errors: list[str] = field(default_factory=list)
    network_requests: list[dict[str, Any]] = field(default_factory=list)
    status: CaptureStatus = "UNAVAILABLE"
    captured_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Verification result — independent check
# ---------------------------------------------------------------------------


@dataclass
class VerificationResult:
    """Independent verification of a proposed fix.

    Must NOT be produced by the fix generator itself.
    """

    finding_id: str = ""
    proposed_fix_id: str = ""
    verdict: VerificationVerdict = "INCONCLUSIVE"
    original_defect_present: bool = True
    new_defects_introduced: list[str] = field(default_factory=list)
    regression_count: int = 0
    diff_summary: str = ""
    axe_violations_before: int = 0
    axe_violations_after: int = 0
    console_errors_before: int = 0
    console_errors_after: int = 0
    visual_diff_percent: float = 0.0
    confidence: float = 0.0
    verifier_id: str = ""
    verified_at: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Proof package — full before/after/verify bundle for human review
# ---------------------------------------------------------------------------


@dataclass
class ProofPackage:
    """Complete proof package for human review.

    Contains before state, proposed fix, after state, and independent
    verification result. Ready for reviewer consumption.
    """

    package_id: str
    finding_id: str
    url: str
    before: BeforeState = field(default_factory=BeforeState)
    proposed_fix: ProposedFix = field(default_factory=ProposedFix)
    after: AfterState = field(default_factory=AfterState)
    verification: VerificationResult = field(default_factory=VerificationResult)
    before_screenshot_path: str = ""
    after_screenshot_path: str = ""
    diff_path: str = ""
    status: str = "DRAFT"  # DRAFT, READY, REVIEWED, ACCEPTED, REJECTED
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def is_complete(self) -> bool:
        return all([
            self.before.status == "CAPTURED",
            self.after.status == "CAPTURED",
            self.verification.verdict != "INCONCLUSIVE",
        ])

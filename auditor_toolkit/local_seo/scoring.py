"""Local SEO opportunity scoring.

Assigns impact levels and priority scores to local SEO findings.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal

ImpactLevel = Literal[
    "HIGH",
    "MEDIUM_HIGH",
    "MEDIUM",
    "LOW",
    "INFO",
]

# ---------------------------------------------------------------------------
# Defect type definitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DefectType:
    """A known local SEO defect with fixed impact classification."""

    key: str
    title: str
    impact: ImpactLevel
    description: str
    check: str = "local_seo"


DEFECT_CATALOGUE: dict[str, DefectType] = {
    "broken_location_page": DefectType(
        key="broken_location_page",
        title="Broken location page",
        impact="HIGH",
        description="A location page returns an error or is inaccessible",
    ),
    "important_location_noindex": DefectType(
        key="important_location_noindex",
        title="Important location page noindex'd",
        impact="HIGH",
        description="A location page has a noindex directive preventing search visibility",
    ),
    "wrong_branch_phone": DefectType(
        key="wrong_branch_phone",
        title="Wrong phone for branch",
        impact="HIGH",
        description="A branch location shows a phone number that belongs to a different branch",
    ),
    "wrong_branch_address": DefectType(
        key="wrong_branch_address",
        title="Wrong address for branch",
        impact="HIGH",
        description="A branch location shows an address that belongs to a different branch",
    ),
    "schema_visible_conflict": DefectType(
        key="schema_visible_conflict",
        title="Schema vs visible content conflict",
        impact="HIGH",
        description="Structured data contradicts visible page content for NAP fields",
    ),
    "duplicate_conflicting_pages": DefectType(
        key="duplicate_conflicting_pages",
        title="Duplicate/conflicting location pages",
        impact="MEDIUM_HIGH",
        description="Multiple pages claim to represent the same location with conflicting info",
    ),
    "malformed_localbusiness_schema": DefectType(
        key="malformed_localbusiness_schema",
        title="Malformed LocalBusiness schema",
        impact="MEDIUM",
        description="LocalBusiness schema is present but has missing or invalid required fields",
    ),
    "missing_localbusiness_schema": DefectType(
        key="missing_localbusiness_schema",
        title="Missing LocalBusiness schema",
        impact="MEDIUM",
        description="Location page has no LocalBusiness structured data",
    ),
    "weak_internal_location_linking": DefectType(
        key="weak_internal_location_linking",
        title="Weak internal linking to locations",
        impact="MEDIUM",
        description="Location pages are not well-linked from the site's navigation or internal pages",
    ),
    "poor_location_page_uniqueness": DefectType(
        key="poor_location_page_uniqueness",
        title="Poor location page uniqueness",
        impact="MEDIUM",
        description="Location pages are too similar to each other, risking thin-content penalties",
    ),
    "missing_geo": DefectType(
        key="missing_geo",
        title="Missing geo coordinates",
        impact="LOW",
        description="LocalBusiness schema or page lacks geo coordinates",
    ),
    "missing_map_link": DefectType(
        key="missing_map_link",
        title="Missing map link",
        impact="LOW",
        description="Location page has no embedded map or link to map directions",
    ),
}

# ---------------------------------------------------------------------------
# Finding scoring
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScoredFinding:
    """A finding with its impact score and priority."""

    defect_key: str
    title: str
    impact: ImpactLevel
    severity: str
    source_url: str = ""
    page_url: str = ""
    confidence: float = 0.0
    evidence: dict[str, Any] = field(default_factory=dict)
    detail: str = ""
    finding_id: str = ""
    review_required: bool = True

    @property
    def priority_score(self) -> float:
        """Numeric priority for sorting (higher = more important)."""
        impact_weights: dict[ImpactLevel, float] = {
            "HIGH": 10.0,
            "MEDIUM_HIGH": 7.5,
            "MEDIUM": 5.0,
            "LOW": 2.5,
            "INFO": 1.0,
        }
        base = impact_weights.get(self.impact, 0.0)
        return round(base * self.confidence, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id or self._compute_id(),
            "defect_key": self.defect_key,
            "title": self.title,
            "impact": self.impact,
            "severity": self.severity,
            "priority_score": self.priority_score,
            "source_url": self.source_url,
            "page_url": self.page_url,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "detail": self.detail,
            "review_required": self.review_required,
        }

    def _compute_id(self) -> str:
        key = [self.defect_key, self.source_url, self.page_url]
        return hashlib.sha256(json.dumps(key).encode()).hexdigest()[:24]


# ---------------------------------------------------------------------------
# Scoring engine
# ---------------------------------------------------------------------------


def score_finding(
    defect_key: str,
    source_url: str = "",
    page_url: str = "",
    confidence: float = 0.8,
    evidence: dict[str, Any] | None = None,
    detail: str = "",
) -> ScoredFinding | None:
    """Score a single finding against the defect catalogue.

    Returns None if the defect key is not recognised.
    """
    defect = DEFECT_CATALOGUE.get(defect_key)
    if not defect:
        return None

    return ScoredFinding(
        defect_key=defect.key,
        title=defect.title,
        impact=defect.impact,
        severity="high" if defect.impact == "HIGH" else (
            "medium" if defect.impact in ("MEDIUM_HIGH", "MEDIUM") else "low"
        ),
        source_url=source_url,
        page_url=page_url,
        confidence=min(max(confidence, 0.0), 1.0),
        evidence=evidence or {},
        detail=detail,
        review_required=defect.impact in ("HIGH", "MEDIUM_HIGH"),
    )


def score_findings_batch(
    findings: list[dict[str, Any]],
) -> list[ScoredFinding]:
    """Score a batch of finding dicts.

    Each dict must have at least 'defect_key'. Other keys are passed through.
    """
    scored: list[ScoredFinding] = []
    for f in findings:
        key = f.get("defect_key", "")
        result = score_finding(
            defect_key=key,
            source_url=f.get("source_url", ""),
            page_url=f.get("page_url", ""),
            confidence=f.get("confidence", 0.8),
            evidence=f.get("evidence"),
            detail=f.get("detail", ""),
        )
        if result:
            scored.append(result)
    return scored


# ---------------------------------------------------------------------------
# Summary / aggregation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScoringSummary:
    """Aggregated scoring summary for a run."""

    total_findings: int = 0
    by_impact: dict[ImpactLevel, int] = field(default_factory=dict)
    high_confidence_count: int = 0
    avg_confidence: float = 0.0
    max_priority_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_findings": self.total_findings,
            "by_impact": dict(self.by_impact),
            "high_confidence_count": self.high_confidence_count,
            "avg_confidence": round(self.avg_confidence, 2),
            "max_priority_score": self.max_priority_score,
        }


def build_scoring_summary(findings: list[ScoredFinding]) -> ScoringSummary:
    """Build an aggregated summary from scored findings."""
    if not findings:
        return ScoringSummary()

    by_impact: dict[ImpactLevel, int] = {}
    high_conf = 0
    total_conf = 0.0
    max_score = 0.0

    for f in findings:
        by_impact[f.impact] = by_impact.get(f.impact, 0) + 1
        if f.confidence >= 0.8:
            high_conf += 1
        total_conf += f.confidence
        score = f.priority_score
        if score > max_score:
            max_score = score

    return ScoringSummary(
        total_findings=len(findings),
        by_impact=by_impact,
        high_confidence_count=high_conf,
        avg_confidence=total_conf / len(findings),
        max_priority_score=round(max_score, 2),
    )


# ---------------------------------------------------------------------------
# Quick defect detection helpers
# ---------------------------------------------------------------------------


def detect_missing_schema(
    has_schema: bool,
    page_url: str = "",
) -> ScoredFinding | None:
    """Detect missing LocalBusiness schema on a page that should have it."""
    if has_schema:
        return None
    return score_finding(
        defect_key="missing_localbusiness_schema",
        page_url=page_url,
        confidence=0.7,
        detail="Page appears to represent a local business but has no LocalBusiness schema",
    )


def detect_missing_geo(
    has_geo: bool,
    page_url: str = "",
) -> ScoredFinding | None:
    """Detect missing geo coordinates on a location page."""
    if has_geo:
        return None
    return score_finding(
        defect_key="missing_geo",
        page_url=page_url,
        confidence=0.6,
        detail="Location page has no geo coordinates in schema or visible content",
    )


def detect_schema_visible_conflict(
    contradictions: list[dict[str, Any]],
    page_url: str = "",
) -> ScoredFinding | None:
    """Detect conflicts between schema and visible content."""
    real_conflicts = [
        c for c in contradictions
        if c.get("status") == "CONTRADICTION"
    ]
    if not real_conflicts:
        return None

    fields = [c.get("field", "?") for c in real_conflicts]
    return score_finding(
        defect_key="schema_visible_conflict",
        page_url=page_url,
        confidence=0.85,
        detail=f"Schema contradicts visible content on: {', '.join(fields)}",
    )

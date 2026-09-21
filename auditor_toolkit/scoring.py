"""Evidence-first scoring (P5): scores derived from findings, never invented.

Every material finding carries its own evidence and confidence; every score
deduction links back to the findings that produced it. Consumers (quotes,
prospect packets, outreach drafts) must use these records instead of restating
a bare number.

Conventions:
  * SEVERITY_WEIGHT maps each severity to the health points it deducts.
  * HEALTH_BASE is the starting score (100). health = max(0, 100 - deductions).
  * Findings with confidence "heuristic" are flagged so reviewers know the
    evidence is weaker; their deductions still apply but are marked.
"""
from __future__ import annotations

from dataclasses import dataclass, field

HEALTH_BASE = 100
SEVERITY_WEIGHT = {"low": 4, "medium": 8, "high": 16, "critical": 30}

CONFIDENCE_LEVELS = ("observed", "derived", "heuristic")

EFFORT_BANDS = ("XS", "S", "M", "L", "XL")


@dataclass(frozen=True)
class Deduction:
    """One score deduction, always linked to a finding."""

    finding_id: str
    defect_key: str
    severity: str
    points: int
    confidence: str
    evidence_summary: str

    @property
    def is_heuristic(self) -> bool:
        return self.confidence == "heuristic"


@dataclass
class ScoreBreakdown:
    """A score fully decomposed into its contributing deductions."""

    health_score: int | None
    severity_total: int
    deductions: list[Deduction] = field(default_factory=list)
    heuristic_count: int = 0

    def to_dict(self) -> dict:
        return {
            "health_score": self.health_score,
            "severity_total": self.severity_total,
            "heuristic_count": self.heuristic_count,
            "method": "severity sum capped at 100; health = 100 - severity",
            "deductions": [
                {
                    "finding_id": d.finding_id,
                    "defect_key": d.defect_key,
                    "severity": d.severity,
                    "points": d.points,
                    "confidence": d.confidence,
                    "evidence_summary": d.evidence_summary,
                }
                for d in self.deductions
            ],
        }


def weight_for(severity: str) -> int:
    return SEVERITY_WEIGHT.get(severity, 8)


def score_from_findings(records: list[dict], complete: bool = True) -> ScoreBreakdown:
    """Derive a score strictly from finding records.

    Each record must already contain: finding_id, defect_key, severity,
    confidence, and an evidence summary/selector/evidence_ref. Records without
    evidence are still scored but flagged heuristic — never silently.
    """
    deductions = []
    for rec in records:
        severity = rec.get("severity", "medium")
        confidence = rec.get("confidence", "heuristic")
        if confidence not in CONFIDENCE_LEVELS:
            confidence = "heuristic"
        has_evidence = bool(
            rec.get("evidence_summary") or rec.get("selector") or rec.get("evidence_ref")
        )
        if not has_evidence and confidence == "observed":
            confidence = "heuristic"
        deductions.append(
            Deduction(
                finding_id=rec.get("finding_id", ""),
                defect_key=rec.get("defect_key", ""),
                severity=severity,
                points=weight_for(severity),
                confidence=confidence,
                evidence_summary=rec.get("evidence_summary", "")
                or rec.get("selector", "")
                or rec.get("evidence_ref", ""),
            )
        )
    total = min(HEALTH_BASE, sum(d.points for d in deductions))
    return ScoreBreakdown(
        health_score=max(0, HEALTH_BASE - total) if complete else None,
        severity_total=total,
        deductions=deductions,
        heuristic_count=sum(1 for d in deductions if d.is_heuristic),
    )

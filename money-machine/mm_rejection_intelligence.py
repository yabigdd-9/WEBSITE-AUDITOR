"""V45 P2: Rejection Intelligence.

Canonical rejection taxonomy. Every terminal rejection is classified into
a primary reason + secondary reasons, with supporting/contradicting evidence
and missing evidence recorded. Historical rows are NOT retroactively
reinterpreted — only new decisions use the taxonomy.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Canonical rejection taxonomy (from the v45 plan)
# ---------------------------------------------------------------------------

REJECTION_CATEGORIES = (
    "NOT_BUSINESS",
    "NON_NZ",
    "DIRECTORY_OR_AGGREGATOR",
    "SOCIAL_PROFILE_ONLY",
    "MARKETPLACE",
    "NEWS_OR_ARTICLE",
    "GOVERNMENT_OR_REGISTRY",
    "JOB_BOARD",
    "INVALID_DOMAIN",
    "UNREACHABLE",
    "DUPLICATE",
    "PARENT_BRANCH_COLLISION",
    "INSUFFICIENT_IDENTITY_EVIDENCE",
    "INSUFFICIENT_COMMERCIAL_EVIDENCE",
    "TECHNICAL_SCORE_TOO_LOW",
    "NO_ACTIONABLE_OPPORTUNITY",
    "SUPPRESSED_POLICY",
    "RETRY_EXHAUSTED",
    "UNKNOWN_REQUIRES_REVIEW",
)

# Human-readable descriptions for operator visibility
CATEGORY_DESCRIPTIONS = {
    "NOT_BUSINESS": "URL or domain does not resolve to a legitimate business",
    "NON_NZ": "Business does not serve New Zealand market",
    "DIRECTORY_OR_AGGREGATOR": "URL is a business directory or aggregator, not a standalone business",
    "SOCIAL_PROFILE_ONLY": "URL is a social media profile with no independent business presence",
    "MARKETPLACE": "URL is a multi-vendor marketplace, not a single business",
    "NEWS_OR_ARTICLE": "URL is a news article or blog post, not a business page",
    "GOVERNMENT_OR_REGISTRY": "URL is a government or registry page",
    "JOB_BOARD": "URL is a job listing or career board",
    "INVALID_DOMAIN": "Domain is malformed, reserved, or private",
    "UNREACHABLE": "Website is unreachable (transient network failure)",
    "DUPLICATE": "Business is already tracked under a canonical identity",
    "PARENT_BRANCH_COLLISION": "Business is a branch of a parent already tracked; kept distinct",
    "INSUFFICIENT_IDENTITY_EVIDENCE": "Cannot confirm this evidence belongs to a specific active business",
    "INSUFFICIENT_COMMERCIAL_EVIDENCE": "No verifiable commercial activity, services, or products observed",
    "TECHNICAL_SCORE_TOO_LOW": "Audit shows no meaningful technical improvement opportunity",
    "NO_ACTIONABLE_OPPORTUNITY": "Business is legitimate but no actionable technical/commercial opportunity",
    "SUPPRESSED_POLICY": "Suppressed by policy (e.g. out of territory, already contacted)",
    "RETRY_EXHAUSTED": "Transient failures exhausted all retries",
    "UNKNOWN_REQUIRES_REVIEW": "Classification unclear; requires human review",
}

# Mapping from pipeline stage + handler reason patterns → canonical category
# Used to classify rejections that come from existing handler outputs.
REASON_TO_CATEGORY = {
    # qualification_handler
    "not qualified": "INSUFFICIENT_COMMERCIAL_EVIDENCE",
    "No independent commercial or technical qualification threshold met": "INSUFFICIENT_COMMERCIAL_EVIDENCE",
    "technical_score too low": "TECHNICAL_SCORE_TOO_LOW",
    # identity_handler
    "no public website": "INSUFFICIENT_IDENTITY_EVIDENCE",
    "identity cannot be resolved": "INSUFFICIENT_IDENTITY_EVIDENCE",
    # audit_handler
    "public website required for audit": "INSUFFICIENT_IDENTITY_EVIDENCE",
    "auditor_toolkit incomplete": "UNREACHABLE",
    # contact_handler
    "no current VERIFIED_HIGH contact": "INSUFFICIENT_IDENTITY_EVIDENCE",  # contact is identity evidence
    "Email Finder V2 production release gate is not open": "UNKNOWN_REQUIRES_REVIEW",
    # discovery_worker_handler
    "Insufficient evidence for meaningful opportunity": "INSUFFICIENT_COMMERCIAL_EVIDENCE",
    "No viable opportunity discovered": "NO_ACTIONABLE_OPPORTUNITY",
    # dead-letter
    "dead-lettered": "RETRY_EXHAUSTED",
}

# Retryability: some rejection categories can be retried later if conditions change
RETRYABLE_CATEGORIES = frozenset({
    "UNREACHABLE",
    "INSUFFICIENT_IDENTITY_EVIDENCE",
    "INSUFFICIENT_COMMERCIAL_EVIDENCE",
    "UNKNOWN_REQUIRES_REVIEW",
})


@dataclass
class RejectionRecord:
    """A classified rejection with traceable evidence."""
    prospect_id: int
    business_name: str
    domain: str
    primary_reason: str  # must be in REJECTION_CATEGORIES
    secondary_reasons: list[str] = field(default_factory=list)
    stage: str = ""
    disposition: str = "REJECTED"
    supporting_evidence: list[str] = field(default_factory=list)  # evidence IDs
    contradicting_evidence: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0  # 0.0–1.0 that this classification is correct
    rule_version: str = "v45.1"
    retryable: bool = False
    decision_detail: str = ""  # raw handler reason, preserved for audit
    recorded_at: str | None = None

    def __post_init__(self):
        if self.primary_reason not in REJECTION_CATEGORIES:
            raise ValueError(
                f"Unknown rejection category: {self.primary_reason}. "
                f"Must be one of {REJECTION_CATEGORIES}"
            )
        for reason in self.secondary_reasons:
            if reason not in REJECTION_CATEGORIES:
                raise ValueError(f"Unknown secondary rejection category: {reason}")


def classify_rejection(handler_reason: str, stage: str = "") -> str:
    """Map a handler's free-text rejection reason to a canonical category.

    Deterministic prefix/keyword matching. Unclassifiable reasons default to
    UNKNOWN_REQUIRES_REVIEW — never silently reinterpreted as a "good" category.
    """
    reason_lower = handler_reason.lower().strip()
    for pattern, category in REASON_TO_CATEGORY.items():
        if pattern.lower() in reason_lower:
            return category
    # Stage-based inference for common patterns
    if stage == "contact" or "email" in reason_lower:
        return "INSUFFICIENT_IDENTITY_EVIDENCE"
    if "not qualified" in reason_lower or "commercial" in reason_lower:
        return "INSUFFICIENT_COMMERCIAL_EVIDENCE"
    if "technical" in reason_lower or "score" in reason_lower:
        return "TECHNICAL_SCORE_TOO_LOW"
    if "audit" in reason_lower:
        return "UNREACHABLE"
    if "directory" in reason_lower or "aggregator" in reason_lower:
        return "DIRECTORY_OR_AGGREGATOR"
    if "duplicate" in reason_lower:
        return "DUPLICATE"
    if "junk" in reason_lower or "not a business" in reason_lower:
        return "NOT_BUSINESS"
    if "non.nz" in reason_lower or "not nz" in reason_lower or "nZ" in reason_lower:
        return "NON_NZ"
    if "dead-letter" in reason_lower or "exhaust" in reason_lower or "retry" in reason_lower:
        return "RETRY_EXHAUSTED"
    # Default: do not reinterpret, mark for human review
    return "UNKNOWN_REQUIRES_REVIEW"


def is_retryable(category: str) -> bool:
    """Whether a rejection category can be retried if conditions change."""
    return category in RETRYABLE_CATEGORIES


def confidence_for_category(category: str) -> float:
    """Default confidence for a classified rejection.

    Deterministic classifications get higher confidence than fallbacks.
    """
    if category == "UNKNOWN_REQUIRES_REVIEW":
        return 0.3
    return 0.85


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

REJECTION_DDL = """
CREATE TABLE IF NOT EXISTS intelligence_rejections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id INTEGER NOT NULL,
    business_name TEXT NOT NULL,
    domain TEXT NOT NULL,
    primary_reason TEXT NOT NULL CHECK (primary_reason IN (
        'NOT_BUSINESS','NON_NZ','DIRECTORY_OR_AGGREGATOR','SOCIAL_PROFILE_ONLY',
        'MARKETPLACE','NEWS_OR_ARTICLE','GOVERNMENT_OR_REGISTRY','JOB_BOARD',
        'INVALID_DOMAIN','UNREACHABLE','DUPLICATE','PARENT_BRANCH_COLLISION',
        'INSUFFICIENT_IDENTITY_EVIDENCE','INSUFFICIENT_COMMERCIAL_EVIDENCE',
        'TECHNICAL_SCORE_TOO_LOW','NO_ACTIONABLE_OPPORTUNITY','SUPPRESSED_POLICY',
        'RETRY_EXHAUSTED','UNKNOWN_REQUIRES_REVIEW'
    )),
    secondary_reasons TEXT,            -- JSON array
    stage TEXT,
    disposition TEXT,
    supporting_evidence TEXT,          -- JSON array of evidence IDs
    contradicting_evidence TEXT,       -- JSON array
    missing_evidence TEXT,             -- JSON array
    confidence REAL CHECK (confidence BETWEEN 0 AND 1),
    rule_version TEXT NOT NULL,
    retryable INTEGER NOT NULL DEFAULT 0,
    decision_detail TEXT,              -- raw handler reason
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rejections_prospect ON intelligence_rejections(prospect_id);
CREATE INDEX IF NOT EXISTS idx_rejections_primary ON intelligence_rejections(primary_reason);
CREATE INDEX IF NOT EXISTS idx_rejections_recorded_at ON intelligence_rejections(recorded_at);
CREATE INDEX IF NOT EXISTS idx_rejections_domain ON intelligence_rejections(domain);
"""


def migrate(d: sqlite3.Connection) -> None:
    """Apply rejection DDL without committing the caller's transaction."""
    # Worker decisions are recorded inside the pipeline transaction.
    # executescript() commits an active sqlite transaction, so keep these
    # simple table/index statements on the caller's transaction instead.
    for statement in REJECTION_DDL.split(';'):
        statement = statement.strip()
        if statement:
            d.execute(statement)


def record_rejection(d: sqlite3.Connection, record: RejectionRecord) -> int:
    """Append a classified rejection to the rejection intelligence table.

    Does NOT modify any existing data. Returns the row id.
    """
    migrate(d)
    from mm_core import now
    if record.recorded_at is None:
        record.recorded_at = now()
    cur = d.execute(
        """INSERT INTO intelligence_rejections (
            prospect_id, business_name, domain, primary_reason,
            secondary_reasons, stage, disposition, supporting_evidence,
            contradicting_evidence, missing_evidence, confidence,
            rule_version, retryable, decision_detail, recorded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            record.prospect_id,
            record.business_name,
            record.domain,
            record.primary_reason,
            json.dumps(record.secondary_reasons),
            record.stage,
            record.disposition,
            json.dumps(record.supporting_evidence),
            json.dumps(record.contradicting_evidence),
            json.dumps(record.missing_evidence),
            record.confidence,
            record.rule_version,
            1 if record.retryable else 0,
            record.decision_detail,
            record.recorded_at,
        ),
    )
    row_id = cur.lastrowid
    assert row_id is not None
    return int(row_id)


def rejection_summary(d: sqlite3.Connection, limit: int = 1000) -> list[dict]:
    """Return a summary of recent rejections grouped by primary_reason."""
    migrate(d)
    rows = d.execute(
        """SELECT primary_reason, COUNT(*) as n,
                  ROUND(AVG(confidence), 2) as avg_confidence
           FROM intelligence_rejections
           GROUP BY primary_reason
           ORDER BY n DESC""",
    ).fetchall()
    return [dict(r) for r in rows]


def rejection_rate_by_domain(d: sqlite3.Connection, domain_pattern: str) -> dict:
    """Return rejection rate statistics for a domain or domain pattern."""
    migrate(d)
    row = d.execute(
        """SELECT COUNT(*) as total,
                  SUM(CASE WHEN primary_reason IS NOT NULL THEN 1 ELSE 0 END) as rejected
           FROM intelligence_rejections
           WHERE domain LIKE ?""",
        (f"%{domain_pattern}%",),
    ).fetchone()
    total = row["total"]
    rejected = row["rejected"]
    return {
        "domain_pattern": domain_pattern,
        "total": total,
        "rejected": rejected,
        "rate": round(rejected / total, 4) if total else 0.0,
    }

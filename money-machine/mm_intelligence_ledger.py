"""V45 Wave 1: Experience Memory and Decision Ledger.

Append-only intelligence event history that records every candidate decision
as a future learning example. Preserves the append-only principle: raw evidence
is immutable, derived views are rebuildable, decisions are versioned.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

from mm_core import now


# ---------------------------------------------------------------------------
# Decision versioning — every decision logic version is recorded so we can
# replay history with the rules that were active at the time.
# ---------------------------------------------------------------------------

DECISION_LOGIC_VERSION = "v45.1"


@dataclass
class DecisionEvidence:
    """Traceable evidence references backing a decision."""
    evidence_refs: list[str] = field(default_factory=list)   # IDs in mm_evidence or audit tables
    signals: list[str] = field(default_factory=list)           # Observed human-readable signals
    missing: list[str] = field(default_factory=list)          # Evidence that was sought but not found


@dataclass
class SourceFingerprint:
    """Fingerprint of the discovery source and query that yielded a candidate."""
    source: str = ""      # e.g. "searxng-local:abc123", "import:file.csv"
    query: str = ""       # The search query or import path
    query_fingerprint: str = ""  # Stable hash of the query


@dataclass
class IntelligenceDecision:
    """A single candidate decision, stored as structured learning experience."""
    prospect_id: int
    business_name: str
    domain: str
    candidate_url: str = ""
    source: str = ""
    query_fingerprint: str = ""
    industry: str = ""
    region: str = ""
    raw_evidence_refs: list[str] = field(default_factory=list)
    derived_evidence: dict[str, Any] = field(default_factory=dict)
    decision: str = ""          # REJECTED, REVIEW, QUALIFIED, SUPPRESSED, etc.
    disposition: str = ""       # terminal state category
    primary_reason: str = ""    # canonical rejection category
    secondary_reasons: list[str] = field(default_factory=list)
    confidence: float = 0.0     # 0.0–1.0
    rule_version: str = DECISION_LOGIC_VERSION
    stage: str = ""             # Which pipeline stage produced the decision
    processing_cost: float = 0.0  # Model calls + compute units
    latency_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)
    human_correction: Optional[str] = None
    later_outcome: Optional[str] = None
    recorded_at: str = field(default_factory=now)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS intelligence_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id INTEGER NOT NULL,
    business_name TEXT NOT NULL,
    domain TEXT NOT NULL,
    candidate_url TEXT,
    source TEXT,
    query_fingerprint TEXT,
    industry TEXT,
    region TEXT,
    raw_evidence_refs TEXT,      -- JSON array of evidence IDs
    derived_evidence TEXT,       -- JSON dict of derived signals
    decision TEXT NOT NULL,      -- pipeline state that resulted
    disposition TEXT,            -- terminal category: REJECTED, ACCEPTED, REVIEW, DEFER
    primary_reason TEXT,         -- canonical rejection/success category
    secondary_reasons TEXT,      -- JSON array
    confidence REAL CHECK (confidence BETWEEN 0 AND 1),
    rule_version TEXT NOT NULL,
    stage TEXT,                 -- pipeline stage where decision was made
    processing_cost REAL DEFAULT 0,
    latency_seconds REAL DEFAULT 0,
    errors TEXT,                 -- JSON array
    human_correction TEXT,       -- free text of operator correction
    later_outcome TEXT,          -- outcome discovered after the decision
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ledger_prospect ON intelligence_ledger(prospect_id);
CREATE INDEX IF NOT EXISTS idx_ledger_decision ON intelligence_ledger(decision);
CREATE INDEX IF NOT EXISTS idx_ledger_rule_version ON intelligence_ledger(rule_version);
CREATE INDEX IF NOT EXISTS idx_ledger_source ON intelligence_ledger(source);
CREATE INDEX IF NOT EXISTS idx_ledger_recorded_at ON intelligence_ledger(recorded_at);
CREATE INDEX IF NOT EXISTS idx_ledger_primary_reason ON intelligence_ledger(primary_reason);
"""


def migrate(d: sqlite3.Connection) -> None:
    """Idempotent DDL apply for the intelligence ledger."""
    d.executescript(LEDGER_DDL)


def append_decision(d: sqlite3.Connection, record: IntelligenceDecision) -> int:
    """Append a decision record. Returns the ledger row id.

    This is append-only: existing rows are never updated. Human corrections
    and later outcomes are recorded as new rows with the same prospect_id.
    """
    migrate(d)
    cur = d.execute(
        """INSERT INTO intelligence_ledger (
            prospect_id, business_name, domain, candidate_url, source,
            query_fingerprint, industry, region, raw_evidence_refs,
            derived_evidence, decision, disposition, primary_reason,
            secondary_reasons, confidence, rule_version, stage,
            processing_cost, latency_seconds, errors, human_correction,
            later_outcome, recorded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            record.prospect_id,
            record.business_name,
            record.domain,
            record.candidate_url,
            record.source,
            record.query_fingerprint,
            record.industry,
            record.region,
            json.dumps(record.raw_evidence_refs),
            json.dumps(record.derived_evidence),
            record.decision,
            record.disposition,
            record.primary_reason,
            json.dumps(record.secondary_reasons),
            record.confidence,
            record.rule_version,
            record.stage,
            record.processing_cost,
            record.latency_seconds,
            json.dumps(record.errors),
            record.human_correction,
            record.later_outcome,
            record.recorded_at,
        ),
    )
    row_id = cur.lastrowid
    assert row_id is not None
    return int(row_id)


def record_correction(d: sqlite3.Connection, prospect_id: int, correction: str,
                      corrected_decision: str, confidence: float,
                      rule_version: str = DECISION_LOGIC_VERSION) -> int:
    """Record a human correction as a new append-only ledger entry.

    The correction becomes a future learning example. We do NOT mutate the
    original decision row.
    """
    migrate(d)
    # Look up the original decision for context
    original = d.execute(
        "SELECT * FROM intelligence_ledger WHERE prospect_id=? "
        "ORDER BY recorded_at DESC LIMIT 1",
        (prospect_id,),
    ).fetchone()
    if original:
        row = IntelligenceDecision(
            prospect_id=prospect_id,
            business_name=original["business_name"],
            domain=original["domain"],
            candidate_url=original["candidate_url"],
            source=original["source"],
            query_fingerprint=original["query_fingerprint"],
            industry=original["industry"],
            region=original["region"],
            raw_evidence_refs=json.loads(original["raw_evidence_refs"] or "[]"),
            derived_evidence=json.loads(original["derived_evidence"] or "{}"),
            decision=corrected_decision,
            disposition="HUMAN_CORRECTED",
            primary_reason="human_correction",
            secondary_reasons=[],
            confidence=confidence,
            rule_version=rule_version,
            stage=original["stage"],
            human_correction=correction,
        )
    else:
        row = IntelligenceDecision(
            prospect_id=prospect_id,
            business_name="",
            domain="",
            decision=corrected_decision,
            disposition="HUMAN_CORRECTED",
            primary_reason="human_correction",
            confidence=confidence,
            rule_version=rule_version,
            human_correction=correction,
        )
    return append_decision(d, row)


def count_decisions(d: sqlite3.Connection, **filters) -> int:
    """Count decisions matching filter criteria."""
    migrate(d)
    where, args = _build_filter(filters)
    q = "SELECT COUNT(*) FROM intelligence_ledger"
    if where:
        q += " WHERE " + " AND ".join(where)
    return d.execute(q, args).fetchone()[0]


def decision_history(d: sqlite3.Connection, prospect_id: int) -> list[dict]:
    """Return all ledger entries for a prospect, newest first."""
    migrate(d)
    rows = d.execute(
        "SELECT * FROM intelligence_ledger WHERE prospect_id=? ORDER BY recorded_at DESC",
        (prospect_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _build_filter(filters: dict) -> tuple[list[str], list]:
    """Build a WHERE clause from a dict of filter conditions."""
    where = []
    args = []
    for key, val in filters.items():
        if key in ("prospect_id", "decision", "disposition", "primary_reason",
                    "rule_version", "stage", "source"):
            where.append(f"{key} = ?")
            args.append(val)
        elif key == "min_confidence":
            where.append("confidence >= ?")
            args.append(val)
        elif key == "max_confidence":
            where.append("confidence <= ?")
            args.append(val)
    return where, args

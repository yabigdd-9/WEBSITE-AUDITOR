"""Evidence-backed outcome tracking for measured learning.

Outcomes are append-only observations. They do not auto-edit prompts, prices, code,
approval state, or production. Promotion decisions remain P18 challenger/integrator work.
"""
from __future__ import annotations

import json
from pathlib import Path

import mm_core as core

OUTCOMES = {
    "NO_RESPONSE",
    "REPLIED",
    "CALL_OR_DISCOVERY",
    "PROPOSAL_SENT",
    "WON",
    "LOST",
    "BOUNCED",
    "UNSUBSCRIBED",
}

DDL = """
CREATE TABLE IF NOT EXISTS prospect_outcomes(
  id INTEGER PRIMARY KEY,
  business_id INTEGER NOT NULL REFERENCES businesses(id),
  outcome TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  actor TEXT NOT NULL,
  evidence_path TEXT NOT NULL,
  evidence_hash TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS prospect_outcomes_business
  ON prospect_outcomes(business_id, observed_at DESC);
CREATE TRIGGER IF NOT EXISTS prospect_outcomes_no_update
BEFORE UPDATE ON prospect_outcomes BEGIN
  SELECT RAISE(ABORT,'prospect outcomes are append-only');
END;
CREATE TRIGGER IF NOT EXISTS prospect_outcomes_no_delete
BEFORE DELETE ON prospect_outcomes BEGIN
  SELECT RAISE(ABORT,'prospect outcomes are append-only');
END;
"""


def migrate(d):
    d.executescript(DDL)


def record(d, business_id, outcome, evidence_path, evidence_hash, actor, note="", observed_at=None):
    migrate(d)
    core.business(d, business_id)
    outcome = str(outcome or "").upper()
    if outcome not in OUTCOMES:
        raise ValueError("Unknown outcome: " + outcome)
    actor = str(actor or "").strip()
    if not actor:
        raise ValueError("actor is required")
    path = Path(evidence_path).resolve()
    root = core.root()
    if not path.is_relative_to(root):
        raise ValueError("Outcome evidence must remain inside the canonical workspace")
    if not core.artifact_valid(path, evidence_hash):
        raise ValueError("Outcome evidence missing or modified")
    observed = observed_at or core.now()
    # Reject future-dated evidence.
    if core.timestamp(observed) > core.timestamp(core.now()):
        raise ValueError("Outcome evidence cannot be future-dated")
    cur = d.execute(
        "INSERT INTO prospect_outcomes("
        "business_id,outcome,observed_at,actor,evidence_path,evidence_hash,note,created_at"
        ") VALUES(?,?,?,?,?,?,?,?)",
        (
            business_id,
            outcome,
            observed,
            actor,
            str(path),
            evidence_hash,
            str(note or "")[:1000],
            core.now(),
        ),
    )
    core.event(
        d,
        "prospect_outcome",
        business_id,
        json.dumps(
            {
                "outcome_id": cur.lastrowid,
                "outcome": outcome,
                "evidence_hash": evidence_hash,
                "actor": actor,
            },
            sort_keys=True,
        ),
    )
    return {
        "id": cur.lastrowid,
        "business_id": business_id,
        "outcome": outcome,
        "observed_at": observed,
        "evidence_path": str(path),
        "evidence_hash": evidence_hash,
        "automatic_learning_applied": False,
        "production_modified": False,
    }


def summary(d):
    exists = d.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='prospect_outcomes'"
    ).fetchone()
    if not exists:
        return {
            "generated_at": core.now(),
            "total": 0,
            "by_outcome": {},
            "latest": [],
            "status": "uninitialised",
            "automatic_learning_applied": False,
            "promotion_requires_p18_evaluation": True,
        }
    by_outcome = {
        r[0]: r[1]
        for r in d.execute(
            "SELECT outcome,count(*) FROM prospect_outcomes GROUP BY outcome"
        )
    }
    total = sum(by_outcome.values())
    latest = [
        dict(r)
        for r in d.execute(
            "SELECT id,business_id,outcome,observed_at,actor,note "
            "FROM prospect_outcomes ORDER BY id DESC LIMIT 100"
        )
    ]
    return {
        "generated_at": core.now(),
        "total": total,
        "by_outcome": by_outcome,
        "latest": latest,
        "status": "ready",
        "automatic_learning_applied": False,
        "promotion_requires_p18_evaluation": True,
    }

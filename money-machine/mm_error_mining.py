"""V45 P3: Error Mining Engine.

Learn more aggressively from mistakes than successes. Detects false positives,
false negatives, high-confidence wrong decisions, classification disagreements,
identity conflicts, score inversions, and unexpected terminations.

Produces error clusters with suspected root causes, supporting examples,
candidate hypotheses, candidate regression fixtures, and candidate challengers.
"""
from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from mm_core import now


# ---------------------------------------------------------------------------
# Error types the engine can detect
# ---------------------------------------------------------------------------

ERROR_TYPES = (
    "SUSPECTED_FALSE_POSITIVE",
    "SUSPECTED_FALSE_NEGATIVE",
    "CONFIRMED_FALSE_POSITIVE",
    "CONFIRMED_FALSE_NEGATIVE",
    "HIGH_CONF_WRONG",        # High-confidence decision contradicted by correction/outcome
    "CLASSIFICATION_DISAGREEMENT",  # Conflicting classifications from ensemble
    "IDENTITY_CONFLICT",      # Same evidence attributed to different businesses
    "SUSPECTED_SCORE_INVERSION",
    "UNEXPECTED_REJECT",      # Good business unexpectedly rejected
    "UNEXPECTED_ACCEPT",      # Junk unexpectedly accepted
    "REPEATED_MISSING_EVIDENCE",  # Same evidence missing across many candidates
    "SOURCE_FAILURE_CLUSTER", # Failures clustered by source
    "INDUSTRY_FAILURE_CLUSTER",  # Failures clustered by industry
    "REGIONAL_FAILURE_CLUSTER",  # Failures clustered by region
)

# ---------------------------------------------------------------------------
# Error detection functions
# ---------------------------------------------------------------------------


def detect_false_negatives(d: sqlite3.Connection) -> list[dict]:
    """Detect *suspected* false negatives from heuristic positive signals.

    High technical or borderline commercial scores are review signals only.
    They do not prove the rejection was wrong; confirmation requires a later
    human correction or contradictory observed outcome.
    """
    from mm_intelligence_ledger import migrate as ledger_migrate
    from mm_rejection_intelligence import migrate as rejection_migrate
    ledger_migrate(d)
    rejection_migrate(d)
    rows = d.execute(
        """SELECT l.id as ledger_id, l.prospect_id, l.business_name, l.domain,
                  l.decision, l.primary_reason, l.confidence,
                  l.derived_evidence
           FROM intelligence_ledger l
           WHERE l.decision = 'REJECTED'
             AND coalesce(l.disposition,'') != 'HUMAN_CORRECTED'
           ORDER BY l.recorded_at DESC LIMIT ?""",
        (1000,),
    ).fetchall()
    confirmed_ids = {
        item["ledger_id"] for item in detect_confirmed_false_negatives(d)
    }
    candidates = []
    for row in rows:
        if row["ledger_id"] in confirmed_ids:
            continue
        if row["decision"] not in POSITIVE_DECISIONS:
            continue
        if row["disposition"] == "OUTCOME_OBSERVED":
            continue
        derived = json.loads(row["derived_evidence"] or "{}")
        tech_score = derived.get("technical_score")
        comm_score = derived.get("commercial_score")
        # False negative: rejected but had strong technical or borderline commercial
        if (tech_score is not None and tech_score >= 70) or \
           (comm_score is not None and comm_score >= 25):
            candidates.append({
                "type": "SUSPECTED_FALSE_NEGATIVE",
                "prospect_id": row["prospect_id"],
                "business_name": row["business_name"],
                "domain": row["domain"],
                "ledger_id": row["ledger_id"],
                "reason": row["primary_reason"],
                "confidence": row["confidence"],
                "signals": f"tech={tech_score}, comm={comm_score}",
            })
    return candidates


def detect_false_positives(d: sqlite3.Connection) -> list[dict]:
    """Detect *suspected* false positives from weak acceptance evidence.

    Weak evidence is a review signal, not proof that acceptance was wrong.
    Confirmation requires a later human correction to a negative decision.
    """
    from mm_intelligence_ledger import migrate as ledger_migrate
    ledger_migrate(d)
    rows = d.execute(
        """SELECT l.id as ledger_id, l.prospect_id, l.business_name, l.domain,
                  l.decision, l.disposition, l.confidence,
                  l.derived_evidence
           FROM intelligence_ledger l
           WHERE l.decision NOT IN ('REJECTED', 'SUPPRESSED')
             AND l.disposition != 'HUMAN_CORRECTED'
           ORDER BY l.recorded_at DESC LIMIT ?""",
        (1000,),
    ).fetchall()
    confirmed_ids = {
        item["ledger_id"] for item in detect_confirmed_false_positives(d)
    }
    candidates = []
    for row in rows:
        if row["ledger_id"] in confirmed_ids:
            continue
        derived = json.loads(row["derived_evidence"] or "{}")
        evidence_conf = derived.get("evidence_confidence", 0)
        tech_score = derived.get("technical_score")
        if evidence_conf <= 0.3 and (tech_score is None or tech_score < 30):
            candidates.append({
                "type": "SUSPECTED_FALSE_POSITIVE",
                "prospect_id": row["prospect_id"],
                "business_name": row["business_name"],
                "domain": row["domain"],
                "ledger_id": row["ledger_id"],
                "decision": row["decision"],
                "confidence": row["confidence"],
                "signals": f"evidence_conf={evidence_conf}, tech={tech_score}",
            })
    return candidates


POSITIVE_DECISIONS = frozenset({
    "ACCEPTED", "QUALIFIED", "CONTACT_PENDING", "CONTACT_RESOLVED",
    "VERIFIED", "REMEDIATION_PENDING", "DEMO_PENDING", "DEMO_READY",
    "QA_PENDING", "OUTREACH_PENDING", "APPROVAL_PENDING", "APPROVED",
    "READY_TO_SEND", "SENT", "RESPONDED", "CONVERTED",
})
NEGATIVE_DECISIONS = frozenset({
    "REJECTED", "SUPPRESSED", "DUPLICATE", "PERMANENT_FAILURE",
})
POSITIVE_OUTCOMES = frozenset({
    "REPLIED", "CALL_OR_DISCOVERY", "PROPOSAL_SENT", "WON",
})


def _ledger_rows(d: sqlite3.Connection) -> list[dict]:
    from mm_intelligence_ledger import migrate as ledger_migrate

    ledger_migrate(d)
    return [
        dict(row)
        for row in d.execute(
            "SELECT * FROM intelligence_ledger ORDER BY id"
        ).fetchall()
    ]


def _previous_real_decision(rows: list[dict], index: int) -> dict | None:
    """Return the nearest prior non-correction/non-outcome decision row."""
    for row in reversed(rows[:index]):
        if row.get("disposition") in {"HUMAN_CORRECTED", "OUTCOME_OBSERVED"}:
            continue
        if row.get("decision"):
            return row
    return None


def detect_confirmed_false_negatives(d: sqlite3.Connection) -> list[dict]:
    """Return rejected decisions contradicted by correction/outcome evidence."""
    rows = _ledger_rows(d)
    by_prospect: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        by_prospect[int(row["prospect_id"])].append(row)

    results = []
    seen_original_ids = set()
    for prospect_rows in by_prospect.values():
        for index, evidence in enumerate(prospect_rows):
            original = None
            confirmation = None

            if (
                evidence.get("disposition") == "HUMAN_CORRECTED"
                and evidence.get("decision") in POSITIVE_DECISIONS
            ):
                candidate = _previous_real_decision(prospect_rows, index)
                if candidate and candidate.get("decision") == "REJECTED":
                    original = candidate
                    confirmation = "human_correction"

            if evidence.get("later_outcome") in POSITIVE_OUTCOMES:
                candidate = (
                    evidence
                    if evidence.get("decision") == "REJECTED"
                    else _previous_real_decision(prospect_rows, index)
                )
                if candidate and candidate.get("decision") == "REJECTED":
                    original = candidate
                    confirmation = "positive_later_outcome"

            if not original or original["id"] in seen_original_ids:
                continue
            seen_original_ids.add(original["id"])
            results.append({
                "type": "CONFIRMED_FALSE_NEGATIVE",
                "prospect_id": original["prospect_id"],
                "business_name": original["business_name"],
                "domain": original["domain"],
                "ledger_id": original["id"],
                "confidence": original["confidence"],
                "confirmation": confirmation,
                "confirmation_ledger_id": evidence["id"],
                "corrected_decision": evidence.get("decision"),
                "later_outcome": evidence.get("later_outcome"),
            })
    return results


def detect_confirmed_false_positives(d: sqlite3.Connection) -> list[dict]:
    """Return positive decisions later corrected by a human to a negative state."""
    rows = _ledger_rows(d)
    by_prospect: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        by_prospect[int(row["prospect_id"])].append(row)

    results = []
    seen_original_ids = set()
    for prospect_rows in by_prospect.values():
        for index, correction in enumerate(prospect_rows):
            if (
                correction.get("disposition") != "HUMAN_CORRECTED"
                or correction.get("decision") not in NEGATIVE_DECISIONS
            ):
                continue
            original = _previous_real_decision(prospect_rows, index)
            if (
                not original
                or original.get("decision") not in POSITIVE_DECISIONS
                or original["id"] in seen_original_ids
            ):
                continue
            seen_original_ids.add(original["id"])
            results.append({
                "type": "CONFIRMED_FALSE_POSITIVE",
                "prospect_id": original["prospect_id"],
                "business_name": original["business_name"],
                "domain": original["domain"],
                "ledger_id": original["id"],
                "confidence": original["confidence"],
                "confirmation": "human_correction",
                "confirmation_ledger_id": correction["id"],
                "corrected_decision": correction.get("decision"),
            })
    return results


def detect_high_conf_wrong(d: sqlite3.Connection) -> list[dict]:
    """Detect high-confidence decisions with actual contradictory evidence."""
    confirmed = (
        detect_confirmed_false_negatives(d)
        + detect_confirmed_false_positives(d)
    )
    results = []
    for item in confirmed:
        confidence = item.get("confidence")
        if confidence is None or float(confidence) < 0.8:
            continue
        results.append({
            "type": "HIGH_CONF_WRONG",
            "prospect_id": item["prospect_id"],
            "business_name": item["business_name"],
            "domain": item["domain"],
            "ledger_id": item["ledger_id"],
            "confidence": confidence,
            "confirmation": item["confirmation"],
            "confirmation_ledger_id": item["confirmation_ledger_id"],
            "confirmed_error_type": item["type"],
        })
    return results


def detect_repeated_missing_evidence(d: sqlite3.Connection) -> list[dict]:
    """Detect evidence fields that are repeatedly missing across candidates.

    Scans the intelligence_ledger for decisions that list the same missing
    evidence field across multiple prospects with the same primary_reason.
    """
    from mm_intelligence_ledger import migrate as ledger_migrate
    ledger_migrate(d)
    rows = d.execute(
        """SELECT l.primary_reason, l.derived_evidence
           FROM intelligence_ledger l
           WHERE l.primary_reason IS NOT NULL
           ORDER BY l.recorded_at DESC LIMIT ?""",
        (5000,),
    ).fetchall()
    # Aggregate missing evidence by rejection reason
    missing_by_reason: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        reason = row["primary_reason"]
        if not reason:
            continue
        derived = json.loads(row["derived_evidence"] or "{}")
        missing = derived.get("missing_evidence", [])
        if isinstance(missing, list):
            for item in missing:
                missing_by_reason[reason][item] += 1
    # Find evidence fields missing in >5 candidates for the same reason
    results = []
    for reason, counter in missing_by_reason.items():
        for field, count in counter.most_common(10):
            if count > 5:
                results.append({
                    "type": "REPEATED_MISSING_EVIDENCE",
                    "reason": reason,
                    "missing_field": field,
                    "count": count,
                    "suggested_action": f"Gather {field} evidence for candidates rejected as {reason}",
                })
    return results


def detect_source_failure_clusters(d: sqlite3.Connection) -> list[dict]:
    """Detect sources that produce disproportionately high rejection rates."""
    from mm_intelligence_ledger import migrate as ledger_migrate
    ledger_migrate(d)
    rows = d.execute(
        """SELECT l.source, l.decision, l.primary_reason,
                  COUNT(*) as n
           FROM intelligence_ledger l
           WHERE l.source IS NOT NULL AND l.source != ''
           GROUP BY l.source, l.decision, l.primary_reason
           HAVING n >= 5
           ORDER BY l.source, n DESC""",
    ).fetchall()
    # Build per-source summary
    by_source: dict[str, dict] = defaultdict(lambda: {"total": 0, "rejected": 0, "by_reason": Counter()})
    for row in rows:
        src = row["source"]
        by_source[src]["total"] += row["n"]
        if row["decision"] == "REJECTED":
            by_source[src]["rejected"] += row["n"]
            by_source[src]["by_reason"][row["primary_reason"]] += row["n"]
    results = []
    for src, stats in by_source.items():
        if stats["total"] >= 20:
            rate = stats["rejected"] / stats["total"]
            if rate > 0.5:  # More than 50% rejection rate
                results.append({
                    "type": "SOURCE_FAILURE_CLUSTER",
                    "source": src,
                    "total": stats["total"],
                    "rejected": stats["rejected"],
                    "rejection_rate": round(rate, 4),
                    "top_reasons": [
                        {"reason": r, "count": c}
                        for r, c in stats["by_reason"].most_common(3)
                    ],
                })
    return results


def _opportunity_score(derived: dict) -> float | None:
    value = derived.get("opportunity_score")
    if isinstance(value, dict):
        value = value.get("score")
    if isinstance(value, bool):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return score


def detect_score_inversions(d: sqlite3.Connection) -> list[dict]:
    """Detect suspected score inversions within a comparable source/day cohort.

    An inversion is only considered when a rejected prospect and an accepted
    prospect share the same source, query fingerprint, stage and calendar day,
    and both have numeric opportunity scores. It remains suspected because
    score ordering alone does not prove the decision was wrong.
    """
    from mm_intelligence_ledger import migrate as ledger_migrate

    ledger_migrate(d)
    rows = d.execute(
        """SELECT l.id,l.prospect_id,l.business_name,l.domain,l.source,
                  l.query_fingerprint,l.stage,l.derived_evidence,l.decision,
                  l.recorded_at
           FROM intelligence_ledger l
           WHERE l.disposition != 'HUMAN_CORRECTED'
             AND json_valid(l.derived_evidence)
           ORDER BY l.id DESC LIMIT ?""",
        (1000,),
    ).fetchall()

    cohorts: dict[tuple[str, str, str, str], list[dict]] = defaultdict(list)
    for row in rows:
        source = str(row["source"] or "")
        query_fp = str(row["query_fingerprint"] or "")
        if not source and not query_fp:
            continue
        derived = json.loads(row["derived_evidence"] or "{}")
        score = _opportunity_score(derived)
        if score is None:
            continue
        day = str(row["recorded_at"] or "")[:10]
        key = (day, source, query_fp, str(row["stage"] or ""))
        cohorts[key].append({
            "ledger_id": row["id"],
            "prospect_id": row["prospect_id"],
            "business_name": row["business_name"],
            "domain": row["domain"],
            "decision": row["decision"],
            "score": score,
        })

    results = []
    for cohort, items in cohorts.items():
        rejected = [item for item in items if item["decision"] == "REJECTED"]
        accepted = [
            item for item in items
            if item["decision"] in POSITIVE_DECISIONS
        ]
        if not rejected or not accepted:
            continue
        for reject in rejected:
            lower_accepts = [
                accept for accept in accepted
                if reject["score"] > accept["score"]
            ]
            if not lower_accepts:
                continue
            accept = min(lower_accepts, key=lambda item: item["score"])
            results.append({
                "type": "SUSPECTED_SCORE_INVERSION",
                "prospect_id": reject["prospect_id"],
                "business_name": reject["business_name"],
                "domain": reject["domain"],
                "rejected_score": reject["score"],
                "accepted_prospect_id": accept["prospect_id"],
                "accepted_score": accept["score"],
                "score_gap": round(reject["score"] - accept["score"], 4),
                "cohort": {
                    "day": cohort[0],
                    "source": cohort[1],
                    "query_fingerprint": cohort[2],
                    "stage": cohort[3],
                },
                "confirmed": False,
            })
    return results


# ---------------------------------------------------------------------------
# Error cluster + hypothesis generation
# ---------------------------------------------------------------------------


@dataclass
class ErrorCluster:
    """A cluster of related errors with a suspected root cause."""
    cluster_type: str
    size: int
    suspected_root_cause: str
    supporting_examples: list[dict] = field(default_factory=list)
    candidate_hypothesis: str = ""
    candidate_regression_fixture: str = ""
    candidate_challenger: str = ""


def mine_errors(d: sqlite3.Connection) -> dict[str, Any]:
    """Run all error detection routines and return a structured analysis.

    Returns:
        Dict with 'errors' list, 'clusters' list, 'total_errors', 'timestamp'
    """
    from mm_intelligence_ledger import migrate as ledger_migrate
    from mm_rejection_intelligence import migrate as rejection_migrate
    ledger_migrate(d)
    rejection_migrate(d)
    errors: list[dict] = []
    errors.extend(detect_confirmed_false_negatives(d))
    errors.extend(detect_confirmed_false_positives(d))
    errors.extend(detect_false_negatives(d))
    errors.extend(detect_false_positives(d))
    errors.extend(detect_high_conf_wrong(d))
    errors.extend(detect_repeated_missing_evidence(d))
    errors.extend(detect_source_failure_clusters(d))
    errors.extend(detect_score_inversions(d))

    # Build error clusters
    clusters: dict[str, list[dict]] = defaultdict(list)
    for err in errors:
        clusters[err["type"]].append(err)

    cluster_list = []
    for err_type, items in clusters.items():
        if err_type == "SUSPECTED_FALSE_NEGATIVE":
            root = "Rejected candidate has positive heuristic signals; correctness is unconfirmed"
            hypothesis = "Replay a threshold/evidence challenger against corrected hard cases before any rule change"
        elif err_type == "CONFIRMED_FALSE_NEGATIVE":
            root = "A rejection was contradicted by later human correction or positive outcome evidence"
            hypothesis = "Add this case to the hard-case corpus and test challenger rules offline"
        elif err_type == "SUSPECTED_FALSE_POSITIVE":
            root = "Accepted candidate has weak evidence; correctness is unconfirmed"
            hypothesis = "Replay stronger evidence requirements against corrected hard cases"
        elif err_type == "CONFIRMED_FALSE_POSITIVE":
            root = "A positive decision was later corrected by a human to a negative state"
            hypothesis = "Add this case to the hard-case corpus and test evidence-gating challengers offline"
        elif err_type == "HIGH_CONF_WRONG":
            root = "High-confidence decision contradicted by later correction/outcome evidence"
            hypothesis = "Replay confidence calibration on confirmed hard cases before changing production confidence"
        elif err_type == "REPEATED_MISSING_EVIDENCE":
            root = "Missing evidence source for specific rejection categories"
            hypothesis = "Add evidence-gathering step for identified missing fields"
        elif err_type == "SOURCE_FAILURE_CLUSTER":
            root = f"Source quality degradation: {items[0].get('source', 'unknown')}"
            hypothesis = "Deprioritize or refine search from this source"
        elif err_type == "SUSPECTED_SCORE_INVERSION":
            root = "Comparable cohort contains rejected candidates scored above accepted candidates"
            hypothesis = "Replay ranking weights on this cohort; score ordering alone is not confirmation"
        else:
            root = f"Cluster of {len(items)} {err_type} errors"
            hypothesis = f"Investigate {err_type} pattern"

        cluster_list.append(ErrorCluster(
            cluster_type=err_type,
            size=len(items),
            suspected_root_cause=root,
            supporting_examples=items[:5],
            candidate_hypothesis=hypothesis,
            candidate_regression_fixture=f"test_{err_type.lower()}_cluster_{err_type}",
            candidate_challenger=f"challenger_{err_type.lower()}_fix",
        ))

    # Sort clusters by size (most errors first)
    cluster_list.sort(key=lambda c: c.size, reverse=True)

    confirmed_types = {
        "CONFIRMED_FALSE_NEGATIVE", "CONFIRMED_FALSE_POSITIVE", "HIGH_CONF_WRONG"
    }
    suspected_types = {
        "SUSPECTED_FALSE_NEGATIVE", "SUSPECTED_FALSE_POSITIVE",
        "SUSPECTED_SCORE_INVERSION",
    }
    return {
        "timestamp": now(),
        "total_errors": len(errors),
        "confirmed_errors": sum(err["type"] in confirmed_types for err in errors),
        "suspected_errors": sum(err["type"] in suspected_types for err in errors),
        "errors": errors,
        "cluster_count": len(cluster_list),
        "clusters": [
            {
                "cluster_type": c.cluster_type,
                "size": c.size,
                "suspected_root_cause": c.suspected_root_cause,
                "supporting_examples": c.supporting_examples,
                "candidate_hypothesis": c.candidate_hypothesis,
                "candidate_regression_fixture": c.candidate_regression_fixture,
                "candidate_challenger": c.candidate_challenger,
            }
            for c in cluster_list
        ],
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

ERROR_MINING_DDL = """
CREATE TABLE IF NOT EXISTS intelligence_error_clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_type TEXT NOT NULL,
    size INTEGER NOT NULL,
    suspected_root_cause TEXT,
    candidate_hypothesis TEXT,
    candidate_regression_fixture TEXT,
    candidate_challenger TEXT,
    supporting_examples TEXT,       -- JSON array
    discovered_at TEXT NOT NULL,
    resolved INTEGER NOT NULL DEFAULT 0 CHECK (resolved IN (0,1)),
    resolved_at TEXT,
    resolution_note TEXT
);
CREATE INDEX IF NOT EXISTS idx_error_clusters_type ON intelligence_error_clusters(cluster_type);
CREATE INDEX IF NOT EXISTS idx_error_clusters_size ON intelligence_error_clusters(size);
CREATE INDEX IF NOT EXISTS idx_error_clusters_resolved ON intelligence_error_clusters(resolved);
"""


def migrate(d: sqlite3.Connection) -> None:
    """Idempotent DDL apply for error mining tables."""
    d.executescript(ERROR_MINING_DDL)


def record_error_clusters(d: sqlite3.Connection, analysis: dict) -> int:
    """Persist error clusters from a mine_errors analysis run."""
    migrate(d)
    count = 0
    for cluster in analysis.get("clusters", []):
        supporting_examples = json.dumps(
            cluster["supporting_examples"], sort_keys=True
        )
        existing = d.execute(
            """SELECT 1 FROM intelligence_error_clusters
               WHERE resolved=0
                 AND cluster_type=?
                 AND size=?
                 AND coalesce(suspected_root_cause,'')=?
                 AND coalesce(candidate_hypothesis,'')=?
                 AND coalesce(supporting_examples,'')=?
               LIMIT 1""",
            (
                cluster["cluster_type"],
                cluster["size"],
                cluster["suspected_root_cause"],
                cluster["candidate_hypothesis"],
                supporting_examples,
            ),
        ).fetchone()
        if existing:
            continue
        d.execute(
            """INSERT INTO intelligence_error_clusters (
                cluster_type, size, suspected_root_cause,
                candidate_hypothesis, candidate_regression_fixture,
                candidate_challenger, supporting_examples, discovered_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                cluster["cluster_type"],
                cluster["size"],
                cluster["suspected_root_cause"],
                cluster["candidate_hypothesis"],
                cluster["candidate_regression_fixture"],
                cluster["candidate_challenger"],
                supporting_examples,
                analysis["timestamp"],
            ),
        )
        count += 1
    return count


def unresolved_clusters(d: sqlite3.Connection, limit: int = 100) -> list[dict]:
    """Return unresolved error clusters, largest first."""
    migrate(d)
    rows = d.execute(
        """SELECT * FROM intelligence_error_clusters
           WHERE resolved = 0
           ORDER BY size DESC, discovered_at DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]

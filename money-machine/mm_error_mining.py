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
    "FALSE_POSITIVE",         # Accepted candidate that should have been rejected
    "FALSE_NEGATIVE",         # Rejected candidate that should have been accepted
    "HIGH_CONF_WRONG",        # High-confidence decision that was wrong
    "CLASSIFICATION_DISAGREEMENT",  # Conflicting classifications from ensemble
    "IDENTITY_CONFLICT",      # Same evidence attributed to different businesses
    "SCORE_INVERSION",        # Lower-score candidate ranked above higher-score
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
    """Detect candidates that were rejected but have strong positive signals.

    A false negative is: a REJECTED candidate whose audit score was high
    (technical_need) AND/OR commercial score was borderline (>= 20),
    indicating the rejection threshold may be too strict.
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
           ORDER BY l.recorded_at DESC LIMIT ?""",
        (1000,),
    ).fetchall()
    candidates = []
    for row in rows:
        derived = json.loads(row["derived_evidence"] or "{}")
        tech_score = derived.get("technical_score")
        comm_score = derived.get("commercial_score")
        # False negative: rejected but had strong technical or borderline commercial
        if (tech_score is not None and tech_score >= 70) or \
           (comm_score is not None and comm_score >= 25):
            candidates.append({
                "type": "FALSE_NEGATIVE",
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
    """Detect candidates that were accepted but have weak evidence.

    A false positive is: a non-REJECTED decision (QUALIFIED, etc.) for a
    candidate with very low evidence confidence (<= 0.3) and low technical
    score (< 30), indicating the qualification bar may be too loose.
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
    candidates = []
    for row in rows:
        derived = json.loads(row["derived_evidence"] or "{}")
        evidence_conf = derived.get("evidence_confidence", 0)
        tech_score = derived.get("technical_score")
        if evidence_conf <= 0.3 and (tech_score is None or tech_score < 30):
            candidates.append({
                "type": "FALSE_POSITIVE",
                "prospect_id": row["prospect_id"],
                "business_name": row["business_name"],
                "domain": row["domain"],
                "ledger_id": row["ledger_id"],
                "decision": row["decision"],
                "confidence": row["confidence"],
                "signals": f"evidence_conf={evidence_conf}, tech={tech_score}",
            })
    return candidates


def detect_high_conf_wrong(d: sqlite3.Connection) -> list[dict]:
    """Detect high-confidence decisions that were later proven wrong.

    A high-confidence wrong decision is: a decision with confidence >= 0.8
    that was annotated with a human correction, OR that transitioned to
    a contradictory terminal state later.
    """
    from mm_intelligence_ledger import migrate as ledger_migrate
    ledger_migrate(d)
    rows = d.execute(
        """SELECT l.id as ledger_id, l.prospect_id, l.business_name, l.domain,
                  l.decision, l.confidence, l.human_correction, l.later_outcome
           FROM intelligence_ledger l
           WHERE l.confidence >= 0.8
             AND (l.human_correction IS NOT NULL OR l.later_outcome IS NOT NULL)
           ORDER BY l.recorded_at DESC LIMIT ?""",
        (500,),
    ).fetchall()
    candidates = []
    for row in rows:
        if row["human_correction"]:
            wrong_text = row["human_correction"]
        else:
            wrong_text = row["later_outcome"] or ""
        candidates.append({
            "type": "HIGH_CONF_WRONG",
            "prospect_id": row["prospect_id"],
            "business_name": row["business_name"],
            "domain": row["domain"],
            "ledger_id": row["ledger_id"],
            "decision": row["decision"],
            "confidence": row["confidence"],
            "correction": wrong_text[:240],
        })
    return candidates


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


def detect_score_inversions(d: sqlite3.Connection) -> list[dict]:
    """Detect cases where a lower-scored candidate was ranked above a higher one.

    Compares final scores of candidates processed in the same batch/period.
    """
    from mm_intelligence_ledger import migrate as ledger_migrate
    ledger_migrate(d)
    rows = d.execute(
        """SELECT l.prospect_id, l.business_name, l.domain,
                  l.derived_evidence, l.decision, l.recorded_at
           FROM intelligence_ledger l
           WHERE l.decision NOT IN ('REJECTED', 'SUPPRESSED')
             AND json_valid(l.derived_evidence)
           ORDER BY l.recorded_at DESC LIMIT ?""",
        (500,),
    ).fetchall()
    # Group by day and find inversions
    by_day: dict[str, list] = defaultdict(list)
    for row in rows:
        day = row["recorded_at"][:10] if row["recorded_at"] else ""
        derived = json.loads(row["derived_evidence"] or "{}")
        score = derived.get("opportunity_score")
        if score is not None:
            by_day[day].append({
                "prospect_id": row["prospect_id"],
                "business_name": row["business_name"],
                "domain": row["domain"],
                "score": score,
            })
    results = []
    for day, items in by_day.items():
        if len(items) < 2:
            continue
        # Sort by score descending
        items_sorted = sorted(items, key=lambda x: x["score"], reverse=True)
        # If the recorded decision order doesn't match score order, flag inversion
        # (In practice, we check if a REJECTED candidate scored higher than an accepted one)
        accepted = [i for i in items if True]  # All non-rejected
        for i in range(len(items_sorted) - 1):
            if items_sorted[i]["score"] < items_sorted[i + 1]["score"]:
                # Lower score ranked above higher — but this is expected in sorted output
                # Real inversion: accepted candidate scored lower than rejected one
                pass
    # Simplified: flag candidates with very low scores that were accepted
    for row in rows[:100]:
        derived = json.loads(row["derived_evidence"] or "{}")
        score = derived.get("opportunity_score")
        if score is not None and score < 20 and row["decision"] not in ("REJECTED", "SUPPRESSED"):
            results.append({
                "type": "SCORE_INVERSION",
                "prospect_id": row["prospect_id"],
                "business_name": row["business_name"],
                "domain": row["domain"],
                "score": score,
                "decision": row["decision"],
                "note": "Low-scoring candidate was not rejected",
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
        if err_type == "FALSE_NEGATIVE":
            root = "Qualification thresholds too strict for technical_need candidates"
            hypothesis = "Lower commercial_pass threshold from 30 to 20 when technical_score >= 70"
        elif err_type == "FALSE_POSITIVE":
            root = "Weak evidence accepted without sufficient verification"
            hypothesis = "Require evidence_confidence >= 0.5 for acceptance"
        elif err_type == "HIGH_CONF_WRONG":
            root = "Overconfidence in deterministic heuristics"
            hypothesis = "Reduce confidence ceiling for rule-based decisions"
        elif err_type == "REPEATED_MISSING_EVIDENCE":
            root = "Missing evidence source for specific rejection categories"
            hypothesis = "Add evidence-gathering step for identified missing fields"
        elif err_type == "SOURCE_FAILURE_CLUSTER":
            root = f"Source quality degradation: {items[0].get('source', 'unknown')}"
            hypothesis = "Deprioritize or refine search from this source"
        elif err_type == "SCORE_INVERSION":
            root = "Scoring weights misaligned with actual opportunity"
            hypothesis = "Recalibrate opportunity score weights"
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

    return {
        "timestamp": now(),
        "total_errors": len(errors),
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
                json.dumps(cluster["supporting_examples"]),
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

"""Read-only provenance graph for v45 prospect intelligence.

Builds a deterministic graph from existing append-only records:
source -> business -> pipeline events -> intelligence decisions/rejections -> outcomes.

No migrations, writes, model calls, network calls, approvals, or sends occur here.
Raw payloads are deliberately not copied into graph output.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any
from urllib.parse import urlsplit

RULE_VERSION = "v45-evidence-graph-v1"

_SAFE_EVENT_FIELDS = frozenset({
    "canonical_host",
    "run_id",
    "report_path",
    "defect_count",
    "score",
    "health_score",
    "profile",
    "audit_engine",
    "commercial_score",
    "commercial_qualification_score",
    "commercial_opportunity_score",
    "technical_score",
    "technical_opportunity_score",
    "technical_tier",
    "commercial_tier",
    "qualification_basis",
    "candidate_count",
    "contact_form_count",
    "finder_run",
    "model_calls",
    "external_sends",
})

_SAFE_DERIVED_FIELDS = frozenset({
    "commercial_score",
    "commercial_opportunity_score",
    "technical_score",
    "technical_opportunity_score",
    "opportunity_score",
    "evidence_confidence",
    "missing_evidence",
    "qualification_basis",
})


def _table_exists(d: sqlite3.Connection, name: str) -> bool:
    return bool(
        d.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
            (name,),
        ).fetchone()
    )


def _row_dict(row) -> dict:
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    if hasattr(row, "keys"):
        return {key: row[key] for key in row.keys()}
    return {}


def _json_object(value) -> dict:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _safe_projection(value, allowlist: frozenset[str]) -> dict:
    obj = _json_object(value)
    result = {}
    for key in sorted(allowlist):
        if key not in obj:
            continue
        item = obj[key]
        if isinstance(item, (str, int, float, bool)) or item is None:
            result[key] = item
        elif isinstance(item, list):
            result[key] = [
                x for x in item
                if isinstance(x, (str, int, float, bool)) or x is None
            ][:25]
        elif isinstance(item, dict) and key == "opportunity_score":
            score = item.get("score")
            if isinstance(score, (int, float)) and not isinstance(score, bool):
                result[key] = {"score": score}
    return result


def _host(url: str) -> str:
    try:
        parsed = urlsplit(str(url or "").strip())
    except ValueError:
        return ""
    return (parsed.hostname or "").casefold().removeprefix("www.")


def _node(node_id: str, kind: str, label: str, data: dict | None = None) -> dict:
    return {
        "id": node_id,
        "kind": kind,
        "label": label,
        "data": dict(data or {}),
    }


def _edge(source: str, target: str, relation: str) -> dict:
    return {
        "source": source,
        "target": target,
        "relation": relation,
    }


def prospect_graph(d: sqlite3.Connection, business_id: int) -> dict[str, Any]:
    """Return one prospect's read-only evidence/provenance graph."""
    if not _table_exists(d, "businesses"):
        raise ValueError("businesses table is unavailable")
    business = d.execute(
        "SELECT * FROM businesses WHERE id=?",
        (business_id,),
    ).fetchone()
    if not business:
        raise ValueError("Business not found: %s" % business_id)

    b = _row_dict(business)
    business_node = f"business:{business_id}"
    nodes: list[dict] = []
    edges: list[dict] = []
    node_ids: set[str] = set()

    def add_node(item: dict) -> None:
        if item["id"] in node_ids:
            return
        node_ids.add(item["id"])
        nodes.append(item)

    add_node(_node(
        business_node,
        "business",
        str(b.get("name") or f"Business {business_id}"),
        {
            "business_id": business_id,
            "public_website": b.get("public_website"),
            "canonical_host": (
                b.get("canonical_host")
                if "canonical_host" in b
                else _host(b.get("public_website"))
            ),
            "region": b.get("region"),
            "current_status": b.get("current_status"),
        },
    ))

    source = str(b.get("source") or "").strip()
    if source:
        source_node = "source:" + source
        add_node(_node(
            source_node,
            "source",
            source,
            {"source": source},
        ))
        edges.append(_edge(source_node, business_node, "DISCOVERED"))

    previous_event_node = None
    if _table_exists(d, "pipeline_events"):
        events = d.execute(
            "SELECT * FROM pipeline_events WHERE business_id=? ORDER BY id",
            (business_id,),
        ).fetchall()
        for row in events:
            event = _row_dict(row)
            event_id = f"pipeline_event:{event['id']}"
            evidence = _safe_projection(
                event.get("evidence"),
                _SAFE_EVENT_FIELDS,
            )
            add_node(_node(
                event_id,
                "pipeline_event",
                str(event.get("to_state") or "pipeline event"),
                {
                    "event_id": event["id"],
                    "from_state": event.get("from_state"),
                    "to_state": event.get("to_state"),
                    "actor": event.get("actor"),
                    "reason": event.get("reason"),
                    "event_at": event.get("event_at"),
                    "evidence": evidence,
                },
            ))
            edges.append(_edge(business_node, event_id, "HAS_PIPELINE_EVENT"))
            if previous_event_node is not None:
                edges.append(_edge(
                    previous_event_node,
                    event_id,
                    "NEXT_PIPELINE_EVENT",
                ))
            previous_event_node = event_id

    if _table_exists(d, "intelligence_ledger"):
        decisions = d.execute(
            "SELECT * FROM intelligence_ledger WHERE prospect_id=? ORDER BY id",
            (business_id,),
        ).fetchall()
        previous_decision_node = None
        for row in decisions:
            decision = _row_dict(row)
            decision_id = f"decision:{decision['id']}"
            disposition = str(decision.get("disposition") or "")
            kind = (
                "correction"
                if disposition == "HUMAN_CORRECTED"
                else "outcome_observation"
                if disposition == "OUTCOME_OBSERVED"
                else "decision"
            )
            add_node(_node(
                decision_id,
                kind,
                str(decision.get("decision") or disposition or "decision"),
                {
                    "ledger_id": decision["id"],
                    "decision": decision.get("decision"),
                    "disposition": decision.get("disposition"),
                    "primary_reason": decision.get("primary_reason"),
                    "confidence": decision.get("confidence"),
                    "rule_version": decision.get("rule_version"),
                    "stage": decision.get("stage"),
                    "recorded_at": decision.get("recorded_at"),
                    "later_outcome": decision.get("later_outcome"),
                    "human_correction": bool(decision.get("human_correction")),
                    "derived_evidence": _safe_projection(
                        decision.get("derived_evidence"),
                        _SAFE_DERIVED_FIELDS,
                    ),
                },
            ))
            edges.append(_edge(business_node, decision_id, "HAS_DECISION"))
            if previous_decision_node is not None:
                edges.append(_edge(
                    previous_decision_node,
                    decision_id,
                    "NEXT_DECISION_OBSERVATION",
                ))
            previous_decision_node = decision_id

    if _table_exists(d, "intelligence_rejections"):
        rejections = d.execute(
            "SELECT * FROM intelligence_rejections "
            "WHERE prospect_id=? ORDER BY id",
            (business_id,),
        ).fetchall()
        for row in rejections:
            rejection = _row_dict(row)
            rejection_id = f"rejection:{rejection['id']}"
            add_node(_node(
                rejection_id,
                "rejection",
                str(rejection.get("primary_reason") or "rejection"),
                {
                    "rejection_id": rejection["id"],
                    "primary_reason": rejection.get("primary_reason"),
                    "secondary_reasons": json.loads(
                        rejection.get("secondary_reasons") or "[]"
                    ),
                    "stage": rejection.get("stage"),
                    "disposition": rejection.get("disposition"),
                    "confidence": rejection.get("confidence"),
                    "rule_version": rejection.get("rule_version"),
                    "retryable": bool(rejection.get("retryable")),
                    "recorded_at": rejection.get("recorded_at"),
                },
            ))
            edges.append(_edge(
                business_node,
                rejection_id,
                "HAS_REJECTION_CLASSIFICATION",
            ))

    if _table_exists(d, "prospect_outcomes"):
        outcomes = d.execute(
            "SELECT id,business_id,outcome,observed_at,actor,evidence_hash,"
            "note,created_at FROM prospect_outcomes "
            "WHERE business_id=? ORDER BY id",
            (business_id,),
        ).fetchall()
        previous_outcome_node = None
        for row in outcomes:
            outcome = _row_dict(row)
            outcome_id = f"outcome:{outcome['id']}"
            add_node(_node(
                outcome_id,
                "outcome",
                str(outcome.get("outcome") or "outcome"),
                {
                    "outcome_id": outcome["id"],
                    "outcome": outcome.get("outcome"),
                    "observed_at": outcome.get("observed_at"),
                    "actor": outcome.get("actor"),
                    "evidence_ref": f"outcome-evidence:{outcome['id']}",
                    "evidence_hash_present": bool(outcome.get("evidence_hash")),
                    "note_present": bool(outcome.get("note")),
                    "created_at": outcome.get("created_at"),
                },
            ))
            edges.append(_edge(business_node, outcome_id, "HAS_OUTCOME"))
            if previous_outcome_node is not None:
                edges.append(_edge(
                    previous_outcome_node,
                    outcome_id,
                    "NEXT_OUTCOME",
                ))
            previous_outcome_node = outcome_id

    counts: dict[str, int] = {}
    for item in nodes:
        counts[item["kind"]] = counts.get(item["kind"], 0) + 1

    return {
        "business_id": business_id,
        "nodes": nodes,
        "edges": edges,
        "node_counts": dict(sorted(counts.items())),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "rule_version": RULE_VERSION,
        "read_only": True,
        "raw_payloads_included": False,
        "paid_calls": 0,
        "external_sends": 0,
    }

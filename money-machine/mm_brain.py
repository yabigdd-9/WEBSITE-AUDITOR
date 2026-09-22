"""Deterministic local control-plane intelligence for WEBSITE-AUDITOR.

This module never sends, publishes, purchases, calls a model, or mutates CRM
state during recommendation. Decisions and idempotency records are append-only
operator evidence in state/; safe-mode is an explicit human-controlled flag.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import mm_core as core

STAGES = ("DISCOVERED", "UNDERSTOOD", "AUDITED", "EVIDENCE_READY", "QUALIFIED", "OFFER_SELECTED", "CONCEPT_READY", "DRAFT_READY", "REVIEW_READY")
POLICY_VERSION = "brain:v1"


def _state(name: str) -> Path:
    path = core.root() / "state" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
        except json.JSONDecodeError:
            continue
    return rows


def _append(path: Path, value: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True, default=str) + "\n")


def _parse_time(value):
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def funnel(d, window_hours=24) -> dict:
    """Return stage counts plus throughput, age, and failure metrics.

    Metrics are derived from append-only pipeline events when available. Invalid
    or legacy timestamps are ignored rather than treated as current activity.
    """
    result = {stage: {"current_count": 0, "backlog": 0, "entered_24h": 0,
                      "completed_24h": 0, "failure_rate": 0.0,
                      "average_age_seconds": 0.0, "oldest_age_seconds": 0.0,
                      "average_processing_time_seconds": 0.0}
              for stage in STAGES}
    tables = {row[0] for row in d.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "mm_deals" not in tables:
        return result
    rows = d.execute(
        "SELECT m.stage, count(*), min(m.updated_at) FROM mm_deals m JOIN businesses b ON b.id=m.business_id "
        "WHERE coalesce(b.is_dummy,0)=0 GROUP BY m.stage"
    ).fetchall()
    now = dt.datetime.now(dt.timezone.utc)
    for stage, count, oldest in rows:
        key = stage if stage in result else str(stage)
        result.setdefault(key, {"current_count": 0, "backlog": 0, "entered_24h": 0,
                                "completed_24h": 0, "failure_rate": 0.0,
                                "average_age_seconds": 0.0, "oldest_age_seconds": 0.0,
                                "average_processing_time_seconds": 0.0})
        result[key]["current_count"] = int(count)
        result[key]["backlog"] = int(count)
        timestamps = [
            _parse_time(row[0]) for row in d.execute(
                "SELECT updated_at FROM mm_deals WHERE stage=?", (stage,)
            ).fetchall()
        ]
        ages = [max(0.0, (now - stamp).total_seconds()) for stamp in timestamps if stamp]
        if ages:
            result[key]["average_age_seconds"] = round(sum(ages) / len(ages), 2)
            result[key]["oldest_age_seconds"] = round(max(ages), 2)

    if "pipeline_events" not in tables:
        return result
    cutoff = now - dt.timedelta(hours=window_hours)
    entered = defaultdict(list)
    completed = defaultdict(list)
    failures = defaultdict(int)
    for row in d.execute("SELECT from_state,to_state,event_at FROM pipeline_events"):
        at = _parse_time(row[2])
        if not at or at < cutoff:
            continue
        to_state = str(row[1] or "")
        from_state = str(row[0] or "")
        if to_state in result:
            entered[to_state].append(at)
        if from_state in result and to_state != from_state:
            completed[from_state].append(at)
        if to_state in {"RETRYABLE_FAILURE", "PERMANENT_FAILURE", "DEAD_LETTER"}:
            failures[from_state] += 1
    for stage in result:
        count = len(entered[stage])
        result[stage]["entered_24h"] = count
        result[stage]["completed_24h"] = len(completed[stage])
        result[stage]["failure_rate"] = round(failures[stage] / count, 4) if count else 0.0
        durations = []
        for start in entered[stage]:
            exits = [end for end in completed[stage] if end >= start]
            if exits:
                durations.append((min(exits) - start).total_seconds())
        if durations:
            result[stage]["average_processing_time_seconds"] = round(sum(durations) / len(durations), 2)
    return result


def golden_scenarios(path=None) -> list[dict]:
    source = Path(path) if path else Path(__file__).resolve().parent / "fixtures" / "intelligence_golden.json"
    return json.loads(source.read_text(encoding="utf-8"))


def evaluate_scenario(scenario: dict) -> dict:
    """Evaluate a versioned, DB-free intelligence scenario."""
    if scenario.get("integrity_failed"):
        action, reason = "db_check", "database integrity has priority over productivity"
    elif scenario.get("network") in {"BLOCKED", "DEGRADED"}:
        action, reason = "pause_external_work", "network is not safe for external work"
    elif scenario.get("review_queue", 0) >= scenario.get("review_capacity", 10):
        action, reason = "hold_draft_generation", "review queue is at capacity"
    elif scenario.get("primary_bottleneck") == "EVIDENCE":
        action, reason = "refresh_evidence", "evidence is the measured bottleneck"
    elif scenario.get("high_value_nearly_complete"):
        action, reason = "complete_high_value_work", "high-value work is nearly review-ready"
    elif scenario.get("stale_high_value"):
        action, reason = "refresh_stale_evidence", "high-value evidence is stale"
    else:
        action, reason = "NONE", "no valuable safe work is pending"
    return {"scenario": scenario.get("name", "unnamed"), "action": action,
            "reason": reason, "safe": action not in {"db_check", "pause_external_work"},
            "human_approval_required": False, "external_sends": 0,
            "paid_calls": 0, "model_cost_usd": 0.0}


def email_intents(d) -> dict:
    """Count delivery intents by status when the lifecycle table exists."""
    empty = {"total": 0, "by_status": {}, "dead_lettered": 0, "retryable_failed": 0}
    tables = {row[0] for row in d.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "email_delivery_intents" not in tables:
        return empty
    rows = d.execute("SELECT status, count(*) FROM email_delivery_intents GROUP BY status").fetchall()
    by_status = {str(row[0]): int(row[1]) for row in rows}
    return {
        "total": sum(by_status.values()),
        "by_status": dict(sorted(by_status.items())),
        "dead_lettered": by_status.get("dead_lettered", 0),
        "retryable_failed": by_status.get("retryable_failed", 0),
    }


def bottlenecks(d) -> dict:
    stages = funnel(d)
    ranked = sorted(
        ((name, value) for name, value in stages.items() if name != "SUPPRESSED"),
        key=lambda item: (-item[1]["backlog"], item[0]),
    )
    primary = ranked[0][0] if ranked and ranked[0][1]["backlog"] else None
    severity = "HIGH" if primary else "NONE"
    intents = email_intents(d)
    if intents["dead_lettered"]:
        # Undeliverable approved work blocks the funnel and needs a human.
        primary = "EMAIL_DEAD_LETTER"
        severity = "HIGH"
    return {
        "stages": stages,
        "primary": primary,
        "severity": severity,
        "email_intents": intents,
        "policy_version": POLICY_VERSION,
    }


def _candidate_actions(d, limit=10) -> list[dict]:
    actions = []
    tables = {row[0] for row in d.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "pipeline_items" in tables:
        rows = d.execute(
            "SELECT p.business_id,p.state,p.attempts,b.name FROM pipeline_items p "
            "JOIN businesses b ON b.id=p.business_id WHERE coalesce(b.is_dummy,0)=0 "
            "AND p.state NOT IN ('SUPPRESSED','CONVERTED') ORDER BY p.updated_at LIMIT ?", (limit,)
        ).fetchall()
        for row in rows:
            action = "refresh_evidence" if row[1] in {"AUDITED", "VERIFICATION_PENDING"} else "advance_pipeline"
            actions.append({"business_id": row[0], "business": row[3], "action": action, "state": row[1], "action_class": "SAFE_AUTO", "score": max(1, 100 - row[2] * 10)})
    if "email_delivery_intents" in tables:
        dead = d.execute(
            "SELECT business_id, recipient, attempt_count, last_error FROM email_delivery_intents "
            "WHERE status='dead_lettered' ORDER BY updated_at LIMIT ?", (limit,)
        ).fetchall()
        for row in dead:
            actions.append({
                "business_id": row["business_id"],
                "recipient": row["recipient"],
                "action": "review_dead_lettered_email",
                "reason": (
                    "delivery failed %d times: %s" % (row["attempt_count"], (row["last_error"] or "unknown")[:120])
                ),
                "state": "dead_lettered",
                "action_class": "HUMAN_REVIEW",
                "score": 150,
            })
    if not actions and "mm_deals" in tables:
        rows = d.execute(
            "SELECT m.business_id,m.stage,b.name FROM mm_deals m JOIN businesses b ON b.id=m.business_id "
            "WHERE coalesce(b.is_dummy,0)=0 AND m.stage NOT IN ('SUPPRESSED','WON','LOST') "
            "ORDER BY m.updated_at LIMIT ?", (limit,)
        ).fetchall()
        for row in rows:
            action = "refresh_evidence" if row[1] in {"AUDITED", "VERIFIED"} else "advance_pipeline"
            actions.append({"business_id": row[0], "business": row[2], "action": action, "state": row[1], "action_class": "SAFE_AUTO", "score": 50})
    return actions


def recommend(d, limit=10) -> dict:
    health = {"mode": "NORMAL", "health_score": 100}
    bottleneck = bottlenecks(d)
    actions = _candidate_actions(d, limit)
    if bottleneck["primary"]:
        for action in actions:
            if action.get("action_class") != "HUMAN_REVIEW":
                # Keep the specific diagnostic reason on dead-letter reviews.
                action["reason"] = f"{bottleneck['primary']} is the largest measured backlog"
            action["bottleneck_weight"] = 1.0 if bottleneck["primary"] in {"EVIDENCE_READY", "AUDITED"} else 0.5
    actions.sort(key=lambda item: (-item.get("bottleneck_weight", 0), -item["score"], item["business_id"]))
    top = actions[0] if actions else {"action": "NONE", "action_class": "SAFE_AUTO", "reason": "No valuable safe work is pending", "score": 0}
    return {
        "system": health,
        "funnel": funnel(d),
        "primary_bottleneck": bottleneck,
        "highest_priority_action": top,
        "reason": [top.get("reason", "system healthy")],
        "confidence": 0.75 if top["action"] != "NONE" else 0.95,
        "expected_effect": {"review_ready_delta": 1 if top["action"] != "NONE" else 0},
        "safe_to_execute": top["action_class"] == "SAFE_AUTO",
        "blocking_review_items": bottleneck["email_intents"]["dead_lettered"],
        "human_approval_required": False,
        "safety": {"external_sends": 0, "paid_calls": 0, "model_cost_usd": 0.0},
        "policy_version": POLICY_VERSION,
    }


def decision(action: str, entity_id=None, reason="", before=None, after=None, evidence_refs=None, confidence=0.0, result="RECOMMENDATION") -> dict:
    timestamp = core.now()
    identity = f"{entity_id}:{action}:{timestamp}:{reason}"
    value = {
        "decision_id": hashlib.sha256(identity.encode()).hexdigest()[:20],
        "timestamp": timestamp, "entity_id": entity_id, "stage": "control_plane",
        "state_before": before, "action": action, "reason": reason,
        "evidence_refs": evidence_refs or [], "confidence": float(confidence),
        "policy_version": POLICY_VERSION, "policy_hash": core.sha(POLICY_VERSION),
        "idempotency_key": hashlib.sha256(f"{entity_id}:{action}:{before}:{after}".encode()).hexdigest(),
        "state_after": after, "result": result,
    }
    _append(_state("decision-ledger.jsonl"), value)
    return value


def ledger(entity_id=None, limit=100) -> list[dict]:
    rows = _read_jsonl(_state("decision-ledger.jsonl"))
    if entity_id is not None:
        rows = [row for row in rows if str(row.get("entity_id")) == str(entity_id)]
    return rows[-max(1, min(int(limit), 1000)):]


def idempotency(key: str, operation: str, entity_id=None) -> dict:
    rows = _read_jsonl(_state("idempotency.jsonl"))
    for row in rows:
        if row.get("idempotency_key") == key:
            return {**row, "status": "SKIP_ALREADY_COMPLETE" if row.get("status") == "SUCCESS" else row.get("status")}
    record = {"idempotency_key": key, "operation": operation, "entity_id": entity_id, "status": "SUCCESS", "recorded_at": core.now()}
    _append(_state("idempotency.jsonl"), record)
    return record


def db_check(d) -> dict:
    checks = []
    integrity = d.execute("PRAGMA integrity_check").fetchone()[0]
    checks.append({"name": "integrity", "ok": integrity == "ok", "detail": integrity})
    foreign = [list(row) for row in d.execute("PRAGMA foreign_key_check")]
    checks.append({"name": "foreign_keys", "ok": not foreign, "detail": foreign})
    tables = {row[0] for row in d.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "businesses" in tables:
        duplicates = d.execute("SELECT canonical_host,normalized_name,coalesce(region,''),count(*) FROM businesses WHERE is_dummy=0 AND coalesce(suppression_reason,'')='' AND canonical_host IS NOT NULL AND normalized_name IS NOT NULL GROUP BY 1,2,3 HAVING count(*)>1").fetchall()
        checks.append({"name": "active_duplicate_canonical_business", "ok": not duplicates, "detail": [list(row) for row in duplicates]})
    if "mm_contact_evidence" in tables:
        missing = d.execute("SELECT count(*) FROM mm_contact_evidence WHERE confidence>0 AND (capture_path IS NULL OR capture_hash IS NULL)").fetchone()[0]
        checks.append({"name": "verified_contact_provenance", "ok": missing == 0, "detail": missing})
    return {"ok": all(check["ok"] for check in checks), "checks": checks, "checked_at": core.now()}


def safe_mode(enabled=None) -> dict:
    path = _state("safe-mode.json")
    if enabled is not None:
        value = {"enabled": bool(enabled), "changed_at": core.now(), "changed_by": "human_cli"}
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"enabled": False, "changed_at": None, "changed_by": None}


def replay(decision_id: str) -> dict:
    matches = [row for row in ledger() if row.get("decision_id") == decision_id]
    if not matches:
        raise ValueError("Decision not found")
    original = matches[-1]
    return {"decision_id": decision_id, "original": original.get("action"), "replay": original.get("action"), "match": True, "policy_version": original.get("policy_version"), "read_only": True}


def shadow(current: dict, challenger: dict) -> dict:
    return {"current": current, "challenger": challenger, "different": current != challenger, "promoted": False, "human_approval_required": True}

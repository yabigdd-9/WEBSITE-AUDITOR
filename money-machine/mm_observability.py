"""P17 lightweight observability over canonical SQLite/state.

No Prometheus/Grafana dependency. Database access is read-only; optional snapshots
write only to state/*.json or jsonl for Obsidian/operator visibility.
"""
from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path

import mm_core as core


def _tables(d):
    return {r[0] for r in d.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _open():
    path = core.root() / "database" / "money_machine.db"
    if not path.is_file():
        return None
    return core.connect(path, readonly=True)


def health() -> dict:
    from supervisor.cli import cmd_health
    from types import SimpleNamespace

    result = cmd_health(SimpleNamespace())
    result["generated_at"] = core.now()
    result["authoritative"] = "SQLite + ./mm supervisor"
    result["paid_model_fallback"] = False
    result["live_outreach_default"] = False
    # P6: typed alert rules surfaced with every health snapshot.
    try:
        import mm_reporting
        result["alerts"] = mm_reporting.evaluate_alerts()["alerts"]
    except Exception as ex:  # never let alerting break the health probe
        result["alerts"] = [{"rule": "evaluate_alerts", "status": "ERROR", "detail": str(ex)}]
    return result


def metrics() -> dict:
    result = {
        "generated_at": core.now(),
        "metrics": {},
        "pipeline_states": {},
        "model_cost_usd": 0,
    }
    d = _open()
    if d is None:
        result["database"] = "missing"
        return result
    with contextlib.closing(d):
        tables = _tables(d)
        if "mm_metrics" in tables:
            result["metrics"] = {r[0]: r[1] for r in d.execute("SELECT name,value FROM mm_metrics")}
        if "pipeline_items" in tables:
            result["pipeline_states"] = {
                r[0]: r[1]
                for r in d.execute("SELECT state,count(*) FROM pipeline_items GROUP BY state")
            }
        # P6: per-stage funnel counts (canonical CRM stages).
        if "mm_deals" in tables:
            result["funnel_stages"] = {
                r[0]: r[1] for r in d.execute("SELECT stage,count(*) FROM mm_deals GROUP BY stage")
            }
        if "mm_model_invocations" in tables:
            spent = d.execute("SELECT coalesce(sum(cost_usd),0) FROM mm_model_invocations").fetchone()[0]
            result["model_cost_usd"] = float(spent or 0)
    return result


def queue(limit=100) -> dict:
    limit = max(1, min(int(limit), 1000))
    d = _open()
    if d is None:
        return {"generated_at": core.now(), "items": [], "count": 0, "database": "missing"}
    with contextlib.closing(d):
        if "pipeline_items" not in _tables(d):
            return {"generated_at": core.now(), "items": [], "count": 0, "pipeline": "uninitialised"}
        rows = [
            dict(r)
            for r in d.execute(
                "SELECT business_id,state,attempts,max_attempts,next_retry_at,lease_owner,"
                "lease_until,heartbeat_at,last_error,updated_at FROM pipeline_items "
                "ORDER BY updated_at ASC LIMIT ?",
                (limit,),
            )
        ]
    return {"generated_at": core.now(), "items": rows, "count": len(rows)}


def dead_letter(limit=100) -> dict:
    all_items = queue(1000)
    items = [
        row
        for row in all_items.get("items", [])
        if row.get("state") in {"RETRYABLE_FAILURE", "PERMANENT_FAILURE"}
    ][: max(1, min(int(limit), 1000))]
    return {
        "generated_at": core.now(),
        "items": items,
        "count": len(items),
        "triage_required": bool(items),
    }


def errors(limit=100, show_root_causes=False) -> dict:
    if show_root_causes:
        # Show root causes from pipeline_items table
        d = _open()
        if d is None:
            return {"generated_at": core.now(), "root_causes": [], "count": 0, "database": "missing"}

        with contextlib.closing(d):
            # Check if error tracking columns exist
            tables = _tables(d)
            if "pipeline_items" not in tables:
                return {"generated_at": core.now(), "root_causes": [], "count": 0, "pipeline": "uninitialised"}
            cols = {r[1] for r in d.execute("PRAGMA table_info(pipeline_items)")}
            if "error_fingerprint" not in cols:
                # Pre-migration database: the query would raise, not report.
                return {"generated_at": core.now(), "root_causes": [], "count": 0,
                        "pipeline": "error tracking columns not migrated yet"}

            # Get items with error fingerprints (non-null error_fingerprint)
            rows = [
                dict(r)
                for r in d.execute(
                    """
                    SELECT business_id, state, attempts, error_fingerprint, repeat_count,
                           component, origin, classification, first_seen, last_seen, last_error,
                           updated_at
                    FROM pipeline_items
                    WHERE error_fingerprint IS NOT NULL
                    ORDER BY repeat_count DESC, last_seen DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
            ]

            # Enrich with business information
            for row in rows:
                if row['business_id']:
                    try:
                        business_row = d.execute(
                            "SELECT name, public_website FROM businesses WHERE id = ?",
                            (row['business_id'],)
                        ).fetchone()
                        if business_row:
                            row['business_name'] = business_row['name']
                            row['business_website'] = business_row['public_website']
                    except Exception:
                        pass  # Business might have been deleted

            return {
                "generated_at": core.now(),
                "root_causes": rows,
                "count": len(rows)
            }
    else:
        # Original behavior - show recent errors from logs
        limit = max(1, min(int(limit), 1000))
        records = []
        log_dir = core.root() / "state" / "worker-logs"
        for path in sorted(log_dir.glob("*.jsonl"), reverse=True):
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeError):
                continue
            for raw in reversed(lines):
                try:
                    row = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if row.get("error") or row.get("kind") in {
                    "failure",
                    "worker_error",
                    "logrotate_error",
                    "schema_drift_repaired",
                }:
                    records.append(row)
                    if len(records) >= limit:
                        break
            if len(records) >= limit:
                break
        return {"generated_at": core.now(), "errors": records, "count": len(records)}


def _append_jsonl(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def write_snapshots() -> dict:
    from auditor_toolkit.common import atomic_write_json

    state = core.root() / "state"
    state.mkdir(parents=True, exist_ok=True)
    health_doc = health()
    metrics_doc = metrics()
    errors_doc = errors()
    dead_doc = dead_letter(1000)
    atomic_write_json(state / "health.json", health_doc)
    _append_jsonl(state / "metrics.jsonl", metrics_doc)
    _append_jsonl(state / "errors.jsonl", errors_doc)

    dead_dir = state / "dead-letter"
    dead_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(dead_dir / "queue.json", dead_doc)

    heartbeat_dir = state / "worker-heartbeats"
    heartbeat_dir.mkdir(parents=True, exist_ok=True)
    workers = []
    d = _open()
    if d is not None:
        with contextlib.closing(d):
            if "worker_registry" in _tables(d):
                workers = [dict(r) for r in d.execute("SELECT * FROM worker_registry ORDER BY worker_id")]
    for worker in workers:
        safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in worker["worker_id"])
        atomic_write_json(heartbeat_dir / (safe + ".json"), worker)

    return {
        "health": str(state / "health.json"),
        "metrics": str(state / "metrics.jsonl"),
        "errors": str(state / "errors.jsonl"),
        "dead_letter": str(dead_dir / "queue.json"),
        "worker_heartbeats": str(heartbeat_dir),
        "worker_count": len(workers),
        "database_mutations": 0,
    }

"""P17 lightweight observability over canonical SQLite/state.

No Prometheus/Grafana dependency. Database access is read-only; optional snapshots
write only to state/*.json or jsonl for Obsidian/operator visibility.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
from pathlib import Path

import mm_core as core


def _tables(d):
    return {r[0] for r in d.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _open():
    path = core.root() / "database" / "money_machine.db"
    if not path.is_file():
        return None
    return core.connect(path, readonly=True)


def _discovery_health(probe_service=True) -> dict:
    """Read recurring-discovery state and probe only the configured loopback service."""
    import mm_recurring_discovery as recurring
    import mm_search_backend

    try:
        config = recurring.load_config()
    except Exception as exc:
        return {
            "enabled": False,
            "state": "CONFIG_ERROR",
            "error": "%s: %s" % (type(exc).__name__, exc),
        }

    endpoint = str(
        config.get("searxng_endpoint") or "http://127.0.0.1:8888"
    )
    if probe_service:
        try:
            probe = mm_search_backend.probe(endpoint, timeout=2)
        except Exception as exc:
            probe = {
                "provider": "searxng",
                "endpoint": endpoint,
                "ok": False,
                "state": "PROBE_ERROR",
                "reason": "%s: %s" % (type(exc).__name__, exc),
            }
    else:
        probe = {"provider": "searxng", "endpoint": endpoint, "ok": None,
                 "state": "NOT_PROBED", "reason": "Automatic export performs no search/provider requests"}

    path = Path(recurring.DEFAULT_STATE)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            state = {}
    except (OSError, TypeError, ValueError):
        state = {}

    interval = 360
    try:
        interval = max(15, int(config.get("interval_minutes", 360)))
    except (TypeError, ValueError):
        pass

    last = state.get("last_finished_at")
    next_due = None
    due_now = True
    if last:
        try:
            parsed = dt.datetime.fromisoformat(
                str(last).replace("Z", "+00:00")
            )
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            due_at = parsed.astimezone(dt.timezone.utc) + dt.timedelta(
                minutes=interval
            )
            next_due = due_at.isoformat()
            due_now = dt.datetime.now(dt.timezone.utc) >= due_at
        except (TypeError, ValueError):
            due_now = True

    return {
        "enabled": config.get("enabled") is True,
        "interval_minutes": interval,
        "endpoint": endpoint,
        "state_file": str(path),
        "state_file_exists": path.is_file(),
        "last_finished_at": last,
        "next_due_at": next_due,
        "due_now": due_now,
        "collection_counts": state.get("collection_counts"),
        "intake_counts": state.get("intake_counts"),
        "sources": state.get("sources"),
        "searxng": probe,
        "external_sends": 0,
        "paid_calls": 0,
    }


def health(probe_discovery=True) -> dict:
    from types import SimpleNamespace

    from supervisor.cli import cmd_health

    result = cmd_health(SimpleNamespace())
    result["generated_at"] = core.now()
    result["authoritative"] = "SQLite + ./mm supervisor"
    result["paid_model_fallback"] = False
    result["live_outreach_default"] = False
    result["recurring_discovery"] = _discovery_health() if probe_discovery else _discovery_health(probe_service=False)
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
    limit = max(1, min(int(limit), 1000))
    items = []
    total = 0
    d = _open()
    if d is not None:
        with contextlib.closing(d):
            if "pipeline_items" in _tables(d):
                # Filter before LIMIT so a large healthy queue cannot hide
                # failures beyond its first 1,000 oldest entries.
                where = "state IN ('RETRYABLE_FAILURE','PERMANENT_FAILURE')"
                total = d.execute("SELECT count(*) FROM pipeline_items WHERE " + where).fetchone()[0]
                items = [dict(row) for row in d.execute(
                    "SELECT business_id,state,attempts,max_attempts,next_retry_at,lease_owner,"
                    "lease_until,heartbeat_at,last_error,updated_at FROM pipeline_items WHERE "
                    + where + " ORDER BY updated_at ASC,business_id ASC LIMIT ?", (limit,))]
    return {
        "generated_at": core.now(),
        "items": items,
        "count": len(items),
        "total_count": total,
        "truncated": total > len(items),
        "triage_required": total > 0,
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
    from supervisor.logrotate import append_jsonl
    append_jsonl(path, value)


def write_snapshots(probe_discovery=True) -> dict:
    from supervisor.logrotate import directory_lock
    if type(probe_discovery) is not bool:
        raise ValueError("Explicit discovery-probe boolean required")
    with directory_lock(core.root() / "state", ".observability-snapshot.lock"):
        return _write_snapshots(probe_discovery)


def _write_snapshots(probe_discovery) -> dict:
    from auditor_toolkit.common import atomic_write_json

    state = core.root() / "state"
    state.mkdir(parents=True, exist_ok=True)
    health_doc = health() if probe_discovery else health(probe_discovery=False)
    metrics_doc = metrics()
    errors_doc = errors()
    dead_doc = dead_letter(1000)
    atomic_write_json(state / "health.json", health_doc)
    _append_jsonl(state / "metrics.jsonl", metrics_doc)
    # Repeated unchanged historical errors are not appended every minute.
    error_payload = {key: value for key, value in errors_doc.items() if key != "generated_at"}
    error_hash = hashlib.sha256(json.dumps(error_payload, sort_keys=True, default=str).encode()).hexdigest()
    cursor_path = state / "observability-error-cursor.json"
    try:
        cursor = json.loads(cursor_path.read_text())
    except (OSError, ValueError):
        cursor = {}
    if not isinstance(cursor, dict) or cursor.get("sha256") != error_hash:
        errors_doc["snapshot_sha256"] = error_hash
        _append_jsonl(state / "errors.jsonl", errors_doc)
        atomic_write_json(cursor_path, {"sha256": error_hash, "updated_at": core.now()})

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

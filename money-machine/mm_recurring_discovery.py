"""Bounded recurring discovery for the always-on local Money Machine.

The runner only uses:
- local inbox files (CSV/JSON/JSONL), and
- loopback SearXNG via mm_discovery.

It never sends outreach, never calls paid models, and never talks directly to a
public search API. Existing host/name dedupe remains authoritative at ingest.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import yaml

import mm_core
import mm_discovery

UTC = dt.timezone.utc
DEFAULT_CONFIG = mm_core.root() / "money-machine" / "config" / "discovery_schedule.yaml"
DEFAULT_STATE = mm_core.root() / "state" / "recurring-discovery.json"


def _timestamp(value):
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def load_config(path=DEFAULT_CONFIG):
    path = Path(path)
    if not path.is_file():
        return {"enabled": False, "reason": "config_missing"}
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError("recurring discovery config must be an object")
    return data


def _read_state(path):
    path = Path(path)
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_state(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def _inbox_files(root, config):
    inbox = Path(config.get("inbox_dir") or (Path(root) / "discovery-inbox"))
    if not inbox.is_absolute():
        inbox = Path(root) / inbox
    if not inbox.exists():
        return []
    allowed = {".csv", ".json", ".jsonl"}
    return [
        str(path)
        for path in sorted(inbox.iterdir())
        if path.is_file() and path.suffix.lower() in allowed
    ][: mm_discovery.MAX_BATCH_FILES]


def due(config, state, at=None):
    if config.get("enabled") is not True:
        return False
    at = at or dt.datetime.now(UTC)
    try:
        minutes = max(15, int(config.get("interval_minutes", 360)))
    except (TypeError, ValueError):
        minutes = 360
    last = _timestamp(state.get("last_finished_at"))
    return last is None or at - last >= dt.timedelta(minutes=minutes)


def run_due(
    d,
    *,
    config_path=DEFAULT_CONFIG,
    state_path=DEFAULT_STATE,
    at=None,
    force=False,
):
    """Run one bounded cycle; force bypasses only the interval timer."""
    at = at or dt.datetime.now(UTC)
    config = load_config(config_path)
    state = _read_state(state_path)
    if config.get("enabled") is not True:
        return {
            "ran": False,
            "reason": "disabled",
            "last_finished_at": state.get("last_finished_at"),
            "forced": bool(force),
            "external_sends": 0,
            "paid_calls": 0,
        }
    if not force and not due(config, state, at):
        return {
            "ran": False,
            "reason": "disabled_or_not_due",
            "last_finished_at": state.get("last_finished_at"),
            "forced": False,
            "external_sends": 0,
            "paid_calls": 0,
        }

    root = mm_core.root()
    files = _inbox_files(root, config)
    queries = [
        str(item).strip()
        for item in (config.get("queries") or [])
        if str(item).strip()
    ][: mm_discovery.MAX_BATCH_QUERIES]
    if not files and not queries:
        result = {
            "ran": False,
            "reason": "no_sources",
            "last_finished_at": at.isoformat(),
            "forced": bool(force),
            "external_sends": 0,
            "paid_calls": 0,
        }
        _write_state(state_path, result)
        return result

    collection = mm_discovery.collect_multi_source(
        files=files,
        queries=queries,
        region=str(config.get("region") or "New Zealand"),
        endpoint=str(config.get("searxng_endpoint") or "http://127.0.0.1:8888"),
        limit=max(1, min(int(config.get("results_per_query", 10)), 50)),
    )
    intake = mm_discovery.ingest(
        d,
        collection["candidates"],
        actor="recurring-discovery",
        dry_run=False,
    )
    result = {
        "ran": True,
        "started_at": state.get("current_started_at") or at.isoformat(),
        "last_finished_at": at.isoformat(),
        "forced": bool(force),
        "sources": collection["sources"],
        "collection_counts": collection["counts"],
        "intake_counts": intake["counts"],
        "external_sends": 0,
        "paid_calls": 0,
    }
    _write_state(state_path, result)
    return result

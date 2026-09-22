"""Provider-neutral email lifecycle tracking; no transport and no hidden telemetry.

Events are provider receipts, DSNs, replies, suppressions, and human outcomes.
The event log is append-only and replay-safe.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections import Counter
from pathlib import Path

import mm_core as core

STATUSES = {"draft", "approved", "queued", "provider_accepted", "delivered", "delayed", "bounced", "replied", "suppressed", "failed", "retryable_failed", "dead_lettered", "reconciled"}
EVENT_KINDS = {"approval", "queued", "provider_accepted", "delivered", "delayed", "failed", "bounce", "reply", "suppression", "human_outcome", "reconcile"}


def _path(path=None) -> Path:
    target = Path(path) if path else core.root() / "state" / "email-events.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _rows(path=None):
    target = _path(path)
    if not target.exists():
        return []
    rows = []
    for line in target.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
        except json.JSONDecodeError:
            continue
    return rows


def event_id(event: dict) -> str:
    stable = {key: event.get(key) for key in ("provider", "provider_event_id", "message_id", "kind", "recipient", "status")}
    return hashlib.sha256(json.dumps(stable, sort_keys=True, default=str).encode()).hexdigest()


def normalize_event(event: dict) -> dict:
    if not isinstance(event, dict):
        raise ValueError("event object required")
    kind = str(event.get("kind", "")).strip().lower()
    status = str(event.get("status", "")).strip().lower()
    if kind not in EVENT_KINDS:
        raise ValueError("unknown email event kind")
    if status not in STATUSES:
        raise ValueError("unknown email event status")
    message_id = str(event.get("message_id", "")).strip()
    if not message_id:
        raise ValueError("message_id required")
    normalized = {
        "event_id": event_id(event),
        "observed_at": str(event.get("observed_at") or core.now()),
        "kind": kind,
        "status": status,
        "message_id": message_id,
        "business_id": event.get("business_id"),
        "recipient": str(event.get("recipient") or "").strip().lower(),
        "provider": str(event.get("provider") or "operator").strip(),
        "provider_event_id": str(event.get("provider_event_id") or "").strip(),
        "thread_id": str(event.get("thread_id") or "").strip(),
        "source_path": str(event.get("source_path") or ""),
        "source_sha256": str(event.get("source_sha256") or ""),
        "note": str(event.get("note") or "")[:1000],
        "human_review_required": True,
    }
    return normalized


def record(event: dict, path=None) -> dict:
    normalized = normalize_event(event)
    rows = _rows(path)
    if any(row.get("event_id") == normalized["event_id"] for row in rows):
        return {"recorded": False, "duplicate": True, "event": normalized}
    with _path(path).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(normalized, sort_keys=True) + "\n")
    return {"recorded": True, "duplicate": False, "event": normalized}


def _observed_at_key(row: dict, index: int):
    """Sort key from a real timestamp; unparsable stamps sort first by arrival."""
    raw = str(row.get("observed_at") or "")
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return (0, parsed.timestamp(), index)
    except (TypeError, ValueError):
        return (1, 0.0, index)


def _ordered(rows):
    return sorted(enumerate(rows), key=lambda item: _observed_at_key(item[1], item[0]))


def events_for(message_id: str, path=None) -> list[dict]:
    """Return one message's event trail in observed-time order."""
    return [row for _, row in _ordered([row for row in _rows(path) if row.get("message_id") == str(message_id)])]


def summary(path=None) -> dict:
    rows = _rows(path)
    latest = {}
    for _, row in _ordered(rows):
        latest[row["message_id"]] = row
    counts = Counter(row.get("status") for row in latest.values())
    unresolved = [row for row in latest.values() if row.get("status") in {"delayed", "failed", "retryable_failed"}]
    return {
        "messages": len(latest),
        "events": len(rows),
        "status_counts": dict(sorted(counts.items())),
        "unresolved": unresolved,
        "open_tracking": False,
        "click_tracking": False,
        "human_review_required": True,
        "external_sends_by_this_module": 0,
    }


def reconcile(message_id: str, path=None) -> dict:
    events = events_for(message_id, path)
    if not events:
        raise ValueError("message has no tracking events")
    terminal = {"suppressed", "replied", "bounced", "delivered", "dead_lettered", "reconciled"}
    current = events[-1]
    return {
        "message_id": message_id,
        "status": current.get("status"),
        "terminal": current.get("status") in terminal,
        "observed_at": current.get("observed_at"),
        "event_count": len(events),
        "provider_ids": sorted({row.get("provider_event_id") for row in events if row.get("provider_event_id")}),
        "thread_ids": sorted({row.get("thread_id") for row in events if row.get("thread_id")}),
        "human_review_required": True,
        "automatic_retry": False,
    }

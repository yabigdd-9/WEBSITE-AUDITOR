"""End-to-end regression: drive the email lifecycle through the real ./mm CLI.

Mirrors the manual verification exactly: create intent, idempotent replay,
bounded failures to dead-letter, terminal-regression rejection, full
reconstruction, and tracker reconciliation — all via subprocess against an
isolated MM_ROOT with a real SQLite database.
"""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

import mm_core as core

REPO = Path(__file__).resolve().parents[1]
MM = REPO / "mm"


def database(tmp_path):
    (tmp_path / "database").mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "database" / "money_machine.db"
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE businesses(id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE mm_messages(
            id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL,
            recipient TEXT NOT NULL, body TEXT NOT NULL,
            sent_at TEXT, invalidated_reason TEXT);
        CREATE TABLE approval_records(
            id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL,
            status TEXT NOT NULL, content_hash TEXT, actor TEXT);
        CREATE TABLE mm_suppression(address TEXT PRIMARY KEY, reason TEXT);
        INSERT INTO businesses VALUES(1, 'CLI Verify Fixture');
        INSERT INTO mm_messages VALUES(9, 1, 'team@fixture.example', 'Subject: CLI Verify\n\nHello', NULL, NULL);
    """)
    message = db.execute("SELECT recipient, body FROM mm_messages WHERE id=9").fetchone()
    db.execute(
        "INSERT INTO approval_records VALUES(4, 1, ?, ?, ?)",
        ("APPROVED", core.digest(message["recipient"], message["body"]), "human-cli-verify"),
    )
    db.commit()
    db.close()
    return db_path


def run_cli(args, tmp_path, check=True):
    env = {**os.environ, "MM_ROOT": str(tmp_path), "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run(
        [str(MM), *args], capture_output=True, text=True, env=env, timeout=60, cwd=str(REPO)
    )
    if check:
        assert result.returncode == 0, f"mm {args} failed:\n{result.stderr}\n{result.stdout}"
    return result


def run_json(args, tmp_path):
    return json.loads(run_cli(args, tmp_path).stdout)


def event_store(tmp_path):
    return tmp_path / "state" / "email-events.jsonl"


def test_full_lifecycle_through_real_cli(tmp_path):
    database(tmp_path)

    # 1. Create intent
    intent = run_json(["email-intent", "9", "--campaign", "cli-verify"], tmp_path)
    assert intent["status"] == "planned"
    assert intent["transport"] == "none"
    assert intent["transport_send_performed"] is False
    assert intent["external_sends"] == 0
    assert intent["replayed"] is False
    key = intent["idempotency_key"]

    # 2. Idempotent replay
    replay = run_json(["email-intent", "9", "--campaign", "cli-verify"], tmp_path)
    assert replay["replayed"] is True
    assert replay["idempotency_key"] == key

    # 3. Bounded failures: max_attempts=2 -> first retryable, second dead-lettered
    first = run_json(
        ["email-intent-result", key, "--status", "failed", "--error", "transient outage",
         "--max-attempts", "2"],
        tmp_path,
    )
    assert first["status"] == "retryable_failed"
    assert first["attempt_count"] == 1

    dead = run_json(
        ["email-intent-result", key, "--status", "failed", "--error", "still down",
         "--max-attempts", "2"],
        tmp_path,
    )
    assert dead["status"] == "dead_lettered"
    assert dead["attempt_count"] == 2

    # 4. Terminal regression after dead-letter must be rejected fail-closed
    regress = run_cli(["email-intent-result", key, "--status", "delivered"], tmp_path, check=False)
    assert regress.returncode != 0
    assert "terminal delivery state cannot regress" in regress.stderr

    # 5. Reconstruction through the CLI
    history = run_json(["email-lifecycle", "9"], tmp_path)
    assert history["message"]["id"] == 9
    assert history["approval"]["id"] == 4
    assert history["approval"]["status"] == "APPROVED"
    assert history["intents"][0]["status"] == "dead_lettered"
    statuses = [event["status"] for event in history["events"]]
    assert statuses == ["queued", "retryable_failed", "dead_lettered"]
    assert history["human_approval_required"] is True
    assert history["external_sends"] == 0
    assert history["paid_calls"] == 0

    # 6. Tracker summary + reconciliation through the CLI
    track = run_json(["email-track", "--store", str(event_store(tmp_path))], tmp_path)
    assert track["messages"] == 1
    assert track["status_counts"].get("dead_lettered") == 1
    assert track["external_sends_by_this_module"] == 0
    assert track["open_tracking"] is False and track["click_tracking"] is False

    reconcile = run_json(["email-reconcile", "9", "--store", str(event_store(tmp_path))], tmp_path)
    assert reconcile["status"] == "dead_lettered"
    assert reconcile["terminal"] is True
    assert reconcile["automatic_retry"] is False


def test_suppressed_recipient_cannot_get_intent_through_cli(tmp_path):
    database(tmp_path)
    db = sqlite3.connect(tmp_path / "database" / "money_machine.db")
    db.execute("INSERT INTO mm_suppression VALUES('team@fixture.example', 'human unsubscribe')")
    db.commit()
    db.close()

    result = run_cli(["email-intent", "9", "--campaign", "blocked"], tmp_path, check=False)
    assert result.returncode != 0
    assert "suppressed" in result.stderr


def test_unapproved_draft_cannot_get_intent_through_cli(tmp_path):
    database(tmp_path)
    db = sqlite3.connect(tmp_path / "database" / "money_machine.db")
    db.execute("UPDATE approval_records SET status='PENDING' WHERE id=4")
    db.commit()
    db.close()

    result = run_cli(["email-intent", "9", "--campaign", "unapproved"], tmp_path, check=False)
    assert result.returncode != 0
    assert "exact human approval required" in result.stderr


def test_out_of_order_events_reconcile_by_timestamp(tmp_path):
    """A late-arriving historical event must not regress the reported status."""
    database(tmp_path)
    store = event_store(tmp_path)
    store.parent.mkdir(parents=True, exist_ok=True)

    import mm_email_tracking as tracking

    # Append in arrival order: delivered first, then a stale provider event
    # with an older observed_at timestamp.
    tracking.record(
        {"provider": "fixture", "provider_event_id": "evt-2", "message_id": "9",
         "kind": "delivered", "status": "delivered",
         "observed_at": "2026-09-22T12:00:00+00:00"}, store,
    )
    tracking.record(
        {"provider": "fixture", "provider_event_id": "evt-1", "message_id": "9",
         "kind": "queued", "status": "queued",
         "observed_at": "2026-09-22T10:00:00+00:00"}, store,
    )

    result = tracking.reconcile("9", store)
    assert result["status"] == "delivered"
    assert result["terminal"] is True
    assert result["observed_at"] == "2026-09-22T12:00:00+00:00"

    events = tracking.events_for("9", store)
    assert [row["status"] for row in events] == ["queued", "delivered"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

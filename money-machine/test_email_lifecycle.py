import sqlite3

import pytest

import mm_core as core
import mm_email_lifecycle as lifecycle
import mm_email_tracking as tracking


def database(tmp_path):
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE businesses(id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE mm_messages(
            id INTEGER PRIMARY KEY,
            business_id INTEGER NOT NULL,
            recipient TEXT NOT NULL,
            body TEXT NOT NULL,
            sent_at TEXT,
            invalidated_reason TEXT
        );
        CREATE TABLE approval_records(
            id INTEGER PRIMARY KEY,
            business_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            content_hash TEXT,
            actor TEXT
        );
        CREATE TABLE mm_suppression(address TEXT PRIMARY KEY, reason TEXT);
        INSERT INTO businesses VALUES(1, 'Fixture Business');
        INSERT INTO mm_messages VALUES(7, 1, 'Team@fixture.example', 'Subject: Fixture\\n\\nHello', NULL, NULL);
        """
    )
    body = db.execute("SELECT body FROM mm_messages WHERE id=7").fetchone()[0]
    recipient = db.execute("SELECT recipient FROM mm_messages WHERE id=7").fetchone()[0]
    db.execute(
        "INSERT INTO approval_records VALUES(1, 1, 'APPROVED', ?, 'human-fixture')",
        (core.digest(recipient, body),),
    )
    return db


def test_intent_requires_exact_human_approval(tmp_path):
    db = database(tmp_path)
    event_path = tmp_path / "events.jsonl"
    db.execute("UPDATE approval_records SET content_hash='wrong'")
    with pytest.raises(ValueError, match="exact human approval"):
        lifecycle.create_intent(db, 7, "fixture", event_store=event_path)
    assert db.execute("SELECT count(*) FROM email_delivery_intents").fetchone()[0] == 0


def test_intent_is_idempotent_and_records_no_send(tmp_path):
    db = database(tmp_path)
    event_path = tmp_path / "events.jsonl"
    first = lifecycle.create_intent(db, 7, "fixture", event_store=event_path)
    second = lifecycle.create_intent(db, 7, "fixture", event_store=event_path)
    assert first["status"] == "planned"
    assert second["replayed"] is True
    assert first["idempotency_key"] == second["idempotency_key"]
    assert db.execute("SELECT count(*) FROM email_delivery_intents").fetchone()[0] == 1
    assert len(event_path.read_text().splitlines()) == 1
    assert first["transport"] == "none"
    assert first["transport_send_performed"] is False
    assert first["external_sends"] == 0


def test_suppression_blocks_intent_without_mutating_suppression(tmp_path):
    db = database(tmp_path)
    event_path = tmp_path / "events.jsonl"
    db.execute("INSERT INTO mm_suppression VALUES('team@fixture.example', 'human unsubscribe')")
    with pytest.raises(ValueError, match="suppressed"):
        lifecycle.create_intent(db, 7, "fixture", event_store=event_path)
    assert db.execute("SELECT count(*) FROM email_delivery_intents").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM mm_suppression").fetchone()[0] == 1


def test_failures_are_bounded_and_dead_lettered(tmp_path):
    db = database(tmp_path)
    event_path = tmp_path / "events.jsonl"
    intent = lifecycle.create_intent(db, 7, "fixture", max_attempts=2, event_store=event_path)
    retry = lifecycle.record_result(db, intent["idempotency_key"], "failed", error="temporary", event_store=event_path)
    dead = lifecycle.record_result(db, intent["idempotency_key"], "failed", error="still unavailable", event_store=event_path)
    assert retry["status"] == "retryable_failed"
    assert retry["attempt_count"] == 1
    assert dead["status"] == "dead_lettered"
    assert dead["attempt_count"] == 2
    assert tracking.reconcile("7", event_path)["status"] == "dead_lettered"
    with pytest.raises(ValueError, match="terminal"):
        lifecycle.record_result(db, intent["idempotency_key"], "delivered", event_store=event_path)


def test_reconstruction_contains_message_approval_intent_and_events(tmp_path):
    db = database(tmp_path)
    event_path = tmp_path / "events.jsonl"
    intent = lifecycle.create_intent(db, 7, "fixture", event_store=event_path)
    lifecycle.record_result(db, intent["idempotency_key"], "provider_accepted", provider_message_id="fixture-provider-id", event_store=event_path)
    result = lifecycle.reconstruct(db, 7, event_store=event_path)
    assert result["message"]["id"] == 7
    assert result["approval"]["id"] == 1
    assert result["intents"][0]["provider_message_id"] == "fixture-provider-id"
    assert [event["status"] for event in result["events"]] == ["queued", "provider_accepted"]
    assert result["human_approval_required"] is True
    assert result["external_sends"] == 0
    assert result["paid_calls"] == 0


def test_draft_change_after_intent_is_blocked(tmp_path):
    db = database(tmp_path)
    event_path = tmp_path / "events.jsonl"
    intent = lifecycle.create_intent(db, 7, "fixture", event_store=event_path)
    db.execute("UPDATE mm_messages SET body=body || ' changed' WHERE id=7")
    with pytest.raises(ValueError, match="draft changed"):
        lifecycle.record_result(db, intent["idempotency_key"], "delivered", event_store=event_path)


def test_provider_acceptance_remains_open_until_final_outcome(tmp_path):
    """provider_accepted is not terminal: delivered/bounced must still land."""
    db = database(tmp_path)
    event_path = tmp_path / "events.jsonl"
    intent = lifecycle.create_intent(db, 7, "fixture", event_store=event_path)
    accepted = lifecycle.record_result(
        db, intent["idempotency_key"], "provider_accepted", provider_message_id="prov-1",
        event_store=event_path,
    )
    assert accepted["status"] == "provider_accepted"
    delivered = lifecycle.record_result(
        db, intent["idempotency_key"], "delivered", event_store=event_path
    )
    assert delivered["status"] == "delivered"
    # Only now is the intent terminal: replaying delivered is safe, regressing is not.
    again = lifecycle.record_result(db, intent["idempotency_key"], "delivered", event_store=event_path)
    assert again["replayed"] is True
    with pytest.raises(ValueError, match="terminal"):
        lifecycle.record_result(db, intent["idempotency_key"], "failed", event_store=event_path)

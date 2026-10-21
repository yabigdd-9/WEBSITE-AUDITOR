"""Registered transport contract tests. Synthetic SQLite and fake SMTP only."""

import json
import os
import smtplib
import sqlite3

import mm_core as core
import mm_runtime_guards as guards
import mm_send_readiness as readiness
import mm_smtp_candidate as engine
import mm_smtp_live as live
import mm_transport as transport
import pytest
from test_send_readiness import db as db
from test_smtp_candidate import FakeSMTP, password
from test_smtp_candidate import approved as approved


@pytest.fixture
def registered(approved, monkeypatch, tmp_path):
    monkeypatch.setattr(core, "root", lambda: tmp_path)
    monkeypatch.delenv("MM_EXTERNAL_SEND_DISABLED", raising=False)
    import mm_outreach

    monkeypatch.setattr(core, "readiness", lambda *args: [])
    monkeypatch.setattr(mm_outreach, "require_copy", lambda *args, **kwargs: None)
    for name, kind in [
        ("approval_ref", "TEXT"),
        ("approved_by", "TEXT"),
        ("evidence_id", "INTEGER"),
        ("kind", "TEXT"),
    ]:
        approved.execute(f"ALTER TABLE mm_messages ADD COLUMN {name} {kind}")
    approved.execute(
        "UPDATE mm_messages SET approval_ref='1',approved_by='Synthetic Owner',evidence_id=3,kind='initial'"
    )
    approved.execute(
        "CREATE TABLE mm_receipts(id INTEGER,kind TEXT,business_id INTEGER,object_id INTEGER,content_hash TEXT,artifact_path TEXT,artifact_hash TEXT,verified_by TEXT)"
    )
    artifact = tmp_path / "exact-approval.txt"
    artifact.write_text("Synthetic exact-content owner approval fixture")
    digest = approved.execute("SELECT approved_hash FROM mm_messages WHERE id=1").fetchone()[0]
    approved.execute(
        "INSERT INTO mm_receipts VALUES(1,?,?,?,?,?,?,?)",
        (
            "approval",
            2,
            1,
            digest,
            str(artifact),
            core.sha(artifact.read_bytes()),
            "Synthetic Owner",
        ),
    )
    approved.commit()

    def gates(connection, bid):
        duplicate = readiness.mm_approval._gate_duplicate_send(connection, bid)
        return {
            "all_passed": duplicate[0],
            "gates": {
                "no_duplicate_send": {"passed": duplicate[0], "evidence": duplicate[1]},
                "synthetic_other_gates": {"passed": True},
            },
        }

    # Use the real duplicate check, including the engine's own reservation.
    readiness.mm_approval.migrate(approved)
    monkeypatch.setattr(readiness.mm_approval, "evaluate", gates)
    return approved, tmp_path / "email-events.jsonl"


def test_accepted_updates_claim_intent_ledger_and_durable_events(registered):
    connection, events = registered
    client = FakeSMTP()
    result = live.submit(
        connection, 1, password_loader=password, smtp_factory=client, event_store=events
    )
    assert result["status"] == "ACCEPTED"
    assert result["delivery_confirmed"] is result["external_receipt_verified"] is False
    assert (
        connection.execute("SELECT status FROM smtp_candidate_submissions").fetchone()[0]
        == "ACCEPTED"
    )
    assert connection.execute("SELECT status,transport FROM outreach_send_ledger").fetchone()[
        :
    ] == ("sent", "gmail")
    assert connection.execute(
        "SELECT status,attempt_count,max_attempts FROM email_delivery_intents"
    ).fetchone()[:] == ("provider_accepted", 1, 1)
    assert connection.execute("SELECT count(*) FROM smtp_event_outbox").fetchone()[0] == 2
    assert len(events.read_text().splitlines()) == 2
    with pytest.raises(ValueError):
        live.submit(
            connection, 1, password_loader=password, smtp_factory=client, event_store=events
        )
    assert client.events.count("submit") == 1


@pytest.mark.parametrize(
    "error,expected",
    [
        (TimeoutError("private provider details"), "UNKNOWN"),
        (smtplib.SMTPDataError(550, b"private provider details"), "REJECTED"),
    ],
)
def test_timeout_and_explicit_rejection_never_retry(registered, error, expected):
    connection, events = registered
    client = FakeSMTP(send_error=error)
    result = live.submit(
        connection, 1, password_loader=password, smtp_factory=client, event_store=events
    )
    assert result["status"] == expected
    assert "private provider details" not in json.dumps(result)
    assert (
        connection.execute("SELECT status FROM email_delivery_intents").fetchone()[0]
        == "dead_lettered"
    )
    before = list(connection.iterdump())
    result = live.reconciliation_status(connection, 1)
    assert result["claim"]["status"] == expected
    assert result["resend_authorized"] is False
    assert list(connection.iterdump()) == before
    with pytest.raises(ValueError):
        live.submit(
            connection, 1, password_loader=password, smtp_factory=client, event_store=events
        )
    assert client.events.count("submit") == 1


def test_revocation_after_login_is_held_before_data(registered):
    connection, events = registered

    def reject():
        connection.execute("INSERT INTO approval_records VALUES(2,2,'REJECTED',NULL)")
        connection.commit()

    client = FakeSMTP(login_hook=reject)
    result = live.submit(
        connection, 1, password_loader=password, smtp_factory=client, event_store=events
    )
    assert result["status"] == "HELD"
    assert "submit" not in client.events
    assert (
        connection.execute("SELECT status FROM outreach_send_ledger").fetchone()[0] == "quarantined"
    )


def test_failed_shared_persistence_retains_durable_reservation(registered):
    connection, events = registered

    class BrokenLedger:
        def __getattr__(self, name):
            return getattr(connection, name)

        def execute(self, sql, args=()):
            if sql.startswith("UPDATE outreach_send_ledger"):
                raise sqlite3.OperationalError("synthetic persistence failure")
            return connection.execute(sql, args)

    client = FakeSMTP()
    with pytest.raises(sqlite3.OperationalError):
        live.submit(
            BrokenLedger(), 1, password_loader=password, smtp_factory=client, event_store=events
        )
    assert not connection.in_transaction
    assert (
        connection.execute("SELECT status FROM smtp_candidate_submissions").fetchone()[0]
        == "RESERVED"
    )
    assert connection.execute("SELECT status FROM outreach_send_ledger").fetchone()[0] == "planned"
    assert connection.execute("SELECT count(*) FROM smtp_event_outbox").fetchone()[0] == 1
    with pytest.raises(ValueError):
        live.submit(
            connection, 1, password_loader=password, smtp_factory=client, event_store=events
        )
    assert client.events.count("submit") == 1


def test_projection_failure_is_replayable_without_resending(registered, monkeypatch):
    connection, events = registered
    original = live.tracking.record

    def broken(*args, **kwargs):
        raise OSError("synthetic event projection failure")

    monkeypatch.setattr(live.tracking, "record", broken)
    client = FakeSMTP()
    result = live.submit(
        connection, 1, password_loader=password, smtp_factory=client, event_store=events
    )
    assert result["status"] == "ACCEPTED"
    assert result["event_projection"]["state"] == "PENDING_REPLAY"
    monkeypatch.setattr(live.tracking, "record", original)
    assert live.project_events(connection, events)["events_projected"] == 2
    assert live.project_events(connection, events)["events_projected"] == 0
    assert client.events.count("submit") == 1


def test_credential_failure_has_no_provider_call(registered):
    connection, events = registered

    def unavailable(account):
        raise LookupError("private credential error")

    client = FakeSMTP()
    result = live.submit(
        connection, 1, password_loader=unavailable, smtp_factory=client, event_store=events
    )
    assert result["status"] == "HELD" and not client.events
    assert result["provider_submission_attempted"] is False


def test_environment_kill_switch_stops_before_any_side_effect(registered, monkeypatch):
    connection, events = registered
    before = list(connection.iterdump())
    monkeypatch.setenv("MM_EXTERNAL_SEND_DISABLED", "1")
    with pytest.raises(ValueError, match="disabled"):
        transport.submit(connection, 1, password_loader=password, smtp_factory=FakeSMTP())
    assert list(connection.iterdump()) == before


def test_changed_recipient_verification_before_data_is_held(registered, monkeypatch):
    connection, events = registered

    def revoke():
        def held(*args):
            raise ValueError("recipient no longer verified")

        monkeypatch.setattr(readiness.mm_email_store, "require_email", held)

    client = FakeSMTP(login_hook=revoke)
    assert (
        live.submit(
            connection, 1, password_loader=password, smtp_factory=client, event_store=events
        )["status"]
        == "HELD"
    )
    assert "submit" not in client.events


def test_private_enablement_schema_preserves_all_gates(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "root", lambda: tmp_path)
    result = transport.set_owner_policy(enabled=True, daily_cap=1, actor="Synthetic Owner")
    assert result["external_messages_sent"] == 0
    policy = tmp_path / "state/transport-policy.json"
    assert policy.stat().st_mode & 0o777 == 0o600
    assert transport.load_config()["provider"] == "gmail"
    transport.set_owner_policy(enabled=False, daily_cap=0, actor="Synthetic Owner")
    assert transport.load_config()["enabled"] is False
    assert len(list((tmp_path / "state/transport-policy-history").glob("*.json"))) == 1
    os.chmod(policy, 0o644)
    with pytest.raises(ValueError, match="private"):
        transport.load_config()


@pytest.mark.parametrize(
    "change",
    [
        {"daily_cap": True},
        {"daily_cap": 0},
        {"daily_cap": 11},
        {"requires_exact_approval": False},
        {"requires_verified_recipient": False},
        {"requires_suppression_check": False},
        {"provider": "other"},
        {"extra": True},
        {"version": True},
    ],
)
def test_invalid_live_policy_rejected(tmp_path, monkeypatch, change):
    monkeypatch.setattr(core, "root", lambda: tmp_path)
    transport.set_owner_policy(enabled=True, daily_cap=1, actor="Synthetic Owner")
    path = tmp_path / "state/transport-policy.json"
    doc = json.loads(path.read_text())
    doc.update(change)
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError):
        transport.load_config()


def test_policy_symlink_and_duplicate_fields_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "root", lambda: tmp_path)
    state = tmp_path / "state"
    state.mkdir()
    target = tmp_path / "outside.json"
    target.write_text("{}")
    policy = state / "transport-policy.json"
    policy.symlink_to(target)
    with pytest.raises(ValueError):
        transport.load_config()
    with pytest.raises(ValueError):
        transport.set_owner_policy(enabled=True, daily_cap=1, actor="Synthetic Owner")
    policy.unlink()
    policy.write_text('{"version":1,"version":1}')
    policy.chmod(0o600)
    with pytest.raises(ValueError, match="Duplicate"):
        transport.load_config()


def test_accounting_counts_acceptance_and_refuses_zero_for_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "root", lambda: tmp_path)
    (tmp_path / "database").mkdir()
    path = tmp_path / "database/money_machine.db"
    with sqlite3.connect(path) as connection:
        connection.executescript("""
          CREATE TABLE mm_model_invocations(cost_usd REAL);
          CREATE TABLE mm_messages(id INTEGER,sent_at TEXT,send_receipt TEXT);
          CREATE TABLE mm_proposals(sent_at TEXT,send_receipt TEXT);
          CREATE TABLE smtp_candidate_submissions(message_id INTEGER,status TEXT);
          INSERT INTO mm_messages VALUES(1,NULL,NULL);
          INSERT INTO smtp_candidate_submissions VALUES(1,'ACCEPTED');
        """)
    result = guards.accounting_snapshot(tmp_path)
    assert result["status"] == "measured" and result["external_sends"] == 1
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE smtp_candidate_submissions SET status='UNKNOWN'")
    result = guards.accounting_snapshot(tmp_path)
    assert result["status"] == "unknown" and result["external_sends"] is None


def test_canonical_submit_binds_expected_hash_before_credentials(registered):
    connection, events = registered
    client = FakeSMTP()
    with pytest.raises(ValueError, match="Exact reviewed"):
        transport.submit(connection, 1, password_loader=password, smtp_factory=client)
    with pytest.raises(ValueError, match="reviewed_content_hash_changed"):
        transport.submit(
            connection,
            1,
            expected_content_hash="0" * 64,
            password_loader=password,
            smtp_factory=client,
        )
    assert not client.events
    digest = connection.execute("SELECT approved_hash FROM mm_messages WHERE id=1").fetchone()[0]
    result = transport.submit(
        connection, 1, expected_content_hash=digest, password_loader=password, smtp_factory=client
    )
    assert result["status"] == "ACCEPTED"


def test_other_planned_ledger_cannot_be_excluded_as_own_claim(registered):
    connection, events = registered
    envelope = engine._approved_envelope(connection, 1)
    live.lifecycle.migrate(connection)
    connection.execute(live.DDL)
    connection.commit()
    engine._reserve(connection, 1, envelope, 1, live._claim)
    assert readiness.inspect_message(connection, 1, own_claim=envelope.submission_key)[
        "message_ready_for_transport_review"
    ]
    connection.execute(
        "INSERT INTO outreach_send_ledger SELECT 'other-key',business_id,recipient,content_hash,campaign,approval_id,transport,status,retry_count,provider_message_id,sent_at,bounce,created_at,updated_at FROM outreach_send_ledger LIMIT 1"
    )
    connection.commit()
    assert not readiness.inspect_message(connection, 1, own_claim=envelope.submission_key)[
        "message_ready_for_transport_review"
    ]


def test_approval_artifact_change_after_login_blocks_data(registered):
    connection, events = registered
    artifact = connection.execute("SELECT artifact_path FROM mm_receipts").fetchone()[0]
    from pathlib import Path

    client = FakeSMTP(login_hook=lambda: Path(artifact).write_text("Changed approval artifact"))
    assert (
        live.submit(
            connection, 1, password_loader=password, smtp_factory=client, event_store=events
        )["status"]
        == "HELD"
    )
    assert "submit" not in client.events


def test_canonical_readiness_change_after_login_blocks_data(registered, monkeypatch):
    connection, events = registered

    def changed():
        monkeypatch.setattr(core, "readiness", lambda *args: ["recipient evidence no longer valid"])

    client = FakeSMTP(login_hook=changed)
    assert (
        live.submit(
            connection, 1, password_loader=password, smtp_factory=client, event_store=events
        )["status"]
        == "HELD"
    )
    assert "submit" not in client.events

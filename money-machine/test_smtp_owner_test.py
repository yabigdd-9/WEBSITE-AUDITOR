"""Owner-only diagnostic purpose: fake SMTP and synthetic ownership proof."""

import json
import smtplib
import sqlite3

import mm_core as core
import mm_smtp_candidate as engine
import mm_smtp_owner_test as owner
import mm_transport as transport
import pytest
from test_smtp_candidate import FakeSMTP, password


@pytest.fixture
def packet(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "root", lambda: tmp_path)
    monkeypatch.delenv("MM_EXTERNAL_SEND_DISABLED", raising=False)
    config = {
        "version": 1,
        "provider": "gmail",
        "enabled": True,
        "daily_cap": 1,
        "external_send_allowed": True,
        "requires_exact_approval": True,
        "requires_verified_recipient": True,
        "requires_suppression_check": True,
    }
    monkeypatch.setattr(transport, "load_config", lambda path=None: config.copy())
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row

    def proof(account):
        return {
            "account": account,
            "source": "authenticated_readonly_imap",
            "authenticated": True,
            "checked_at": core.now(),
            "messages_read": 0,
            "external_messages_sent": 0,
        }

    result = owner.prepare(connection, "yabigdd@gmail.com", actor="Synthetic Owner", verifier=proof)
    yield connection, result, tmp_path / "events.jsonl"
    connection.close()


class OwnerSMTP(FakeSMTP):
    def sendmail(self, sender, recipients, wire):
        assert sender == engine.SENDER and recipients == ["yabigdd@gmail.com"]
        assert b"Website Auditor owner email test" in wire
        self.events.append("submit")
        if self.send_error:
            raise self.send_error
        return {}


def submit(packet, client):
    db, row, events = packet
    return owner.submit(
        db,
        row["id"],
        content_hash=row["content_hash"],
        actor="Synthetic Owner",
        password_loader=password,
        smtp_factory=client,
        event_store=events,
    )


def test_preparation_never_approves_or_sends(packet):
    db, row, events = packet
    assert row["approved_hash"] is row["approved_by"] is row["claim"] is None
    assert row["recipient"] == "yabigdd@gmail.com" and row["verification_current"]
    assert not events.exists()
    assert db.execute("SELECT count(*) FROM owner_transport_test_claims").fetchone()[0] == 0


def test_exact_owner_action_has_one_durable_attempt_and_events(packet):
    db, row, events = packet
    client = OwnerSMTP()
    result = submit(packet, client)
    assert result["status"] == "ACCEPTED" and result["delivery_confirmed"] is False
    assert result["prospects_contacted"] == 0
    assert len(events.read_text().splitlines()) == 2
    with pytest.raises(ValueError, match="prior_owner_test"):
        submit(packet, client)
    assert client.events.count("submit") == 1


def test_wrong_content_hash_stops_before_credentials(packet):
    db, row, events = packet
    client = OwnerSMTP()
    with pytest.raises(ValueError, match="exact_owner_test_content"):
        owner.submit(
            db,
            row["id"],
            content_hash="0" * 64,
            actor="Synthetic Owner",
            password_loader=password,
            smtp_factory=client,
            event_store=events,
        )
    assert not client.events
    assert owner.preview(db, row["id"])["approved_hash"] is None


@pytest.mark.parametrize(
    "recipient",
    ["customer@example.com", "other@gmail.com", "yabigdd+alias@gmail.com", "YABIGDD@gmail.com"],
)
def test_owner_test_never_accepts_a_prospect_or_unverified_alias(recipient):
    db = sqlite3.connect(":memory:")
    calls = []
    with pytest.raises(ValueError, match="allowlisted"):
        owner.prepare(
            db, recipient, actor="Synthetic Owner", verifier=lambda value: calls.append(value)
        )
    assert calls == [] and db.total_changes == 0
    db.close()


@pytest.mark.parametrize(
    "error,status",
    [
        (TimeoutError("private provider error"), "UNKNOWN"),
        (smtplib.SMTPDataError(550, b"private provider error"), "REJECTED"),
    ],
)
def test_uncertain_or_rejected_owner_test_cannot_retry(packet, error, status):
    client = OwnerSMTP(send_error=error)
    result = submit(packet, client)
    assert result["status"] == status
    assert "private provider error" not in json.dumps(result)
    with pytest.raises(ValueError):
        submit(packet, client)
    assert client.events.count("submit") == 1


def test_expired_ownership_proof_blocks_before_credentials(packet, monkeypatch):
    db, row, events = packet
    client = OwnerSMTP()
    monkeypatch.setattr(core, "fresh", lambda *args: False)
    with pytest.raises(ValueError, match="fresh_authenticated"):
        submit(packet, client)
    assert not client.events


def test_owner_packet_body_and_recipient_are_immutable(packet):
    db, row, events = packet
    for sql in [
        "UPDATE owner_transport_test_packets SET recipient='other@gmail.com'",
        "UPDATE owner_transport_test_packets SET body='changed'",
    ]:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute(sql)
        db.rollback()
    assert owner.preview(db, row["id"])["content_hash"] == row["content_hash"]


def test_owner_and_prospect_paths_share_one_daily_cap(packet):
    db, row, events = packet
    submit(packet, OwnerSMTP())
    envelope = engine.prepare(99, "synthetic@example.com", "Subject: Review\n\nSynthetic")
    with pytest.raises(ValueError, match="daily_cap"):
        engine._reserve(db, 99, envelope, 1)


def test_reserved_prospect_claim_blocks_owner_test(packet):
    db, row, events = packet
    client = OwnerSMTP()
    envelope = engine.prepare(99, "synthetic@example.com", "Subject: Review\n\nSynthetic")
    engine._reserve(db, 99, envelope, 1)
    with pytest.raises(ValueError, match="daily_cap"):
        submit(packet, client)
    assert not client.events


def test_environment_stop_blocks_owner_test_before_credentials(packet, monkeypatch):
    monkeypatch.setenv("MM_EXTERNAL_SEND_DISABLED", "1")
    client = OwnerSMTP()
    with pytest.raises(ValueError, match="disabled"):
        submit(packet, client)
    assert not client.events


def test_failed_owner_result_persistence_retains_claim_and_blocks_replay(packet):
    db, row, events = packet

    class Broken:
        def __getattr__(self, name):
            return getattr(db, name)

        def execute(self, sql, args=()):
            if sql.startswith("UPDATE owner_transport_test_claims"):
                raise sqlite3.OperationalError("synthetic persistence failure")
            return db.execute(sql, args)

    client = OwnerSMTP()
    with pytest.raises(sqlite3.OperationalError):
        owner.submit(
            Broken(),
            row["id"],
            content_hash=row["content_hash"],
            actor="Synthetic Owner",
            password_loader=password,
            smtp_factory=client,
            event_store=events,
        )
    assert not db.in_transaction
    assert db.execute("SELECT status FROM owner_transport_test_claims").fetchone()[0] == "RESERVED"
    with pytest.raises(ValueError):
        submit(packet, client)
    assert client.events.count("submit") == 1


def test_owner_test_accounting_never_reports_zero_after_acceptance_or_ambiguity(tmp_path):
    import mm_runtime_guards as guards

    (tmp_path / "database").mkdir()
    path = tmp_path / "database/money_machine.db"
    with sqlite3.connect(path) as db:
        db.executescript("""CREATE TABLE mm_model_invocations(cost_usd REAL);
         CREATE TABLE mm_messages(id INTEGER,sent_at TEXT,send_receipt TEXT);
         CREATE TABLE mm_proposals(sent_at TEXT,send_receipt TEXT);
         CREATE TABLE owner_transport_test_claims(status TEXT);
         INSERT INTO owner_transport_test_claims VALUES('ACCEPTED');""")
    result = guards.accounting_snapshot(tmp_path)
    assert result["status"] == "measured" and result["external_sends"] == 1
    with sqlite3.connect(path) as db:
        db.execute("UPDATE owner_transport_test_claims SET status='UNKNOWN'")
    result = guards.accounting_snapshot(tmp_path)
    assert result["status"] == "unknown" and result["external_sends"] is None


def test_new_packet_cannot_bypass_prior_uncertain_owner_claim(packet):
    db, row, events = packet
    submit(packet, OwnerSMTP(send_error=TimeoutError("synthetic timeout")))
    newer = owner.prepare(
        db,
        recipient="yabigdd@gmail.com",
        actor="Synthetic Owner",
        verifier=lambda account: row["verification"],
    )
    client = OwnerSMTP()
    with pytest.raises(ValueError):
        owner.submit(
            db,
            newer["id"],
            content_hash=newer["content_hash"],
            actor="Synthetic Owner",
            password_loader=password,
            smtp_factory=client,
            event_store=events,
        )
    assert not client.events

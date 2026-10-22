"""Offline security and replay tests for the read-only Gmail replacement bridge."""
import importlib.util
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1] / "integrations/catalyx_gmail_bridge.py"
    spec = importlib.util.spec_from_file_location("bridge_under_test", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "CONFIG", tmp_path / "config/bridge.json")
    monkeypatch.setattr(module, "STATE", tmp_path / "state")
    module.install()
    return module


def headers(mid="<reply@example.test>", sender="client@example.test", refs="<sent@example.test>"):
    return f"Message-ID: {mid}\r\nFrom: {sender}\r\nIn-Reply-To: {refs}\r\n\r\n".encode()


def test_private_config_and_fixed_policy(bridge):
    assert bridge.CONFIG.stat().st_mode & 0o777 == 0o600
    assert bridge.STATE.stat().st_mode & 0o777 == 0o700
    doc = json.loads(bridge.CONFIG.read_text())
    doc["smtp"]["host"] = "attacker.example"
    bridge.CONFIG.write_text(json.dumps(doc))
    with pytest.raises(ValueError):
        bridge.config()


def test_store_rejects_symlink(bridge, tmp_path):
    target = bridge.STATE / "headers.sqlite3"
    target.unlink()
    other = tmp_path / "other"
    other.write_text("preserve")
    target.symlink_to(other)
    with pytest.raises(ValueError):
        with bridge.store():
            pass
    assert other.read_text() == "preserve"


def test_replay_cross_account_uidvalidity_and_collision(bridge):
    with bridge.store() as db, db:
        assert bridge.ingest(db, bridge.ACCOUNTS[0], "100", 1, headers()) == 1
        assert bridge.ingest(db, bridge.ACCOUNTS[0], "100", 1, headers()) == 0
        assert bridge.ingest(db, bridge.ACCOUNTS[0], "101", 2, headers()) == 0
        assert bridge.ingest(db, bridge.ACCOUNTS[1], "100", 1, headers()) == 1
        assert bridge.ingest(db, bridge.ACCOUNTS[0], "101", 3, headers(sender="other@example.test")) == 1
        assert db.execute("SELECT COUNT(*) FROM headers").fetchone()[0] == 3
        assert db.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 4


def test_missing_ids_do_not_collapse_and_size_is_bounded(bridge):
    with bridge.store() as db, db:
        assert bridge.ingest(db, bridge.ACCOUNTS[0], "1", 1, b"From: a@test\r\n\r\n") == 1
        assert bridge.ingest(db, bridge.ACCOUNTS[0], "1", 2, b"From: a@test\r\n\r\n") == 1
    with pytest.raises(ValueError):
        bridge.header_data(b"x" * 65537, "1", 3)


def test_reply_matching_requires_exact_id_and_sender_and_human_review(bridge):
    receipts = [(1, "<sent@example.test>", "client@example.test")]
    assert bridge.reply_candidates(["<sent@example.test>"], "client@example.test", receipts)["status"] == "candidate"
    assert bridge.reply_candidates(["<sent@example.test>"], "spoof@example.test", receipts)["status"] == "unmatched"
    assert bridge.reply_candidates(["<unknown@example.test>"], "client@example.test", receipts)["status"] == "unmatched"
    receipts.append((2, "<sent@example.test>", "client@example.test"))
    result = bridge.reply_candidates(["<sent@example.test>"], "client@example.test", receipts)
    assert result["status"] == "ambiguous"
    assert result["human_review_required"] is True


def test_smtp_tls_before_login_no_send(bridge, monkeypatch):
    calls = []

    class SMTP:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ("smtp.gmail.com", 587, 20)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def ehlo(self):
            calls.append("ehlo")

        def starttls(self, context):
            assert context.check_hostname
            calls.append("tls")

        def login(self, *args):
            calls.append("login")

    monkeypatch.setattr(bridge.smtplib, "SMTP", SMTP)
    assert bridge.smtp_check("synthetic", bridge.ACCOUNTS[0]) == "authenticated_no_message_sent"
    assert calls == ["ehlo", "tls", "ehlo", "login"]


def test_tls_failure_never_authenticates(bridge, monkeypatch):
    class SMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def ehlo(self):
            pass

        def starttls(self, context):
            raise bridge.ssl.SSLError("synthetic")

        def login(self, *args):
            pytest.fail("Login before TLS")

    monkeypatch.setattr(bridge.smtplib, "SMTP", SMTP)
    with pytest.raises(bridge.ssl.SSLError):
        bridge.smtp_check("synthetic", bridge.ACCOUNTS[0])


class FakeIMAP:
    def __init__(self, uids=(1, 2), validity="100", fail_uid=None):
        self.uids, self.validity, self.fail_uid = uids, validity, fail_uid

    def select(self, folder, readonly):
        assert folder == "INBOX" and readonly is True
        return "OK", [b"2"]

    def response(self, kind):
        assert kind == "UIDVALIDITY"
        return kind, [self.validity.encode()]

    def uid(self, command, *args):
        if command == "search":
            return "OK", [b" ".join(str(x).encode() for x in self.uids)]
        assert command == "fetch" and "BODY.PEEK" in args[1]
        uids = list(map(int, args[0].split(",")))
        if self.fail_uid in uids:
            return "NO", []
        return "OK", [(f"1 (UID {uid} HEADER {{100}}".encode(), headers(mid=f"<r{uid}@test>"))
                      for uid in uids] + [b")"]

    def logout(self):
        pass


def wire_sync(bridge, monkeypatch, client):
    monkeypatch.setattr(bridge, "secret", lambda account: "synthetic")
    monkeypatch.setattr(bridge, "imap_connection", lambda *args: client)


def test_sync_replay_and_uidvalidity_reset(bridge, monkeypatch):
    client = FakeIMAP()
    wire_sync(bridge, monkeypatch, client)
    assert bridge.sync(bridge.ACCOUNTS[0])["inserted"] == 2
    assert bridge.sync(bridge.ACCOUNTS[0])["fetched"] == 0
    client.validity = "101"
    result = bridge.sync(bridge.ACCOUNTS[0])
    assert result["fetched"] == 2 and result["inserted"] == 0
    assert result["remote_mailbox_writes"] == 0


def test_failed_batch_rolls_back_headers_and_cursor(bridge, monkeypatch):
    wire_sync(bridge, monkeypatch, FakeIMAP(fail_uid=2))
    assert bridge.sync(bridge.ACCOUNTS[0])["status"] == "authentication_or_imap_protocol_failed"
    with bridge.store() as db:
        assert db.execute("SELECT COUNT(*) FROM headers").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM cursors").fetchone()[0] == 0


def test_recent_window_does_not_advance_history_cursor(bridge, monkeypatch):
    client = FakeIMAP(uids=(10, 11))
    wire_sync(bridge, monkeypatch, client)
    assert bridge.sync(bridge.ACCOUNTS[0], recent_days=30)["inserted"] == 2
    with bridge.store() as db:
        assert db.execute("SELECT folder FROM cursors").fetchall() == [("INBOX:recent30",)]
    client.uids = (1, 2)
    assert bridge.sync(bridge.ACCOUNTS[0])["inserted"] == 2


def test_wrong_fetch_uid_cannot_advance_cursor(bridge, monkeypatch):
    class WrongUID(FakeIMAP):
        def uid(self, command, *args):
            if command == "fetch":
                return "OK", [(b"1 (UID 99 HEADER {100}", headers())]
            return super().uid(command, *args)

    wire_sync(bridge, monkeypatch, WrongUID())
    assert bridge.sync(bridge.ACCOUNTS[0])["status"] == "local_configuration_or_keychain_error"
    with bridge.store() as db:
        assert db.execute("SELECT COUNT(*) FROM cursors").fetchone()[0] == 0


def test_missing_secret_prevents_network_and_redacts_errors(bridge, monkeypatch):
    def missing(account):
        raise LookupError("do not print this secret")

    monkeypatch.setattr(bridge, "secret", missing)
    monkeypatch.setattr(bridge, "imap_connection", lambda *args: pytest.fail("Network accessed"))
    assert bridge.check(bridge.ACCOUNTS[0])["imap"] == "replacement_app_password_required"
    assert bridge.sync(bridge.ACCOUNTS[0])["status"] == "replacement_app_password_required"
    assert "do not print" not in bridge.failure(RuntimeError("do not print this secret"))


def test_setup_never_puts_secret_in_argv_or_result(bridge, monkeypatch):
    saved = []

    def dialog(argv, **kwargs):
        assert "with hidden answer" in argv[2]
        assert kwargs["capture_output"] is True
        return SimpleNamespace(returncode=0, stdout="abcdefghijklmnop\n")

    monkeypatch.setattr(bridge.subprocess, "run", dialog)
    monkeypatch.setattr(bridge, "keychain", lambda: SimpleNamespace(set_password=lambda *args: saved.append(args)))
    result = bridge.setup(bridge.ACCOUNTS[0])
    assert result["saved"] is True
    assert saved == [(bridge.SERVICE, bridge.ACCOUNTS[0], "abcdefghijklmnop")]
    assert "abcdefghijklmnop" not in json.dumps(result)


def test_audit_does_not_modify_source(bridge, tmp_path):
    path = tmp_path / "auditor.sqlite3"
    with sqlite3.connect(path) as db:
        db.executescript('''CREATE TABLE mm_messages(id,send_receipt,sent_at,recipient,approved_hash,business_id);
        CREATE TABLE mm_receipts(id,external_id,kind,object_id,business_id,content_hash);
        INSERT INTO mm_messages VALUES(1,'2','today','client@example.test','proof',3);
        INSERT INTO mm_receipts VALUES(2,'<sent@example.test>','send',1,3,'proof');''')
    before = path.read_bytes()
    with bridge.store() as db, db:
        bridge.ingest(db, bridge.ACCOUNTS[0], "1", 1, headers())
    result = bridge.audit_links(path)
    assert result["counts"]["candidate"] == 1
    assert result["auditor_database_writes"] == 0
    assert path.read_bytes() == before


def test_launchd_is_template_only(bridge):
    result = bridge.launchd_template()
    assert result["loaded"] is False
    doc = bridge.plistlib.loads(Path(result["template"]).read_bytes())
    assert doc["ProgramArguments"][-3:] == ["sync", "--recent-days", "30"]
    assert doc["RunAtLoad"] is False

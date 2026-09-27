import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MM = ROOT / "money-machine"
if str(MM) not in sys.path:
    sys.path.insert(0, str(MM))


def load(name):
    spec = importlib.util.spec_from_file_location(name, MM / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


outcomes = load("mm_outcomes")
transport = load("mm_transport")
operator = load("mm_operator")


def db(path):
    d = sqlite3.connect(path)
    d.row_factory = sqlite3.Row
    d.executescript(
        """
        CREATE TABLE businesses(
          id INTEGER PRIMARY KEY,
          name TEXT NOT NULL,
          public_website TEXT,
          is_dummy INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE mm_events(
          id INTEGER PRIMARY KEY,
          event_at TEXT NOT NULL,
          action TEXT NOT NULL,
          business_id INTEGER,
          detail TEXT);
        INSERT INTO businesses(id,name,public_website,is_dummy)
          VALUES(1,'Fixture','https://fixture.example',0);
        """
    )
    return d


def test_outcome_tracking_is_evidence_backed_and_append_only(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "database").mkdir()
    monkeypatch.setenv("MM_ROOT", str(root))
    d = db(root / "database" / "money_machine.db")
    evidence = root / "evidence.txt"
    evidence.write_text("Customer replied yes", encoding="utf-8")
    digest = outcomes.core.sha(evidence.read_bytes())
    backup = outcomes.core.backup(root)

    result = outcomes.record(
        d,
        1,
        "REPLIED",
        evidence,
        digest,
        actor="human-fixture",
        note="Synthetic evidence",
        backup_path=backup,
    )
    d.commit()
    assert result["outcome"] == "REPLIED"
    assert result["automatic_learning_applied"] is False
    assert outcomes.summary(d)["by_outcome"]["REPLIED"] == 1

    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        d.execute("UPDATE prospect_outcomes SET outcome='WON' WHERE id=?", (result["id"],))
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        d.execute("DELETE FROM prospect_outcomes WHERE id=?", (result["id"],))
    d.close()


def test_outcome_rejects_missing_or_external_evidence(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "database").mkdir()
    monkeypatch.setenv("MM_ROOT", str(root))
    d = db(root / "database" / "money_machine.db")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    backup = outcomes.core.backup(root)
    with pytest.raises(ValueError, match="canonical workspace"):
        outcomes.record(
            d,
            1,
            "WON",
            outside,
            outcomes.core.sha(outside.read_bytes()),
            "human",
            backup_path=backup,
        )
    with pytest.raises(ValueError, match="Unknown outcome"):
        outcomes.record(d, 1, "MAGIC", root / "missing", "bad", "human", backup_path=backup)
    d.close()


def test_transport_is_schema_locked_disabled_and_network_free(tmp_path):
    status = transport.status()
    assert status["mode"] == "DRAFT_ONLY"
    assert status["enabled"] is False
    assert status["external_send_allowed"] is False
    assert status["network_send_implementation"] is False
    assert status["daily_cap"] == 0

    bad = tmp_path / "transport.json"
    doc = json.loads((MM / "config" / "transport.json").read_text())
    doc["enabled"] = True
    doc["external_send_allowed"] = True
    doc["provider"] = "smtp"
    bad.write_text(json.dumps(doc))
    with pytest.raises(ValueError):
        transport.load_config(bad)


def test_transport_packet_preflight_rejects_any_send_authority():
    safe = {
        "approval_status": "HUMAN_APPROVAL_REQUIRED",
        "send_enabled": False,
        "external_send_allowed": False,
        "outbound_sent": 0,
    }
    assert transport.preflight_packet(safe)["passed"] is True
    unsafe = dict(safe, send_enabled=True)
    result = transport.preflight_packet(unsafe)
    assert result["passed"] is False
    assert result["network_calls"] == 0


def test_outcome_summary_is_read_only_when_uninitialised(tmp_path):
    path = tmp_path / "empty.db"
    d = sqlite3.connect(path)
    d.row_factory = sqlite3.Row
    before = d.execute("SELECT count(*) FROM sqlite_master").fetchone()[0]
    result = outcomes.summary(d)
    after = d.execute("SELECT count(*) FROM sqlite_master").fetchone()[0]
    d.close()
    assert result["status"] == "uninitialised"
    assert result["total"] == 0
    assert before == after


def test_outcome_schema_migration_requires_verified_backup(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "database").mkdir()
    monkeypatch.setenv("MM_ROOT", str(root))
    d = db(root / "database" / "money_machine.db")

    with pytest.raises(ValueError, match="Verified backup required"):
        outcomes.migrate(d, root / "missing-backup")
    assert d.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='prospect_outcomes'"
    ).fetchone() is None

    original_backup = outcomes.core.backup

    def unavailable_backup():
        raise OSError("synthetic backup failure")

    monkeypatch.setattr(outcomes.core, "backup", unavailable_backup)
    with pytest.raises(OSError, match="synthetic backup failure"):
        outcomes.migrate(d)
    assert d.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='prospect_outcomes'"
    ).fetchone() is None
    monkeypatch.setattr(outcomes.core, "backup", original_backup)

    other_root = tmp_path / "other-repo"
    other_root.mkdir()
    (other_root / "database").mkdir()
    other_db = db(other_root / "database" / "money_machine.db")
    other_backup = outcomes.core.backup(other_root)
    with pytest.raises(ValueError, match="does not contain this outcome database"):
        outcomes.migrate(d, other_backup)
    other_db.close()

    backup = outcomes.core.backup(root)
    outcomes.migrate(d, backup)
    assert d.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='prospect_outcomes'"
    ).fetchone() is not None
    d.close()


def test_outcome_record_cli_backs_up_before_schema_change(tmp_path, monkeypatch, capsys):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "database").mkdir()
    monkeypatch.setenv("MM_ROOT", str(root))
    database_path = root / "database" / "money_machine.db"
    d = db(database_path)
    d.close()
    evidence = root / "reply.txt"
    evidence.write_text("Synthetic reply", encoding="utf-8")
    digest = outcomes.core.sha(evidence.read_bytes())
    backups = []
    real_backup = outcomes.core.backup

    def tracked_backup(_root=None):
        path = real_backup(root)
        backups.append(path)
        return path

    monkeypatch.setattr(outcomes.core, "backup", tracked_backup)
    result = operator.main(
        [
            "outcome-record",
            "1",
            "--outcome",
            "REPLIED",
            "--evidence",
            str(evidence),
            "--sha256",
            digest,
            "--actor",
            "synthetic-operator",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert result == 0
    assert len(backups) == 1
    assert output["outcome"] == "REPLIED"
    with sqlite3.connect(database_path) as d:
        assert d.execute("SELECT count(*) FROM prospect_outcomes").fetchone()[0] == 1

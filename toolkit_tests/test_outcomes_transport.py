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


def db(path):
    d = sqlite3.connect(path)
    d.row_factory = sqlite3.Row
    sql = (
        "CREATE TABLE businesses("
        "  id INTEGER PRIMARY KEY,"
        "  name TEXT NOT NULL,"
        "  public_website TEXT,"
        "  is_dummy INTEGER NOT NULL DEFAULT 0);"
        "CREATE TABLE mm_events("
        "  id INTEGER PRIMARY KEY,"
        "  event_at TEXT NOT NULL,"
        "  action TEXT NOT NULL,"
        "  business_id INTEGER,"
        "  detail TEXT);"
        "CREATE TABLE prospect_outcomes("
        "  id INTEGER PRIMARY KEY,"
        "  business_id INTEGER NOT NULL,"
        "  outcome TEXT NOT NULL,"
        "  observed_at TEXT NOT NULL,"
        "  actor TEXT NOT NULL,"
        "  evidence_path TEXT NOT NULL,"
        "  evidence_hash TEXT NOT NULL,"
        "  note TEXT NOT NULL DEFAULT '',"
        "  created_at TEXT NOT NULL);"
        "CREATE INDEX IF NOT EXISTS prospect_outcomes_business"
        "  ON prospect_outcomes(business_id, observed_at DESC);"
        "CREATE TRIGGER IF NOT EXISTS prospect_outcomes_no_update"
        "BEFORE UPDATE ON prospect_outcomes BEGIN"
        "  SELECT RAISE(ABORT,'prospect outcomes are append-only');"
        "END;"
        "CREATE TRIGGER IF NOT EXISTS prospect_outcomes_no_delete"
        "BEFORE DELETE ON prospect_outcomes BEGIN"
        "  SELECT RAISE(ABORT,'prospect outcomes are append-only');"
        "END;"
        "CREATE TABLE experience_ledger("
        "  id INTEGER PRIMARY KEY,"
        "  outcome TEXT NOT NULL,"
        "  actor TEXT NOT NULL,"
        "  observed_at TEXT NOT NULL,"
        "  business_id INTEGER NOT NULL,"
        "  evidence_hash TEXT NOT NULL,"
        "  created_at TEXT NOT NULL);"
        "CREATE INDEX IF NOT EXISTS experience_ledger_outcome_time"
        "  ON experience_ledger(outcome, observed_at DESC);"
        "CREATE INDEX IF NOT EXISTS experience_ledger_actor"
        "  ON experience_ledger(actor);"
        "CREATE TRIGGER IF NOT EXISTS experience_ledger_on_outcome"
        "AFTER INSERT ON prospect_outcomes BEGIN"
        "  INSERT INTO experience_ledger(outcome, actor, observed_at, business_id, evidence_hash, created_at)"
        "  SELECT NEW.outcome, NEW.actor, NEW.observed_at, NEW.business_id, NEW.evidence_hash, NEW.created_at;"
        "END;"
        "CREATE TRIGGER IF NOT EXISTS experience_ledger_no_update"
        "BEFORE UPDATE ON experience_ledger BEGIN"
        "  SELECT RAISE(ABORT,'experience ledger is append-only');"
        "END;"
        "CREATE TRIGGER IF NOT EXISTS experience_ledger_no_delete"
        "BEFORE DELETE ON experience_ledger BEGIN"
        "  SELECT RAISE(ABORT,'experience ledger is append-only');"
        "END;"
        "INSERT INTO businesses(id,name,public_website,is_dummy)"
        "  VALUES(1,'Fixture','https://fixture.example',0);"
    )
    d.executescript(sql)
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

    result = outcomes.record(
        d,
        1,
        "REPLIED",
        evidence,
        digest,
        actor="human-fixture",
        note="Synthetic evidence",
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
    with pytest.raises(ValueError, match="canonical workspace"):
        outcomes.record(d, 1, "WON", outside, outcomes.core.sha(outside.read_bytes()), "human")
    with pytest.raises(ValueError, match="Unknown outcome"):
        outcomes.record(d, 1, "MAGIC", root / "missing", "bad", "human")
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


def test_outcome_summary_includes_experience_ledger_metrics(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "database").mkdir()
    monkeypatch.setenv("MM_ROOT", str(root))
    d = db(root / "database" / "money_machine.db")
    evidence = root / "evidence.txt"
    evidence.write_text("Customer replied yes", encoding="utf-8")
    digest = outcomes.core.sha(evidence.read_bytes())

    r1 = outcomes.record(d, 1, "REPLIED", evidence, digest, actor="human-a", note="")
    d.commit()
    r2 = outcomes.record(d, 1, "PENDING", evidence, digest, actor="human-b", note="")
    d.commit()
    r3 = outcomes.record(d, 1, "REPLIED", evidence, digest, actor="human-a", note="")
    d.commit()
    assert len({r1["id"], r2["id"], r3["id"]}) == 3

    s = outcomes.summary(d)
    assert s["total"] == 3
    assert s["by_outcome"]["REPLIED"] == 2
    assert s["by_outcome"]["PENDING"] == 1
    assert s["by_actor"]["human-a"] == 2
    assert s["by_actor"]["human-b"] == 1
    assert len(s["outcome_trend"]) >= 2


def test_experience_ledger_mirror_is_append_only(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "database").mkdir()
    monkeypatch.setenv("MM_ROOT", str(root))
    d = db(root / "database" / "money_machine.db")
    evidence = root / "evidence.txt"
    evidence.write_text("mirror test", encoding="utf-8")
    digest = outcomes.core.sha(evidence.read_bytes())

    outcomes.record(d, 1, "WON", evidence, digest, actor="automation", note="")
    d.commit()

    row = d.execute(
        "SELECT * FROM experience_ledger WHERE outcome='WON'"
    ).fetchone()
    assert row is not None
    assert row["actor"] == "automation"

    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        d.execute(
            "UPDATE experience_ledger SET actor='x' WHERE id=?",
            (row["id"],),
        )
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        d.execute("DELETE FROM experience_ledger WHERE id=?", (row["id"],))
    d.close()

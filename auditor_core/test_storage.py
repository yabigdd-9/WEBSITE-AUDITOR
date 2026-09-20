import json
from pathlib import Path

from auditor_core.storage import AuditHistoryStore
from auditor_core.verification import compare_audits


FIXTURES = Path(__file__).with_name("fixtures")


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_sqlite_history_stores_audits_and_findings(tmp_path: Path):
    store = AuditHistoryStore(tmp_path / "history.sqlite3")
    before = load("audit_before.json")
    audit_id = store.save_audit(before)
    assert audit_id.startswith("audit_")
    assert store.count("example.co.nz") == 1
    latest = store.latest("example.co.nz")
    assert latest["domain"] == "example.co.nz"
    assert latest["_history_audit_id"] == audit_id


def test_sqlite_history_records_regressions(tmp_path: Path):
    store = AuditHistoryStore(tmp_path / "history.sqlite3")
    before = load("audit_after.json")
    after = load("audit_before.json")
    before_id = store.save_audit(before)
    after["timestamp"] = "2026-09-21T02:00:00+00:00"
    after_id = store.save_audit(after)
    report = compare_audits(before, after)
    store.record_verification("example.co.nz", before_id, after_id, report)
    regressions = store.recent_regressions("example.co.nz")
    assert len(regressions) == 1
    assert regressions[0]["introduced_count"] == 1

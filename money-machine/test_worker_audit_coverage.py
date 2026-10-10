"""Audit implementation gaps stop retry churn and keep their report evidence."""
import json
import sqlite3
import sys
from copy import deepcopy
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mm_pipeline as pipeline  # noqa: E402
import mm_workers as workers  # noqa: E402

from auditor_toolkit.models import UNIMPLEMENTED_STATIC_CHECKS, coverage_summary  # noqa: E402
from toolkit_tests.coverage_fixtures import with_current_coverage  # noqa: E402


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setenv("MM_ROOT", str(tmp_path))
    monkeypatch.setenv("MM_EXTERNAL_SEND_DISABLED", "1")
    monkeypatch.setenv("MM_DISABLE_MODELS", "1")
    monkeypatch.setattr(workers, "REPO", tmp_path)
    monkeypatch.setattr(pipeline, "log", lambda *a, **k: None)
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE businesses(id INTEGER PRIMARY KEY, name TEXT, public_website TEXT);
        CREATE TABLE mm_evidence(id INTEGER PRIMARY KEY, business_id INTEGER);
        INSERT INTO businesses VALUES(1, 'Synthetic fixture', 'https://fixture.example');
    """)
    pipeline.migrate(db)
    pipeline.enqueue(db, 1, state="AUDIT_PENDING")
    yield db
    db.close()


def report():
    result = with_current_coverage({
        "run_id": "synthetic-audit", "status": "complete", "profile": "static",
        "defects": [{"defect_key": "missing-title"}], "severity_score": 16,
        "health_score": 84,
        "artifacts": {"json": "/synthetic/audit/report.json"},
    })
    return result


def partial_report():
    result = report()
    result.update(status="partial", health_score=None)
    for name in UNIMPLEMENTED_STATIC_CHECKS:
        result["checks"][name].update(status="skipped", reason="Not implemented")
        result["evidence"].pop(name)
    result["coverage"] = coverage_summary(result["checks"])
    return result


def mock_audit(monkeypatch, returned, cached=None):
    monkeypatch.setattr("auditor_toolkit.storage.History.get_latest_valid_audit", lambda *a, **k: cached)
    calls = []

    def run(url, options):
        calls.append((url, options))
        return deepcopy(returned)

    monkeypatch.setattr("auditor_toolkit.pipeline.run_audit", run)
    return calls


def test_audit_gap_stops_at_review_without_attempts_or_repeat_audit(database, monkeypatch):
    returned = partial_report()
    calls = mock_audit(monkeypatch, returned)
    ledger = []
    monkeypatch.setattr(workers, "_record_intelligence_decision", lambda *a, **k: ledger.append((a, k)))
    worker = pipeline.Worker("synthetic-audit-worker", ("AUDIT_PENDING",), workers.audit_handler)
    assert worker.run_once(database) == 1
    item = pipeline.item(database, 1)
    assert item["state"] == "NEEDS_REVIEW"
    assert item["attempts"] == 0
    assert item["next_retry_at"] is None
    assert worker.run_once(database) == 0
    assert len(calls) == 1
    event = database.execute("SELECT * FROM pipeline_events WHERE to_state='NEEDS_REVIEW'").fetchone()
    evidence = json.loads(event["evidence"])
    assert set(evidence["missing_checks"]) == UNIMPLEMENTED_STATIC_CHECKS
    assert evidence["run_id"] == returned["run_id"]
    assert evidence["report_path"] == returned["artifacts"]["json"]
    assert evidence["external_sends"] == 0
    assert evidence["model_calls"] == 0
    assert ledger[0][0][2:4] == ("NEEDS_REVIEW", "AUDIT_COVERAGE_INCOMPLETE")
    assert ledger[0][1]["disposition"] == "REVIEW"


def test_fetch_failure_still_retries_when_implementation_gaps_present(database, monkeypatch):
    returned = partial_report()
    returned["checks"]["fetch"].update(status="error", reason="HTTP 503")
    returned["coverage"] = coverage_summary(returned["checks"])
    mock_audit(monkeypatch, returned)
    worker = pipeline.Worker("synthetic-audit-worker", ("AUDIT_PENDING",), workers.audit_handler)
    assert worker.run_once(database) == 0
    item = pipeline.item(database, 1)
    assert item["state"] == "AUDIT_PENDING"
    assert item["attempts"] == 1
    assert item["next_retry_at"]
    assert "fetch" in item["last_error"]
    assert database.execute("SELECT count(*) FROM pipeline_events WHERE to_state='NEEDS_REVIEW'").fetchone()[0] == 0


@pytest.mark.parametrize("check_name", ["browser", "headers", "tls"])
def test_required_execution_failure_retries_before_coverage_hold(database, monkeypatch, check_name):
    returned = partial_report()
    returned["checks"][check_name] = {
        "required": True, "status": "error", "reason": "temporary execution failure",
    }
    returned["coverage"] = coverage_summary(returned["checks"])
    mock_audit(monkeypatch, returned)
    worker = pipeline.Worker("synthetic-audit-worker", ("AUDIT_PENDING",), workers.audit_handler)
    assert worker.run_once(database) == 0
    item = pipeline.item(database, 1)
    assert item["state"] == "AUDIT_PENDING"
    assert item["attempts"] == 1
    assert item["next_retry_at"]
    assert check_name in item["last_error"]
    assert database.execute("SELECT count(*) FROM pipeline_events WHERE to_state='NEEDS_REVIEW'").fetchone()[0] == 0


def test_worker_refuses_legacy_cached_complete_label(database, monkeypatch):
    stale = report()
    stale["evidence"]["hreflang"]["check_version"] = "1"
    calls = mock_audit(monkeypatch, partial_report(), cached=stale)
    state, _, evidence = workers.audit_handler(database, pipeline.item(database, 1), None)
    assert state == "NEEDS_REVIEW"
    assert len(calls) == 1
    assert evidence["report_path"] == "/synthetic/audit/report.json"


def test_worker_reuses_current_complete_coverage(database, monkeypatch):
    calls = mock_audit(monkeypatch, partial_report(), cached=report())
    state, reason, evidence = workers.audit_handler(database, pipeline.item(database, 1), None)
    assert state == "AUDITED"
    assert "reused" in reason
    assert evidence["score"] == 16
    assert calls == []


def test_missing_required_check_in_claimed_complete_report_requires_review(database, monkeypatch):
    returned = report()
    returned["checks"].pop("language")
    returned["coverage"] = coverage_summary(returned["checks"])
    mock_audit(monkeypatch, returned)
    state, _, evidence = workers.audit_handler(database, pipeline.item(database, 1), None)
    assert state == "NEEDS_REVIEW"
    assert evidence["missing_checks"] == ["language"]


def test_runtime_exception_remains_retryable(database, monkeypatch):
    mock_audit(monkeypatch, report())
    monkeypatch.setattr("auditor_toolkit.pipeline.run_audit", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("temporary engine fault")))
    with pytest.raises(pipeline.RetryableError, match="temporary engine fault"):
        workers.audit_handler(database, pipeline.item(database, 1), None)

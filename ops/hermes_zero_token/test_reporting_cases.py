"""JUnit case accounting and local report dates using disposable fixtures."""

import importlib.util
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


def load(name):
    specification = importlib.util.spec_from_file_location(
        name, Path(__file__).with_name(name + ".py")
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


@pytest.fixture
def runner(tmp_path, monkeypatch):
    module = load("runner")
    monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(module, "AUDIT_LOG", tmp_path / "audit.jsonl")
    monkeypatch.setenv("HERMES_ZERO_TOKEN_DISABLE_ALL", "0")
    return module


def test_testing_worker_records_individual_cases_from_junit(runner, monkeypatch):
    def run(command, **kwargs):
        report = Path(next(argument.split("=", 1)[1] for argument in command
                           if argument.startswith("--junitxml=")))
        report.write_text(
            '<testsuites><testsuite><testcase/><testcase/>'
            '<testcase><failure/></testcase><testcase><error/></testcase>'
            '<testcase><skipped/></testcase></testsuite></testsuites>'
        )
        return SimpleNamespace(returncode=1, stdout="fixture output", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", run)
    assert runner.handle_worker("testing_worker") == 1
    record = json.loads(runner.AUDIT_LOG.read_text().splitlines()[-1])
    assert record["test_counts"] == {"passed": 2, "failed": 2, "skipped": 1}


def test_missing_junit_never_invents_passing_cases(runner, monkeypatch):
    monkeypatch.setattr(runner.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=2, stdout="collection error", stderr=""))
    assert runner.handle_worker("testing") == 2
    record = json.loads(runner.AUDIT_LOG.read_text().splitlines()[-1])
    assert record["test_counts"] is None


def test_testing_aliases_share_ownership(runner, monkeypatch):
    monkeypatch.setitem(runner.WORKER_MAP, "testing_worker", lambda: pytest.fail("overlap"))
    with runner._worker_lock("testing"):
        assert runner.handle_worker("testing_worker") == 75


def test_daily_report_uses_latest_cases_and_separate_run_counts(tmp_path, monkeypatch):
    module = load("daily_report")
    monkeypatch.setattr(module, "STATE_DIR", tmp_path)
    monkeypatch.setattr(module, "DB_PATH", tmp_path / "missing.db")
    records = [
        {"worker_id": "testing", "event": "complete", "status": "failed",
         "test_counts": {"passed": 100, "failed": 1, "skipped": 0}},
        {"worker_id": "testing_worker", "event": "complete", "status": "completed",
         "test_counts": {"passed": 12, "failed": 0, "skipped": 3}},
    ]
    (tmp_path / "audit.jsonl").write_text("\n".join(map(json.dumps, records)))
    metrics = module.collect_metrics()
    assert (metrics["test_passed"], metrics["test_failed"], metrics["test_skipped"]) == (12, 0, 3)
    assert (metrics["testing_runs_passed"], metrics["testing_runs_failed"]) == (1, 1)


def test_report_date_uses_auckland_day(tmp_path, monkeypatch):
    module = load("daily_report")

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 15, 19, 0, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(module, "datetime", FrozenDatetime)
    assert module._now_date() == "2026-10-16"


def test_blocked_zero_call_provider_is_not_counted_as_paid(tmp_path, monkeypatch):
    module = load("daily_report")
    database = tmp_path / "fixture.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            "CREATE TABLE mm_model_invocations(provider TEXT,model_calls INTEGER,cost_usd REAL);"
            "INSERT INTO mm_model_invocations VALUES('blocked-provider',0,0);"
        )
    monkeypatch.setattr(module, "DB_PATH", database)
    monkeypatch.setattr(module, "STATE_DIR", tmp_path)
    metrics = module.collect_metrics()
    assert metrics["paid_model_calls"] == 0
    assert metrics["host_model_calls"] == 0
    assert metrics["estimated_paid_cost_nzd"] is None

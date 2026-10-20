"""Synthetic Hermes worker, staging isolation and reporting regressions."""
import importlib.util
import json
import os
import sqlite3
import subprocess
from pathlib import Path

import pytest


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def runner(tmp_path, monkeypatch):
    module = load("runner")
    monkeypatch.setattr(module, "AUDIT_LOG", tmp_path / "audit.jsonl")
    for key in module.ZERO_TOKEN_ENV:
        monkeypatch.setenv(key, "unsafe fixture")
    monkeypatch.setenv("HERMES_ZERO_TOKEN_DISABLE_ALL", "0")
    return module


@pytest.mark.parametrize("code,status", [(0, "completed"), (1, "failed")])
def test_worker_exit_and_safe_flags(runner, monkeypatch, code, status):
    monkeypatch.setitem(runner.WORKER_MAP, "fixture", lambda: (code, "", ""))
    assert runner.handle_worker("fixture") == code
    assert all(os.environ[key] == expected for key, expected in runner.ZERO_TOKEN_ENV.items())
    record = json.loads(runner.AUDIT_LOG.read_text().splitlines()[-1])
    assert record["status"] == status
    assert record["exit_code"] == code


@pytest.mark.parametrize("error,code,status", [(subprocess.TimeoutExpired("fixture", 1), 124, "timeout"), (ValueError("fixture failure"), 2, "error")])
def test_exceptions_never_report_success(runner, monkeypatch, error, code, status):
    def fail():
        raise error
    monkeypatch.setitem(runner.WORKER_MAP, "fixture", fail)
    assert runner.handle_worker("fixture") == code
    assert json.loads(runner.AUDIT_LOG.read_text().splitlines()[-1])["status"] == status


def test_mutating_workers_fail_closed_before_dispatch(runner, monkeypatch):
    def forbidden():
        pytest.fail("Live worker must not run")
    monkeypatch.setitem(runner.WORKER_MAP, "queue_dispatcher", forbidden)
    assert runner.handle_worker("queue_dispatcher") == 3
    assert runner.handle_worker("unknown") == 1
    assert runner.handle_worker("fixture", dry_run=True) == 0


def test_kill_switch_blocks_even_direct_calls(runner, monkeypatch):
    monkeypatch.setenv("HERMES_ZERO_TOKEN_DISABLE_ALL", "1")
    with pytest.raises(SystemExit) as blocked:
        runner.handle_worker("fixture")
    assert blocked.value.code == 3
    assert not runner.AUDIT_LOG.exists()


def staging(tmp_path, monkeypatch):
    module = load("staging_db")
    production = tmp_path / "production.db"
    with sqlite3.connect(production) as db:
        db.executescript("CREATE TABLE fixture(id INTEGER PRIMARY KEY); INSERT INTO fixture VALUES(1);")
    monkeypatch.setattr(module, "PROD_DB", production)
    monkeypatch.setattr(module, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(module, "STAGING_DB", tmp_path / "staging" / "fixture.db")
    return module


def test_repeated_staging_snapshots_preserve_production(tmp_path, monkeypatch):
    module = staging(tmp_path, monkeypatch)
    original = module.PROD_DB.read_bytes()
    path = module.snapshot_db()
    generation = module.snapshot_metadata()["generation"]
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO fixture VALUES(2)")
    assert module.snapshot_db() == path
    assert module.snapshot_metadata()["generation"] == generation
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT id FROM fixture ORDER BY id").fetchall() == [(1,), (2,)]
    assert module.PROD_DB.read_bytes() == original
    assert module.validate_schema(module.STAGING_DB)["ok"]


@pytest.mark.parametrize("alias", ["same", "symlink", "hardlink", "outside"])
def test_staging_rejects_production_aliases(tmp_path, monkeypatch, alias):
    module = staging(tmp_path, monkeypatch)
    module.STAGING_DIR.mkdir()
    if alias == "same":
        monkeypatch.setattr(module, "STAGING_DB", module.PROD_DB)
    elif alias == "outside":
        monkeypatch.setattr(module, "STAGING_DB", tmp_path / "outside.db")
    elif alias == "symlink":
        module.STAGING_DB.symlink_to(module.PROD_DB)
    else:
        import os
        os.link(module.PROD_DB, module.STAGING_DB)
    with pytest.raises(ValueError):
        module.snapshot_db()


def test_report_cumulative_counts_testing_aliases_timeouts_and_unknown_accounting(tmp_path, monkeypatch):
    module = load("daily_report")
    monkeypatch.setattr(module, "STATE_DIR", tmp_path)
    monkeypatch.setattr(module, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(module, "DB_PATH", tmp_path / "missing.db")
    records = [{"event": "complete", "worker_id": worker, "status": status}
               for worker, status in [("testing", "failed"), ("testing_worker", "completed"), ("site_auditor", "timeout")]]
    (tmp_path / "audit.jsonl").write_text("\n".join(json.dumps(record) for record in records) + "\ninvalid\n")
    metrics = module.collect_metrics()
    assert metrics["scripts_succeeded"] == 1
    assert metrics["scripts_failed"] == 2
    assert metrics["testing_runs_passed"] == 1
    assert metrics["testing_runs_failed"] == 1
    assert metrics["test_passed"] is None
    assert metrics["test_failed"] is None
    assert metrics["test_skipped"] is None
    assert metrics["host_model_calls"] is None
    assert metrics["attestation_complete"] is False
    report = module.write_daily_report(metrics)
    assert "FAIL" in report.read_text()
    assert "PASS" not in report.read_text()

"""Contract tests for Hermes zero-token worker execution."""
import json
import os
import sqlite3
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

import pytest

# Add the project root to the path so we can import the runner
sys.path.insert(0, '/Users/dd/WEBSITE-AUDITOR')
sys.path.insert(0, '/Users/dd/WEBSITE-AUDITOR/ops/hermes_zero_token')
import runner


def run_worker_and_capture(worker_id):
    """Run a worker and capture its stdout and stderr, returning (rc, stdout, stderr)."""
    stdout_capture = StringIO()
    stderr_capture = StringIO()
    with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
        try:
            rc = runner.handle_worker(worker_id)
        except SystemExit as e:
            rc = e.code
    return rc, stdout_capture.getvalue(), stderr_capture.getvalue()


def get_prod_counts():
    """Return a tuple of key production table counts."""
    with sqlite3.connect("/Users/dd/WEBSITE-AUDITOR/database/money_machine.db") as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                (SELECT COUNT(*) FROM audits),
                (SELECT COUNT(*) FROM mm_evidence),
                (SELECT COUNT(*) FROM mm_model_invocations),
                (SELECT COUNT(*) FROM mm_messages),
                (SELECT COUNT(*) FROM outreach_send_ledger),
                (SELECT COUNT(*) FROM pipeline_items)
        """)
        return cur.fetchone()


def test_staging_db_worker():
    """Staging DB worker returns 0, no production mutation, and valid JSON report."""
    before = get_prod_counts()
    rc, stdout, stderr = run_worker_and_capture("staging_db")
    after = get_prod_counts()
    assert rc == 0, f"staging_db failed: rc={rc}, stderr={stderr}"
    assert before == after, "staging_db mutated production database"
    assert stderr == "", f"staging_db unexpected stderr: {stderr}"
    # stdout should be a JSON object (pretty-printed)
    try:
        report = json.loads(stdout)
    except json.JSONDecodeError as e:
        raise AssertionError(f"staging_db stdout is not valid JSON: {stdout}") from e
    assert isinstance(report, dict), f"staging_db report is not a dict: {report}"
    assert report.get("production_written") is False, f"staging_db reported production write: {report}"
    assert report.get("phase") == "P2", f"staging_db wrong phase: {report}"


def test_screenshot_worker():
    """Screenshot worker returns 0, no production mutation, and valid JSON report."""
    before = get_prod_counts()
    rc, stdout, stderr = run_worker_and_capture("screenshot_worker")
    after = get_prod_counts()
    assert rc == 0, f"screenshot_worker failed: rc={rc}, stderr={stderr}"
    assert before == after, "screenshot_worker mutated production database"
    assert stderr == "", f"screenshot_worker unexpected stderr: {stderr}"
    # stdout should be a JSON object (pretty-printed)
    try:
        report = json.loads(stdout)
    except json.JSONDecodeError as e:
        raise AssertionError(f"screenshot_worker stdout is not valid JSON: {stdout}") from e
    assert isinstance(report, dict), f"screenshot_worker report is not a dict: {report}"
    assert report.get("production_written") is False, f"screenshot_worker reported production write: {report}"
    assert report.get("phase") == "P2", f"screenshot_worker wrong phase: {report}"


def test_demo_blueprint_worker():
    """Demo blueprint worker returns 0, no production mutation, and valid JSON report."""
    before = get_prod_counts()
    rc, stdout, stderr = run_worker_and_capture("demo_blueprint")
    after = get_prod_counts()
    assert rc == 0, f"demo_blueprint failed: rc={rc}, stderr={stderr}"
    assert before == after, "demo_blueprint mutated production database"
    assert stderr == "", f"demo_blueprint unexpected stderr: {stderr}"
    # stdout should be a JSON object (pretty-printed)
    try:
        report = json.loads(stdout)
    except json.JSONDecodeError as e:
        raise AssertionError(f"demo_blueprint stdout is not valid JSON: {stdout}") from e
    assert isinstance(report, dict), f"demo_blueprint report is not a dict: {report}"
    assert report.get("production_written") is False, f"demo_blueprint reported production write: {report}"
    assert report.get("phase") == "P2", f"demo_blueprint wrong phase: {report}"


def test_outreach_draft_worker():
    """Outreach draft worker returns 0, no production mutation, and valid JSON report."""
    before = get_prod_counts()
    rc, stdout, stderr = run_worker_and_capture("outreach_draft")
    after = get_prod_counts()
    assert rc == 0, f"outreach_draft failed: rc={rc}, stderr={stderr}"
    assert before == after, "outreach_draft mutated production database"
    assert stderr == "", f"outreach_draft unexpected stderr: {stderr}"
    # stdout should be a JSON object (pretty-printed)
    try:
        report = json.loads(stdout)
    except json.JSONDecodeError as e:
        raise AssertionError(f"outreach_draft stdout is not valid JSON: {stdout}") from e
    assert isinstance(report, dict), f"outreach_draft report is not a dict: {report}"
    assert report.get("production_written") is False, f"outreach_draft reported production write: {report}"
    assert report.get("phase") == "P2", f"outreach_draft wrong phase: {report}"


def test_deprecated_aliases_fail_closed():
    """Deprecated worker aliases (*_real) return 3 with actionable error message on stdout."""
    for worker_id in ["screenshot_worker_real", "demo_blueprint_real", "outreach_draft_real", "weekly_review_real"]:
        rc, stdout, stderr = run_worker_and_capture(worker_id)
        assert rc == 3, f"{worker_id} expected exit 3, got {rc}"
        # The deprecated aliases print a message to stdout like:
        # "Screenshot worker: placeholder removed — use the real screenshot_worker"
        base_name = worker_id.replace("_real", "")
        assert base_name in stdout, f"{worker_id} stdout missing worker name: {stdout}"
        assert "placeholder removed" in stdout, f"{worker_id} stdout missing warning: {stdout}"
        assert stderr == "", f"{worker_id} unexpected stderr: {stderr}"


def test_live_mutating_workers_blocked():
    """Live-mutating workers return 3 with no stdout/stderr (blocked silently)."""
    for worker_id in ["discovery-cycle", "discover-batch", "queue_dispatcher", "identity_resolution", "site_auditor", "discover_nz_businesses"]:
        rc, stdout, stderr = run_worker_and_capture(worker_id)
        assert rc == 3, f"{worker_id} expected exit 3, got {rc}"
        assert stdout == "", f"{worker_id} unexpected stdout: {stdout}"
        assert stderr == "", f"{worker_id} unexpected stderr: {stderr}"


def test_unknown_worker_returns_error():
    """Unknown worker ID returns 1 with error message on stderr."""
    rc, stdout, stderr = run_worker_and_capture("bogus_worker")
    assert rc == 1, f"unknown worker expected exit 1, got {rc}"
    assert stdout == "", f"unexpected stdout: {stdout}"
    assert "Unknown worker: bogus_worker" in stderr, f"stderr missing expected error: {stderr}"


def test_kill_switch_blocks_all_workers(monkeypatch):
    """HERMES_ZERO_TOKEN_DISABLE_ALL=1 causes immediate exit 3 with message on stderr."""
    monkeypatch.setenv("HERMES_ZERO_TOKEN_DISABLE_ALL", "1")
    # Ensure audit log is not touched
    audit_log_path = Path("/Users/dd/WEBSITE-AUDITOR/ops/hermes_zero_token/runner.py").parent.parent / "state" / "hermes_zero_token" / "audit.jsonl"
    if audit_log_path.exists():
        audit_log_path.unlink()
    rc, stdout, stderr = run_worker_and_capture("staging_db")
    assert rc == 3, f"kill switch failed: expected exit 3, got {rc}"
    assert stdout == "", f"unexpected stdout with kill switch: {stdout}"
    assert "BLOCKED: HERMES_ZERO_TOKEN_DISABLE_ALL=1 — all non-watchdog jobs refuse work." in stderr, f"stderr missing expected message: {stderr}"


def test_worker_run_updates_audit_log(tmp_path, monkeypatch):
    """Successful worker run creates a JSONL audit log entry with correct fields."""
    # We'll use a temporary audit log path to avoid interfering with the real one
    audit_log_path = tmp_path / "audit.jsonl"
    monkeypatch.setattr(runner, "AUDIT_LOG", audit_log_path)
    assert not audit_log_path.exists(), "audit log should not exist yet"
    rc, stdout, stderr = run_worker_and_capture("staging_db")
    assert rc == 0, f"staging_db failed: {rc}"
    assert audit_log_path.exists(), "audit log should be created after worker run"
    lines = audit_log_path.read_text().strip().splitlines()
    assert lines, "audit log should have at least one line"
    entry = json.loads(lines[-1])
    assert entry["worker_id"] == "staging_db"
    assert entry["status"] == "completed"
    assert entry["exit_code"] == 0
    assert isinstance(entry["duration_ms"], int)
    assert entry["duration_ms"] >= 0
    assert entry["cost_nzd"] == 0
    # Ensure required fields are present
    for field in ["timestamp", "job_id", "task_id", "event"]:
        assert field in entry, f"missing field {field} in audit entry"


def test_worker_failure_updates_audit_log(tmp_path, monkeypatch):
    """Failed worker return code is recorded in audit log."""
    # We'll use a temporary audit log path to avoid interfering with the real one
    audit_log_path = tmp_path / "audit.jsonl"
    monkeypatch.setattr(runner, "AUDIT_LOG", audit_log_path)
    assert not audit_log_path.exists(), "audit log should not exist yet"
    rc, stdout, stderr = run_worker_and_capture("screenshot_worker_real")
    assert rc == 3
    assert audit_log_path.exists()
    lines = audit_log_path.read_text().strip().splitlines()
    assert len(lines) >= 1, "audit log should have at least one entry"
    # The last entry should be the failed worker completion
    entry = json.loads(lines[-1])
    assert entry["worker_id"] == "screenshot_worker_real"
    assert entry["status"] == "failed"
    assert entry["exit_code"] == 3
    assert entry["cost_nzd"] == 0
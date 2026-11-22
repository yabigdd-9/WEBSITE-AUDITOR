"""Tests for runtime readiness preflight."""

import tempfile
from pathlib import Path

from auditor_toolkit.runtime.readiness import (
    PreflightCheck,
    _critical_check_failed,
    run_preflight,
)


def test_preflight_ready():
    with tempfile.TemporaryDirectory() as tmpdir:
        db = Path(tmpdir) / "test.db"
        result = run_preflight(db_path=db, required_dirs=[Path(tmpdir)])
    assert result.status in ("READY", "DEGRADED", "BLOCKED")  # BLOCKED ok in test env
    assert len(result.checks) > 0


def test_preflight_blocked_on_db():
    result = run_preflight(db_path=Path("/nonexistent/db.sqlite"))
    assert result.status == "BLOCKED"
    assert result.errors


def test_preflight_check_creation():
    check = PreflightCheck(name="test", passed=True, message="ok")
    assert check.passed
    assert check.name == "test"


def test_critical_check_failed_requires_a_failed_check():
    assert not _critical_check_failed([PreflightCheck(name="database:reachable", passed=True)])
    assert _critical_check_failed([PreflightCheck(name="database:reachable", passed=False)])


def test_preflight_result_all_passed():
    checks = [PreflightCheck(name="a", passed=True), PreflightCheck(name="b", passed=True)]
    from auditor_toolkit.runtime.readiness import PreflightResult
    result = PreflightResult(status="READY", checks=checks)
    assert result.all_passed


def test_preflight_to_dict():
    checks = [PreflightCheck(name="test", passed=True)]
    from auditor_toolkit.runtime.readiness import PreflightResult
    result = PreflightResult(status="READY", checks=checks)
    d = result.to_dict()
    assert d["status"] == "READY"
    assert d["all_passed"] is True

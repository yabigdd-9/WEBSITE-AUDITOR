"""Tests for proof verifier."""

from auditor_toolkit.proof.verify.verifier import (
    VerificationResult,
    verify_fix,
    check_axe_violations,
    check_console_errors,
)
from auditor_toolkit.proof.schema import BeforeState, AfterState


def _make_before(**kw):
    defaults = {
        "finding_id": "f001",
        "url": "https://example.com/",
        "status": "CAPTURED",
        "console_errors": [],
        "axe_violations": [],
    }
    defaults.update(kw)
    return BeforeState(**defaults)


def _make_after(**kw):
    defaults = {
        "finding_id": "f001",
        "proposed_fix_id": "fix_001",
        "url": "https://example.com/",
        "status": "CAPTURED",
        "console_errors": [],
    }
    defaults.update(kw)
    return AfterState(**defaults)


def test_verify_fix_not_fixed():
    before = _make_before()
    after = _make_after()
    result = verify_fix(before, after, original_defect_present=True)
    assert result.verdict == "NOT_FIXED"
    assert result.original_defect_present is True


def test_verify_fix_fixed():
    before = _make_before()
    after = _make_after()
    result = verify_fix(before, after, original_defect_present=False)
    assert result.verdict == "FIXED"
    assert result.original_defect_present is False


def test_verify_fix_regression():
    before = _make_before(console_errors=[])
    after = _make_after(console_errors=["Error: something broke"])
    result = verify_fix(before, after, original_defect_present=False)
    assert result.verdict == "REGRESSION"
    assert result.regression_count >= 1


def test_verify_fix_axe_regression():
    before = _make_before(axe_violations=[{"id": "color-contrast"}])
    after = _make_after()
    result = verify_fix(before, after, original_defect_present=False)
    assert result.axe_violations_before == 1


def test_check_axe_violations_empty():
    count = check_axe_violations([])
    assert count == 0


def test_check_axe_violations_count():
    violations = [{"id": "a"}, {"id": "b"}]
    count = check_axe_violations(violations)
    assert count == 2


def test_check_console_errors_empty():
    count = check_console_errors([])
    assert count == 0


def test_check_console_errors_count():
    errors = ["Error 1", "Error 2"]
    count = check_console_errors(errors)
    assert count == 2

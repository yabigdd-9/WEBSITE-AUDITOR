import json
from pathlib import Path

from auditor_core.verification import compare_audits


FIXTURES = Path(__file__).with_name("fixtures")


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_before_after_verification_uses_stable_check_ids():
    report = compare_audits(load("audit_before.json"), load("audit_after.json"))
    assert report["resolved_check_ids"] == ["seo.h1_missing"]
    assert report["remaining_check_ids"] == ["security.hsts_missing"]
    assert report["introduced_check_ids"] == []
    assert report["health_score"]["delta"] == 6.0
    assert report["verification_passed"] is True


def test_new_regression_fails_verification():
    before = load("audit_before.json")
    after = load("audit_after.json")
    after["findings"].append(
        {"check_id": "seo.title_missing", "message": "Missing title", "category": "seo"}
    )
    report = compare_audits(before, after)
    assert report["introduced_check_ids"] == ["seo.title_missing"]
    assert report["verification_passed"] is False

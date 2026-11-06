"""Explicit synthetic complete coverage for cache and history contract tests.

Real audits remain partial while placeholder analyzers are unimplemented.
These records model fully observed checks without claiming that a stub ran.
"""
from copy import deepcopy

from auditor_toolkit.models import REGISTRY, SCHEMA_VERSION, coverage_summary, required_check_ids


def with_current_coverage(report, browser=False):
    report = deepcopy(report)
    report.update(schema_version=SCHEMA_VERSION, browser_requested=browser)
    report.setdefault("profile", "rendered" if browser else "static")
    report.setdefault("checks", {})
    report.setdefault("evidence", {})
    for name in required_check_ids(browser):
        report["checks"][name] = {"required": True, "status": "ok"}
        report["evidence"][name] = {
            "url": report.get("url", "https://fixture.example"),
            "observed_at": report.get("timestamp", "2026-10-08T00:00:00+00:00"),
            "mode": REGISTRY[name].mode,
            "check_version": REGISTRY[name].version,
            "data": {"synthetic_complete_observation": True},
        }
    report["coverage"] = coverage_summary(report["checks"])
    return report

"""Required analyzers must have observations before audit health is available."""
import json
import socket
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from auditor_toolkit.common import Fetcher
from auditor_toolkit.models import (
    REGISTRY,
    UNIMPLEMENTED_RENDERED_CHECKS,
    UNIMPLEMENTED_STATIC_CHECKS,
    coverage_summary,
    current_coverage_gaps,
    has_current_complete_coverage,
    required_check_ids,
)
from auditor_toolkit.pipeline import AuditOptions, run_audit
from auditor_toolkit.storage import History
from toolkit_tests.coverage_fixtures import with_current_coverage


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [
        (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 443)),
    ])


def audit(root, status=200, **options):
    transport = httpx.MockTransport(lambda request: httpx.Response(
        status, text="<title>Fixture</title><img src='/x.png'>", request=request,
    ))
    client = Fetcher(transport=transport, min_interval=0)
    try:
        return run_audit("https://example.com/", AuditOptions(output_root=root, **options), client)
    finally:
        client.close()


def complete_report(run_id="complete", **changes):
    record = {
        "run_id": run_id,
        "url": "https://example.com/",
        "timestamp": datetime.now(UTC).isoformat(),
        "status": "complete",
        "profile": "static",
        "defects": [],
    }
    record.update(changes)
    return with_current_coverage(record)


def assert_artifacts_preserved(report):
    for kind in ("json", "html", "trend", "actions"):
        assert Path(report["artifacts"][kind]).is_file()
    stored = json.loads(Path(report["artifacts"]["json"]).read_text())
    assert stored["coverage"] == report["coverage"]
    assert stored["defects"] == report["defects"]


def test_static_audit_skips_unimplemented_required_analyzers(tmp_path):
    report = audit(tmp_path)
    assert report["status"] == "partial"
    assert report["health_score"] is None
    assert report["severity_score"] > 0
    assert report["defect_count"] == len(report["defects"])
    assert set(report["coverage"]["missing_checks"]) == UNIMPLEMENTED_STATIC_CHECKS
    assert set(current_coverage_gaps(report)) == UNIMPLEMENTED_STATIC_CHECKS
    for name in UNIMPLEMENTED_STATIC_CHECKS:
        assert report["checks"][name] == {
            "status": "skipped", "reason": "Not implemented", "required": True,
        }
        assert name not in report["evidence"]
        assert REGISTRY[name].version == "2"
    for category in ("seo", "technical", "performance"):
        assert report["category_scores"][category]["health_score"] is None
    assert_artifacts_preserved(report)


def test_browser_disabled_rendered_checks_are_explicit_and_optional(tmp_path):
    report = audit(tmp_path, browser=False)
    assert report["browser_requested"] is False
    for name in UNIMPLEMENTED_RENDERED_CHECKS | {"browser", "axe", "pdf"}:
        assert report["checks"][name]["status"] == "skipped"
        assert report["checks"][name]["required"] is False
        assert report["checks"][name]["reason"]


def test_rendered_audit_retains_browser_findings_and_artifacts(tmp_path, monkeypatch):
    def browser(url, artifact_root, **options):
        artifact_root.mkdir(parents=True)
        screenshot = artifact_root / "screenshot.png"
        screenshot.write_bytes(b"synthetic screenshot")
        return {"status": "ok", "evidence": {
            "screenshot": str(screenshot),
            "axe": {"version": "fixture", "violations": []},
            "images": [{"loaded": False, "src": "/broken.png"}],
        }}

    monkeypatch.setattr("auditor_toolkit.pipeline.run_browser_checks", browser)
    monkeypatch.setattr("auditor_toolkit.pipeline.export_pdf", lambda html, pdf, opts: pdf.write_bytes(b"%PDF fixture"))
    report = audit(tmp_path, profile="rendered")
    assert report["status"] == "partial"
    assert report["health_score"] is None
    assert report["browser_requested"] is True
    missing = UNIMPLEMENTED_STATIC_CHECKS | UNIMPLEMENTED_RENDERED_CHECKS
    assert set(report["coverage"]["missing_checks"]) == missing
    assert set(current_coverage_gaps(report)) == missing
    for name in UNIMPLEMENTED_RENDERED_CHECKS:
        assert report["checks"][name]["reason"] == "Not implemented"
        assert report["checks"][name]["required"] is True
    for name in ("browser", "axe", "pdf"):
        assert report["checks"][name]["status"] == "ok"
        assert report["checks"][name]["required"] is True
    assert "broken-rendered-image" in {defect["defect_key"] for defect in report["defects"]}
    assert Path(report["artifacts"]["screenshot"]).is_file()
    assert Path(report["artifacts"]["pdf"]).read_bytes().startswith(b"%PDF")
    assert report["category_scores"]["privacy"]["health_score"] is None
    assert_artifacts_preserved(report)


@pytest.fixture
def rendered_diff_tools(monkeypatch):
    captures = []
    diff_calls = []

    def browser(url, artifact_root, **options):
        artifact_root.mkdir(parents=True)
        paths = {}
        for name in ("screenshot", "mobile_screenshot"):
            path = artifact_root / (name + ".png")
            path.write_bytes(f"synthetic-{name}-{len(captures)}".encode())
            paths[name] = str(path)
        captures.append(paths)
        return {"status": "ok", "evidence": {
            **paths, "axe": {"version": "fixture", "violations": []}, "images": [],
        }}

    def diff(command, **options):
        assert command[0] == "odiff"
        assert Path(command[-3]).is_file()
        assert Path(command[-2]).is_file()
        diff_calls.append(command)
        Path(command[-1]).write_bytes(b"synthetic visual diff")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("auditor_toolkit.pipeline.run_browser_checks", browser)
    monkeypatch.setattr("auditor_toolkit.pipeline.export_pdf", lambda html, pdf, opts: pdf.write_bytes(b"%PDF fixture"))
    monkeypatch.setattr("subprocess.run", diff)
    return captures, diff_calls


def test_screenshot_diffs_use_successful_partial_rendered_baseline(tmp_path, rendered_diff_tools):
    captures, diff_calls = rendered_diff_tools
    baseline = audit(tmp_path, profile="rendered", screenshot_diff=True)
    current = audit(tmp_path, profile="rendered", screenshot_diff=True)
    assert baseline["status"] == "partial"
    assert current["status"] == "partial"
    assert current["health_score"] is None
    assert len(diff_calls) == 2
    for index, name in enumerate(("screenshot", "mobile_screenshot")):
        assert diff_calls[index][-3] == captures[0][name]
        assert diff_calls[index][-2] == captures[1][name]
        artifact = Path(current["artifacts"][name + "_diff"])
        assert artifact.read_bytes() == b"synthetic visual diff"
        assert History(tmp_path).artifact(current["run_id"], name + "_diff") == artifact
    assert current["comparison"]["resolution_assessed"] is False


@pytest.mark.parametrize("damage", ["failed_browser", "other_url", "missing_artifact"])
def test_screenshot_diff_rejects_unusable_partial_baseline(tmp_path, rendered_diff_tools, damage):
    _, diff_calls = rendered_diff_tools
    baseline = audit(tmp_path, profile="rendered", screenshot_diff=True)
    history = History(tmp_path)
    if damage == "failed_browser":
        baseline["checks"]["browser"]["status"] = "error"
    elif damage == "other_url":
        # Keep the requested host in the other URL's path so the broad LIKE
        # history lookup still returns it and the exact URL guard is exercised.
        baseline["url"] = "https://other.test/https://example.com/"
    else:
        for name in ("screenshot", "mobile_screenshot"):
            Path(baseline["artifacts"][name]).unlink()
    with history.connect() as db:
        db.execute("UPDATE runs SET report=?,url=? WHERE id=?", (
            json.dumps(baseline), baseline["url"], baseline["run_id"],
        ))
    current = audit(tmp_path, profile="rendered", screenshot_diff=True)
    assert diff_calls == []
    assert "screenshot_diff" not in current["artifacts"]
    assert "mobile_screenshot_diff" not in current["artifacts"]
    assert current["status"] == "partial"


def test_screenshot_diff_uses_older_valid_capture_after_missing_artifact(tmp_path, rendered_diff_tools):
    captures, diff_calls = rendered_diff_tools
    baseline = audit(tmp_path, profile="rendered")
    missing = audit(tmp_path, profile="rendered")
    for name in ("screenshot", "mobile_screenshot"):
        Path(missing["artifacts"][name]).unlink()
    current = audit(tmp_path, profile="rendered", screenshot_diff=True)
    assert len(diff_calls) == 2
    assert diff_calls[0][-3] == captures[0]["screenshot"]
    assert diff_calls[1][-3] == captures[0]["mobile_screenshot"]
    assert current["status"] == "partial"
    assert baseline["checks"]["browser"]["status"] == "ok"


@pytest.mark.parametrize("browser", [False, True])
def test_failed_fetch_lists_every_required_check(tmp_path, monkeypatch, browser):
    monkeypatch.setattr("auditor_toolkit.pipeline.run_browser_checks", lambda *a, **k: pytest.fail("rendering an unavailable page"))
    monkeypatch.setattr("auditor_toolkit.pipeline.export_pdf", lambda html, pdf, opts: pdf.write_bytes(b"%PDF fixture"))
    report = audit(tmp_path, status=503, browser=browser)
    assert report["status"] == "partial"
    assert report["health_score"] is None
    assert report["checks"]["fetch"]["status"] == "error"
    assert required_check_ids(browser) <= set(report["checks"])
    for name in required_check_ids(browser) - {"fetch", "pdf"} - UNIMPLEMENTED_STATIC_CHECKS - UNIMPLEMENTED_RENDERED_CHECKS:
        assert report["checks"][name]["reason"] == "Fetch unavailable"
        assert report["checks"][name]["required"] is True
    assert_artifacts_preserved(report)


@pytest.mark.parametrize("damage", ["missing_checks", "old_version", "missing_evidence", "old_coverage", "false_required", "missing_metadata", "malformed_checks", "malformed_evidence"])
def test_cached_complete_reports_need_current_coverage(tmp_path, damage):
    history = History(tmp_path)
    report = complete_report()
    if damage == "missing_checks":
        report["checks"].pop("hreflang")
        report["coverage"] = coverage_summary(report["checks"])
    elif damage == "old_version":
        report["evidence"]["hreflang"]["check_version"] = "1"
    elif damage == "missing_evidence":
        report["evidence"].pop("language")
    elif damage == "old_coverage":
        report["coverage"]["version"] = 0
    elif damage == "false_required":
        report["checks"]["images"]["required"] = False
        report["coverage"] = coverage_summary(report["checks"])
    elif damage == "malformed_checks":
        report["checks"] = []
    elif damage == "malformed_evidence":
        report["evidence"]["hreflang"] = "legacy placeholder"
    else:
        report.pop("coverage")
        report.pop("schema_version")
    history.save(report)
    assert history.get_latest_valid_audit("example.com") is None
    assert not has_current_complete_coverage(report)
    assert history.get(report["run_id"]) == report


def test_cache_finds_current_complete_report_below_newer_stale_record(tmp_path):
    history = History(tmp_path)
    current = complete_report("current", timestamp=(datetime.now(UTC) - timedelta(hours=1)).isoformat())
    outdated = deepcopy(current)
    outdated.update(run_id="outdated", timestamp=datetime.now(UTC).isoformat())
    outdated["evidence"]["hreflang"]["check_version"] = "1"
    history.save(current)
    history.save(outdated)
    assert history.get_latest_valid_audit("example.com") == current
    assert has_current_complete_coverage(current)


@pytest.mark.parametrize("url", [
    "https://siblingexample.com/", "https://example.com.evil.test/",
    "https://other.test/example.com/report", "https://example.com:8443/",
])
def test_cache_domain_matching_rejects_substrings_and_other_ports(tmp_path, url):
    history = History(tmp_path)
    history.save(complete_report(url=url))
    assert history.get_latest_valid_audit("example.com") is None


def test_cache_domain_match_is_case_insensitive_and_retains_ports(tmp_path):
    history = History(tmp_path)
    report = complete_report(url="https://EXAMPLE.COM:8443/")
    history.save(report)
    assert history.get_latest_valid_audit("example.com:8443") == report


def test_rendered_request_requires_rendered_coverage_even_with_static_profile():
    report = complete_report()
    report["browser_requested"] = True
    assert set(current_coverage_gaps(report)) == required_check_ids(True) - required_check_ids(False)


def test_rendered_profile_cannot_disable_required_browser_coverage(tmp_path):
    report = complete_report(profile="rendered")
    assert report["browser_requested"] is False
    assert set(current_coverage_gaps(report)) == required_check_ids(True)
    assert not has_current_complete_coverage(report)
    history = History(tmp_path)
    history.save(report)
    assert history.get_latest_valid_audit("example.com") is None


def test_legacy_complete_report_cannot_verify_remediation(tmp_path):
    history = History(tmp_path)
    detected = complete_report("detected", timestamp="2026-10-01T00:00:00+00:00", defects=[
        {"finding_id": "finding-1"},
    ])
    legacy = complete_report("legacy-fixed", timestamp="2026-10-02T00:00:00+00:00")
    legacy.pop("coverage")
    legacy.pop("evidence")
    history.save(detected)
    history.save(legacy)
    with pytest.raises(ValueError, match="current coverage"):
        history.transition("finding-1", "verified", {"verification_run": legacy["run_id"]})
    assert history.get(legacy["run_id"]) == legacy
    with history.connect() as db:
        assert db.execute("SELECT state FROM remediations WHERE id='finding-1'").fetchone()[0] == "detected"
    current = complete_report("current-fixed", timestamp="2026-10-03T00:00:00+00:00")
    history.save(current)
    history.transition("finding-1", "verified", {"verification_run": current["run_id"]})
    with history.connect() as db:
        assert db.execute("SELECT state FROM remediations WHERE id='finding-1'").fetchone()[0] == "verified"


@pytest.mark.parametrize("current_valid,baseline_valid", [(True, True), (True, False), (False, True), (False, False)])
def test_resolution_requires_current_coverage_on_both_runs(tmp_path, current_valid, baseline_valid):
    history = History(tmp_path)
    baseline = complete_report("baseline", defects=[
        {"finding_id": "persistent"}, {"finding_id": "missing-now"},
    ])
    current = complete_report("current", defects=[
        {"finding_id": "persistent"}, {"finding_id": "new"},
    ])
    if not baseline_valid:
        baseline.pop("coverage")
    if not current_valid:
        current.pop("coverage")
    history.save(baseline)
    comparison = history.compare(current)
    assert comparison["baseline"] == "baseline"
    assert comparison["persistent"] == ["persistent"]
    assert comparison["new"] == ["new"]
    assert comparison["resolved"] == (["missing-now"] if current_valid and baseline_valid else [])
    assert comparison["resolution_assessed"] is (current_valid and baseline_valid)


def test_complete_label_cannot_override_required_skipped_check():
    report = complete_report()
    report["checks"]["hreflang"].update(status="skipped", reason="Not implemented")
    report["coverage"] = coverage_summary(report["checks"])
    assert current_coverage_gaps(report) == ["hreflang"]
    assert not has_current_complete_coverage(report)

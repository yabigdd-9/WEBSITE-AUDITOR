"""Explicitly authorized synthetic comparison/history and CLI regressions."""
import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree

import httpx
import pytest

from auditor_toolkit.comparison import (
    build_comparison,
    build_trend,
    measurement_contract,
    render_comparison_html,
    render_history_svg,
    write_comparison,
)
from auditor_toolkit.pipeline import AuditOptions
from auditor_toolkit.storage import History


def saved(run="target", health=84, url="https://example.test/", hour=0, profile="static"):
    return {
        "schema_version": 2, "run_id": run, "url": url, "profile": profile,
        "timestamp": (datetime(2026, 10, 3, tzinfo=UTC) + timedelta(hours=hour)).isoformat(),
        "status": "complete", "health_score": health, "defect_count": 1,
        "defects": [{"finding_id": "finding", "severity": "high", "evidence_ref": "page"}],
        "checks": {"fetch": {"status": "ok", "required": True},
                   "page": {"status": "ok", "required": True}},
        "check_registry": {"fetch": {"version": "1", "mode": "static", "category": "technical"},
                           "page": {"version": "1", "mode": "static", "category": "seo"}},
        "coverage": {"required": 2, "passed": 2},
        "scoring": {"method": "severity sum capped at 100; health = 100 - severity",
                    "weights": {"low": 4, "medium": 8, "high": 16, "critical": 30}},
        "measurement_contract": {"version": 1, "toolkit_source_sha256": "1" * 64,
            "limitation": "Matching recorded scope/source does not establish identical lab or field conditions.",
            "settings": {
                "profile": profile, "browser": False, "tls": False, "timeout": 8.0,
                "deep": False, "max_pages": 10, "max_depth": 2, "max_links": 50,
                "max_bytes": 2_000_000, "respect_robots": True, "cache": False,
                "external_tools": False, "allow_private": False, "screenshot_diff": False,
                "use_gotenberg": False,
            }},
        "evidence": {"page": {"data": {"captured": True}}},
    }


def test_comparison_differences_and_mean_preserve_inputs(tmp_path):
    reports = [saved(), saved("a", 92, "https://a.test/"), saved("b", 76, "https://b.test/")]
    before = copy.deepcopy(reports)
    result = write_comparison(reports, tmp_path / "comparison")
    doc = json.loads(Path(result["json"]).read_text())
    assert result["status"] == "comparable"
    assert [row["health_delta_from_target"] for row in doc["rows"]] == [0, 8, -8]
    assert doc["summary"]["mean_comparison_health"] == 84
    assert doc["summary"]["mean_health_delta_from_target"] == 0
    assert all(row["finding_count"] == 1 for row in doc["rows"])
    assert all(len(row["observation_sha256"]) == 64 for row in doc["rows"])
    assert reports == before
    assert "Recorded findings" in Path(result["html"]).read_text()
    with pytest.raises(FileExistsError):
        write_comparison(reports, tmp_path / "comparison")


@pytest.mark.parametrize("field,value", [
    ("status", "partial"), ("health_score", None), ("health_score", True),
    ("health_score", -1), ("health_score", 101), ("health_score", "84"),
    ("timestamp", "unknown"), ("timestamp", "2026-10-03T00:00:00"),
    ("checks", {}), ("check_registry", {}), ("coverage", {}),
    ("measurement_contract", {}), ("scoring", {}), ("schema_version", True),
    ("profile", None),
])
def test_unavailable_provenance_holds_delta_and_mean(field, value):
    other = saved("other", 92)
    other[field] = value
    doc = build_comparison([saved(), other])
    assert doc["status"] == "held"
    assert doc["rows"][1]["health_delta_from_target"] is None
    assert doc["rows"][1]["held_reasons"]
    assert doc["summary"]["mean_comparison_health"] is None


@pytest.mark.parametrize("field,value", [("status", "error"), ("status", "skipped"), ("required", "yes")])
def test_invalid_or_incomplete_check_holds(field, value):
    other = saved("other")
    other["checks"]["page"][field] = value
    assert build_comparison([saved(), other])["status"] == "held"


@pytest.mark.parametrize("mode", ["coverage", "registry", "method", "weight", "source", "scope", "schema", "optional"])
def test_basis_mismatch_does_not_claim_difference(mode):
    other = saved("other")
    if mode == "coverage":
        other["coverage"]["passed"] = 1
    elif mode == "registry":
        other["check_registry"]["page"]["version"] = "2"
    elif mode == "method":
        other["scoring"]["method"] = "a different method"
    elif mode == "weight":
        other["scoring"]["weights"]["high"] = 20
    elif mode == "source":
        other["measurement_contract"]["toolkit_source_sha256"] = "2" * 64
    elif mode == "scope":
        other["measurement_contract"]["settings"]["deep"] = True
    elif mode == "schema":
        other["schema_version"] = 3
    else:
        other["checks"]["extra"] = {"status": "skipped", "required": False}
        other["check_registry"]["extra"] = {"version": "1", "mode": "static", "category": "seo"}
    doc = build_comparison([saved(), other])
    assert not doc["rows"][1]["comparison_allowed"]
    assert doc["summary"]["mean_health_delta_from_target"] is None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_non_json_numbers_are_rejected(value):
    with pytest.raises(ValueError):
        build_comparison([saved(), saved("other", value)])


@pytest.mark.parametrize("reports", [[], [saved()], [saved(), saved()], [None, saved()], [saved(), {}]])
def test_missing_or_duplicate_identity_rejected(reports):
    with pytest.raises(ValueError):
        build_comparison(reports)


def test_no_cherry_picked_average_and_target_held():
    third = saved("third", 95)
    third["status"] = "partial"
    doc = build_comparison([saved(), saved("second", 90), third])
    assert doc["rows"][1]["health_delta_from_target"] == 6
    assert doc["summary"]["mean_comparison_health"] is None
    target = saved()
    target.pop("measurement_contract")
    assert all(not row["comparison_allowed"] for row in build_comparison([target, saved("other")])["rows"])


@pytest.mark.parametrize("mode", ["boolean_contract_version", "boolean_coverage", "boolean_rule_version",
                                  "boolean_method", "negative_weights", "boolean_scope", "boolean_timeout", "schema_zero"])
def test_identically_malformed_provenance_still_held(mode):
    reports = [saved(), saved("other")]
    for report in reports:
        if mode == "boolean_contract_version":
            report["measurement_contract"]["version"] = True
        elif mode == "boolean_coverage":
            report["checks"].pop("page")
            report["coverage"] = {"required": True, "passed": True}
        elif mode == "boolean_rule_version":
            report["check_registry"]["page"]["version"] = True
        elif mode == "boolean_method":
            report["scoring"]["method"] = True
        elif mode == "negative_weights":
            report["scoring"]["weights"]["high"] = -16
        elif mode == "boolean_scope":
            report["measurement_contract"]["settings"]["max_pages"] = True
        elif mode == "boolean_timeout":
            report["measurement_contract"]["settings"]["timeout"] = True
        else:
            report["schema_version"] = 0
    assert build_comparison(reports)["status"] == "held"


@pytest.mark.parametrize("url", ["", "mailto:person@example.test", "https://user:password@example.test/", "https://example.test/\n"])
def test_invalid_or_secret_bearing_site_identity_rejected(url):
    with pytest.raises(ValueError):
        build_comparison([saved(url=url), saved("other")])


def test_bound_comparison_and_html_escaping():
    with pytest.raises(ValueError):
        build_comparison([saved(str(n)) for n in range(101)])
    target = saved(url='https://example.test/<script>alert("x")</script>')
    target["run_id"] = '<img src=x onerror="alert(1)">'
    rendered = render_comparison_html(build_comparison([target, saved("other")]))
    assert "<script>" not in rendered and "<img " not in rendered
    assert "&lt;script&gt;" in rendered
    assert "<script" not in rendered and 'href="http' not in rendered


def test_measurement_contract_records_scope_without_price_or_output(tmp_path):
    first = AuditOptions(output_root=tmp_path / "one", hourly_rate_nzd=100, brand="One")
    second = AuditOptions(output_root=tmp_path / "two", hourly_rate_nzd=250, brand="Two", ai=True)
    assert measurement_contract(first) == measurement_contract(second)
    assert measurement_contract(AuditOptions(deep=True)) != measurement_contract(first)
    assert len(measurement_contract(first)["toolkit_source_sha256"]) == 64


def test_exact_history_selection_and_immutability(tmp_path):
    history = History(tmp_path)
    records = [saved("older", hour=0), saved("near", hour=1),
               saved("future", hour=3), saved("mobile", hour=1, url="https://m.example.test/"),
               saved("substring", hour=1, url="https://example.test.evil/"),
               saved("profile", hour=1, profile="rendered")]
    for item in records:
        history.save(item)
    current = saved("current", hour=2)
    history.save(current)
    before = {item["run_id"]: history.get(item["run_id"]) for item in records + [current]}
    assert [item["run_id"] for item in history.prior_observations(current)] == ["near", "older"]
    assert len(history.prior_observations(current, limit=1)) == 1
    assert before == {identity: history.get(identity) for identity in before}
    with pytest.raises(ValueError):
        history.prior_observations(current, limit=100)


def test_history_limit_and_stable_ties(tmp_path):
    history = History(tmp_path)
    for n in range(105):
        history.save(saved(f"old-{n:03}", hour=0))
    selected = history.prior_observations(saved("current", hour=1))
    assert len(selected) == 99
    assert selected[0]["run_id"] == "old-104" and selected[-1]["run_id"] == "old-006"


def test_trend_order_utc_axis_and_change(tmp_path):
    old = saved("old", 80, hour=0)
    middle = saved("middle", 88, hour=1)
    current = saved("current", 92, hour=3)
    trend = build_trend(current, [middle, old])
    assert [row["run_id"] for row in trend["points"]] == ["old", "middle", "current"]
    assert trend["summary"] == {"starting_health": 80, "current_health": 92, "health_change": 12, "change_assessed": True}
    raw = render_history_svg(trend)
    (tmp_path / "synthetic-trend.svg").write_text(raw)
    (tmp_path / "synthetic-trend.json").write_text(json.dumps(trend, indent=2))
    svg = ElementTree.fromstring(raw)
    circles = svg.findall("{http://www.w3.org/2000/svg}circle")
    assert [float(item.attrib["cx"]) for item in circles] == [50, 260, 680]


@pytest.mark.parametrize("mode", ["partial", "missing_contract", "changed_source"])
def test_held_middle_breaks_line_and_holds_aggregate(mode):
    middle = saved("middle", 95, hour=1)
    if mode == "partial":
        middle["status"] = "partial"
    elif mode == "missing_contract":
        middle.pop("measurement_contract")
    else:
        middle["measurement_contract"]["toolkit_source_sha256"] = "2" * 64
    trend = build_trend(saved("current", 92, hour=2), [saved("old", 80), middle])
    assert trend["points"][1]["plotted_health"] is None
    assert not trend["summary"]["change_assessed"]
    svg = ElementTree.fromstring(render_history_svg(trend))
    assert not [item for item in svg.findall("{http://www.w3.org/2000/svg}path") if item.attrib.get("stroke") == "#0f766e"]
    assert len(svg.findall("{http://www.w3.org/2000/svg}circle")) == 2


def test_partial_current_retains_valid_prior_series():
    current = saved("current", hour=2)
    current["status"] = "partial"
    trend = build_trend(current, [saved("old", 80), saved("near", 88, hour=1)])
    assert trend["basis_run_id"] == "near"
    assert [row["plotted_health"] for row in trend["points"]] == [80, 88, None]
    assert trend["summary"]["current_health"] is None and trend["summary"]["health_change"] is None


@pytest.mark.parametrize("mode", ["url", "profile", "duplicate", "limit"])
def test_trend_rejects_conflicting_inputs(mode):
    current = saved("current", hour=1)
    old = saved("old")
    if mode == "url":
        old["url"] = "https://different.test/"
    elif mode == "profile":
        old["profile"] = "rendered"
    elif mode == "duplicate":
        old["run_id"] = "current"
    with pytest.raises(ValueError):
        build_trend(current, [old] if mode != "limit" else [old] * 100)


def test_single_unknown_offset_and_hostile_chart():
    one = saved("<script>bad</script>")
    trend = build_trend(one, [])
    assert not trend["summary"]["change_assessed"]
    raw = render_history_svg(trend)
    assert "<script>" not in raw and "&lt;script&gt;" in raw
    assert "No change over time established" in raw
    missing = saved("missing")
    missing["timestamp"] = "unknown"
    assert len(build_trend(one, [missing])["points"]) == 2
    old = saved("offset")
    old["timestamp"] = "2026-10-03T13:00:00+13:00"
    assert build_trend(saved("current", hour=1), [old])["points"][0]["timestamp"] == old["timestamp"]


@pytest.mark.parametrize("location", ["health", "weight", "timeout"])
def test_huge_integer_metadata_is_held_without_overflow(location):
    reports = [saved(), saved("other")]
    for report in reports:
        value = 10 ** 400
        if location == "health":
            report["health_score"] = value
        elif location == "weight":
            report["scoring"]["weights"]["high"] = value
        else:
            report["measurement_contract"]["settings"]["timeout"] = value
    assert build_comparison(reports)["status"] == "held"


def test_newer_history_and_simultaneous_runs_cannot_claim_change():
    with pytest.raises(ValueError):
        build_trend(saved("current", hour=1), [saved("future", 92, hour=2)])
    simultaneous = build_trend(saved("current", 92), [saved("old", 80)])
    assert simultaneous["summary"]["health_change"] is None
    assert not simultaneous["summary"]["change_assessed"]


def with_findings(report, identities):
    report["defects"] = [{"finding_id": identity, "severity": "high", "evidence_ref": "page",
                          "defect": "Synthetic finding " + identity} for identity in identities]
    report["defect_count"] = len(report["defects"])
    return report


@pytest.mark.parametrize("mode", ["source", "scope", "weights", "rule", "missing_contract", "partial", "future", "self", "other_url", "other_profile"])
def test_finding_resolution_does_not_use_incompatible_history(tmp_path, mode):
    history = History(tmp_path)
    current = with_findings(saved("current", 100, hour=2), [])
    previous = with_findings(saved("previous", hour=1), ["removed"])
    if mode == "source":
        previous["measurement_contract"]["toolkit_source_sha256"] = "2" * 64
    elif mode == "scope":
        previous["measurement_contract"]["settings"]["deep"] = True
    elif mode == "weights":
        previous["scoring"]["weights"]["high"] = 20
    elif mode == "rule":
        previous["check_registry"]["page"]["version"] = "2"
    elif mode == "missing_contract":
        previous.pop("measurement_contract")
    elif mode == "partial":
        previous["status"] = "partial"
    elif mode == "future":
        previous["timestamp"] = saved(hour=3)["timestamp"]
    elif mode == "self":
        previous["run_id"] = current["run_id"]
    elif mode == "other_url":
        previous["url"] = "https://example.test.evil/"
    else:
        previous["profile"] = "rendered"
        previous["measurement_contract"]["settings"]["profile"] = "rendered"
    history.save(previous)
    result = history.compare(current)
    assert not result["resolution_assessed"]
    assert not result["resolved"]
    assert result["baseline"] is None


@pytest.mark.parametrize("mode", ["partial", "changed_source", "unknown", "other_profile"])
def test_incompatible_older_findings_do_not_invent_regressions(tmp_path, mode):
    history = History(tmp_path)
    older = with_findings(saved("older"), ["again"])
    if mode == "partial":
        older["status"] = "partial"
    elif mode == "changed_source":
        older["measurement_contract"]["toolkit_source_sha256"] = "2" * 64
    elif mode == "unknown":
        older.pop("measurement_contract")
    else:
        older["profile"] = "rendered"
        older["measurement_contract"]["settings"]["profile"] = "rendered"
    history.save(older)
    history.save(with_findings(saved("baseline", 100, hour=1), []))
    result = history.compare(with_findings(saved("current", hour=2), ["again"]))
    assert result["baseline"] == "baseline"
    assert result["new"] == ["again"] and not result["regressed"]


def test_matching_history_classifies_all_four_states_and_partial_current(tmp_path):
    history = History(tmp_path)
    history.save(with_findings(saved("older"), ["again"]))
    history.save(with_findings(saved("baseline", hour=1), ["persistent", "resolved"]))
    current = with_findings(saved("current", hour=2), ["persistent", "again", "new"])
    result = history.compare(current)
    assert result["resolution_assessed"]
    assert result["baseline"] == "baseline"
    assert result["new"] == ["new"] and result["persistent"] == ["persistent"]
    assert result["regressed"] == ["again"] and result["resolved"] == ["resolved"]
    (tmp_path / "matching-labels.json").write_text(json.dumps(result, indent=2))
    current["status"] = "partial"
    held = history.compare(current)
    assert not held["comparison_assessed"] and not held["resolution_assessed"]
    assert not any(held[key] for key in ("new", "persistent", "regressed", "resolved"))
    assert held["observed_current"] == ["again", "new", "persistent"]
    (tmp_path / "partial-labels.json").write_text(json.dumps(held, indent=2))


@pytest.mark.parametrize("mode", ["empty", "duplicate", "missing", "non_dict"])
def test_invalid_finding_inventory_cannot_prove_resolution(tmp_path, mode):
    history = History(tmp_path)
    history.save(with_findings(saved("baseline"), ["old"]))
    current = with_findings(saved("current", hour=1), ["other"])
    if mode == "empty":
        current["defects"][0]["finding_id"] = ""
    elif mode == "duplicate":
        current["defects"].append(copy.deepcopy(current["defects"][0]))
    elif mode == "missing":
        current.pop("defects")
    else:
        current["defects"] = ["not a finding"]
    result = history.compare(current)
    assert not result["resolution_assessed"] and not result["resolved"]


@pytest.mark.parametrize("mode", ["changed_source", "different_rule", "missing_contract", "partial_detection"])
def test_verification_rejects_incompatible_detection(tmp_path, mode):
    history = History(tmp_path)
    detection = with_findings(saved("detected"), ["old"])
    if mode == "changed_source":
        detection["measurement_contract"]["toolkit_source_sha256"] = "2" * 64
    elif mode == "different_rule":
        detection["check_registry"]["page"]["version"] = "2"
    elif mode == "missing_contract":
        detection.pop("measurement_contract")
    else:
        detection["status"] = "partial"
    history.save(detection)
    history.save(with_findings(saved("verified", 100, hour=1), []))
    with pytest.raises(ValueError):
        history.transition("old", "verified", {"verification_run": "verified"})
    with history.connect() as db:
        assert db.execute("SELECT state FROM remediations WHERE id='old'").fetchone()[0] == "detected"
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0


def test_verified_event_binds_actual_state_identity_and_detection(tmp_path):
    history = History(tmp_path)
    history.save(with_findings(saved("detected"), ["old"]))
    history.save(with_findings(saved("verified", 100, hour=1), []))
    history.transition("old", "verified", {"verification_run": "verified", "id": "spoof", "state": "regressed"})
    with history.connect() as db:
        state, metadata = db.execute("SELECT state,metadata FROM remediations WHERE id='old'").fetchone()
        event = json.loads(db.execute("SELECT payload FROM events").fetchone()[0])
    assert state == "verified" and event["id"] == "old" and event["state"] == "verified"
    assert event["detection_run"] == "detected" and len(event["verification_basis_sha256"]) == 64
    assert json.loads(metadata)["detection_run"] == "detected"


def test_history_orders_offset_timestamps_at_microsecond_precision(tmp_path):
    history = History(tmp_path)
    earlier = with_findings(saved("earlier"), ["old"])
    earlier["timestamp"] = "2026-10-03T13:00:00.000001+13:00"
    future = with_findings(saved("future"), ["should_not_resolve"])
    future["timestamp"] = "2026-10-02T11:00:00.000003-13:00"
    unknown = with_findings(saved("unknown"), ["unknown"])
    unknown["timestamp"] = "unplaced"
    current = with_findings(saved("current", 100), [])
    current["timestamp"] = "2026-10-03T00:00:00.000002+00:00"
    for run in (earlier, future, unknown):
        history.save(run)
    assert [run["run_id"] for run in history.prior_observations(current)] == ["earlier", "unknown"]
    result = history.compare(current)
    assert result["baseline"] == "earlier" and result["resolved"] == ["old"]
    assert result["eligible_prior_count"] == 1


@pytest.fixture
def mocked_pipeline(monkeypatch):
    from auditor_toolkit import pipeline as p
    monkeypatch.setattr(p, "validate_url", lambda url, *args, **kwargs: url)
    no_findings = lambda *args, **kwargs: ([], {})  # noqa: E731
    for name in ("analyse_html", "inspect_schema", "inspect_headers", "check_robots",
                 "check_sitemap", "grade_security_headers", "check_mixed_content", "detect_conversion_signals"):
        monkeypatch.setattr(p, name, no_findings)
    for module in (p.tech, p.vuln_js, p.structured_validation, p.hreflang, p.language,
                   p.images, p.social_meta, p.ux_static, p.cookie_consent, p.third_party, p.browser_console):
        monkeypatch.setattr(module, "analyse_html", no_findings)
    monkeypatch.setattr(p, "run_browser_checks", lambda *args, **kwargs: {
        "status": "ok" if kwargs.get("enabled") else "skipped",
        "evidence": {"axe": {"violations": []}} if kwargs.get("enabled") else {},
    })
    response = httpx.Response(200, text="<html>synthetic</html>", request=httpx.Request("GET", "https://example.test/"))
    return p, SimpleNamespace(get=lambda *args, **kwargs: response)


@pytest.mark.parametrize("pdf_failure", [False, True])
def test_pipeline_final_chart_manifest_and_pdf_failure(tmp_path, mocked_pipeline, monkeypatch, pdf_failure):
    p, fetcher = mocked_pipeline
    calls = []

    def export(source, output, options):
        calls.append(source.read_text())
        if pdf_failure and len(calls) % 2 == 0:
            raise RuntimeError("synthetic final PDF failure")
        output.write_bytes(b"synthetic PDF")

    monkeypatch.setattr(p, "export_pdf", export)
    options = AuditOptions(output_root=tmp_path, browser=True)
    first = p.run_audit("https://example.test/", options, fetcher)
    old_json = Path(first["artifacts"]["json"]).read_bytes()
    old_trend = Path(first["artifacts"]["trend"]).read_bytes()
    report = p.run_audit("https://example.test/", options, fetcher)
    assert "Recorded health over time" in Path(report["artifacts"]["html"]).read_text()
    assert len(report["history_trend"]["points"]) == 2
    assert report["status"] == ("partial" if pdf_failure else "complete")
    assert ("pdf" in first["artifacts"]) != pdf_failure
    assert first["history_trend"]["summary"]["current_health"] == (None if pdf_failure else 100)
    assert "Recorded health over time" in calls[1]
    assert Path(first["artifacts"]["json"]).read_bytes() == old_json
    assert Path(first["artifacts"]["trend"]).read_bytes() == old_trend
    for key, manifest in report["manifest"].items():
        assert hashlib.sha256(Path(manifest["path"]).read_bytes()).hexdigest() == manifest["sha256"]
    assert json.loads(Path(report["artifacts"]["json"]).read_text())["history_trend"] == report["history_trend"]


@pytest.mark.parametrize("pdf_failure", [False, True])
def test_pipeline_finding_and_fault_labels_refresh_after_final_pdf(tmp_path, mocked_pipeline, monkeypatch, pdf_failure):
    from auditor_toolkit.checks import Finding
    p, fetcher = mocked_pipeline
    state = {"present": True, "exports": 0}

    def page(*args, **kwargs):
        return ([Finding("synthetic", "Synthetic finding", "Captured synthetic evidence", "low",
                         "https://example.test/", check="page", observed="Synthetic marker")]
                if state["present"] else [], {})

    def pdf(source, output, options):
        state["exports"] += 1
        if pdf_failure and state["exports"] == 4:
            raise RuntimeError("synthetic final PDF failure")
        output.write_bytes(b"synthetic PDF")

    monkeypatch.setattr(p, "analyse_html", page)
    monkeypatch.setattr(p, "export_pdf", pdf)
    options = AuditOptions(output_root=tmp_path, browser=True)
    detected = p.run_audit("https://example.test/", options, fetcher)
    assert detected["status"] == "complete" and len(detected["defects"]) == 1
    state["present"] = False
    current = p.run_audit("https://example.test/", options, fetcher)
    identity = detected["defects"][0]["finding_id"]
    assert current["comparison"]["resolution_assessed"] != pdf_failure
    assert current["fault_regression"]["assessed"] != pdf_failure
    assert current["comparison"]["resolved"] == ([] if pdf_failure else [identity])
    assert current["fault_regression"]["resolved"] == ([] if pdf_failure else [identity])
    assert current["status"] == ("partial" if pdf_failure else "complete")
    saved_report = json.loads(Path(current["artifacts"]["json"]).read_text())
    assert saved_report["fault_regression"] == current["fault_regression"]


@pytest.fixture
def cli_inputs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name, data in (("target", saved()), ("other", saved("other", 92))):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "report.json").write_text(json.dumps(data))
    return ["compare", "target/report.json", "--against", "other/report.json", "--output-dir", "result"]


def test_saved_cli_and_immutable_inputs(cli_inputs, capsys):
    from auditor_toolkit.cli import main
    before = Path("target/report.json").read_bytes()
    assert main(cli_inputs) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "comparable"
    assert Path("target/report.json").read_bytes() == before
    assert Path("result/comparison.html").is_file()


@pytest.mark.parametrize("mode", ["partial", "legacy"])
def test_saved_cli_held_returns_two(cli_inputs, mode):
    from auditor_toolkit.cli import main
    report = saved("other")
    if mode == "partial":
        report["status"] = "partial"
    else:
        report.pop("measurement_contract")
    Path("other/report.json").write_text(json.dumps(report))
    assert main(cli_inputs) == 2
    assert json.loads(Path("result/comparison.json").read_text())["status"] == "held"


@pytest.mark.parametrize("mode", ["outside", "duplicate", "malformed", "overwrite", "input_folder", "too_large", "total_size", "limit", "symlink", "output_outside"])
def test_saved_cli_validation_does_not_write(cli_inputs, tmp_path, mode):
    from auditor_toolkit.cli import main
    if mode == "outside":
        cli_inputs[1] = str(tmp_path.parent / "outside.json")
    elif mode == "duplicate":
        cli_inputs[3] = cli_inputs[1]
    elif mode == "malformed":
        Path("other/report.json").write_text("{bad json")
    elif mode == "overwrite":
        Path("result").mkdir()
        Path("result/keep.txt").write_text("keep")
    elif mode == "input_folder":
        cli_inputs[-1] = "target/new"
    elif mode == "too_large":
        Path("other/report.json").write_bytes(b" " * 10_000_001)
    elif mode == "total_size":
        Path("target/report.json").write_bytes(b" " * 8_000_000)
        Path("other/report.json").write_bytes(b" " * 8_000_000)
        Path("third.json").write_bytes(b" " * 8_000_000)
        cli_inputs.extend(["--against", "third.json"])
    elif mode == "symlink":
        outside = tmp_path.parent / "outside.json"
        outside.write_text(json.dumps(saved("outside")))
        Path("link.json").symlink_to(outside)
        cli_inputs[3] = "link.json"
    elif mode == "output_outside":
        cli_inputs[-1] = str(tmp_path.parent / "outside-result")
    else:
        cli_inputs.extend(["--against", "target/report.json"] * 100)
    with pytest.raises(SystemExit) as error:
        main(cli_inputs)
    assert error.value.code == 2
    if mode == "overwrite":
        assert Path("result/keep.txt").read_text() == "keep"
    else:
        assert not Path("result").exists()


@pytest.mark.parametrize("arguments", [
    ["audit", "--competitor", "https://other.test/"],
    ["audit", "https://example.test/", "--competitor", "https://example.test/"],
    ["audit", "https://example.test/", "--batch", "not-present.txt", "--competitor", "https://other.test/"],
])
def test_competitor_invalid_arguments_before_auditing(arguments, monkeypatch):
    from auditor_toolkit import cli
    monkeypatch.setattr(cli, "run_audit", lambda *args: pytest.fail("Invalid arguments started an audit"))
    with pytest.raises(SystemExit) as error:
        cli.main(arguments)
    assert error.value.code == 2


@pytest.mark.parametrize("held", [False, True])
def test_competitor_mocked_audits_emit_shared_comparison(tmp_path, monkeypatch, capsys, held):
    from auditor_toolkit import cli
    monkeypatch.chdir(tmp_path)
    calls = []

    def audit(url, options):
        calls.append(url)
        result = saved("target" if len(calls) == 1 else "other", url=url)
        result["artifacts"] = {"json": "original/report.json"}
        if held and len(calls) == 2:
            result.pop("measurement_contract")
        return result

    monkeypatch.setattr(cli, "run_audit", audit)
    code = cli.main(["audit", "https://example.test/", "--competitor", "https://other.test/", "--concurrency", "1"])
    rows = json.loads(capsys.readouterr().out)
    assert code == (2 if held else 0)
    assert calls == ["https://example.test/", "https://other.test/"]
    assert all(row["artifacts"]["json"] == "original/report.json" for row in rows)
    assert all(row["comparison"]["status"] == ("held" if held else "comparable") for row in rows)
    assert Path(rows[0]["artifacts"]["comparison_html"]).is_file()

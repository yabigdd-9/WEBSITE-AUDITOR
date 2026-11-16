"""Offline coverage of security-sensitive optional adapters and report packaging.

Every external GBP request is monkeypatched. No credentials or network are used.
"""

import json
from unittest.mock import Mock

import pytest

from auditor_toolkit import vuln_js
from auditor_toolkit.local_seo.adapters import authorized_gbp as gbp
from auditor_toolkit.proof.render import package_builder as proof
from auditor_toolkit.proof.schema import (
    AfterState,
    BeforeState,
    ProposedFix,
    ScreenshotArtifact,
    VerificationResult,
)
from auditor_toolkit.technology import report as tech_report
from auditor_toolkit.technology.schema import (
    TechDetection,
    TechEnrichmentResult,
    TechFingerprint,
    TechStack,
    VersionInfo,
    VulnerabilityAdvisory,
)


@pytest.fixture(autouse=True)
def isolate_optional_gbp(monkeypatch):
    monkeypatch.setattr(gbp, "_auth_config", gbp.GBPAuthConfig())
    monkeypatch.setattr(gbp, "_enabled", False)


def _mock_response(body):
    response = Mock()
    response.json.return_value = body
    response.raise_for_status.return_value = None
    return response


def _gbp_payload():
    return {
        "title": "Example Painter",
        "storeCode": "store-1",
        "address": {"addressLines": ["2 Example Street", "Christchurch"]},
        "primaryPhone": "+6431234567",
        "websiteUri": "https://example.test",
        "latlng": {"latitude": -43.53, "longitude": 172.63},
        "primaryCategory": {"displayName": "Painter"},
        "additionalCategories": [
            {"displayName": "Interior decorator"}, {"displayName": ""}
        ],
        "regularHours": {
            "periods": [
                {"openDay": "MONDAY", "openTime": "09:00", "closeTime": "17:00"},
                {"openDay": ""},
            ]
        },
        "state": "OPEN",
    }


def test_gbp_auth_requires_explicit_enable_and_valid_identity(monkeypatch):
    http_get = Mock(side_effect=AssertionError("network must remain disabled"))
    monkeypatch.setattr("httpx.get", http_get)
    assert not gbp.GBPAuthConfig().is_configured
    assert not gbp.enable_gbp()
    assert not gbp.is_enabled()
    assert gbp.list_locations("accounts/example", enable=True) == []
    assert gbp.get_location("accounts/example/locations/1", enable=True) is None

    gbp.configure_auth(client_id="fake-id", refresh_token="fake-refresh")
    assert gbp.GBPAuthConfig(client_id="id", access_token="token").is_configured
    assert not gbp.is_enabled()  # Configuring auth is not authorization to query.
    assert gbp.list_locations("accounts/example", enable=True) == []
    assert gbp.enable_gbp()
    assert gbp.is_enabled()
    assert gbp.list_locations("accounts/example", enable=False) == []
    assert gbp.get_location("accounts/example/locations/1", enable=False) is None
    gbp.disable_gbp()
    assert not gbp.is_enabled()
    http_get.assert_not_called()


def test_gbp_refresh_and_expiry_are_safe_and_mocked(monkeypatch):
    assert gbp._refresh_access_token() is None
    gbp.configure_auth(
        client_id="fake-id", client_secret="fake-secret", refresh_token="fake-refresh"
    )
    monkeypatch.setattr(
        "httpx.post", Mock(return_value=_mock_response({
            "access_token": "test-access", "expires_in": 3600
        }))
    )
    assert gbp._get_access_token() == "test-access"
    assert gbp._auth_config.access_token == "test-access"
    assert gbp._get_access_token() == "test-access"

    gbp._auth_config = gbp.GBPAuthConfig(
        client_id="fake-id", refresh_token="fake-refresh",
        access_token="expired", token_expires_at="2000-01-01T00:00:00+00:00",
    )
    with pytest.MonkeyPatch.context() as patcher:
        callback = Mock(return_value="renewed")
        patcher.setattr(gbp, "_refresh_access_token", callback)
        assert gbp._get_access_token() == "renewed"
        callback.assert_called_once()

    gbp._auth_config = gbp.GBPAuthConfig(
        client_id="fake-id", refresh_token="fake-refresh",
        access_token="bad-date", token_expires_at="invalid-date",
    )
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(gbp, "_refresh_access_token", lambda: "fresh")
        assert gbp._get_access_token() == "fresh"

    monkeypatch.setattr("httpx.post", Mock(side_effect=ConnectionError("offline")))
    assert gbp._refresh_access_token() is None


def test_gbp_parsing_evidence_and_location_fetch_are_offline(monkeypatch):
    raw = _gbp_payload()
    parsed = gbp._parse_gbp_location(raw)
    assert parsed.name == "Example Painter"
    assert parsed.address == "2 Example Street, Christchurch"
    assert parsed.categories == ["Painter", "Interior decorator"]
    assert parsed.geo.latitude == -43.53
    assert parsed.hours["MONDAY"] == "09:00-17:00"
    assert parsed.to_dict()["state"] == "OPEN"

    evidence = parsed.to_external_evidence()
    assert evidence.provider == "Google Business Profile"
    assert evidence.source_confidence == 0.95
    assert evidence.raw_artifact_hash == parsed.to_external_evidence().raw_artifact_hash

    blank = gbp._parse_gbp_location({})
    assert blank.to_dict()["geo"] is None
    assert blank.categories == []
    assert blank.hours == {}

    gbp.configure_auth(client_id="fake-id", refresh_token="fake-refresh")
    assert gbp.enable_gbp()
    monkeypatch.setattr(gbp, "_get_access_token", lambda: "fake-access")
    getter = Mock(side_effect=[
        _mock_response({"locations": [raw]}),
        _mock_response(raw),
        RuntimeError("unavailable"),
        RuntimeError("unavailable"),
    ])
    monkeypatch.setattr("httpx.get", getter)
    locations = gbp.list_locations("accounts/example", enable=True)
    assert len(locations) == 1 and locations[0].store_code == "store-1"
    one = gbp.get_location("accounts/example/locations/1", enable=True)
    assert one.name == "Example Painter"
    assert gbp.list_locations("accounts/example", enable=True) == []
    assert gbp.get_location("accounts/example/locations/1", enable=True) is None
    assert getter.call_count == 4


def test_gbp_no_token_never_contacts_google(monkeypatch):
    gbp.configure_auth(client_id="fake-id", refresh_token="fake-refresh")
    assert gbp.enable_gbp()
    monkeypatch.setattr(gbp, "_get_access_token", lambda: None)
    getter = Mock(side_effect=AssertionError("must not call Google"))
    monkeypatch.setattr("httpx.get", getter)
    assert gbp.list_locations("accounts/example", enable=True) == []
    assert gbp.get_location("accounts/example/locations/1", enable=True) is None
    getter.assert_not_called()


def _tech_result():
    cms = TechDetection(name="WordPress", category="cms", confidence=0.9)
    framework = TechDetection(name="Example Framework", category="framework")
    language = TechDetection(name="Python", category="language")
    analytics = TechDetection(name="Plausible", category="analytics")
    payment = TechDetection(name="Stripe", category="payment")
    fingerprint = TechFingerprint(
        cms=cms, framework=framework, language=language,
        analytics=[analytics], payment=[payment],
        server=TechDetection(name="nginx", category="server"),
        cdn=TechDetection(name="Cloudflare", category="cdn"),
        ecommerce=TechDetection(name="WooCommerce", category="ecommerce"),
        hosting=TechDetection(name="ExampleHost", category="hosting"),
    )
    return TechEnrichmentResult(
        url="https://example.test",
        fingerprint=fingerprint,
        versions=[
            VersionInfo(
                name="WordPress", detected_version="5.0",
                latest_version="6.0", is_outdated=True,
            ),
            VersionInfo(name="nginx", detected_version="1.0"),
        ],
        vulnerabilities=[
            VulnerabilityAdvisory(
                component="WordPress", version="5.0",
                severity="critical", cve_id="CVE-2099-0001",
                description="Fixture vulnerability", remediation="Update software",
            )
        ],
        run_id="offline-tech-report",
        completed_at="2026-11-16T00:00:00Z",
        duration_seconds=1.25,
        errors=["Test-only warning"],
    )


def test_technology_reports_cover_detections_versions_vulns_and_errors(tmp_path):
    result = _tech_result()
    markdown = tech_report.generate_report(result)
    assert "WordPress" in markdown
    assert "Example Framework" in markdown
    assert "Plausible" in markdown
    assert "Stripe" in markdown
    assert "OUTDATED" in markdown
    assert "Current" in markdown
    assert "CVE-2099-0001" in markdown
    assert "Test-only warning" in markdown

    structured = json.loads(tech_report.generate_json_report(result))
    summary = structured["summary"]
    assert summary["total_vulnerabilities"] == 1
    assert summary["outdated_components"] == 1
    assert summary["severity_breakdown"] == {"critical": 1}
    assert structured["report_type"] == "technology_enrichment"

    stack = TechStack(
        fingerprint=result.fingerprint,
        versions=result.versions,
        vulnerabilities=result.vulnerabilities,
    )
    concise = tech_report.generate_stack_summary_markdown(stack)
    assert "## Vulnerabilities" in concise
    assert "⚠️ outdated" in concise
    assert "✅ current" in concise
    assert "Not detected" not in concise

    output_json, output_md = tech_report.save_report(result, tmp_path)
    assert json.loads(output_json.read_text())["run_id"] == "offline-tech-report"
    assert "WordPress" in output_md.read_text()


def test_technology_report_empty_and_fallback_branches(tmp_path):
    result = TechEnrichmentResult(url="https://example.test", fingerprint=TechFingerprint())
    assert "No version information detected" in tech_report.generate_report(result)
    assert "No known vulnerabilities detected" in tech_report.generate_report(result)
    empty_stack = tech_report.generate_stack_summary_markdown(
        TechStack(fingerprint=TechFingerprint())
    )
    assert "Not detected" in empty_stack
    assert "## Vulnerabilities" not in empty_stack
    paths = tech_report.save_report(result, tmp_path)
    assert paths[0].name == "unknown.json"
    assert paths[1].name == "unknown.md"
    for severity, expected in [
        ("critical", 4), ("high", 3), ("medium", 2),
        ("low", 1), ("unknown", 0),
    ]:
        assert tech_report._severity_rank(severity) == expected
        assert tech_report._severity_icon(severity)


def _proof_objects(before_path, after_path):
    return (
        BeforeState(
            finding_id="finding-1", url="https://example.test",
            screenshot=ScreenshotArtifact(path=str(before_path)), status="CAPTURED",
        ),
        ProposedFix(
            finding_id="finding-1", fix_type="html_edit",
            description="Fixture repair",
        ),
        AfterState(
            finding_id="finding-1", url="https://example.test",
            screenshot=ScreenshotArtifact(path=str(after_path)), status="CAPTURED",
        ),
        VerificationResult(
            finding_id="finding-1", verifier_id="independent-test",
            verdict="FIXED",
        ),
    )


def test_proof_package_requires_verified_nonempty_artifacts(tmp_path):
    before_path, after_path, diff = (
        tmp_path / "before.png", tmp_path / "after.png", tmp_path / "diff.png"
    )
    for path in (before_path, after_path, diff):
        path.write_bytes(b"offline fixture")
    args = _proof_objects(before_path, after_path)
    package = proof.build_proof_package(*args, diff_path=str(diff))
    assert package.status == "READY"
    assert package.finding_id == "finding-1"
    assert package.diff_path == str(diff)
    assert package.is_complete()
    assert proof._validate_screenshot(str(before_path), "Before") == ""


def test_proof_package_rejects_missing_artifacts_and_invalid_status(tmp_path):
    before_path, after_path = tmp_path / "before.png", tmp_path / "after.png"
    before_path.write_bytes(b"fixture")
    after_path.write_bytes(b"")  # exists but empty
    args = _proof_objects(before_path, after_path)
    args[0].status = "FAILED"
    args[2].status = "UNAVAILABLE"
    args[1].finding_id = ""
    args[1].fix_type = ""
    args[3].verifier_id = ""
    with pytest.raises(ValueError, match="Proof package validation failed") as exc:
        proof.build_proof_package(*args, diff_path=str(tmp_path / "missing.png"))
    for expected in (
        "Before state status", "After state status", "After: file is empty",
        "Proposed fix type is empty", "Proposed fix finding_id is empty",
        "Verification result has no verifier_id", "Diff: file not found",
    ):
        assert expected in str(exc.value)
    assert "screenshot path is empty" in proof._validate_screenshot("", "Before")
    assert "file not found" in proof._validate_screenshot(
        str(tmp_path / "gone.png"), "After"
    )


@pytest.mark.parametrize("source,expected", [
    ("/lib/jquery-1.4.0.min.js", ("jQuery", "1.4.0")),
    ("/lib/bootstrap_5.0.0.js", ("Bootstrap", "5.0.0")),
    ("/lib/angular.1.2.3.js", ("Angular", "1.2.3")),
    ("/lib/vue-3.1.0.js", ("Vue", "3.1.0")),
    ("/lib/react.18.2.0.js", ("React", "18.2.0")),
    ("not-a-library.js", (None, None)),
])
def test_javascript_library_version_parser(source, expected):
    assert vuln_js._extract_library_and_version(source) == expected


def test_js_vulnerability_checks_known_versions_without_network():
    html = (
        '<script src="/assets/jquery-1.4.0.min.js"></script>'
        '<script src="/assets/bootstrap-5.0.0.js"></script>'
        '<script src="/assets/jquery-3.7.1.min.js"></script>'
    )
    result, data = vuln_js.analyse_html(html, "https://example.test", {})
    assert len(result) == 1
    assert result[0].defect_key == "js_vulnerability_jquery_1_4_0"
    assert data["js_vulnerabilities_detected"] == 1
    assert vuln_js.detect_js_vulnerabilities(
        '<script src="assets/no-version.js"></script>',
        "https://example.test",
    ) == []

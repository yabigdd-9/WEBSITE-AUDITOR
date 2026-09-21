import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from auditor_toolkit import cli
from auditor_toolkit.demo import build_demo
from auditor_toolkit.packet import build_packet
from auditor_toolkit.quote import calculate_quote
from auditor_toolkit.remediation import build_remediation, classify


def full_report(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    screenshot = run_dir / "desktop.png"
    screenshot.write_bytes(b"synthetic-png")
    report_json = run_dir / "report.json"
    defects = []
    keys = [
        ("viewport", "AUTO_SAFE", "XS"),
        ("missing_canonical_url", "AUTO_PREVIEW", "XS"),
        ("missing_title", "AUTO_PREVIEW", "XS"),
        ("missing_meta_description", "AUTO_PREVIEW", "XS"),
        ("robots-missing", "AUTO_PREVIEW", "XS"),
        ("robots-no-sitemap", "AUTO_PREVIEW", "XS"),
        ("sitemap-missing", "AUTO_PREVIEW", "S"),
        ("mixed-content", "AUTO_PREVIEW", "S"),
        ("image-alt", "AUTO_PREVIEW", "S"),
        ("broken-internal-link", "AUTO_PREVIEW", "S"),
        ("header-hsts", "HUMAN_REVIEW", "S"),
        ("unknown-platform-change", "CLIENT_ACCESS_REQUIRED", "M"),
    ]
    for index, (key, remediation_class, effort) in enumerate(keys, 1):
        defects.append(
            {
                "finding_id": f"f{index}",
                "defect_key": key,
                "defect": key.replace("-", " "),
                "source_url": "https://example.co.nz/",
                "impact": "https://example.co.nz/broken" if key == "broken-internal-link" else key,
                "observed": f"observed {key}",
                "remediation_action": f"review {key}",
                "remediation_automation": remediation_class,
                "effort_band": effort,
                "confidence": "observed",
            }
        )
    report = {
        "schema_version": 2,
        "run_id": "run-cli-fixture",
        "url": "https://example.co.nz/",
        "domain": "example.co.nz",
        "status": "complete",
        "health_score": 64,
        "defects": defects,
        "artifacts": {
            "json": str(report_json),
            "screenshot": str(screenshot),
        },
        "manifest": {
            "screenshot": {
                "path": str(screenshot),
                "sha256": hashlib.sha256(screenshot.read_bytes()).hexdigest(),
            }
        },
    }
    report_json.write_text(json.dumps(report), encoding="utf-8")
    return report, report_json


def test_remediation_covers_supported_preview_artifacts(tmp_path):
    report, _ = full_report(tmp_path)
    result = build_remediation(report, tmp_path / "remediation")
    assert result["counts"]["AUTO_SAFE"] == 1
    assert result["counts"]["AUTO_PREVIEW"] == 9
    assert result["counts"]["HUMAN_REVIEW"] == 1
    assert result["counts"]["CLIENT_ACCESS_REQUIRED"] == 1
    artifacts = [Path(x["artifact"]) for x in result["items"] if x.get("artifact")]
    assert len(artifacts) == 10
    assert all(path.is_file() for path in artifacts)
    assert any(path.name.endswith("redirect-map.csv") for path in artifacts)
    assert classify({"defect_key": "unmapped"}) == "HUMAN_REVIEW"


def test_demo_copies_only_manifest_verified_screenshot_and_renders_in_memory(tmp_path):
    report, _ = full_report(tmp_path)
    remediation = build_remediation(report, tmp_path / "remediation")

    def fake_render(html, screenshot):
        assert "LOCAL CONCEPT ONLY" in html
        screenshot.write_bytes(b"rendered-concept")

    with patch("auditor_toolkit.demo._render_html", side_effect=fake_render):
        demo = build_demo(
            report,
            remediation,
            tmp_path / "demo",
            render=True,
            report_path=report["artifacts"]["json"],
        )
    assert demo["before"]["kind"] == "captured_source"
    assert Path(demo["before"]["path"]).read_bytes() == b"synthetic-png"
    assert demo["after"]["kind"] == "local_concept_render"
    assert Path(demo["after"]["path"]).read_bytes() == b"rendered-concept"

    tampered = dict(report)
    tampered["manifest"] = {
        "screenshot": {
            "path": report["artifacts"]["screenshot"],
            "sha256": "0" * 64,
        }
    }
    clean = build_demo(
        tampered,
        remediation,
        tmp_path / "demo-tampered",
        report_path=report["artifacts"]["json"],
    )
    assert clean["before"] is None


def test_packet_verified_contact_and_manifest_binding_do_not_follow_paths(tmp_path):
    report, _ = full_report(tmp_path)
    remediation = build_remediation(report, tmp_path / "remediation")
    demo = build_demo(report, remediation, tmp_path / "demo")
    quote = calculate_quote(report, 150)
    demo["demo_html"] = "/etc/passwd"
    contact = {
        "email": "hello@example.co.nz",
        "selected": {"confidence_label": "VERIFIED_HIGH"},
    }
    packet = build_packet(
        report,
        remediation,
        demo,
        quote,
        tmp_path / "packet",
        contact=contact,
    )
    assert packet["contact"] == "hello@example.co.nz"
    assert packet["email_confidence"] == "VERIFIED_HIGH"
    assert all("file_sha256" not in item for item in packet["evidence"])


def test_delivery_cli_commands_end_to_end(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    report, report_json = full_report(tmp_path)
    remediation_dir = tmp_path / "cli-remediation"
    assert cli.main(["remediate", str(report_json), "--output-dir", str(remediation_dir)]) == 0
    remediation_json = remediation_dir / "remediation.json"
    assert remediation_json.is_file()

    demo_dir = tmp_path / "cli-demo"
    assert (
        cli.main(
            [
                "demo",
                str(report_json),
                str(remediation_json),
                "--output-dir",
                str(demo_dir),
            ]
        )
        == 0
    )
    demo_json = demo_dir / "demo.json"
    assert demo_json.is_file()

    quote_json = tmp_path / "quote.json"
    assert (
        cli.main(
            [
                "quote",
                str(report_json),
                "--hourly-rate-nzd",
                "150",
                "--output",
                str(quote_json),
            ]
        )
        == 0
    )
    assert quote_json.is_file()

    packet_dir = tmp_path / "cli-packet"
    assert (
        cli.main(
            [
                "packet",
                str(report_json),
                str(remediation_json),
                str(demo_json),
                str(quote_json),
                "--output-dir",
                str(packet_dir),
            ]
        )
        == 0
    )
    packet = json.loads((packet_dir / "packet.json").read_text())
    assert packet["send_enabled"] is False
    assert packet["approval_status"] == "HUMAN_APPROVAL_REQUIRED"
    assert "prospect_packet" in capsys.readouterr().out


def test_quote_partial_or_heuristic_lowers_confidence(tmp_path):
    report, _ = full_report(tmp_path)
    report["status"] = "partial"
    assert calculate_quote(report, 150)["confidence"] == "LOW"
    report["status"] = "complete"
    report["defects"][0]["confidence"] = "heuristic"
    assert calculate_quote(report, 150)["confidence"] == "MEDIUM"


def test_workspace_path_rejects_escape(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    outside = tmp_path.parent / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    try:
        with pytest.raises(ValueError, match="current workspace"):
            cli.workspace_path(outside, must_exist=True, file_only=True)
    finally:
        outside.unlink(missing_ok=True)


def test_external_tool_url_rejects_option_and_credentials():
    from auditor_toolkit.external_tools import _safe_url

    with pytest.raises(ValueError):
        _safe_url("--output=/tmp/evil")
    with pytest.raises(ValueError):
        _safe_url("https://user:pass@example.com/")
    assert _safe_url("https://example.com/a#fragment") == "https://example.com/a"

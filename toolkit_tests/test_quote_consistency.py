"""Audit proposals and explicit quotes share deterministic effort and rates."""
import json
import socket
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from auditor_toolkit import cli
from auditor_toolkit.common import Fetcher
from auditor_toolkit.pipeline import AuditOptions, run_audit
from auditor_toolkit.quote import calculate_proposal, calculate_quote


def sample_report():
    return {
        "run_id": "synthetic-quote",
        "status": "partial",
        "defects": [
            {"defect_key": "image", "effort_band": "XS", "finding_id": "first"},
            {"defect_key": "image", "effort_band": "S", "finding_id": "second"},
            {"defect_key": "title", "effort_band": "XS", "finding_id": "third"},
        ],
    }


def test_quotes_dedupe_setup_without_losing_finding_references():
    quote = calculate_quote(sample_report(), "150.50")
    proposal = calculate_proposal(sample_report(), "150.50")
    assert quote["included"] == ["image", "title"]
    assert quote["items"][0]["finding_ids"] == ["first", "second"]
    assert quote["estimated_hours"] == {"low": "2.00", "high": "6.33"}
    assert Decimal(str(proposal["estimate_low"])) == Decimal(quote["price_band_nzd"]["low"])
    assert Decimal(str(proposal["estimate_high"])) == Decimal(quote["price_band_nzd"]["high"])
    assert proposal["hours_low"] == float(quote["estimated_hours"]["low"])
    assert proposal["hours_high"] == float(quote["estimated_hours"]["high"])
    assert proposal["review_required"] is True
    assert proposal["llm_determined_price"] is False


def test_missing_rate_keeps_estimates_unpriced():
    proposal = calculate_proposal(sample_report())
    assert proposal["hourly_rate"] is None
    assert proposal["estimate_low"] is None
    assert proposal["estimate_high"] is None
    assert proposal["hours_low"] == 2.0


@pytest.mark.parametrize("report", [
    [], None, {"defects": [None]}, {"defects": ["title"]},
    {"defects": [{"defect_key": ["title"]}]},
    {"defects": [{"defect_key": " "}]},
    {"defects": [{"defect_key": "title", "effort_band": ["S"]}]},
])
def test_quote_entrypoints_reject_malformed_reports(report):
    with pytest.raises(ValueError):
        calculate_quote(report, 150)
    with pytest.raises(ValueError):
        calculate_proposal(report, 150)


@pytest.mark.parametrize("band", [[], {}, False, 0])
def test_quote_entrypoints_reject_falsey_nonstring_effort_bands(band):
    report = {"defects": [{"defect_key": "title", "effort_band": band}]}
    with pytest.raises(ValueError, match="Unknown effort band"):
        calculate_quote(report, 150)
    with pytest.raises(ValueError, match="Unknown effort band"):
        calculate_proposal(report, 150)


@pytest.mark.parametrize("effort", [{}, {"effort_band": None}, {"effort_band": ""}])
def test_quote_entrypoints_preserve_legacy_default_effort_band(effort):
    report = {"defects": [{"defect_key": "title", **effort}]}
    quote = calculate_quote(report, 150)
    proposal = calculate_proposal(report, 150)
    assert quote["items"][0]["effort_band"] == "M"
    assert quote["estimated_hours"] == {"low": "4.00", "high": "11.50"}
    assert quote["price_band_nzd"] == {"low": "600.00", "high": "1725.00"}
    assert proposal["hours_low"] == 4.0
    assert proposal["hours_high"] == 11.5
    assert proposal["estimate_low"] == 600.0
    assert proposal["estimate_high"] == 1725.0


def test_quote_cli_handles_malformed_defects_without_output(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    report_file = tmp_path / "report.json"
    report_file.write_text(json.dumps({"defects": [None]}))
    output = tmp_path / "quote.json"
    arguments = ["quote", str(report_file), "--hourly-rate-nzd=150",
                 "--output", str(output)]
    with pytest.raises(SystemExit) as caught:
        cli.main(arguments)
    assert caught.value.code == 2
    assert "Every defect must be an object" in capsys.readouterr().err
    assert not output.exists()


def test_quote_cli_handles_invalid_json_without_output(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    report_file = tmp_path / "report.json"
    report_file.write_text("{invalid json")
    output = tmp_path / "quote.json"
    arguments = ["quote", str(report_file), "--hourly-rate-nzd=150",
                 "--output", str(output)]
    with pytest.raises(SystemExit) as caught:
        cli.main(arguments)
    assert caught.value.code == 2
    captured = capsys.readouterr()
    assert "Expecting property name" in captured.err
    assert captured.out == ""
    assert not output.exists()


@pytest.mark.parametrize("rate", [0, -1, 10001, "NaN", "sNaN", "Infinity", "-Infinity", "bad"])
def test_all_quote_entrypoints_reject_invalid_rates(rate, tmp_path):
    with pytest.raises(ValueError):
        calculate_quote(sample_report(), rate)
    with pytest.raises(ValueError):
        calculate_proposal(sample_report(), rate)
    destination = tmp_path / "audit"
    with pytest.raises(ValueError):
        AuditOptions(output_root=destination, hourly_rate_nzd=rate)
    assert not destination.exists()


@pytest.mark.parametrize("contingency", ["NaN", "Infinity", "-Infinity", "bad", -1, 2])
def test_quote_rejects_invalid_contingency(contingency):
    report = sample_report()
    with pytest.raises(ValueError):
        calculate_quote(report, 150, contingency)


@pytest.mark.parametrize("rate", ["0", "-1", "10001", "nan", "inf", "-inf"])
def test_audit_cli_rejects_rate_before_fetching(rate, tmp_path, monkeypatch, capsys):
    def unexpected_audit(*args, **kwargs):
        pytest.fail("Invalid rates must not start an audit")

    monkeypatch.setattr(cli, "run_audit", unexpected_audit)
    arguments = ["audit", "https://example.com", "--output-root", str(tmp_path / "audit"),
                 f"--hourly-rate-nzd={rate}"]
    with pytest.raises(SystemExit) as caught:
        cli.main(arguments)
    assert caught.value.code == 2
    assert "hourly_rate_nzd" in capsys.readouterr().err
    assert not (tmp_path / "audit").exists()


def test_quote_cli_rejects_nonfinite_rate_without_output(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    report_file = tmp_path / "report.json"
    report_file.write_text(json.dumps(sample_report()))
    output = tmp_path / "quote.json"
    arguments = ["quote", str(report_file), "--hourly-rate-nzd=nan",
                 "--output", str(output)]
    with pytest.raises(SystemExit) as caught:
        cli.main(arguments)
    assert caught.value.code == 2
    assert "hourly_rate_nzd" in capsys.readouterr().err
    assert not output.exists()


def test_saved_audit_proposal_matches_standalone_quote(tmp_path, monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 443))
    ])
    transport = httpx.MockTransport(lambda request: httpx.Response(
        200, text="<title>Example</title><img src='one'><img src='two'>", request=request,
    ))
    fetcher = Fetcher(transport=transport, min_interval=0)
    try:
        report = run_audit("https://example.com", AuditOptions(
            output_root=tmp_path, hourly_rate_nzd=150.5,
        ), fetcher)
    finally:
        fetcher.close()
    quote = calculate_quote(report, "150.5")
    proposal = report["proposal"]
    assert proposal["estimate_low"] == float(quote["price_band_nzd"]["low"])
    assert proposal["estimate_high"] == float(quote["price_band_nzd"]["high"])
    saved = json.loads(Path(report["artifacts"]["json"]).read_text())
    assert saved["proposal"] == proposal


def test_secret_list_is_unsupported_without_any_keychain_call(monkeypatch, capsys):
    def forbidden_keychain(*args, **kwargs):
        pytest.fail("Listing must not invoke Keychain")

    monkeypatch.setattr(cli.subprocess, "run", forbidden_keychain)
    assert cli.main(["secret", "list"]) == 1
    output = capsys.readouterr()
    assert "not implemented" in output.err
    assert output.out == ""

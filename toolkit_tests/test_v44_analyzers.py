"""Behavioral contracts for the six V44 analyzers using local fixtures."""
import socket

import httpx
import pytest

from auditor_toolkit import browser_console, hreflang, images, language, social_meta, third_party
from auditor_toolkit.checks import score_findings
from auditor_toolkit.common import Fetcher
from auditor_toolkit.models import REGISTRY, current_coverage_gaps
from auditor_toolkit.pipeline import AuditOptions, run_audit


def keys(result):
    return {finding.defect_key for finding in result[0]}


@pytest.mark.parametrize("module", [third_party, hreflang, language, images, social_meta, browser_console])
@pytest.mark.parametrize("html", ["", "<", "<img src='[bad'><meta content=''>"])
def test_missing_and_malformed_html_is_deterministic(module, html):
    first = module.analyse_html(html, "https://fixture.example/", {})
    assert first == module.analyse_html(html, "https://fixture.example/", {})
    assert first[1]["url"] == "https://fixture.example/"
    for finding in first[0]:
        assert finding.check in REGISTRY
        assert finding.observed
    score = score_findings(first[0])
    assert score["health_score"] == 100 - score["severity_score"]


def test_resource_inventory_handles_relative_protocol_and_attribute_order():
    found, evidence = third_party.analyse_html("""
    <script src = '//cdn.example/x.js'></script>
    <img src=https://cdn.example/a.png><link href='/a.css' rel=stylesheet>
    <link href=https://other.example/ rel=canonical><img src='data:image/png,x'>
    <img src='https://FIXTURE.example:443/x'><img src='http://[bad'>
    """, "https://fixture.example/", {})
    assert evidence["external_domains"] == ["https://cdn.example:443"]
    assert evidence["external_request_count"] == 2
    assert found[0].check == "third_party"


def test_hreflang_attribute_orders_duplicates_and_exact_self_reference():
    html = """<link href=/fr hreflang=fr rel=alternate>
    <link hreflang=en rel=alternate href=/en><link rel=alternate href=/en hreflang=en>
    <link href=/ hreflang=x-default rel=alternate>"""
    result = hreflang.analyse_html(html, "https://fixture.example/en", {})
    assert keys(result) == {"hreflang-duplicate"}
    assert result[1]["hreflang_count"] == 3
    assert "hreflang-no-self" in keys(hreflang.analyse_html(html, "https://fixture.example/other", {}))
    assert keys(hreflang.analyse_html('<link rel=canonical href=/en hreflang=en>', "https://fixture.example/", {})) == set()
    assert "hreflang-no-x-default" in keys(hreflang.analyse_html('<link rel=alternate hreflang=en href=/en>', "https://fixture.example/en", {}))


@pytest.mark.parametrize("lang", ["en-NZ", "mi", "zh-Hant-NZ"])
def test_language_declaration_does_not_infer_english_from_nz_domain(lang):
    result = language.analyse_html(f'<html lang = "{lang}">', "https://fixture.co.nz/", {})
    assert keys(result) == set()
    assert result[1]["html_lang"] == lang.lower()


def test_language_invalid_and_mismatching_declarations():
    assert "invalid-html-lang" in keys(language.analyse_html('<html lang="???">', "https://fixture.example/", {}))
    result = language.analyse_html('<html lang=en><meta content=fr http-equiv=content-language>', "https://fixture.example/", {})
    assert keys(result) == {"lang-mismatch"}


def test_decorative_alt_and_dimensions():
    result = images.analyse_html('<img alt="" width=20 height=30 loading=lazy src=/x>', "https://fixture.example/", {})
    assert keys(result) == set()
    result = images.analyse_html('<img width=0 height=x src="//cdn.example/x">', "https://fixture.example/", {})
    assert keys(result) == {"images-missing-alt", "images-missing-dimensions", "images-external-hosting"}
    assert result[1]["missing_loading"] == 1
    assert next(f for f in result[0] if f.defect_key == "images-missing-dimensions").confidence == "heuristic"


def test_social_metadata_handles_html_entities_and_unquoted_values():
    html = """<meta content='A &amp; B' property=og:title>
    <meta property=og:description content=description><meta content=/x property=og:image>
    <meta property=og:type content=website><meta content=summary name=twitter:card>
    <meta name=twitter:site content=@fixture>"""
    result = social_meta.analyse_html(html, "https://fixture.example/", {})
    assert keys(result) == set()
    assert result[1]["og_tags"]["title"] == "A & B"


def test_console_static_hints_do_not_claim_runtime_errors():
    result = browser_console.analyse_html('<p>document.write()</p><script>console.warn("hint")</script>', "https://fixture.example/", {})
    assert keys(result) == set()
    assert result[1]["console_log_calls"] == [{"level": "warn", "message": "hint"}]
    result = browser_console.analyse_html('<script>document.write("x")</script><img src="http://fixture.example/x">', "https://fixture.example/", {})
    assert keys(result) == {"console-document-write", "console-mixed-content"}


def test_console_requires_actual_capture_and_dedupes_events():
    assert keys(browser_console.analyse_rendered({"console_errors": []}, "https://fixture.example/")) == set()
    assert len(browser_console.analyse_rendered({"console_errors": ["broken", "broken"]}, "https://fixture.example/")[0]) == 1
    for data in ({}, {"console_errors": "missing"}, {"console_errors": [None]}):
        with pytest.raises(ValueError):
            browser_console.analyse_rendered(data, "https://fixture.example/")


@pytest.mark.parametrize("browser_status", ["ok", "error"])
def test_pipeline_registers_static_and_rendered_observations(tmp_path, monkeypatch, browser_status):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 443))])
    monkeypatch.setattr("auditor_toolkit.pipeline.run_browser_checks", lambda *a, **k: {
        "status": browser_status, "evidence": {"console_errors": ["fixture failure"], "resource_requests": ["https://cdn.example/x"], "axe": {"violations": []}, "images": []}})
    monkeypatch.setattr("auditor_toolkit.pipeline.export_pdf", lambda html, pdf, opts: pdf.write_bytes(b"%PDF fixture"))
    client = Fetcher(transport=httpx.MockTransport(lambda request: httpx.Response(200, text='<html lang=en><script src="//cdn.example/x"></script>', request=request)), min_interval=0)
    try:
        report = run_audit("https://fixture.example/", AuditOptions(output_root=tmp_path, browser=True), client)
    finally:
        client.close()
    for name in ("hreflang", "language", "images", "social_meta"):
        assert report["checks"][name]["status"] == "ok"
    for name in ("third_party", "browser_console"):
        assert report["checks"][name]["status"] == ("ok" if browser_status == "ok" else "skipped")
    assert "cookie_consent" in current_coverage_gaps(report)
    if browser_status == "ok":
        defects = {d["defect_key"]: d for d in report["defects"]}
        assert defects["third-party-requests"]["evidence_ref"] == "third_party"
        assert defects["browser-console-error"]["evidence_ref"] == "browser_console"


def test_failed_static_analyzer_retains_partial_coverage(tmp_path, monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 443))])
    monkeypatch.setattr(hreflang, "analyse_html", lambda *a: (_ for _ in ()).throw(ValueError("fixture failure")))
    client = Fetcher(transport=httpx.MockTransport(lambda request: httpx.Response(200, text='<html lang=en>', request=request)), min_interval=0)
    try:
        report = run_audit("https://fixture.example/", AuditOptions(output_root=tmp_path), client)
    finally:
        client.close()
    assert report["status"] == "partial"
    assert report["health_score"] is None
    assert current_coverage_gaps(report) == ["hreflang"]



def test_invalid_hreflang_annotations_are_observed():
    result = hreflang.analyse_html('<link rel=alternate hreflang=??? href=""><link rel=alternate hreflang=en href="http://[bad">', "https://fixture.example/", {})
    assert "hreflang-invalid" in keys(result)
    assert len(result[1]["invalid_links"]) == 2


def test_third_party_browser_capture_validation():
    for data in ({}, {"resource_requests": "absent"}, {"resource_requests": [None]}):
        with pytest.raises(ValueError):
            third_party.analyse_rendered(data, "https://fixture.example/")
    found, evidence = third_party.analyse_rendered({"resource_requests": [
        "https://fixture.example/x", "https://cdn.example/x", "https://cdn.example/y",
        "http://[bad", "data:image/png,x"]}, "https://fixture.example/")
    assert len(found) == 1
    assert evidence["external_request_count"] == 2

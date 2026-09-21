"""P4 deterministic audit-depth tests: robots, sitemap, headers, links, signals.

All $0 / offline (httpx.MockTransport): no browser, no paid services.
Every new finding must carry P5 evidence fields.
"""
from __future__ import annotations

import socket

import httpx

from auditor_toolkit.common import Fetcher
from auditor_toolkit.hygiene import (
    check_mixed_content,
    check_robots,
    check_sitemap,
    detect_conversion_signals,
    discover_internal_links,
    grade_security_headers,
    validate_links,
)

PUBLIC_ADDR = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 443))]

PAGE = (
    "<html><head><title>T</title>"
    '<meta name="description" content="D"><link rel="canonical" href="https://example.com/">'
    '<meta property="og:title" content="T"><meta name="viewport" content="width=device-width">'
    "</head><body><h1>Hi</h1><p>" + ("word " * 250) + "</p>"
    '<a href="/contact">Contact us</a><a href="tel:+6421000000">Call</a>'
    '<a href="/missing-page">Missing</a><a href="/gone">Gone</a>'
    '<img src="https://example.com/i.png" alt="x">'
    '<script type="application/ld+json">{"@type":"LocalBusiness"}</script>'
    "</body></html>"
)


def make_fetcher(routes: dict, monkeypatch) -> Fetcher:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: PUBLIC_ADDR)

    def handler(request):
        path = request.url.path or "/"
        status, body = routes.get(path, (200, PAGE))
        return httpx.Response(status, text=body, request=request)

    return Fetcher(transport=httpx.MockTransport(handler))


def assert_evidence_complete(findings, keys):
    assert {f.defect_key for f in findings} >= set(keys)
    for f in findings:
        assert f.observed or f.evidence_source or f.selector, f.defect_key
        assert f.remediation_action, f.defect_key
        assert f.effort_band in {"XS", "S", "M", "L", "XL"}, f.defect_key


def test_robots_missing_and_no_sitemap_flagged(monkeypatch):
    fetcher = make_fetcher({"/robots.txt": (404, "nope"), "/sitemap.xml": (404, "nope")}, monkeypatch)
    r_found, r_ev = check_robots(fetcher, "https://example.com/")
    assert r_ev["status_code"] == 404
    assert [f.defect_key for f in r_found] == ["robots-missing"]
    assert_evidence_complete(r_found, ["robots-missing"])
    s_found, s_ev = check_sitemap(fetcher, "https://example.com/")
    assert [f.defect_key for f in s_found] == ["sitemap-missing"]
    assert s_ev["checked"][0]["status"] == 404


def test_robots_with_sitemap_declared_is_clean(monkeypatch):
    body = "User-agent: *\nAllow: /\nSitemap: https://example.com/sitemap.xml"
    xml = '<?xml version="1.0"?><urlset><url><loc>https://example.com/</loc></url></urlset>'
    fetcher = make_fetcher({"/robots.txt": (200, body), "/sitemap.xml": (200, xml)}, monkeypatch)
    r_found, r_ev = check_robots(fetcher, "https://example.com/")
    assert r_found == []
    assert r_ev["sitemaps_declared"] == ["https://example.com/sitemap.xml"]
    s_found, s_ev = check_sitemap(fetcher, "https://example.com/", r_ev["sitemaps_declared"])
    assert s_found == []
    assert s_ev["checked"][0]["loc_count"] == 1


def test_malformed_sitemap_flagged(monkeypatch):
    fetcher = make_fetcher({"/sitemap.xml": (200, "<not xml")}, monkeypatch)
    s_found, s_ev = check_sitemap(fetcher, "https://example.com/")
    assert [f.defect_key for f in s_found] == ["sitemap-malformed"]
    assert s_ev["checked"][0]["well_formed"] is False


def test_security_header_grading():
    found, ev = grade_security_headers({}, "https://example.com/", deep=True)
    keys = {f.defect_key for f in found}
    assert "header-hsts" in keys
    assert "header-content-security-policy" in keys
    assert "header-referrer-policy" in keys
    assert_evidence_complete(found, keys)
    assert ev["present"] == []
    # default mode grades only the legacy-overlapping headers
    found_default, _ = grade_security_headers({}, "https://example.com/")
    default_keys = {f.defect_key for f in found_default}
    assert "header-referrer-policy" not in default_keys
    assert "header-hsts" in default_keys
    full = {
        "content-security-policy": "default-src 'self'",
        "x-content-type-options": "nosniff",
        "referrer-policy": "strict-origin",
        "permissions-policy": "camera=()",
        "strict-transport-security": "max-age=63072000",
    }
    found2, ev2 = grade_security_headers(full, "https://example.com/", deep=True)
    assert found2 == []
    assert sorted(ev2["present"]) == sorted(full.keys())
    found3, _ = grade_security_headers({}, "http://example.com/")
    assert "header-hsts" not in {f.defect_key for f in found3}


def test_conversion_signals_and_missing_contact_path():
    # presence signals are evidence-only: no deductions for having a path
    found, ev = detect_conversion_signals(PAGE, "https://example.com/")
    assert ev["signals"]["contact_path"] is True
    assert ev["signals"]["phone"] is True
    assert found == []
    assert "no-contact-path" not in {f.defect_key for f in found}
    bare = "<html><body><p>hello world</p></body></html>"
    found2, _ = detect_conversion_signals(bare, "https://example.com/")
    assert "no-contact-path" in {f.defect_key for f in found2}
    assert_evidence_complete(found2, ["no-contact-path"])
    # a page whose only conversion path is a mailto: link is NOT pathless
    mailto = '<html><body><a href="mailto:hi@example.com">Email us</a></body></html>'
    found3, ev3 = detect_conversion_signals(mailto, "https://example.com/")
    assert ev3["signals"]["contact_path"] is True
    assert "no-contact-path" not in {f.defect_key for f in found3}
    # a visible plain-text email address is also a contact path
    plain = "<html><body><p>Write to hello@example.co.nz for help</p></body></html>"
    found4, ev4 = detect_conversion_signals(plain, "https://example.com/")
    assert ev4["signals"]["contact_path"] is True
    assert "no-contact-path" not in {f.defect_key for f in found4}


def test_mixed_content_detection():
    html = '<html><img src="http://example.com/a.png"><script src="https://x/y.js"></script></html>'
    found, ev = check_mixed_content(html, "https://example.com/")
    assert [f.defect_key for f in found] == ["mixed-content"]
    assert ev["count"] == 1
    found2, _ = check_mixed_content(html, "http://example.com/")
    assert found2 == []


def test_broken_link_validation_bounded(monkeypatch):
    fetcher = make_fetcher(
        {"/missing-page": (404, "nf"), "/gone": (500, "err"), "/contact": (200, "ok")},
        monkeypatch,
    )
    links = discover_internal_links(PAGE, "https://example.com/")
    assert "https://example.com/missing-page" in links
    assert "https://example.com/contact" in links
    assert not any("tel:" in link for link in links)
    found, ev = validate_links(fetcher, "https://example.com/", links)
    keys = {f.defect_key for f in found}
    assert "broken-internal-link" in keys
    assert "server-error-link" in keys
    assert ev["broken"] == 1
    assert_evidence_complete(found, keys)


def test_pipeline_includes_hygiene_ux_and_links(tmp_path, monkeypatch):
    from auditor_toolkit.pipeline import AuditOptions, run_audit

    routes = {
        "/": (200, PAGE),
        "/robots.txt": (404, "nope"),
        "/sitemap.xml": (404, "nope"),
        "/contact": (200, "ok"),
        "/missing-page": (404, "nf"),
        "/gone": (200, "ok"),
    }
    fetcher = make_fetcher(routes, monkeypatch)
    monkeypatch.setattr("dns.resolver.Resolver.resolve", lambda self, name, kind: [])
    report = run_audit("https://example.com/", AuditOptions(output_root=tmp_path, deep=True), fetcher)
    assert report["status"] == "complete"
    assert report["checks"]["hygiene"]["status"] == "ok"
    assert "robots" in report["evidence"]["hygiene"]["data"]
    assert report["evidence"]["ux"]["data"]["signals"]["phone"] is True
    assert report["evidence"]["links"]["data"]["broken"] == 1
    keys = {d["defect_key"] for d in report["defects"]}
    assert {"robots-missing", "sitemap-missing", "broken-internal-link"} <= keys
    defect_ids = {d["finding_id"] for d in report["defects"]}
    assert {d["finding_id"] for d in report["breakdown"]["deductions"]} <= defect_ids
    for d in report["defects"]:
        if d["defect_key"] in {
            "robots-missing", "sitemap-missing", "broken-internal-link", "no-contact-path",
        }:
            assert d.get("evidence_summary"), d["defect_key"]

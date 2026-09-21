import json
import socket
import subprocess
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from auditor_toolkit.actions import import_report, preview_report
from auditor_toolkit.ai import fallback_drafts, generate_drafts
from auditor_toolkit.checks import classify_response
from auditor_toolkit.common import Fetcher, validate_url
from auditor_toolkit.pipeline import AuditOptions, run_audit
from auditor_toolkit.portal import create_app, setup_password
from auditor_toolkit.storage import History

HEALTHY = (
    """<!doctype html><html lang="en"><head><title>Local services</title>
<meta name="description" content="Useful services"><meta name="viewport" content="width=device-width">
<link rel="canonical" href="https://example.com/"><meta property="og:title" content="Services">
<script type="application/ld+json">{"@type":"LocalBusiness"}</script></head>
<body><main><h1>Services</h1><p>"""
    + ("Useful business information " * 100)
    + "</p></main></body></html>"
)
HEADERS = {
    "content-type": "text/html",
    "content-security-policy": "default-src 'self'",
    "strict-transport-security": "max-age=1000",
    "x-content-type-options": "nosniff",
}


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 443))],
    )


def fixture_audit(root, body=HEALTHY, **kwargs):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, text=body, headers=HEADERS, request=request)
    )
    client = Fetcher(transport=transport, min_interval=0)
    try:
        return run_audit("https://example.com/", AuditOptions(output_root=root, **kwargs), client)
    finally:
        client.close()


def test_healthy_defective_history_and_counts(tmp_path):
    healthy = fixture_audit(tmp_path)
    assert healthy["health_score"] == 100
    defective = fixture_audit(tmp_path, '<h1>Broken</h1><img src="a"><img src="b">')
    assert defective["health_score"] < 100
    assert len({d["finding_id"] for d in defective["defects"]}) == defective["defect_count"]
    assert defective["action_preview"]["count"] == defective["defect_count"]
    fixed = fixture_audit(tmp_path)
    assert len(fixed["comparison"]["resolved"]) == defective["defect_count"]
    regressed = fixture_audit(tmp_path, '<h1>Broken</h1><img src="a"><img src="b">')
    assert regressed["comparison"]["regressed"]
    history = History(tmp_path)
    identity = defective["defects"][0]["finding_id"]
    with pytest.raises(ValueError):
        history.transition(identity, "verified", {"verification_run": defective["run_id"]})
    history.transition(identity, "verified", {"verification_run": fixed["run_id"]})
    assert history.get(regressed["run_id"])["defect_count"] == regressed["defect_count"]


def test_browser_plugin_failure_is_partial(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "auditor_toolkit.pipeline.run_browser_checks",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("browser unavailable")),
    )
    monkeypatch.setattr(
        "auditor_toolkit.pipeline.export_pdf",
        lambda *a: (_ for _ in ()).throw(RuntimeError("no PDF")),
    )
    report = fixture_audit(tmp_path, browser=True)
    assert report["health_score"] is None
    assert report["status"] == "partial"
    assert report["checks"]["browser"]["status"] == "error"
    assert report["checks"]["pdf"]["status"] == "error"


def test_page_plugin_failure_visible(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "auditor_toolkit.pipeline.analyse_html",
        lambda *a: (_ for _ in ()).throw(RuntimeError("plugin crash")),
    )
    report = fixture_audit(tmp_path)
    assert report["checks"]["page"]["reason"] == "plugin crash"
    assert report["health_score"] is None


def test_failed_fetch_and_dns_are_not_healthy(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "auditor_toolkit.pipeline.inspect_dns",
        lambda *a: (_ for _ in ()).throw(RuntimeError("DNS timeout")),
    )
    report = fixture_audit(tmp_path, deep=True)
    assert report["checks"]["dns"]["status"] == "error"
    assert report["health_score"] is None
    client = Fetcher(transport=httpx.MockTransport(lambda r: httpx.Response(503, request=r)))
    failed = run_audit("https://example.com/", AuditOptions(output_root=tmp_path), client)
    assert failed["health_score"] is None
    assert failed["checks"]["page"]["status"] == "skipped"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://127.0.0.1",
        "http://169.254.169.254",
        "http://[::1]",
        "http://user:password@example.com",
    ],
)
def test_invalid_urls(url):
    with pytest.raises(ValueError):
        validate_url(url)


def test_response_limit_and_soft404():
    with pytest.raises(ValueError):
        Fetcher(
            max_bytes=5,
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, content=b"123456", request=r)
            ),
        ).get("https://example.com")
    assert classify_response(200, "<h1>Our 404 repair guide</h1>")[0] == "ok"
    assert classify_response(200, "<title>Page not found</title>")[1][0].review_required


def test_conditional_cache_keeps_observation_timestamp(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, text="hello", headers={"etag": "one"}, request=request)
        assert request.headers["if-none-match"] == "one"
        return httpx.Response(304, request=request)

    fetcher = Fetcher(cache_dir=tmp_path, transport=httpx.MockTransport(handler), min_interval=0)
    original = fetcher.get("https://example.com")
    cached = fetcher.get("https://example.com")
    assert original.extensions["observed_at"] == cached.extensions["observed_at"]
    assert cached.text == "hello"


def test_portal_sessions_csrf_injection_and_artifacts(tmp_path):
    report = fixture_audit(tmp_path, '<img src="&lt;script&gt;bad&lt;/script&gt;">')
    setup_password(tmp_path, "long fixture password")
    app = create_app(tmp_path)
    client = TestClient(app)
    assert client.get("/api/session", cookies={"wa_session": "forged"}).status_code == 401
    assert client.get("/artifacts/" + report["run_id"] + "/html").status_code == 401
    assert client.post("/login", data={"password": "wrong"}).status_code == 401
    assert client.post("/login", data={"password": "long fixture password"}).status_code == 200
    token = client.get("/api/session").json()["csrf"]
    assert client.get("/?q=%3Cscript%3E").text.find("<script>") == -1
    assert client.get("/artifacts/" + report["run_id"] + "/unknown").status_code == 404
    artifact = client.get("/artifacts/" + report["run_id"] + "/html")
    assert artifact.status_code == 200 and "attachment" in artifact.headers["content-disposition"]
    identity = report["defects"][0]["finding_id"]
    assert (
        client.post("/api/remediations/" + identity, json={"state": "patched"}).status_code == 403
    )
    assert (
        client.post(
            "/api/remediations/" + identity,
            json={"state": "patched"},
            headers={"x-csrf-token": token},
        ).status_code
        == 200
    )
    assert client.post("/logout").status_code == 403
    assert client.post("/logout", headers={"x-csrf-token": token}).status_code == 200
    assert client.get("/api/session").status_code == 401
    client.post("/login", data={"password": "long fixture password"})
    for entry in app.state.sessions.values():
        entry["expires"] = 0
    assert client.get("/api/session").status_code == 401


def test_registered_artifact_cannot_escape_or_change(tmp_path):
    report = fixture_audit(tmp_path)
    history = History(tmp_path)
    Path(report["artifacts"]["html"]).write_text("tampered")
    with pytest.raises(ValueError, match="integrity"):
        history.artifact(report["run_id"], "html")
    outside = tmp_path / "secret"
    outside.write_text("secret")
    report["artifacts"]["html"] = str(outside)
    with history.connect() as db:
        db.execute("UPDATE runs SET report=? WHERE id=?", (json.dumps(report), report["run_id"]))
    with pytest.raises(ValueError, match="Unregistered"):
        history.artifact(report["run_id"], "html")


def test_previews_are_idempotent_and_never_execute(tmp_path, monkeypatch):
    report = fixture_audit(tmp_path)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("No subprocess allowed")),
    )
    output = tmp_path / "previews"
    preview_report(report, output)
    preview_report(report, output)
    assert len(json.loads((output / "events.json").read_text())) == 1
    from website_auditor.connectors.git_connector import GitConnector

    action = SimpleNamespace(action_id="../escape", name="test", payload={})
    result = GitConnector(output).execute_local_patch(action)
    assert result["status"] == "preview" and not result["committed"]
    assert Path(result["file"]).parent == output


def test_malformed_import_rejected(tmp_path):
    path = tmp_path / "old.json"
    path.write_text('{"random":[{"issue":"Missing title"}]}')
    with pytest.raises(ValueError):
        import_report(path)


def test_ai_timeout_and_malformed_output_fall_back(monkeypatch):
    monkeypatch.setattr("auditor_toolkit.ai.verify_model", lambda: {"ready": True})
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("worker", 1)),
    )
    result = generate_drafts({}, enabled=True, timeout=1)
    assert result["status"] == "fallback" and "TimeoutExpired" in result["reason"]
    assert set(result["drafts"]) == set(fallback_drafts())
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="{}"))
    assert generate_drafts({}, enabled=True)["status"] == "fallback"

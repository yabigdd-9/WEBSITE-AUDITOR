from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
import sys
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

from integrations.auditor_mcp import TOOLS, tool_specs, serve as mcp_serve
from integrations.registry import integrations_status, format_integrations_status
from integrations.schemas import EventEnvelope, JobHandoff
from integrations.security import redact, verify_agent_token, verify_github_signature
from integrations import webhooks

_MM_DIR = str(Path(__file__).resolve().parents[1] / "money-machine")
sys.path.insert(0, _MM_DIR)
try:
    import mm_operator
finally:
    sys.path.remove(_MM_DIR)


def event_doc(**overrides):
    value = {"event_id": "evt-1", "type": "audit.completed", "source": "auditor",
             "created_at": datetime.now(timezone.utc).isoformat(), "correlation_id": "job-1",
             "payload": {"business_id": 3}, "schema_version": 1}
    value.update(overrides)
    return value


def test_event_schema_strict_and_timezone_aware():
    assert EventEnvelope.parse(event_doc()).type == "audit.completed"
    with pytest.raises(ValueError): EventEnvelope.parse(event_doc(extra=True))
    with pytest.raises(ValueError): EventEnvelope.parse(event_doc(type="shell.exec"))
    with pytest.raises(ValueError): EventEnvelope.parse(event_doc(created_at="2026-09-24T00:00:00"))


def test_job_handoff_enforces_zero_cost_and_approval():
    job = {"job_id": "job-1", "parent_job_id": None, "task_type": "audit", "objective": "Audit a public website",
           "repository": "WEBSITE-AUDITOR", "assigned_to": "Hermes", "constraints": {"paid_allowed": False, "max_cost_usd": 0},
           "artifacts": [], "status": "pending", "created_at": datetime.now(timezone.utc).isoformat(),
           "updated_at": datetime.now(timezone.utc).isoformat(), "retries": 0, "provenance": {}}
    assert JobHandoff.parse(job).job_id == "job-1"
    with pytest.raises(ValueError): JobHandoff.parse({**job, "constraints": {"paid_allowed": True, "max_cost_usd": 0}})
    with pytest.raises(ValueError): JobHandoff.parse({**job, "constraints": {"paid_allowed": False, "max_cost_usd": 0, "send": True}})


def test_github_and_agent_authentication_and_redaction():
    body, secret = b'{"action":"opened"}', "test-webhook-secret"
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_github_signature(body, signature, secret)
    assert not verify_github_signature(body, signature, "wrong")
    assert verify_agent_token("agent-token", "agent-token")
    assert not verify_agent_token("wrong", "agent-token")
    cleaned = redact({"Authorization": "Bearer abc", "message": "api_key=supersecret sk-12345678901234567890"})
    assert "supersecret" not in json.dumps(cleaned)
    assert "12345678901234567890" not in json.dumps(cleaned)


def test_event_dedupe_uses_sqlite(tmp_path, monkeypatch):
    monkeypatch.setenv("MM_ROOT", str(tmp_path))
    monkeypatch.setattr(webhooks, "_db", lambda: __import__("sqlite3").connect(tmp_path / "events.db"))
    # Use a minimal sqlite-compatible adapter with the project's received timestamp expression.
    import sqlite3
    def db():
        con = sqlite3.connect(tmp_path / "events.db")
        con.execute("CREATE TABLE IF NOT EXISTS integration_events(event_id TEXT PRIMARY KEY, event_type TEXT, source TEXT, correlation_id TEXT, created_at TEXT, payload_json TEXT, received_at TEXT)")
        con.commit()
        return con
    monkeypatch.setattr(webhooks, "_db", db)
    item = EventEnvelope.parse(event_doc())
    assert webhooks.record_event(item) is True
    assert webhooks.record_event(item) is False


def test_mcp_tool_allowlist_and_no_dangerous_capabilities():
    names = {item["name"] for item in tool_specs()}
    assert names == {item[0] for item in TOOLS}
    assert {"queue_submit", "proof_build", "obsidian_sync"} <= names
    assert not any(token in name for name in names for token in ("shell", "send_email", "deploy", "purchase", "credential"))
    assert all(item["inputSchema"]["additionalProperties"] is False for item in tool_specs())


def test_integration_status_masks_credentials(monkeypatch):
    monkeypatch.setenv("FCC_BASE_URL", "http://127.0.0.1:8082")
    monkeypatch.setenv("OPENROUTER_API_KEY", "api-key=should-never-render")
    status = integrations_status()
    rendered = json.dumps(status)
    assert "should-never-render" not in rendered
    assert status["routing"]["paid_allowed"] is False
    assert status["routing"]["max_cost_usd"] == 0
    assert next(x for x in status["integrations"] if x["name"] == "FCC")["endpoint"] == "http://127.0.0.1:8082"
    omni = next(x for x in status["integrations"] if x["name"] == "OmniRoute")
    assert omni["endpoint"] == "http://127.0.0.1:20128"
    assert omni["health"] in {"healthy", "unavailable"}
    assert next(x for x in status["integrations"] if x["name"] == "OmniRoute MCP")["health"] in {"disabled", "offline", "unknown"}
    assert next(x for x in status["integrations"] if x["name"] == "OmniRoute A2A")["health"] in {"disabled", "offline", "unknown"}
    gateway = next(x for x in status["integrations"] if x["name"] == "WEBSITE-AUDITOR A2A gateway")
    assert gateway["endpoint"] == "http://127.0.0.1:8094"
    assert gateway["safety"]["max_cost_usd"] == 0


def test_integration_status_human_output_includes_endpoint_health_error_and_safety():
    rendered = format_integrations_status({
        "generated_at": "2026-09-24T00:00:00+00:00",
        "integrations": [{
            "name": "Example MCP", "endpoint": "http://127.0.0.1:8765/mcp",
            "protocol": "streamable-http", "capability": "local tools",
            "health": "unavailable", "last_error": "ConnectionRefusedError",
            "safety": {"paid_allowed": False, "max_cost_usd": 0, "send_enabled": False},
        }],
        "routing": {"primary": "OmniRoute", "compatibility": "FCC", "local": "Ollama",
                    "paid_allowed": False, "max_cost_usd": 0, "fallback": "DEFER"},
    })
    assert "Example MCP: UNAVAILABLE" in rendered
    assert "http://127.0.0.1:8765/mcp" in rendered
    assert "Last error: ConnectionRefusedError" in rendered
    assert "paid_allowed=False; max_cost_usd=0; send_enabled=False" in rendered
    assert "fallback=DEFER" in rendered


def test_omniroute_status_maps_reported_disabled_and_offline(monkeypatch):
    from integrations import registry
    monkeypatch.setattr(registry, "_omniroute_feature_status", lambda url, path: (
        ("offline", None, {"status": "offline", "enabled": True, "online": False})
        if path.endswith("mcp/status") else
        ("disabled", None, {"status": "disabled", "enabled": False, "online": False})
    ))
    status = integrations_status()
    entries = {item["name"]: item for item in status["integrations"]}
    assert entries["OmniRoute MCP"]["health"] == "offline"
    assert entries["OmniRoute A2A"]["health"] == "disabled"


def test_webhook_receiver_rejects_unsigned_github_and_dedupes(monkeypatch, tmp_path):
    import sqlite3
    def db():
        con = sqlite3.connect(tmp_path / "requests.db")
        con.execute("CREATE TABLE IF NOT EXISTS integration_events(event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL, source TEXT NOT NULL, correlation_id TEXT NOT NULL, created_at TEXT NOT NULL, payload_json TEXT NOT NULL, received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        con.commit()
        return con
    monkeypatch.setattr(webhooks, "_db", db)
    server = ThreadingHTTPServer(("127.0.0.1", 0), webhooks.Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        body = json.dumps(event_doc()).encode()
        req = Request(base + "/events", data=body, headers={"Content-Type": "application/json"}, method="POST")
        assert json.load(urlopen(req))["duplicate"] is False
        req = Request(base + "/events", data=body, headers={"Content-Type": "application/json"}, method="POST")
        assert json.load(urlopen(req))["duplicate"] is True
        req = Request(base + "/webhooks/github", data=b'{"action":"opened"}', headers={"Content-Type": "application/json"}, method="POST")
        with pytest.raises(HTTPError) as error: urlopen(req)
        assert error.value.code == 401
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def test_webhook_server_operator_command_defaults_to_loopback(monkeypatch):
    called = {}
    monkeypatch.setattr(webhooks, "serve", lambda **kwargs: called.update(kwargs))
    assert mm_operator.main(["webhook-server"]) == 0
    assert called == {"host": "127.0.0.1", "port": None}


def test_webhook_receiver_refuses_non_loopback_bind():
    with pytest.raises(ValueError, match="loopback"):
        webhooks.serve(host="0.0.0.0", port=8093)


def test_mcp_stdio_initialize_and_tool_list():
    import io
    def frame(obj):
        raw = json.dumps(obj).encode()
        return b"Content-Length: " + str(len(raw)).encode() + b"\r\n\r\n" + raw
    source = io.BytesIO(frame({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) +
                        frame({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}))
    destination = io.BytesIO()
    mcp_serve(source, destination)
    assert b'"name":"website-auditor"' in destination.getvalue()
    assert b'"name":"queue_submit"' in destination.getvalue()

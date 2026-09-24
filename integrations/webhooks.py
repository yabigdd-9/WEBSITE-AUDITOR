"""Loopback-only, bounded webhook receiver with SQLite event deduplication."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import hmac
import json
import os
from pathlib import Path
import sys

from integrations.schemas import EventEnvelope
from integrations.security import redact, verify_agent_token, verify_github_signature

MM = Path(__file__).resolve().parents[1] / "money-machine"
if str(MM) not in sys.path:
    sys.path.insert(0, str(MM))


def _db():
    import mm_core
    db = mm_core.connect()
    db.execute("CREATE TABLE IF NOT EXISTS integration_events(event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL, source TEXT NOT NULL, correlation_id TEXT NOT NULL, created_at TEXT NOT NULL, payload_json TEXT NOT NULL, received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_integration_events_correlation ON integration_events(correlation_id)")
    return db


def record_event(envelope: EventEnvelope) -> bool:
    from mm_core import now
    import sqlite3
    db = _db()
    try:
        before = db.total_changes
        db.execute("INSERT OR IGNORE INTO integration_events(event_id,event_type,source,correlation_id,created_at,payload_json,received_at) VALUES(?,?,?,?,?,?,?)",
                   (envelope.event_id, envelope.type, envelope.source, envelope.correlation_id, envelope.created_at,
                    json.dumps(envelope.payload, sort_keys=True, separators=(",", ":")), now()))
        db.commit()
        return db.total_changes > before
    except sqlite3.Error:
        db.rollback()
        raise
    finally:
        db.close()


def _event_from_request(route: str, body: dict) -> EventEnvelope:
    if set(body) == {"event_id", "type", "source", "created_at", "correlation_id", "payload", "schema_version"}:
        return EventEnvelope.parse(body)
    allowed = {"/webhooks/github": "github", "/webhooks/agent": "agent", "/webhooks/audit": "auditor", "/webhooks/provider": "provider"}
    if route not in allowed:
        raise ValueError("Unknown webhook route")
    event_type = body.get("type")
    payload = body.get("payload", body)
    if route == "/webhooks/github":
        action = body.get("action")
        mapping = {"opened": "github.pr_opened", "completed": "github.ci_passed", "failure": "github.ci_failed"}
        event_type = mapping.get(action, event_type)
        if not event_type:
            raise ValueError("Unsupported GitHub webhook action")
    return EventEnvelope.create(event_type, allowed[route], payload, body.get("correlation_id"))


class Handler(BaseHTTPRequestHandler):
    server_version = "WebsiteAuditorWebhook/1"
    sys_version = ""
    max_body = 256_000

    def log_message(self, fmt, *args):
        # Never emit headers/body because either may contain secrets.
        return

    def _reply(self, status, data):
        raw = json.dumps(redact(data), separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path != "/health":
            return self._reply(404, {"error": "not_found"})
        self._reply(200, {"status": "ok", "bind": self.server.server_address[0]})

    def do_POST(self):
        if self.path not in {"/webhooks/github", "/webhooks/agent", "/webhooks/audit", "/webhooks/provider", "/events"}:
            return self._reply(404, {"error": "not_found"})
        try:
            length = int(self.headers.get("Content-Length", "-1"))
            if not 0 <= length <= self.max_body:
                return self._reply(413, {"error": "invalid_body_size"})
            raw = self.rfile.read(length)
            if self.path == "/webhooks/github":
                if not verify_github_signature(raw, self.headers.get("X-Hub-Signature-256"), os.environ.get("GITHUB_WEBHOOK_SECRET")):
                    return self._reply(401, {"error": "signature_invalid"})
            elif self.path == "/webhooks/agent":
                supplied = self.headers.get("Authorization", "").removeprefix("Bearer ")
                if not verify_agent_token(supplied, os.environ.get("MM_AGENT_WEBHOOK_TOKEN")):
                    return self._reply(401, {"error": "authentication_required"})
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise ValueError("JSON object required")
            envelope = _event_from_request("/webhooks/audit" if self.path == "/events" else self.path, body)
            fresh = record_event(envelope)
            self._reply(202 if fresh else 200, {"accepted": True, "duplicate": not fresh, "event_id": envelope.event_id, "correlation_id": envelope.correlation_id})
        except (ValueError, json.JSONDecodeError) as exc:
            self._reply(400, {"error": str(redact(str(exc)))})
        except Exception as exc:
            self._reply(500, {"error": "event_store_unavailable", "detail": type(exc).__name__})


def serve(host: str | None = None, port: int | None = None):
    host = host or os.environ.get("MM_WEBHOOK_HOST", "127.0.0.1")
    port = int(port or os.environ.get("MM_WEBHOOK_PORT", "8093"))
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("Webhook receiver must bind to loopback")
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    print(json.dumps({"status": "listening", "endpoint": f"http://{host}:{port}", "external_sends": 0}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    serve()

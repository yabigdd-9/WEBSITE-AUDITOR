import contextlib
import http.client
import importlib
import json
import os
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import mm_bridge as bridge


class FakeDB:
    def __init__(self, rows=None, inserted_id=42):
        self.rows = list(rows or [])
        self.inserted_id = inserted_id
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if sql.lstrip().startswith("SELECT id,name,public_website"):
            return list(self.rows)
        if sql.lstrip().startswith("INSERT INTO businesses"):
            return SimpleNamespace(lastrowid=self.inserted_id)
        return SimpleNamespace(lastrowid=None)


def handler():
    return object.__new__(bridge.BridgeHandler)


@pytest.mark.parametrize(
    "value,expected",
    [("1", 1), (1, 1), (str(bridge.MAX_ID), bridge.MAX_ID)],
)
def test_safe_int_accepts_valid(value, expected):
    assert bridge._safe_int(value) == expected


@pytest.mark.parametrize("value", [None, "", "abc", 0, -1, bridge.MAX_ID + 1])
def test_safe_int_rejects_invalid(value):
    with pytest.raises(ValueError):
        bridge._safe_int(value)


def test_scalar_map_collapses_query_values():
    assert bridge._scalar_map({"a": ["1", "2"], "b": "x"}) == {"a": "2", "b": "x"}


def test_require_token_fail_closed(monkeypatch):
    monkeypatch.delenv("MM_BRIDGE_TOKEN", raising=False)
    assert bridge._require_token("Bearer anything") == (False, "bridge token not configured")

    monkeypatch.setenv("MM_BRIDGE_TOKEN", "secret")
    assert bridge._require_token(None)[0] is False
    assert bridge._require_token("Basic secret")[0] is False
    assert bridge._require_token("Bearer wrong")[0] is False
    assert bridge._require_token("Bearer secret") == (True, None)


def test_dispatch_forbids_external_send():
    h = handler()
    for action in bridge.FORBIDDEN_ACTIONS:
        with pytest.raises(PermissionError):
            h._dispatch(action, {})


def test_dispatch_rejects_unknown_action():
    with pytest.raises(ValueError, match="unknown action"):
        handler()._dispatch("definitely-not-real", {})


def test_status_doctor_email_and_preflight(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(bridge.core, "connect", lambda readonly=False: db)
    monkeypatch.setattr(bridge.operator, "run_day", lambda d, write=False: {"status": "ok", "write": write})
    monkeypatch.setattr(bridge.operator, "doctor", lambda d: {"db_integrity": "ok"})
    monkeypatch.setattr(bridge.email_store, "status", lambda d, bid: {"business_id": bid})
    monkeypatch.setattr(bridge.outreach, "preflight", lambda d, mid: {"message_id": mid, "passed": False})

    h = handler()
    assert h._dispatch("status", {})["write"] is False
    assert h._dispatch("doctor", {})["db_integrity"] == "ok"
    assert h._dispatch("email-status", {"id": "7"}) == {"business_id": 7}
    assert h._dispatch("outreach-preflight", {"id": "9"}) == {"message_id": 9, "passed": False}


def test_intake_success(monkeypatch):
    db = FakeDB(inserted_id=73)
    monkeypatch.setattr(bridge.core, "connect", lambda readonly=False: db)
    monkeypatch.setattr(bridge.core, "public_url", lambda url: "example.test")
    monkeypatch.setattr(bridge.core, "now", lambda: "2026-09-21T00:00:00+00:00")
    events = []
    monkeypatch.setattr(bridge.core, "event", lambda d, kind, bid, source: events.append((kind, bid, source)))

    result = handler()._dispatch(
        "intake",
        {"name": "Example Ltd", "url": "https://example.test", "region": "Canterbury", "source": "test"},
    )

    assert result == {"business_id": 73}
    assert events == [("intake", 73, "test")]
    assert any("INSERT INTO businesses" in sql for sql, _ in db.calls)
    assert any("INSERT INTO mm_deals" in sql for sql, _ in db.calls)


def test_intake_duplicate_is_blocked(monkeypatch):
    db = FakeDB(rows=[{"id": 3, "name": "Example Ltd", "public_website": "https://example.test"}])
    monkeypatch.setattr(bridge.core, "connect", lambda readonly=False: db)
    monkeypatch.setattr(bridge.core, "public_url", lambda url: "example.test")

    with pytest.raises(ValueError, match="duplicate prospect"):
        handler()._dispatch(
            "intake",
            {"name": "Example Ltd", "url": "https://example.test", "region": "Canterbury"},
        )


@pytest.mark.parametrize(
    "params,message",
    [
        ({"name": "", "url": "https://example.test", "region": "Canterbury"}, "intake requires"),
        ({"name": "X", "url": "", "region": "Canterbury"}, "intake requires"),
        ({"name": "X", "url": "https://example.test", "region": ""}, "intake requires"),
    ],
)
def test_intake_requires_identity_fields(params, message):
    with pytest.raises(ValueError, match=message):
        handler()._dispatch("intake", params)


def test_audit_success(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(bridge.core, "connect", lambda readonly=False: db)
    captured = {}

    def record_evidence(d, bid, url, observation, limitation, capture, status, method, confidence, claim_type):
        captured.update(
            bid=bid,
            url=url,
            observation=observation,
            limitation=limitation,
            capture=capture,
            status=status,
            method=method,
            confidence=confidence,
            claim_type=claim_type,
        )
        return 88

    monkeypatch.setattr(bridge.core, "record_evidence", record_evidence)

    result = handler()._dispatch(
        "audit",
        {
            "id": "5",
            "url": "https://example.test",
            "observation": "Missing CTA",
            "limitation": "Public homepage only",
            "capture": "sha256:abc",
            "status": "verified",
            "method": "browser",
            "confidence": "0.9",
            "claim_type": "website_quality",
        },
    )
    assert result == {"evidence_id": 88}
    assert captured["bid"] == 5
    assert captured["confidence"] == 0.9


@pytest.mark.parametrize(
    "params,error",
    [
        ({"id": 1}, "audit requires"),
        (
            {
                "id": 1, "url": "u", "observation": "o", "limitation": "l", "capture": "c",
                "status": "not-a-status",
            },
            "invalid evidence status",
        ),
        (
            {
                "id": 1, "url": "u", "observation": "o", "limitation": "l", "capture": "c",
                "claim_type": "made-up",
            },
            "invalid claim-type",
        ),
        (
            {
                "id": 1, "url": "u", "observation": "o", "limitation": "l", "capture": "c",
                "confidence": "not-a-number",
            },
            "confidence must be numeric",
        ),
    ],
)
def test_audit_validation(params, error):
    with pytest.raises(ValueError, match=error):
        handler()._dispatch("audit", params)


@pytest.fixture
def live_server(monkeypatch):
    monkeypatch.setenv("MM_BRIDGE_TOKEN", "unit-secret")
    db = FakeDB()
    monkeypatch.setattr(bridge.core, "connect", lambda readonly=False: db)
    monkeypatch.setattr(bridge.operator, "run_day", lambda d, write=False: {"status": "ok"})

    server = bridge.http.server.ThreadingHTTPServer(("127.0.0.1", 0), bridge.BridgeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def request(server, path, token=None, method="GET", body=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=3)
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    payload = None
    if body is not None:
        payload = json.dumps(body)
        headers["Content-Type"] = "application/json"
    conn.request(method, path, body=payload, headers=headers)
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    return resp.status, json.loads(raw.decode())


def test_http_auth_and_status(live_server):
    status, body = request(live_server, "/status")
    assert status == 401
    assert body["ok"] is False

    status, body = request(live_server, "/status", token="wrong")
    assert status == 401

    status, body = request(live_server, "/status", token="unit-secret")
    assert status == 200
    assert body["result"] == {"status": "ok"}
    assert body["request_id"]


def test_http_forbidden_and_unknown(live_server):
    status, body = request(live_server, "/send", token="unit-secret")
    assert status == 403
    assert "forbidden action" in body["error"]

    status, body = request(live_server, "/unknown", token="unit-secret")
    assert status == 422
    assert "unknown action" in body["error"]


def test_parse_action_and_request_id():
    h = handler()
    h.path = "/email-status?id=12&id=13"
    action, params = h._parse_action()
    assert action == "email-status"
    assert params == {"id": "13"}

    h.client_address = ("127.0.0.1", 1234)
    rid = h._request_id()
    assert isinstance(rid, str)
    assert len(rid) == 16

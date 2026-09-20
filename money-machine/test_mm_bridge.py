import importlib.util
import io
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "money-machine" / "mm_bridge.py"
spec = importlib.util.spec_from_file_location("mm_bridge_under_test", MODULE_PATH)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


def handler():
    h = object.__new__(bridge.BridgeHandler)
    h.path = "/status"
    h.headers = {}
    h.client_address = ("127.0.0.1", 12345)
    return h


def fake_connection():
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.__exit__.return_value = False
    return conn


def test_scalar_map_and_safe_int():
    assert bridge._scalar_map({"a": ["1", "2"], "b": "x"}) == {"a": "2", "b": "x"}
    assert bridge._safe_int("7") == 7
    with pytest.raises(ValueError):
        bridge._safe_int("bad")
    with pytest.raises(ValueError):
        bridge._safe_int("0")
    with pytest.raises(ValueError):
        bridge._safe_int(str(bridge.MAX_ID + 1))


def test_require_token(monkeypatch):
    monkeypatch.delenv("MM_BRIDGE_TOKEN", raising=False)
    assert bridge._require_token(None) == (False, "bridge token not configured")

    monkeypatch.setenv("MM_BRIDGE_TOKEN", "secret")
    assert bridge._require_token(None) == (False, "missing bearer token")
    assert bridge._require_token("Token secret") == (False, "missing bearer token")
    assert bridge._require_token("Bearer wrong") == (False, "invalid bearer token")
    assert bridge._require_token("Bearer secret") == (True, None)


def test_parse_action():
    h = handler()
    h.path = "/email-status?id=42&id=43"
    action, params = h._parse_action()
    assert action == "email-status"
    assert params == {"id": "43"}


def test_read_body_json_and_form():
    h = handler()
    raw = json.dumps({"name": "Example"}).encode()
    h.headers = {"Content-Length": str(len(raw)), "Content-Type": "application/json"}
    h.rfile = io.BytesIO(raw)
    assert h._read_body() == {"name": "Example"}

    raw = b"id=3&name=Test"
    h.headers = {"Content-Length": str(len(raw)), "Content-Type": "application/x-www-form-urlencoded"}
    h.rfile = io.BytesIO(raw)
    assert h._read_body() == {"id": "3", "name": "Test"}

    h.headers = {"Content-Length": str(bridge.MAX_BODY + 1)}
    h.rfile = io.BytesIO()
    with pytest.raises(ValueError):
        h._read_body()


def test_json_response_helpers():
    h = handler()
    h.send_response = MagicMock()
    h.send_header = MagicMock()
    h.end_headers = MagicMock()
    h.wfile = io.BytesIO()
    h._json(200, {"ok": True})
    h.send_response.assert_called_once_with(200)
    assert json.loads(h.wfile.getvalue()) == {"ok": True}


def test_dispatch_rejects_send_and_unknown():
    h = handler()
    with pytest.raises(PermissionError):
        h._dispatch("send", {})
    with pytest.raises(PermissionError):
        h._dispatch("record-sent", {})
    with pytest.raises(ValueError):
        h._dispatch("does-not-exist", {})


def test_dispatch_read_actions():
    h = handler()
    conn = fake_connection()

    with patch.object(bridge.core, "connect", return_value=conn), patch.object(
        bridge.operator, "run_day", return_value={"status": "ok"}
    ):
        assert h._dispatch("status", {}) == {"status": "ok"}

    with patch.object(bridge.core, "connect", return_value=conn), patch.object(
        bridge.operator, "doctor", return_value={"db_integrity": "ok"}
    ):
        assert h._dispatch("doctor", {}) == {"db_integrity": "ok"}

    with patch.object(bridge.core, "connect", return_value=conn), patch.object(
        bridge.email_store, "status", return_value={"selected": None}
    ) as status:
        assert h._dispatch("email-status", {"id": "5"}) == {"selected": None}
        status.assert_called_once_with(conn, 5)

    with patch.object(bridge.core, "connect", return_value=conn), patch.object(
        bridge.outreach, "preflight", return_value={"passed": False}
    ) as preflight:
        assert h._dispatch("outreach-preflight", {"id": "8"}) == {"passed": False}
        preflight.assert_called_once_with(conn, 8)


def test_dispatch_intake_and_duplicate():
    h = handler()
    conn = fake_connection()

    def execute(sql, params=None):
        if sql.startswith("SELECT id,name,public_website"):
            return []
        if sql.startswith("INSERT INTO businesses"):
            return SimpleNamespace(lastrowid=42)
        return MagicMock()

    conn.execute.side_effect = execute
    with patch.object(bridge.core, "connect", return_value=conn), patch.object(
        bridge.core, "public_url", return_value="example.com"
    ), patch.object(bridge.core, "event") as event:
        result = h._dispatch(
            "intake",
            {"name": "Example Ltd", "url": "https://example.com", "region": "Canterbury"},
        )
    assert result == {"business_id": 42}
    event.assert_called_once()

    existing = {"id": 9, "name": "Example Ltd", "public_website": "https://example.com"}
    conn.execute.side_effect = lambda sql, params=None: [existing] if sql.startswith("SELECT") else MagicMock()
    with patch.object(bridge.core, "connect", return_value=conn), patch.object(
        bridge.core, "public_url", return_value="example.com"
    ):
        with pytest.raises(ValueError, match="duplicate prospect"):
            h._dispatch(
                "intake",
                {"name": "Example Ltd", "url": "https://example.com", "region": "Canterbury"},
            )

    with pytest.raises(ValueError, match="intake requires"):
        h._dispatch("intake", {"name": "Only name"})


def test_dispatch_audit_validation_and_write():
    h = handler()
    conn = fake_connection()
    payload = {
        "id": "4",
        "url": "https://example.com",
        "observation": "Missing clear CTA",
        "limitation": "Public homepage only",
        "capture": "sha256:abc",
        "status": "verified",
        "method": "observed",
        "confidence": "0.9",
        "claim_type": "website_quality",
    }
    with patch.object(bridge.core, "connect", return_value=conn), patch.object(
        bridge.core, "record_evidence", return_value=77
    ) as record:
        assert h._dispatch("audit", payload) == {"evidence_id": 77}
        assert record.call_args.args[1] == 4

    bad = dict(payload, confidence="nope")
    with pytest.raises(ValueError, match="confidence"):
        h._dispatch("audit", bad)

    bad = dict(payload, status="invented")
    with pytest.raises(ValueError, match="invalid evidence status"):
        h._dispatch("audit", bad)

    bad = dict(payload, claim_type="invented")
    with pytest.raises(ValueError, match="invalid claim-type"):
        h._dispatch("audit", bad)

    bad = dict(payload, capture="")
    with pytest.raises(ValueError, match="audit requires"):
        h._dispatch("audit", bad)


def test_auth_and_serve_error_paths(monkeypatch):
    h = handler()
    h._error = MagicMock()
    monkeypatch.setenv("MM_BRIDGE_TOKEN", "secret")

    h.headers = {"Authorization": "Bearer wrong"}
    assert h._auth("rid") is False
    h._error.assert_called_once()

    h._error.reset_mock()
    h.headers = {"Authorization": "Bearer secret"}
    assert h._auth("rid") is True

    h._json = MagicMock()
    h._dispatch = MagicMock(return_value={"ok": 1})
    h._parse_action = MagicMock(return_value=("status", {}))
    h._serve("GET")
    h._json.assert_called_once()

    h._json.reset_mock()
    h._dispatch.side_effect = PermissionError("forbidden")
    h._serve("GET")
    h._error.assert_called()

    h._error.reset_mock()
    h._dispatch.side_effect = ValueError("bad")
    h._serve("GET")
    h._error.assert_called()

    h._error.reset_mock()
    h._dispatch.side_effect = RuntimeError("sensitive detail")
    h._serve("GET")
    assert h._error.call_args.args[1] == "internal error"


def test_main_fails_closed_and_runs_local_server(monkeypatch):
    monkeypatch.setenv("MM_BRIDGE_TOKEN", "secret")
    monkeypatch.setenv("MM_EXTERNAL_SEND_DISABLED", "1")

    with patch.object(sys, "argv", ["mm_bridge.py", "--host", "0.0.0.0"]):
        with pytest.raises(SystemExit, match="localhost"):
            bridge.main()

    monkeypatch.setenv("MM_EXTERNAL_SEND_DISABLED", "0")
    with patch.object(sys, "argv", ["mm_bridge.py"]):
        with pytest.raises(SystemExit, match="must remain 1"):
            bridge.main()

    monkeypatch.setenv("MM_EXTERNAL_SEND_DISABLED", "1")
    monkeypatch.delenv("MM_BRIDGE_TOKEN")
    with patch.object(sys, "argv", ["mm_bridge.py"]):
        with pytest.raises(SystemExit, match="MM_BRIDGE_TOKEN"):
            bridge.main()

    monkeypatch.setenv("MM_BRIDGE_TOKEN", "secret")
    fake_server = MagicMock()
    fake_server.serve_forever.side_effect = KeyboardInterrupt
    with patch.object(sys, "argv", ["mm_bridge.py"]), patch.object(
        bridge.http.server, "ThreadingHTTPServer", return_value=fake_server
    ) as server_cls:
        bridge.main()
    server_cls.assert_called_once()
    fake_server.server_close.assert_called_once()

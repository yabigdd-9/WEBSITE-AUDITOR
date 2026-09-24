"""Loopback A2A-compatible gateway with WEBSITE-AUDITOR free-role enforcement.

Only explicit role requests may reach the repository's free-role router. The
gateway never delegates model selection to OmniRoute and fails closed unless
both the gateway and the external-free route are explicitly opted in.
"""
from __future__ import annotations

from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import hashlib
import os
from pathlib import Path
import secrets
import sys
from threading import Lock
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
MM = ROOT / "money-machine"
ROUTER_SCRIPT = MM / "scripts" / "free_role_router.py"
ROUTING_CONFIG = MM / "config" / "routing.yaml"
if str(ROUTER_SCRIPT.parent) not in sys.path:
    sys.path.insert(0, str(ROUTER_SCRIPT.parent))

MAX_BODY = 32_000
MAX_PROMPT = 24_000
_TASKS: dict[str, dict] = {}
_TASKS_LOCK = Lock()


class GatewayError(ValueError):
    """Safe, user-facing rejection that never includes request secrets."""


def _load_config() -> dict:
    try:
        import yaml
        data = yaml.safe_load(ROUTING_CONFIG.read_text(encoding="utf-8"))
    except Exception as exc:
        raise GatewayError("free_role_policy_unavailable") from exc
    if not isinstance(data, dict):
        raise GatewayError("free_role_policy_invalid")
    try:
        from free_role_router import validate
        validate(data)
    except Exception as exc:
        raise GatewayError("free_role_policy_rejected") from exc
    return data


def _check_flags() -> dict:
    if os.environ.get("MM_A2A_GATEWAY_ENABLED") != "1":
        raise GatewayError("a2a_gateway_disabled")
    if os.environ.get("MM_ALLOW_EXTERNAL_FREE_MODELS") != "1":
        raise GatewayError("external_free_routes_not_opted_in")
    if os.environ.get("MM_A2A_FREE_ROUTING") != "1":
        raise GatewayError("a2a_free_routing_not_opted_in")
    return _load_config()


def _validate_request(params: object, config: dict) -> tuple[str, str]:
    if not isinstance(params, dict) or set(params) != {"skill", "input", "idempotency_key"}:
        raise GatewayError("params_must_contain_skill_input_and_idempotency_key")
    key = params["idempotency_key"]
    if not isinstance(key, str) or not 1 <= len(key) <= 128 or any(ord(char) < 33 or ord(char) > 126 for char in key):
        raise GatewayError("invalid_idempotency_key")
    role, payload = params["skill"], params["input"]
    if not isinstance(role, str) or role not in config.get("roles", {}):
        raise GatewayError("unknown_role")
    if not isinstance(payload, dict) or set(payload) != {"prompt", "data_classification"}:
        raise GatewayError("input_must_contain_prompt_and_data_classification")
    prompt = payload["prompt"]
    classification = payload["data_classification"]
    if not isinstance(classification, str) or classification not in {"public", "synthetic"}:
        raise GatewayError("only_public_or_synthetic_input_is_allowed")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT:
        raise GatewayError("prompt_must_be_bounded_nonempty_text")
    return role, prompt


def _db():
    import mm_core
    db = mm_core.connect()
    db.execute("""CREATE TABLE IF NOT EXISTS a2a_gateway_requests (
        idempotency_key TEXT PRIMARY KEY,
        request_hash TEXT NOT NULL,
        role TEXT NOT NULL,
        status TEXT NOT NULL,
        model TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    db.commit()
    return db


def _reserve_request(key: str, role: str, prompt: str) -> None:
    """Atomically reserve a one-shot request; persist no prompt or answer."""
    import sqlite3
    from mm_core import now
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    request_hash = hashlib.sha256((role + "\0" + prompt).encode()).hexdigest()
    db = _db()
    try:
        db.execute("BEGIN IMMEDIATE")
        try:
            db.execute("INSERT INTO a2a_gateway_requests(idempotency_key,request_hash,role,status,created_at,updated_at) VALUES(?,?,?,'reserved',?,?)",
                       (key_hash, request_hash, role, now(), now()))
        except sqlite3.IntegrityError as exc:
            prior = db.execute("SELECT request_hash FROM a2a_gateway_requests WHERE idempotency_key=?", (key_hash,)).fetchone()
            db.rollback()
            if prior and prior[0] != request_hash:
                raise GatewayError("idempotency_key_conflict") from exc
            raise GatewayError("duplicate_request_not_replayed") from exc
        db.commit()
    finally:
        db.close()


def _finish_request(key: str, status: str, model: str | None = None) -> None:
    from mm_core import now
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    db = _db()
    try:
        db.execute("UPDATE a2a_gateway_requests SET status=?,model=?,updated_at=? WHERE idempotency_key=?",
                   (status, model, now(), key_hash))
        db.commit()
    finally:
        db.close()


def execute_role(params: object, *, catalog_request=None, completion_request=None,
                 credential_provider=None) -> dict:
    """Execute one validated role through free_role_router; injection supports offline tests."""
    config = _check_flags()
    role, prompt = _validate_request(params, config)
    from free_role_router import credential, request, route
    catalog_call = catalog_request or request
    completion_call = completion_request or request
    get_credential = credential_provider or credential

    from mm_model_router import prepare_external_prompt
    screened = prepare_external_prompt(prompt)
    if screened.get("secret_detected"):
        raise GatewayError("secret_like_prompt_blocked")
    key_id = params["idempotency_key"]
    _reserve_request(key_id, role, screened["prompt"])
    try:
        status, catalog_doc = catalog_call("/models")
    except Exception as exc:
        _finish_request(key_id, "failed")
        raise GatewayError("free_model_catalog_unavailable") from exc
    if status != 200 or not isinstance(catalog_doc, dict) or not isinstance(catalog_doc.get("data"), list):
        _finish_request(key_id, "failed")
        raise GatewayError("free_model_catalog_unverified")
    try:
        key = get_credential()
        result = route(config, role, screened["prompt"], key,
                       {item.get("id"): item for item in catalog_doc["data"] if isinstance(item, dict) and isinstance(item.get("id"), str)},
                       transport=completion_call)
    except GatewayError:
        _finish_request(key_id, "failed")
        raise
    except Exception as exc:
        # The existing router rejects price changes, quota exhaustion, paid
        # routes, malformed responses, and transport failures. Never leak details.
        _finish_request(key_id, "failed")
        raise GatewayError("free_role_router_blocked") from exc
    usage = result.get("usage") if isinstance(result, dict) else None
    cost = usage.get("cost") if isinstance(usage, dict) else None
    if not isinstance(result, dict) or cost not in (0, "0", "0.0"):
        _finish_request(key_id, "failed")
        raise GatewayError("zero_cost_response_not_verified")
    actual = result.get("actual_model")
    requested = result.get("requested_model")
    if not isinstance(actual, str) or not isinstance(requested, str) or actual.removesuffix(":free") != requested.removesuffix(":free"):
        _finish_request(key_id, "failed")
        raise GatewayError("unexpected_model_response")
    _finish_request(key_id, "completed", actual)
    return result


def _agent_card(base_url: str) -> dict:
    roles = list(_load_config().get("roles", {}))
    return {
        "name": "WEBSITE-AUDITOR Free-Only A2A Gateway",
        "description": "Explicit WEBSITE-AUDITOR role requests, routed through its zero-cost role router. Public or synthetic input only.",
        "url": base_url.rstrip("/") + "/a2a",
        "version": "1.0.0",
        "protocolVersion": "0.3.0",
        "preferredTransport": "JSONRPC",
        "capabilities": {"streaming": False, "pushNotifications": False},
        "skills": [{"id": role, "name": role, "description": "Free-only explicit role route",
                    "inputSchema": {"type": "object", "properties": {
                        "prompt": {"type": "string", "maxLength": MAX_PROMPT},
                        "data_classification": {"type": "string", "enum": ["public", "synthetic"]},
                        "idempotency_key": {"type": "string", "maxLength": 128}},
                        "required": ["prompt", "data_classification", "idempotency_key"],
                        "additionalProperties": False}} for role in roles],
        "securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}},
        "security": [{"bearerAuth": []}],
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "WebsiteAuditorA2A/1"
    sys_version = ""

    def log_message(self, fmt, *args):
        return

    def _reply(self, status: int, value: dict):
        raw = json.dumps(value, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/health":
            self._reply(200, {"status": "ok", "a2a_enabled": os.environ.get("MM_A2A_GATEWAY_ENABLED") == "1",
                              "paid_allowed": False, "max_cost_usd": 0})
        elif self.path == "/.well-known/agent.json":
            host, port = self.server.server_address[:2]
            shown_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
            self._reply(200, _agent_card(f"http://{shown_host}:{port}"))
        else:
            self._reply(404, {"error": {"code": -32004, "message": "not_found"}})

    def do_POST(self):
        if self.path != "/a2a":
            return self._reply(404, {"error": {"code": -32004, "message": "not_found"}})
        expected = os.environ.get("MM_A2A_GATEWAY_TOKEN", "")
        supplied = self.headers.get("Authorization", "").removeprefix("Bearer ")
        if not expected or not secrets.compare_digest(supplied, expected):
            return self._reply(401, {"error": {"code": -32001, "message": "authentication_required"}})
        try:
            length = int(self.headers.get("Content-Length", "-1"))
            if not 0 <= length <= MAX_BODY:
                return self._reply(413, {"error": {"code": -32600, "message": "invalid_request_size"}})
            message = json.loads(self.rfile.read(length))
            if (not isinstance(message, dict) or set(message) - {"jsonrpc", "id", "method", "params"}
                    or message.get("jsonrpc") != "2.0" or "id" not in message
                    or not isinstance(message.get("id"), (str, int)) or isinstance(message.get("id"), bool)
                    or not isinstance(message.get("method"), str)):
                return self._reply(400, {"error": {"code": -32600, "message": "invalid_jsonrpc_request"}})
            method = message.get("method")
            if method == "tasks.get":
                params = message.get("params")
                if not isinstance(params, dict) or set(params) != {"id"} or not isinstance(params["id"], str):
                    return self._reply(200, {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32602, "message": "invalid_params"}})
                task_id = params["id"]
                with _TASKS_LOCK:
                    task = _TASKS.get(task_id)
                if not task:
                    return self._reply(200, {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32004, "message": "task_not_found"}})
                return self._reply(200, {"jsonrpc": "2.0", "id": message["id"], "result": task})
            if method not in {"tasks.create", "tasks/send"}:
                return self._reply(200, {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": "method_not_allowed"}})
            params = message.get("params")
            try:
                result = execute_role(params)
            except GatewayError as exc:
                return self._reply(200, {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32010, "message": str(exc)}})
            task_id = str(uuid4())
            task = {"id": task_id, "status": {"state": "completed"}, "skill": params["skill"],
                    "createdAt": datetime.now(timezone.utc).isoformat(),
                    "result": {"model": result["actual_model"], "answer": result["answer"],
                               "cost_usd": 0, "paid_allowed": False, "approval_granted": False}}
            with _TASKS_LOCK:
                if len(_TASKS) >= 500:
                    _TASKS.pop(next(iter(_TASKS)))
                _TASKS[task_id] = task
            return self._reply(200, {"jsonrpc": "2.0", "id": message["id"], "result": task})
        except (ValueError, json.JSONDecodeError):
            self._reply(400, {"error": {"code": -32600, "message": "invalid_request"}})
        except Exception:
            self._reply(500, {"error": {"code": -32603, "message": "gateway_error"}})


def serve(host: str | None = None, port: int | None = None):
    host = host or os.environ.get("MM_A2A_GATEWAY_HOST", "127.0.0.1")
    port = int(port or os.environ.get("MM_A2A_GATEWAY_PORT", "8094"))
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("A2A gateway must bind to loopback")
    if not os.environ.get("MM_A2A_GATEWAY_TOKEN"):
        raise ValueError("MM_A2A_GATEWAY_TOKEN is required; configure it in the process environment or keychain")
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    print(json.dumps({"status": "listening", "endpoint": f"http://{host}:{port}",
                      "paid_allowed": False, "max_cost_usd": 0}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    serve()

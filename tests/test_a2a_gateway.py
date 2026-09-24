from __future__ import annotations

import json
import sqlite3
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from integrations import a2a_gateway as gateway


def valid_params(role="PLANNER", prompt="Summarize this public test fixture"):
    return {"skill": role, "input": {"prompt": prompt, "data_classification": "public"},
            "idempotency_key": "test-" + role + "-" + str(abs(hash(prompt)))}


@pytest.fixture(autouse=True)
def isolated_gateway_db(monkeypatch, tmp_path):
    path = tmp_path / "a2a.db"
    def db():
        connection = sqlite3.connect(path, timeout=2)
        connection.execute("""CREATE TABLE IF NOT EXISTS a2a_gateway_requests (
            idempotency_key TEXT PRIMARY KEY, request_hash TEXT NOT NULL, role TEXT NOT NULL,
            status TEXT NOT NULL, model TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        connection.commit()
        return connection
    monkeypatch.setattr(gateway, "_db", db)


def allow_gateway(monkeypatch):
    monkeypatch.setenv("MM_A2A_GATEWAY_ENABLED", "1")
    monkeypatch.setenv("MM_A2A_FREE_ROUTING", "1")
    monkeypatch.setenv("MM_ALLOW_EXTERNAL_FREE_MODELS", "1")


def test_gateway_disabled_without_explicit_opt_ins(monkeypatch):
    monkeypatch.delenv("MM_A2A_GATEWAY_ENABLED", raising=False)
    monkeypatch.setenv("MM_A2A_FREE_ROUTING", "1")
    monkeypatch.setenv("MM_ALLOW_EXTERNAL_FREE_MODELS", "1")
    with pytest.raises(gateway.GatewayError, match="a2a_gateway_disabled"):
        gateway._check_flags()


@pytest.mark.parametrize("params", [
    {"skill": "UNKNOWN", "input": {"prompt": "ok", "data_classification": "public"}, "idempotency_key": "x"},
    {"skill": "PLANNER", "input": {"prompt": "private", "data_classification": "confidential"}, "idempotency_key": "x"},
    {"skill": "PLANNER", "input": {"prompt": "ok", "data_classification": "public", "extra": True}, "idempotency_key": "x"},
    {"skill": "PLANNER", "input": {"prompt": "", "data_classification": "public"}, "idempotency_key": "x"},
])
def test_invalid_role_and_input_fail_closed(params):
    with pytest.raises(gateway.GatewayError):
        gateway._validate_request(params, gateway._load_config())


def test_secret_like_prompt_is_blocked_before_any_provider_request(monkeypatch):
    allow_gateway(monkeypatch)
    calls = []
    with pytest.raises(gateway.GatewayError, match="secret_like_prompt_blocked"):
        gateway.execute_role(valid_params(prompt="api_key=do-not-send"),
                             catalog_request=lambda *a: calls.append(a),
                             credential_provider=lambda: "test-only")
    assert calls == []


def test_role_request_uses_only_zero_priced_catalog_and_zero_caps(monkeypatch):
    allow_gateway(monkeypatch)
    config = gateway._load_config()
    model = config["roles"]["PLANNER"]["preferred"]
    calls = []

    def catalog(path):
        calls.append(("catalog", path))
        return 200, {"data": [{"id": model, "pricing": {"prompt": "0", "completion": "0"}}]}

    def completion(path, key, body):
        calls.append(("completion", body))
        return 200, {"model": model, "choices": [{"message": {"content": "fixture answer"}, "finish_reason": "stop"}],
                     "usage": {"cost": 0}}

    result = gateway.execute_role(valid_params(), catalog_request=catalog,
                                  completion_request=completion, credential_provider=lambda: "test-only")
    sent = next(call[1] for call in calls if call[0] == "completion")
    assert result["actual_model"] == model
    assert sent["model"].endswith(":free")
    assert sent["provider"]["max_price"] == {"prompt": 0, "completion": 0, "request": 0, "image": 0}
    assert sent["provider"]["data_collection"] == "deny"


def test_paid_catalog_route_never_calls_completion(monkeypatch):
    allow_gateway(monkeypatch)
    config = gateway._load_config()
    model = config["roles"]["PLANNER"]["preferred"]
    catalog = lambda path: (200, {"data": [{"id": model, "pricing": {"prompt": "0", "completion": "0.1"}}]})
    completions = []
    with pytest.raises(gateway.GatewayError, match="free_role_router_blocked"):
        gateway.execute_role(valid_params(), catalog_request=catalog,
                             completion_request=lambda *args: completions.append(args),
                             credential_provider=lambda: "test-only")
    assert completions == []


def test_missing_reported_cost_is_not_claimed_zero(monkeypatch):
    allow_gateway(monkeypatch)
    config = gateway._load_config()
    model = config["roles"]["PLANNER"]["preferred"]
    catalog = lambda path: (200, {"data": [{"id": model, "pricing": {"prompt": "0", "completion": "0"}}]})
    completion = lambda path, key, body: (200, {"model": model,
        "choices": [{"message": {"content": "answer"}, "finish_reason": "stop"}], "usage": {}})
    with pytest.raises(gateway.GatewayError, match="zero_cost_response_not_verified"):
        gateway.execute_role(valid_params(), catalog_request=catalog,
                             completion_request=completion, credential_provider=lambda: "test-only")


def test_duplicate_idempotency_key_never_repeats_provider_call(monkeypatch):
    allow_gateway(monkeypatch)
    config = gateway._load_config()
    model = config["roles"]["PLANNER"]["preferred"]
    catalog = lambda path: (200, {"data": [{"id": model, "pricing": {"prompt": "0", "completion": "0"}}]})
    calls = []
    completion = lambda path, key, body: (calls.append(body) or (200, {
        "model": model, "choices": [{"message": {"content": "answer"}, "finish_reason": "stop"}], "usage": {"cost": 0}}))
    params = valid_params()
    gateway.execute_role(params, catalog_request=catalog, completion_request=completion,
                         credential_provider=lambda: "test-only")
    with pytest.raises(gateway.GatewayError, match="duplicate_request_not_replayed"):
        gateway.execute_role(params, catalog_request=catalog, completion_request=completion,
                             credential_provider=lambda: "test-only")
    assert len(calls) == 1


def test_gateway_binds_loopback_and_requires_token(monkeypatch):
    monkeypatch.delenv("MM_A2A_GATEWAY_TOKEN", raising=False)
    with pytest.raises(ValueError, match="loopback"):
        gateway.serve(host="0.0.0.0", port=0)
    with pytest.raises(ValueError, match="TOKEN"):
        gateway.serve(host="127.0.0.1", port=0)


def test_http_endpoint_requires_bearer_and_exposes_no_secret(monkeypatch):
    token = "test-token-not-a-real-secret"
    monkeypatch.setenv("MM_A2A_GATEWAY_TOKEN", token)
    monkeypatch.setenv("MM_A2A_GATEWAY_ENABLED", "1")
    monkeypatch.setattr(gateway, "execute_role", lambda params: {
        "actual_model": "vendor/model:free", "answer": "fixture", "requested_model": "vendor/model:free"})
    server = ThreadingHTTPServer(("127.0.0.1", 0), gateway.Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    body = json.dumps({"jsonrpc": "2.0", "id": "test", "method": "tasks.create", "params": valid_params()}).encode()
    try:
        req = Request(base + "/a2a", data=body, headers={"Content-Type": "application/json"}, method="POST")
        with pytest.raises(HTTPError) as error:
            urlopen(req)
        assert error.value.code == 401
        req = Request(base + "/a2a", data=body, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
        response = json.load(urlopen(req))
        assert response["result"]["status"]["state"] == "completed"
        assert response["result"]["result"]["cost_usd"] == 0
        health = json.load(urlopen(base + "/health"))
        assert "test-token-not-a-real-secret" not in json.dumps(health)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

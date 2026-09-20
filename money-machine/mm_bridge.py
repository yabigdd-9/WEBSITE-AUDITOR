#!/usr/bin/env python3
"""Fail-closed localhost bridge between n8n and MoneyMachine.

The bridge intentionally exposes no external-send capability. It supports read-only
status checks plus bounded internal intake/audit actions. No arbitrary shell, Python
or SQL is available.
"""
from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import os
import secrets
import sys
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

MM_DIR = Path(__file__).resolve().parent
ROOT = MM_DIR.parent
sys.path.insert(0, str(MM_DIR))

import mm_core as core
import mm_email_store as email_store
import mm_operator as operator
import mm_outreach as outreach

HOST = "127.0.0.1"
PORT = 8787
REQUEST_TIMEOUT = 30
MAX_BODY = 1024 * 1024
MAX_ID = 2**63 - 1

READ_ACTIONS = {"status", "doctor", "email-status", "outreach-preflight"}
WRITE_ACTIONS = {"intake", "audit"}
ALLOWED_ACTIONS = READ_ACTIONS | WRITE_ACTIONS
FORBIDDEN_ACTIONS = {
    "send",
    "send-via-approved-transport",
    "record-sent",
    "delete-suppression",
    "clear-hold",
    "raw-sql",
    "arbitrary-shell",
    "arbitrary-python",
    "modify-approval-hash-manually",
}


def _scalar_map(values):
    return {k: (v[-1] if isinstance(v, list) else v) for k, v in values.items()}


def _safe_int(value, name="id"):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer")
    if not 0 < parsed <= MAX_ID:
        raise ValueError(f"{name} out of range")
    return parsed


def _require_token(header):
    expected = os.environ.get("MM_BRIDGE_TOKEN", "")
    if not expected:
        return False, "bridge token not configured"
    if not header or not header.startswith("Bearer "):
        return False, "missing bearer token"
    if not secrets.compare_digest(header[7:], expected):
        return False, "invalid bearer token"
    return True, None


class BridgeHandler(http.server.BaseHTTPRequestHandler):
    server_version = "mm-bridge/2.0"
    protocol_version = "HTTP/1.1"
    _lock = threading.Lock()

    def log_message(self, fmt, *args):
        return

    def _json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, code, message, request_id):
        self._json(code, {"ok": False, "error": message, "request_id": request_id})

    def _request_id(self):
        seed = f"{time.time_ns()}:{os.getpid()}:{self.client_address[0]}".encode()
        return hashlib.sha256(seed).hexdigest()[:16]

    def _auth(self, request_id):
        ok, error = _require_token(self.headers.get("Authorization"))
        if not ok:
            self._error(401, error, request_id)
            return False
        return True

    def _parse_action(self):
        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]
        action = parts[0] if parts else ""
        params = _scalar_map(parse_qs(parsed.query))
        return action, params

    def _read_body(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length < 0 or length > MAX_BODY:
            raise ValueError("request body too large")
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        content_type = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if content_type == "application/json":
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("JSON request body must be an object")
            return data
        return _scalar_map(parse_qs(raw.decode("utf-8")))

    def _dispatch(self, action, params):
        if action in FORBIDDEN_ACTIONS:
            raise PermissionError(f"forbidden action: {action}")
        if action not in ALLOWED_ACTIONS:
            raise ValueError(f"unknown action: {action}")

        if action == "status":
            with core.connect(readonly=True) as d:
                return operator.run_day(d, write=False)

        if action == "doctor":
            with core.connect(readonly=True) as d:
                return operator.doctor(d)

        if action == "email-status":
            business_id = _safe_int(params.get("id"), "id")
            with core.connect(readonly=True) as d:
                return email_store.status(d, business_id)

        if action == "outreach-preflight":
            message_id = _safe_int(params.get("id"), "id")
            with core.connect(readonly=True) as d:
                return outreach.preflight(d, message_id)

        if action == "intake":
            name = str(params.get("name") or "").strip()
            url = str(params.get("url") or "").strip()
            region = str(params.get("region") or "").strip()
            source = str(params.get("source") or "n8n").strip()
            if not name or not url or not region:
                raise ValueError("intake requires name, url and region")
            host = core.public_url(url)
            with core.connect() as d, d:
                for business in d.execute(
                    "SELECT id,name,public_website FROM businesses WHERE is_dummy=0"
                ):
                    same_name = business["name"].strip().casefold() == name.casefold()
                    same_host = (
                        business["public_website"]
                        and core.public_url(business["public_website"]) == host
                    )
                    if same_name or same_host:
                        raise ValueError(f"duplicate prospect: {business['id']}")
                cursor = d.execute(
                    "INSERT INTO businesses(name,region,public_website,source,discovered_at,"
                    "current_status,is_dummy) VALUES(?,?,?,?,?,'discovered',0)",
                    (name, region, url, source, core.now()),
                )
                business_id = cursor.lastrowid
                d.execute(
                    "INSERT INTO mm_deals(business_id,stage,updated_at) "
                    "VALUES(?,'DISCOVERED',?)",
                    (business_id, core.now()),
                )
                core.event(d, "intake", business_id, source)
            return {"business_id": business_id}

        if action == "audit":
            business_id = _safe_int(params.get("id"), "id")
            url = str(params.get("url") or "").strip()
            observation = str(params.get("observation") or "").strip()
            limitation = str(params.get("limitation") or "").strip()
            capture = str(params.get("capture") or "").strip()
            status = str(params.get("status") or "unverified").strip()
            method = str(params.get("method") or "observed").strip()
            claim_type = str(params.get("claim-type") or params.get("claim_type") or "website_quality").strip()
            try:
                confidence = float(params.get("confidence", 0.5))
            except (TypeError, ValueError):
                raise ValueError("confidence must be numeric")
            if not all((url, observation, limitation, capture)):
                raise ValueError("audit requires url, observation, limitation and capture")
            if status not in {"verified", "partial", "refuted", "unverified"}:
                raise ValueError("invalid evidence status")
            if claim_type not in {
                "conversion", "lead_flow", "booking", "quote", "crm", "website_quality"
            }:
                raise ValueError("invalid claim-type")
            with core.connect() as d, d:
                evidence_id = core.record_evidence(
                    d,
                    business_id,
                    url,
                    observation,
                    limitation,
                    capture,
                    status,
                    method,
                    confidence,
                    claim_type,
                )
            return {"evidence_id": evidence_id}

        raise ValueError(f"unhandled action: {action}")

    def _serve(self, method):
        started = time.monotonic()
        request_id = self._request_id()
        if not self._auth(request_id):
            return

        try:
            action, params = self._parse_action()
            if method == "POST":
                params.update(self._read_body())
            with self._lock:
                result = self._dispatch(action, params)
            if time.monotonic() - started > REQUEST_TIMEOUT:
                return self._error(408, "request timeout", request_id)
            self._json(
                200,
                {"ok": True, "action": action, "request_id": request_id, "result": result},
            )
        except PermissionError as exc:
            self._error(403, str(exc), request_id)
        except (ValueError, json.JSONDecodeError) as exc:
            self._error(422, str(exc), request_id)
        except Exception:
            self._error(500, "internal error", request_id)

    def do_GET(self):
        self._serve("GET")

    def do_POST(self):
        self._serve("POST")


def main():
    parser = argparse.ArgumentParser(description="Local n8n MoneyMachine bridge")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()

    if args.host not in {"127.0.0.1", "localhost"}:
        raise SystemExit("Bridge is restricted to localhost")
    if os.environ.get("MM_EXTERNAL_SEND_DISABLED", "1") != "1":
        raise SystemExit("MM_EXTERNAL_SEND_DISABLED must remain 1")
    if not os.environ.get("MM_BRIDGE_TOKEN"):
        raise SystemExit("MM_BRIDGE_TOKEN is required")

    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), BridgeHandler)
    print(f"MoneyMachine bridge listening on http://127.0.0.1:{args.port}")
    print("External send actions: DISABLED")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

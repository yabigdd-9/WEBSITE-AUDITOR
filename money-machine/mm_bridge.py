#!/usr/bin/env python3
"""Narrow localhost bridge between n8n and MoneyMachine.

Binds 127.0.0.1 only. n8n calls http://host.docker.internal:8787/<action>.
No arbitrary shell, no SQL direct access, no suppression/hold deletion.
"""
import argparse
import hashlib
import http.server
import json
import os
import secrets
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT))

import mm_core as core
from mm_brain import review as brain_review, approve as brain_approve, reject as brain_reject, record_outcome as brain_outcome
import mm_email_store as email_store
import mm_outreach as outreach
import mm_operator as operator

HOST = "127.0.0.1"
PORT = 8787
TOKEN = os.environ.get("MM_BRIDGE_TOKEN", "")
ALLOWED_ACTIONS = {
    # read-only
    "status", "doctor", "exa-status", "email-status", "outreach-preflight", "brain-review",
    # mutating but internal
    "intake", "audit", "contact", "email-find", "draft",
    "brain-approve", "brain-reject", "brain-outcome", "stage",
    # external boundary
    "send-via-approved-transport", "record-sent",
}
FORBIDDEN = {"delete-suppression", "clear-hold", "raw-sql", "arbitrary-shell", "arbitrary-python", "modify-approval-hash-manually"}
REQUEST_TIMEOUT = 30  # seconds
MAX_ID = 2**63 - 1


def require_token(header):
    token = os.environ.get("MM_BRIDGE_TOKEN", "")
    if not token:
        return False, "bridge token not configured"
    got = header or ""
    if not got.startswith("Bearer "):
        return False, "missing bearer token"
    if not secrets.compare_digest(got[7:], token):
        return False, "invalid token"
    return True, None


def safe_int(value, name="id"):
    try:
        v = int(value)
    except (TypeError, ValueError):
        return None, f"{name} must be an integer"
    if not (0 < v <= MAX_ID):
        return None, f"{name} out of range"
    return v, None


def safe_url(value):
    if not value or not isinstance(value, str):
        return None, "url must be a non-empty string"
    if " " in value or "\n" in value or "\r" in value:
        return None, "url contains illegal characters"
    return value, None


class BridgeHandler(http.server.BaseHTTPRequestHandler):
    server_version = "mm-bridge/1.0"
    protocol_version = "HTTP/1.1"
    _lock = threading.Lock()

    def log_message(self, format, *args):
        pass  # silence default stderr; we use request_id below

    def _json(self, code, data):
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, code, error, request_id):
        return self._json(code, {"ok": False, "error": error, "request_id": request_id})

    def do_GET(self):
        started = time.monotonic()
        request_id = hashlib.sha256(f"{time.time_ns()}{os.getpid()}".encode()).hexdigest()[:16]
        token_ok, token_err = require_token(self.headers.get("Authorization"))
        if not token_ok:
            return self._error(401, token_err, request_id)
        if time.monotonic() - started > REQUEST_TIMEOUT:
            return self._error(408, "request timeout", request_id)

        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]
        if not parts:
            return self._error(400, "missing action", request_id)
        action = parts[0]
        if action in FORBIDDEN:
            return self._error(403, f"forbidden action: {action}", request_id)
        if action not in ALLOWED_ACTIONS:
            return self._error(400, f"unknown action: {action}", request_id)

        q = parse_qs(parsed.query)
        try:
            with BridgeHandler._lock:
                result = self._handle(action, q, request_id)
        except ValueError as e:
            return self._error(422, str(e), request_id)
        except Exception as e:
            return self._error(500, f"internal error: {e}", request_id)

        if time.monotonic() - started > REQUEST_TIMEOUT:
            return self._error(408, "request timeout", request_id)
        self._json(200, {"ok": True, "action": action, "request_id": request_id, "result": result})

    def _handle(self, action, q, request_id):
        if action == "status":
            return operator.run_day(core.connect(), write=False)
        if action == "doctor":
            return operator.doctor(core.connect())
        if action == "exa-status":
            import mm_exa
            return mm_exa.check_exa_available()
        if action == "email-status":
            bid, e = safe_int(q.get("id", [None])[0], "id")
            if e: raise ValueError(e)
            with core.connect(readonly=True) as d:
                return email_store.status(d, bid)
        if action == "outreach-preflight":
            mid, e = safe_int(q.get("id", [None])[0], "id")
            if e: raise ValueError(e)
            with core.connect(readonly=True) as d:
                return outreach.preflight(d, mid)
        if action == "brain-review":
            mid, e = safe_int(q.get("id", [None])[0], "id")
            if e: raise ValueError(e)
            with core.connect() as d:
                return brain_review(d, mid)
        if action == "intake":
            name = q.get("name", [""])[0]
            url = q.get("url", [""])[0]
            region = q.get("region", [""])[0]
            source = q.get("source", ["fixture"])[0]
            if not name or not url or not region:
                raise ValueError("intake requires name, url, region")
            host = core.public_url(url)
            with core.connect() as d:
                for b in d.execute("SELECT id,name,public_website FROM businesses WHERE is_dummy=0"):
                    if b["name"].strip().casefold() == name.strip().casefold() or (b["public_website"] and core.public_url(b["public_website"]) == host):
                        raise ValueError(f"Duplicate prospect")
                c = d.execute("INSERT INTO businesses(name,region,public_website,source,discovered_at,current_status,is_dummy) VALUES(?,?,?,?,?,?,0)",
                              (name.strip(), region.strip(), url, source, core.now())).lastrowid
                d.execute("INSERT INTO mm_deals(business_id,stage,updated_at) VALUES(?,'DISCOVERED',?)", (c, core.now()))
                core.event(d, "intake", c, source)
            return {"business_id": c}
        if action == "audit":
            bid, e = safe_int(q.get("id", [None])[0], "id")
            if e: raise ValueError(e)
            url = q.get("url", [""])[0]
            obs = q.get("observation", [""])[0]
            limitation = q.get("limitation", [""])[0]
            capture = q.get("capture", [""])[0]
            status = q.get("status", ["verified"])[0]
            method = q.get("method", ["observed"])[0]
            confidence = float(q.get("confidence", ["0.9"])[0])
            claim_type = q.get("claim-type", ["conversion"])[0]
            if not all([url, obs, limitation, capture]):
                raise ValueError("audit requires url, observation, limitation, capture")
            if status not in ("verified", "partial", "refuted", "unverified"):
                raise ValueError("invalid status")
            if claim_type not in ("conversion", "lead_flow", "booking", "quote", "crm", "website_quality"):
                raise ValueError("invalid claim-type")
            eid = core.record_evidence(core.connect(), bid, url, obs, limitation, capture, status, method, confidence, claim_type)
            return {"evidence_id": eid}
        if action == "contact":
            bid, e = safe_int(q.get("id", [None])[0], "id")
            if e: raise ValueError(e)
            recipient = q.get("recipient", [""])[0]
            url = q.get("url", [""])[0]
            capture = q.get("capture", [""])[0]
            relevance = q.get("relevance", [""])[0]
            if not all([recipient, url, capture, relevance]):
                raise ValueError("contact requires recipient, url, capture, relevance")
            core.record_contact(core.connect(), bid, recipient, url, capture, relevance)
            return {"contact_source": "captured", "permission": "Human review required"}
        if action == "email-find":
            bid, e = safe_int(q.get("id", [None])[0], "id")
            if e: raise ValueError(e)
            with core.connect(readonly=True) as d:
                return email_store.status(d, bid)
        if action == "draft":
            bid, e = safe_int(q.get("id", [None])[0], "id")
            if e: raise ValueError(e)
            recipient = q.get("recipient", [""])[0]
            body = q.get("body", [""])[0]
            if not recipient or not body:
                raise ValueError("draft requires recipient and body")
            parent, _e = safe_int(q.get("parent", ["0"])[0], "parent")
            if _e: raise ValueError(_e)
            with core.connect() as d:
                did = core.create_draft(d, bid, recipient, body, parent if parent else None)
            return {"draft_id": did}
        if action == "brain-approve":
            mid, e = safe_int(q.get("id", [None])[0], "id")
            if e: raise ValueError(e)
            with core.connect() as d:
                brain_approve(d, mid)
            return {"approved": True}
        if action == "brain-reject":
            mid, e = safe_int(q.get("id", [None])[0], "id")
            if e: raise ValueError(e)
            reason = q.get("reason", [""])[0]
            if not reason:
                raise ValueError("brain-reject requires reason")
            with core.connect() as d:
                brain_reject(d, mid, reason)
            return {"rejected": True, "reason": reason}
        if action == "brain-outcome":
            mid, e = safe_int(q.get("id", [None])[0], "id")
            if e: raise ValueError(e)
            outcome = q.get("outcome", [""])[0]
            detail = q.get("detail", [""])[0]
            if outcome not in ("positive_reply", "negative_reply", "bounce", "opt_out", "no_reply", "sale", "unsubscribed"):
                raise ValueError("invalid outcome")
            with core.connect() as d:
                brain_outcome(d, mid, outcome, detail or None)
            return {"outcome": outcome}
        if action == "stage":
            bid, e = safe_int(q.get("id", [None])[0], "id")
            if e: raise ValueError(e)
            stage = q.get("stage", [""])[0]
            next_action = q.get("next-action", [""])[0]
            if stage not in core.STAGES:
                raise ValueError(f"invalid stage: {stage}")
            due = q.get("due", [None])[0]
            core.change_stage(core.connect(), bid, stage, next_action, due)
            return {"stage": stage}
        if action == "send-via-approved-transport":
            return self._error(403, "external send requires LIVE_SEND_ENABLED and full preflight — not exposed via bridge", request_id)
        if action == "record-sent":
            mid, e = safe_int(q.get("id", [None])[0], "id")
            if e: raise ValueError(e)
            receipt = q.get("receipt", [""])[0]
            if not receipt:
                raise ValueError("record-sent requires receipt")
            rid, _e = safe_int(receipt, "receipt")
            if _e: raise ValueError(_e)
            with core.connect() as d:
                core.record_sent(d, mid, rid)
            return {"recorded": True}
        raise ValueError(f"unimplemented action: {action}")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "http://localhost:5678")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET")
        self.end_headers()

    def do_POST(self):
        return self._error(405, "bridge only accepts GET; POST is blocked", self._rid())

    def do_PUT(self):
        return self._error(405, "bridge only accepts GET; PUT is blocked", self._rid())

    def do_DELETE(self):
        return self._error(405, "bridge only accepts GET; DELETE is blocked", self._rid())

    def _rid(self):
        return hashlib.sha256(f"{time.time_ns()}{os.getpid()}".encode()).hexdigest()[:16]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=HOST)
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--token", default=TOKEN)
    args = ap.parse_args()

    if not args.token:
        print("BLOCKED: MM_BRIDGE_TOKEN not set", file=sys.stderr)
        sys.exit(2)

    server = http.server.HTTPServer((args.host, args.port), BridgeHandler)
    print(f"mm-bridge listening on {args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("shutting down", flush=True)
        server.server_close()


if __name__ == "__main__":
    main()
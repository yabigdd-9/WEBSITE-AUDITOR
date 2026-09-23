"""HTTP webhook and MCP-over-stdio bridge."""
import json, os, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .layer import DEFAULT_PORT, EventBus, Job, github_signature_valid, status

class Handler(BaseHTTPRequestHandler):
    bus: EventBus; root: Path; worker_state = {"running": False, "last_run": None, "processed": 0}
    def _authorized(self):
        import hmac
        expected = os.getenv("WA_WEBHOOK_TOKEN", "")
        supplied = self.headers.get("X-WA-Token") or self.headers.get("Authorization", "").removeprefix("Bearer ")
        return bool(expected and supplied and hmac.compare_digest(expected, supplied))
    def _json(self, data, code=200):
        body = json.dumps(data).encode(); self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path == "/health":
            result = status(self.root); result["worker"] = dict(self.worker_state); result["worker"]["running"] = bool(self.worker_state["running"])
            if self.headers.get("Cf-Connecting-Ip"):
                result = {"service": result["service"], "status": result["status"], "worker": result["worker"]}
            return self._json(result)
        if self.path == "/events/claim":
            if not self._authorized(): return self._json({"error": "unauthorized"}, 401)
            try: limit = min(100, max(1, int(self.headers.get("X-WA-Limit", "10"))))
            except ValueError: limit = 10
            return self._json({"events": self.bus.claim(limit)})
        self._json({"error": "not_found"}, 404)
    def do_POST(self):
        if self.path not in {"/webhooks/event", "/events", "/webhooks/github"}: return self._json({"error": "not_found"}, 404)
        if self.path != "/webhooks/github" and not self._authorized(): return self._json({"error": "unauthorized"}, 401)
        try:
            raw_length = self.headers.get("Content-Length", "0")
            if not raw_length.isdigit(): return self._json({"error": "invalid_content_length"}, 400)
            if int(raw_length) > 1_000_000:
                return self._json({"error": "payload_too_large"}, 413)
            body = self.rfile.read(int(raw_length))
            if self.path == "/webhooks/github":
                if not github_signature_valid(os.getenv("GITHUB_WEBHOOK_SECRET", ""), body, self.headers.get("X-Hub-Signature-256")): return self._json({"error": "invalid_signature"}, 401)
                payload = json.loads(body or b"{}")
                event_name = self.headers.get("X-GitHub-Event", "unknown")
                kind = "github." + event_name
                job = Job(kind, {"event": event_name, "delivery": self.headers.get("X-GitHub-Delivery"), "payload": _github_summary(event_name, payload)}, "github")
                job_id = self.bus.publish(job, "github:" + (self.headers.get("X-GitHub-Delivery") or ""))
                return self._json({"accepted": True, "duplicate": job_id != job.id, "job_id": job_id}, 202)
            payload = json.loads(body or b"{}")
            if not isinstance(payload, dict): return self._json({"error": "object_required"}, 400)
            idem = self.headers.get("Idempotency-Key")
            kind = str(payload.pop("kind", "integration.event")); job = Job(kind, payload, self.headers.get("X-WA-Source", "webhook")); job_id = self.bus.publish(job, idem); self._json({"accepted": True, "duplicate": job_id != job.id, "job": job.to_dict(), "job_id": job_id}, 202)
        except (ValueError, json.JSONDecodeError) as exc: self._json({"error": "invalid_json", "detail": str(exc)}, 400)

def _github_summary(event: str, body: dict):
    """Keep only low-sensitivity event metadata; omit comment/issue/commit text and identities."""
    if not isinstance(body, dict): raise ValueError("GitHub payload must be a JSON object")
    summary = {key: body[key] for key in ("action", "number", "ref", "before", "after", "created", "deleted", "forced", "size", "compare") if key in body}
    repo = body.get("repository")
    if isinstance(repo, dict) and isinstance(repo.get("full_name"), str): summary["repository"] = repo["full_name"][:200]
    if event == "pull_request":
        pr = body.get("pull_request")
        if isinstance(pr, dict):
            summary["pull_request"] = {key: pr[key] for key in ("number", "state", "merged", "draft", "html_url") if key in pr}
            for side in ("head", "base"):
                branch = pr.get(side)
                if isinstance(branch, dict) and isinstance(branch.get("ref"), str): summary["pull_request"][side] = {"ref": branch["ref"][:200]}
    return summary

    def do_PATCH(self):
        if not self.path.startswith("/events/"): return self._json({"error": "not_found"}, 404)
        if not self._authorized(): return self._json({"error": "unauthorized"}, 401)
        try:
            event_id = self.path.removeprefix("/events/")
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
            self.bus.finish(event_id, data.get("error"))
            return self._json({"updated": True, "event_id": event_id})
        except (ValueError, json.JSONDecodeError) as exc: return self._json({"error": "invalid_json", "detail": str(exc)}, 400)

def process_batch(bus: EventBus):
    bus.recover_stale()
    processed = 0
    # GitHub events are durably recorded and acknowledged as received only.
    # No domain actions, model calls, or outbound messages are performed.
    for event in bus.claim(20):
        payload = json.loads(event["payload"])
        kind = event["kind"]
        job_payload = payload.get("payload", {}) if isinstance(payload, dict) else {}
        if kind == "integration.noop" or (kind.startswith("github.") and isinstance(job_payload, dict) and job_payload.get("delivery")):
            bus.finish(event["id"])
        else:
            bus.finish(event["id"], "no_safe_handler_registered")
        processed += 1
    Handler.worker_state["processed"] += processed
    Handler.worker_state["last_run"] = time.time()
    return processed

def _worker_loop(bus: EventBus, idle_seconds: float = 1.0):
    Handler.worker_state["running"] = True
    while True:
        try: process_batch(bus)
        except Exception as exc: Handler.worker_state["last_error"] = type(exc).__name__
        time.sleep(idle_seconds)

def run_http(root=".", host="127.0.0.1", port=DEFAULT_PORT, worker=True):
    if host not in {"127.0.0.1", "localhost", "::1"}: raise ValueError("integration receiver must bind to loopback")
    root = Path(root); Handler.root, Handler.bus = root, EventBus(root / "outputs" / "integration-events.db")
    if worker: threading.Thread(target=_worker_loop, args=(Handler.bus,), daemon=True, name="integration-worker").start()
    ThreadingHTTPServer((host, port), Handler).serve_forever()

def run_mcp():
    root = Path(os.getenv("WA_ROOT", ".")); bus = EventBus(root / "outputs" / "integration-events.db")
    for line in sys.stdin:
        try:
            req = json.loads(line); method, ident = req.get("method"), req.get("id")
            if method == "notifications/initialized":
                continue
            if method == "initialize": result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "website-auditor-integrations", "version": "1.0"}}
            elif method == "tools/list": result = {"tools": [
                {"name": "integration_status", "description": "Return local integration health", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}, "annotations": {"readOnlyHint": True}},
                {"name": "publish_event", "description": "Queue a local event", "inputSchema": {"type": "object", "properties": {"kind": {"type": "string"}, "payload": {"type": "object"}}, "required": ["payload"], "additionalProperties": False}}
            ]}
            elif method == "tools/call":
                args = req.get("params", {}).get("arguments", {}); name = req.get("params", {}).get("name")
                if name == "publish_event": job = Job(args.get("kind", "integration.event"), args.get("payload", {}), "mcp"); result = {"content": [{"type": "text", "text": json.dumps({"job_id": bus.publish(job)})}]}
                elif name == "integration_status": result = {"content": [{"type": "text", "text": json.dumps(status(root))}], "isError": False}
                else: result = {"content": [{"type": "text", "text": "Unknown tool"}], "isError": True}
            else:
                if ident is None: continue
                print(json.dumps({"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": "Method not found"}}), flush=True)
                continue
            if ident is not None: print(json.dumps({"jsonrpc": "2.0", "id": ident, "result": result}), flush=True)
        except Exception as exc: print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(exc)}}), flush=True)

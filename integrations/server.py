"""HTTP webhook and MCP-over-stdio bridge."""

import ipaddress
import json
import os
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .layer import DEFAULT_PORT, EventBus, Job, github_signature_valid, status


class Handler(BaseHTTPRequestHandler):
    bus: EventBus
    root: Path
    worker_state = {"running": False, "last_run": None, "processed": 0}

    def _authorized(self):
        import hmac

        expected = os.getenv("WA_WEBHOOK_TOKEN", "")
        supplied = self.headers.get("X-WA-Token") or self.headers.get(
            "Authorization", ""
        ).removeprefix("Bearer ")
        return bool(expected and supplied and hmac.compare_digest(expected, supplied))

    def log_message(self, _format, *_args):
        return

    def _json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            result = status(self.root)
            result["worker"] = dict(self.worker_state)
            result["worker"]["running"] = bool(self.worker_state["running"])
            if self.headers.get("Cf-Connecting-Ip"):
                result = {
                    "service": result["service"],
                    "status": result["status"],
                    "worker": result["worker"],
                }
            return self._json(result)
        if self.path == "/events/claim":
            if not self._authorized():
                return self._json({"error": "unauthorized"}, 401)
            try:
                limit = min(100, max(1, int(self.headers.get("X-WA-Limit", "10"))))
            except ValueError:
                limit = 10
            return self._json({"events": self.bus.claim(limit)})
        self._json({"error": "not_found"}, 404)

    def do_PATCH(self):
        if not self.path.startswith("/events/"):
            return self._json({"error": "not_found"}, 404)
        if not self._authorized():
            return self._json({"error": "unauthorized"}, 401)
        try:
            event_id = self.path.removeprefix("/events/")
            data = json.loads(
                self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}"
            )
            self.bus.finish(event_id, data.get("error"))
            return self._json({"updated": True, "event_id": event_id})
        except (ValueError, json.JSONDecodeError) as exc:
            return self._json({"error": "invalid_json", "detail": str(exc)}, 400)

    def do_POST(self):
        if self.path not in {"/webhooks/event", "/events", "/webhooks/github"}:
            return self._json({"error": "not_found"}, 404)
        if self.path != "/webhooks/github" and not self._authorized():
            return self._json({"error": "unauthorized"}, 401)
        try:
            raw_length = self.headers.get("Content-Length", "0")
            if not raw_length.isdigit():
                return self._json({"error": "invalid_content_length"}, 400)
            if int(raw_length) > 1_000_000:
                return self._json({"error": "payload_too_large"}, 413)
            body = self.rfile.read(int(raw_length))
            if self.path == "/webhooks/github":
                if not github_signature_valid(
                    os.getenv("GITHUB_WEBHOOK_SECRET", ""),
                    body,
                    self.headers.get("X-Hub-Signature-256"),
                ):
                    return self._json({"error": "invalid_signature"}, 401)
                payload = json.loads(body or b"{}")
                event_name = self.headers.get("X-GitHub-Event", "unknown")
                kind = "github." + event_name
                job = Job(
                    kind,
                    {
                        "event": event_name,
                        "delivery": self.headers.get("X-GitHub-Delivery"),
                        "payload": _github_summary(event_name, payload),
                    },
                    "github",
                )
                job_id = self.bus.publish(
                    job, "github:" + (self.headers.get("X-GitHub-Delivery") or "")
                )
                return self._json(
                    {"accepted": True, "duplicate": job_id != job.id, "job_id": job_id}, 202
                )
            payload = json.loads(body or b"{}")
            if not isinstance(payload, dict):
                return self._json({"error": "object_required"}, 400)
            idem = self.headers.get("Idempotency-Key")
            kind = str(payload.pop("kind", "integration.event"))
            job = Job(kind, payload, self.headers.get("X-WA-Source", "webhook"))
            job_id = self.bus.publish(job, idem)
            self._json(
                {
                    "accepted": True,
                    "duplicate": job_id != job.id,
                    "job": job.to_dict(),
                    "job_id": job_id,
                },
                202,
            )
        except (ValueError, json.JSONDecodeError) as exc:
            self._json({"error": "invalid_json", "detail": str(exc)}, 400)


def _github_summary(event: str, body: dict):
    """Keep only low-sensitivity event metadata; omit comment/issue/commit text and identities."""
    if not isinstance(body, dict):
        raise ValueError("GitHub payload must be a JSON object")
    summary = {
        key: body[key]
        for key in (
            "action",
            "number",
            "ref",
            "before",
            "after",
            "created",
            "deleted",
            "forced",
            "size",
            "compare",
        )
        if key in body
    }
    repo = body.get("repository")
    if isinstance(repo, dict) and isinstance(repo.get("full_name"), str):
        summary["repository"] = repo["full_name"][:200]
    if event == "pull_request":
        pr = body.get("pull_request")
        if isinstance(pr, dict):
            summary["pull_request"] = {
                key: pr[key]
                for key in ("number", "state", "merged", "draft", "html_url")
                if key in pr
            }
            for side in ("head", "base"):
                branch = pr.get(side)
                if isinstance(branch, dict) and isinstance(branch.get("ref"), str):
                    summary["pull_request"][side] = {"ref": branch["ref"][:200]}
    return summary


def process_batch(bus: EventBus):
    bus.recover_stale()
    processed = 0
    for event in bus.claim(20):
        payload = json.loads(event["payload"])
        kind = event["kind"]
        job_payload = payload.get("payload", {}) if isinstance(payload, dict) else {}
        try:
            if kind == "integration.noop":
                bus.finish(event["id"])
            elif kind in {"github.push", "github.pull_request"}:
                result = handle_github_audit(kind, job_payload)
                bus.finish(event["id"])
                Handler.worker_state["last_audit"] = result
            elif kind.startswith("github."):
                # Valid but unsupported event: acknowledge without side effects.
                bus.finish(event["id"])
            else:
                bus.finish(event["id"], "no_safe_handler_registered")
        except Exception as exc:
            bus.finish(event["id"], type(exc).__name__ + ": " + str(exc)[:300])
        processed += 1
    Handler.worker_state["processed"] += processed
    Handler.worker_state["last_run"] = time.time()
    return processed


def _safe_public_url(value):
    """Require a public HTTP(S) target and reject non-global DNS answers."""
    from urllib.parse import urlparse

    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("invalid_site_url")
    parsed = urlparse(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("invalid_site_url")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(
        (".local", ".internal", ".localhost", ".test")
    ):
        raise ValueError("non_public_site_url")
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(
                host,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        }
        if not addresses or any(
            not ipaddress.ip_address(address).is_global for address in addresses
        ):
            raise ValueError("non_public_site_url")
    except socket.gaierror as exc:
        raise ValueError("site_host_not_resolvable") from exc
    return value


def handle_github_audit(kind, payload):
    """Run a bounded, deterministic site audit only for explicitly wired GitHub events."""
    if not isinstance(payload, dict) or not payload.get("delivery"):
        raise ValueError("missing_delivery_id")
    event_name = kind.removeprefix("github.")
    summary = payload.get("payload") or {}
    if not isinstance(summary, dict):
        raise ValueError("invalid_github_summary")
    expected_repos = {
        item.strip().lower()
        for item in os.getenv("GITHUB_REPOSITORY_ALLOWLIST", "").split(",")
        if item.strip()
    }
    repository = summary.get("repository", "")
    if (
        not expected_repos
        or not isinstance(repository, str)
        or repository.lower() not in expected_repos
    ):
        raise ValueError("github_repository_not_allowlisted")
    event_action = summary.get("action")
    if event_name == "pull_request" and event_action not in {
        "opened",
        "synchronize",
        "reopened",
        "ready_for_review",
    }:
        return {"status": "skipped", "reason": "pull_request_action_not_allowlisted"}
    if event_name == "push" and (summary.get("deleted") or summary.get("forced")):
        return {"status": "skipped", "reason": "push_action_not_allowlisted"}
    site_url = os.getenv("GITHUB_AUDIT_SITE_URL", "")
    if not site_url:
        raise ValueError("GITHUB_AUDIT_SITE_URL_not_configured")
    site_url = _safe_public_url(site_url)
    from auditor_toolkit.pipeline import AuditOptions, run_audit

    output_root = Path(os.getenv("WA_ROOT", ".")).resolve() / "outputs" / "github-audits"
    report = run_audit(
        site_url,
        AuditOptions(
            output_root=output_root,
            profile="static",
            deep=False,
            ai=False,
            browser=False,
            tls=False,
            external_tools=False,
            max_pages=3,
            max_depth=1,
            max_links=10,
            timeout=8.0,
            max_bytes=1_000_000,
        ),
    )
    return {
        "status": "complete",
        "run_id": report.get("run_id"),
        "url": site_url,
        "findings": report.get("defect_count", 0),
        "report": report.get("artifacts", {}).get("json"),
    }


def serve_omniroute_mcp():
    """Exec OmniRoute's stdio server with its full upstream tool set hidden behind our allowlist."""
    command = os.getenv("OMNIROUTE_MCP_COMMAND", "omniroute --mcp")
    os.environ["OMNIROUTE_MCP_ENFORCE_SCOPES"] = "true"
    os.environ["OMNIROUTE_MCP_SCOPES"] = "read:health,read:combos,read:quota,read:usage,read:models"
    child = __import__("subprocess").Popen(
        command.split(),
        stdin=__import__("subprocess").PIPE,
        stdout=__import__("subprocess").PIPE,
        stderr=sys.stderr,
        text=True,
        bufsize=1,
    )
    assert child.stdin and child.stdout

    def next_json_line():
        while True:
            reply = child.stdout.readline()
            if not reply:
                return None
            try:
                return json.loads(reply)
            except json.JSONDecodeError:
                print(reply, file=sys.stderr, end="", flush=True)

    try:
        for line in sys.stdin:
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                continue
            method = request.get("method")
            if method == "tools/list":
                child.stdin.write(line)
                child.stdin.flush()
                response = next_json_line()
                if response is None:
                    break
                result = response.get("result", {})
                result["tools"] = [
                    tool
                    for tool in result.get("tools", [])
                    if tool.get("name") in READONLY_OMNIROUTE_TOOLS
                ]
                response["result"] = result
                print(json.dumps(response), flush=True)
                continue
            if (
                method == "tools/call"
                and request.get("params", {}).get("name") not in READONLY_OMNIROUTE_TOOLS
            ):
                print(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": request.get("id"),
                            "error": {
                                "code": -32602,
                                "message": "Tool is not in the read-only OmniRoute allowlist",
                            },
                        }
                    ),
                    flush=True,
                )
                continue
            child.stdin.write(line)
            child.stdin.flush()
            if method and method.startswith("notifications/"):
                continue
            response = next_json_line()
            if response is None:
                break
            print(json.dumps(response), flush=True)
    finally:
        child.terminate()
        try:
            child.wait(timeout=3)
        except __import__("subprocess").TimeoutExpired:
            child.kill()


READONLY_OMNIROUTE_TOOLS = {
    "omniroute_get_health",
    "omniroute_list_combos",
    "omniroute_get_combo_metrics",
    "omniroute_check_quota",
    "omniroute_cost_report",
    "omniroute_list_models_catalog",
}


def _worker_loop(bus: EventBus, idle_seconds: float = 1.0):
    Handler.worker_state["running"] = True
    while True:
        try:
            process_batch(bus)
        except Exception as exc:
            Handler.worker_state["last_error"] = type(exc).__name__
        time.sleep(idle_seconds)


def run_http(root=".", host="127.0.0.1", port=DEFAULT_PORT, worker=True):
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("integration receiver must bind to loopback")
    root = Path(root)
    Handler.root, Handler.bus = root, EventBus(root / "outputs" / "integration-events.db")
    if worker:
        threading.Thread(
            target=_worker_loop, args=(Handler.bus,), daemon=True, name="integration-worker"
        ).start()
    ThreadingHTTPServer((host, port), Handler).serve_forever()


def run_mcp():
    root = Path(os.getenv("WA_ROOT", "."))
    bus = EventBus(root / "outputs" / "integration-events.db")
    for line in sys.stdin:
        try:
            req = json.loads(line)
            method, ident = req.get("method"), req.get("id")
            if method == "notifications/initialized":
                continue
            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "website-auditor-integrations", "version": "1.0"},
                }
            elif method == "tools/list":
                result = {
                    "tools": [
                        {
                            "name": "integration_status",
                            "description": "Return local integration health",
                            "inputSchema": {
                                "type": "object",
                                "properties": {},
                                "additionalProperties": False,
                            },
                            "annotations": {"readOnlyHint": True},
                        },
                        {
                            "name": "publish_event",
                            "description": "Queue a local event",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "kind": {"type": "string"},
                                    "payload": {"type": "object"},
                                },
                                "required": ["payload"],
                                "additionalProperties": False,
                            },
                        },
                    ]
                }
            elif method == "tools/call":
                args = req.get("params", {}).get("arguments", {})
                name = req.get("params", {}).get("name")
                if name == "publish_event":
                    job = Job(args.get("kind", "integration.event"), args.get("payload", {}), "mcp")
                    result = {
                        "content": [
                            {"type": "text", "text": json.dumps({"job_id": bus.publish(job)})}
                        ]
                    }
                elif name == "integration_status":
                    result = {
                        "content": [{"type": "text", "text": json.dumps(status(root))}],
                        "isError": False,
                    }
                else:
                    result = {
                        "content": [{"type": "text", "text": "Unknown tool"}],
                        "isError": True,
                    }
            else:
                if ident is None:
                    continue
                print(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": ident,
                            "error": {"code": -32601, "message": "Method not found"},
                        }
                    ),
                    flush=True,
                )
                continue
            if ident is not None:
                print(json.dumps({"jsonrpc": "2.0", "id": ident, "result": result}), flush=True)
        except Exception as exc:
            print(
                json.dumps(
                    {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(exc)}}
                ),
                flush=True,
            )

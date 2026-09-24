"""Bounded stdio MCP server backed by MoneyMachine's Python API."""
from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path
from typing import Any

MM = Path(__file__).resolve().parents[1] / "money-machine"
if str(MM) not in sys.path:
    sys.path.insert(0, str(MM))

TOOLS = [
    ("auditor_health", "Read local supervisor and system health", {}),
    ("auditor_status", "Read the deterministic operator status", {}),
    ("audit_site", "Request a bounded public-site audit via existing queued pipeline", {"business_id": "integer"}),
    ("audit_get_result", "Read latest evidence for a prospect", {"business_id": "integer"}),
    ("audit_get_evidence", "Read one evidence record", {"evidence_id": "integer"}),
    ("prospect_get", "Read one real prospect", {"business_id": "integer"}),
    ("prospect_search", "Search real prospects by name or domain", {"query": "string"}),
    ("prospect_score", "Read saved deterministic prospect score", {"business_id": "integer"}),
    ("queue_list", "List local leased pipeline jobs", {"limit": "integer?"}),
    ("queue_get", "Read a queued prospect job", {"business_id": "integer"}),
    ("queue_submit", "Idempotently enqueue an existing prospect for audit", {"business_id": "integer", "idempotency_key": "string"}),
    ("queue_retry", "Retry eligible prospect work through bounded pipeline policy", {"business_id": "integer"}),
    ("proof_build", "Build evidence packet by returning existing proof status (no deployment)", {"business_id": "integer"}),
    ("proof_status", "Read evidence/proof readiness", {"business_id": "integer"}),
    ("quote_generate", "Return an existing proposal; prices require separate human decision", {"business_id": "integer"}),
    ("draft_generate", "Read existing draft; does not compose or send messages", {"business_id": "integer"}),
    ("draft_quality_check", "Check stored draft for quality and secret-like content", {"business_id": "integer"}),
    ("approval_status", "Read human approval gates", {"business_id": "integer"}),
    ("metrics_get", "Read local metrics", {}),
    ("errors_get", "Read sanitized local errors", {"limit": "integer?"}),
    ("dead_letter_list", "List failed local pipeline items", {"limit": "integer?"}),
    ("obsidian_sync", "Sync read-mostly runtime summaries to operator vault", {}),
]


def _schema(props: dict[str, str]) -> dict[str, Any]:
    mapping = {"integer": {"type": "integer"}, "integer?": {"type": "integer", "minimum": 1, "maximum": 1000},
               "string": {"type": "string", "minLength": 1, "maxLength": 200}}
    required = [key for key, kind in props.items() if not kind.endswith("?")]
    return {"type": "object", "properties": {key: mapping[kind] for key, kind in props.items()}, "required": required, "additionalProperties": False}


def tool_specs():
    return [{"name": name, "description": description, "inputSchema": _schema(props)} for name, description, props in TOOLS]


def _prospect(bid: int, readonly=True):
    import mm_core as core
    d = core.connect(readonly=readonly)
    row = d.execute("SELECT id,name,region,public_website,source,discovered_at,current_status FROM businesses WHERE id=? AND is_dummy=0", (bid,)).fetchone()
    d.close()
    if not row:
        raise ValueError("Real prospect not found")
    return dict(row)


def call_tool(name: str, args: dict[str, Any]):
    import mm_core as core
    import mm_observability as obs
    import mm_pipeline as pipeline
    import mm_intelligence as intelligence
    import mm_approval as approval
    from integrations.registry import integrations_status
    if name == "auditor_health": return obs.health()
    if name == "auditor_status": return integrations_status()
    if name in {"audit_site", "queue_submit"}:
        bid = args["business_id"]
        key = args.get("idempotency_key", f"mcp-audit-{bid}")
        if len(key) > 128: raise ValueError("idempotency_key is too long")
        d = core.connect()
        try:
            core.business(d, bid)
            pipeline.migrate(d)
            existing = d.execute("SELECT state,attempts FROM pipeline_items WHERE business_id=?", (bid,)).fetchone()
            if existing and existing["state"] not in {"RETRYABLE_FAILURE", "PERMANENT_FAILURE"}:
                return {"business_id": bid, "state": existing["state"], "idempotent": True, "external_sends": 0}
            result = dict(pipeline.enqueue(d, bid, "DISCOVERED"))
            result.update({"business_id": bid, "idempotency_key": key, "external_sends": 0})
            return result
        finally: d.close()
    if name in {"audit_get_result", "proof_build", "proof_status"}:
        bid = args["business_id"]
        _prospect(bid)
        d = core.connect(readonly=True)
        try:
            rows = [dict(r) for r in d.execute("SELECT id,claim_type,claim,checked_at FROM mm_evidence WHERE business_id=? ORDER BY id DESC LIMIT 100", (bid,))]
            return {"business_id": bid, "evidence": rows, "proof_ready": bool(rows), "build_action": "read_only_existing_evidence", "live_site_changed": False}
        finally: d.close()
    if name == "audit_get_evidence":
        d = core.connect(readonly=True)
        try:
            row = d.execute("SELECT id,business_id,claim_type,claim,checked_at FROM mm_evidence WHERE id=?", (args["evidence_id"],)).fetchone()
            if not row: raise ValueError("Evidence not found")
            return dict(row)
        finally: d.close()
    if name == "prospect_get": return _prospect(args["business_id"])
    if name == "prospect_search":
        query = args["query"].strip()
        if len(query) < 2: raise ValueError("Search query must contain at least 2 characters")
        d = core.connect(readonly=True)
        try:
            rows = d.execute("SELECT id,name,region,public_website,current_status FROM businesses WHERE is_dummy=0 AND (name LIKE ? OR public_website LIKE ?) ORDER BY id LIMIT 100", ("%"+query+"%", "%"+query+"%"))
            return {"items": [dict(row) for row in rows]}
        finally: d.close()
    if name == "prospect_score":
        _prospect(args["business_id"])
        d = core.connect(readonly=True)
        try:
            row = d.execute("SELECT computed_json FROM mm_scores WHERE business_id=?", (args["business_id"],)).fetchone()
            return json.loads(row[0]) if row else {"status": "not_scored"}
        finally: d.close()
    if name in {"queue_list", "dead_letter_list"}:
        result = obs.queue(args.get("limit", 100))
        if name == "dead_letter_list": result["items"] = [item for item in result["items"] if item.get("state") in ("RETRYABLE_FAILURE", "PERMANENT_FAILURE")]; result["count"] = len(result["items"])
        return result
    if name in {"queue_get", "queue_retry"}:
        bid = args["business_id"]
        _prospect(bid)
        if name == "queue_retry":
            d = core.connect()
            try:
                pipeline.migrate(d)
                row = d.execute("SELECT state,attempts,max_attempts,next_retry_at FROM pipeline_items WHERE business_id=?", (bid,)).fetchone()
                if not row: raise ValueError("Queue item not found")
                if row["state"] not in ("RETRYABLE_FAILURE", "PERMANENT_FAILURE") or row["attempts"] >= row["max_attempts"]:
                    raise ValueError("Retry is not permitted by current queue state/budget")
                result = dict(pipeline.transition(d, bid, "DISCOVERED", "mcp", "operator-requested bounded retry"))
                d.commit(); return result
            finally: d.close()
        return next((row for row in obs.queue(1000)["items"] if row["business_id"] == bid), None)
    if name in {"quote_generate", "draft_generate", "draft_quality_check", "approval_status"}:
        bid = args["business_id"]
        _prospect(bid)
        d = core.connect(readonly=name in {"draft_generate", "draft_quality_check", "approval_status"})
        try:
            if name == "approval_status": return approval.evaluate(d, bid)
            table = "mm_proposals" if name == "quote_generate" else "mm_messages"
            row = d.execute(f"SELECT id,recipient,body,created_at,approved_hash,price_cents FROM {table} WHERE business_id=? AND invalidated_reason IS NULL ORDER BY id DESC LIMIT 1", (bid,)).fetchone()
            if not row: return {"status": "not_found"}
            result = dict(row)
            if name == "draft_quality_check":
                from mm_approval import contains_secret
                issues = ["secret_like_content"] if contains_secret(row["body"]) else []
                result = {"id": row["id"], "passed": not issues, "issues": issues, "human_review_required": True}
            else:
                result.pop("body", None)
                result["human_review_required"] = True
                result["send_enabled"] = False
            return result
        finally: d.close()
    if name == "metrics_get": return obs.metrics()
    if name == "errors_get": return obs.errors(args.get("limit", 100))
    if name == "obsidian_sync":
        import mm_obsidian
        return mm_obsidian.sync()
    raise ValueError("Unknown tool")


def _response(request_id, result=None, error=None):
    body = {"jsonrpc": "2.0", "id": request_id}
    if error: body["error"] = error
    else: body["result"] = result
    encoded = json.dumps(body, separators=(",", ":")).encode()
    return f"Content-Length: {len(encoded)}\r\n\r\n".encode() + encoded


def serve(reader=None, writer=None):
    reader, writer = reader or sys.stdin.buffer, writer or sys.stdout.buffer
    while True:
        headers = {}
        while True:
            line = reader.readline()
            if not line: return
            if line in (b"\r\n", b"\n"): break
            if b":" in line:
                key, value = line.decode("ascii", "replace").split(":", 1); headers[key.lower()] = value.strip()
        try:
            size = int(headers.get("content-length", "-1"))
            if not 0 <= size <= 1_000_000: raise ValueError("invalid frame length")
            msg = json.loads(reader.read(size))
            method, request_id = msg.get("method"), msg.get("id")
            params = msg.get("params", {})
            if method == "initialize": result = {"protocolVersion": params.get("protocolVersion", "2025-03-26"), "capabilities": {"tools": {}}, "serverInfo": {"name": "website-auditor", "version": "1.0.0"}}
            elif method == "notifications/initialized": continue
            elif method == "ping": result = {}
            elif method == "tools/list": result = {"tools": tool_specs()}
            elif method == "tools/call":
                tool_name = params.get("name")
                args = params.get("arguments", {})
                if tool_name not in {tool[0] for tool in TOOLS}: raise ValueError("Unknown tool")
                result = {"content": [{"type": "text", "text": json.dumps(call_tool(tool_name, args), default=str)}], "isError": False}
            else: raise ValueError("Unsupported MCP method")
            if request_id is not None: writer.write(_response(request_id, result)); writer.flush()
        except Exception as exc:
            if 'request_id' in locals() and request_id is not None:
                from integrations.security import redact
                writer.write(_response(request_id, error={"code": -32000, "message": str(redact(str(exc)))})); writer.flush()


if __name__ == "__main__":
    with contextlib.suppress(BrokenPipeError):
        serve()

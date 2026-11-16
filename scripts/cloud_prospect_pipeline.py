"""Bounded, checkpointed audit-to-draft worker. No outreach/provider adapter exists."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.robotparser import RobotFileParser

from auditor_toolkit.common import Fetcher
from scripts.cloud_pipeline_outcomes import import_outcomes, outcome_metrics
from scripts.cloud_review_only_opportunities import _verify_safety, run_review_sites
from scripts.cloud_scheduled_audits import HOST, load_sites

MAX_PROSPECTS = 100
MAX_EVENTS = 10000
MAX_STATE_BYTES = 5_000_000
ERRORS = {"none", "audit_incomplete", "audit_failed", "robots_blocked", "policy_blocked"}
ACTIONS = {"discovery", "audit", "draft", "suppression", "approval_config", "recovery"}
STATUSES = {"queued", "succeeded", "retry", "failed", "pending", "blocked", "disabled", "approved"}


def timestamp(now: int) -> str:
    return datetime.fromtimestamp(now, timezone.utc).isoformat()


def empty_state() -> dict:
    return {"schema_version": 1, "prospects": {}, "events": []}


def event(state, now, run_id, entity_id, action, status, error="none"):
    # Allowlist codes; no arbitrary exception, website text, address or credential.
    if action not in ACTIONS or status not in STATUSES or error not in ERRORS:
        raise ValueError("Invalid event schema")
    if not run_id or len(run_id) > 100 or not all(c.isalnum() or c in "-_" for c in run_id):
        raise ValueError("Invalid correlation ID")
    if len(entity_id) != 64 or any(c not in "0123456789abcdef" for c in entity_id):
        raise ValueError("Invalid entity ID")
    if len(state["events"]) >= MAX_EVENTS:
        raise ValueError("Event capacity reached; owner archive required")
    state["events"].append(
        dict(
            timestamp_utc=timestamp(now),
            run_id=run_id,
            entity_id=entity_id,
            action=action,
            status=status,
            sanitized_error=error,
        )
    )


def policy_rows(repo: Path) -> list[dict]:
    # Production passes the source checkout root, never a CLI-supplied filename.
    path = repo / "config" / "cloud-prospects.json"
    allowlist = repo / "clients.txt"
    if path.is_symlink() or allowlist.is_symlink() or path.parent.is_symlink():
        raise ValueError("Tracked intake files must not be symlinks")
    if path.stat().st_size > 100_000:
        raise ValueError("Oversized prospect source")
    allowed = dict(load_sites(allowlist))
    rows = json.loads(path.read_text())
    if not isinstance(rows, list) or len(rows) > MAX_PROSPECTS:
        raise ValueError("Invalid bounded prospect source")
    seen = set()
    for row in rows:
        host = row.get("domain")
        if (
            not isinstance(host, str)
            or not HOST.fullmatch(host)
            or "." not in host
            or host in seen
            or (host not in allowed and row.get("suppressed") is not True)
        ):
            raise ValueError("Prospects must be unique reviewed allowlist domains")
        seen.add(host)
        # Only curated business prospects with an explicit owner policy review.
        if (
            row.get("public_business") is not True
            or row.get("terms_reviewed") is not True
            or (row.get("audit_authorized") is not True and row.get("suppressed") is not True)
            or not isinstance(row.get("suppressed", False), bool)
        ):
            raise ValueError("Missing public business, authorization or terms review")
        row["url"] = allowed.get(host, "")
    return rows


def robots_allowed(url: str) -> bool:
    client = Fetcher(timeout=8, max_bytes=100_000, min_interval=1)
    try:
        response = client.get(url.rstrip("/") + "/robots.txt")
        if response.status_code in (404, 410):
            return True
        if response.status_code != 200:
            return False
        robot = RobotFileParser()
        robot.parse(response.text.splitlines())
        return robot.can_fetch("WebsiteAuditorToolkit", url)
    finally:
        client.close()


def process(
    state, rows, *, now, run_id, workspace, audit=run_review_sites, robots=robots_allowed, limit=3
):
    if not 1 <= limit <= 3:
        raise ValueError("Maximum three audits per run")
    # Reserve enough room before any requests; never silently discard history.
    if len(state["events"]) + len(rows) * 3 + limit * 3 + 1 > MAX_EVENTS:
        raise ValueError("Archive state before continuing")
    if (
        len(state["prospects"])
        + sum(
            hashlib.sha256(r["domain"].encode()).hexdigest() not in state["prospects"] for r in rows
        )
        > MAX_PROSPECTS
    ):
        raise ValueError("Queue capacity reached")
    event(state, now, run_id, "0" * 64, "approval_config", "disabled")
    active = set()
    for row in rows:
        identity = hashlib.sha256(row["domain"].encode()).hexdigest()
        active.add(identity)
        p = state["prospects"].get(identity)
        if p is None:
            p = dict(
                domain=row["domain"],
                url=row["url"],
                first_seen=timestamp(now),
                status="queued",
                attempts=0,
                next_attempt=now,
                audit=None,
                draft=None,
            )
            state["prospects"][identity] = p
            event(state, now, run_id, identity, "discovery", "queued")
        p["last_seen"] = timestamp(now)
        if row.get("suppressed") and p["status"] != "suppressed":
            p["status"] = "suppressed"
            p["draft"] = None
            event(state, now, run_id, identity, "suppression", "blocked")
    # Removing a source immediately blocks future audit attempts. Suppression is sticky.
    for identity, p in state["prospects"].items():
        if identity not in active and p["status"] not in {"suppressed", "removed"}:
            p["status"] = "removed"
            p["draft"] = None
            event(state, now, run_id, identity, "suppression", "blocked", "policy_blocked")
    used = 0
    for identity, p in state["prospects"].items():
        if used >= limit or p["status"] not in {"queued", "retry"} or p["next_attempt"] > now:
            continue
        used += 1
        p["attempts"] += 1
        p["last_attempt"] = timestamp(now)
        error = "audit_failed"
        try:
            if not robots(p["url"]):
                error = "robots_blocked"
            else:
                entries = []
                result = audit([(p["domain"], p["url"])], workspace / identity, entries)[0]
                if result["status"] == "COMPLETE" and len(entries) == 1:
                    p["audit"] = entries[0]
                    p["draft"] = entries[0].get("internal_scope_draft")
                    p["status"] = "complete"
                    event(state, now, run_id, identity, "audit", "succeeded")
                    if p["draft"]:
                        event(state, now, run_id, identity, "draft", "pending")
                    continue
                error = "audit_incomplete"
        except Exception:
            pass  # Raw exceptions can contain credentials or external personal data.
        p["status"] = "failed" if p["attempts"] >= 3 else "retry"
        p["next_attempt"] = now + 3600 * 2 ** (p["attempts"] - 1)
        event(state, now, run_id, identity, "audit", p["status"], error)
    return metrics(state)


def metrics(state):
    prospects = list(state["prospects"].values())
    ready = sum(bool(p["draft"]) for p in prospects)
    report = dict(
        prospects_found=len(prospects),
        audits_succeeded=sum(p["status"] == "complete" for p in prospects),
        audits_failed=sum(p["status"] == "failed" for p in prospects),
        retries_pending=sum(p["status"] == "retry" for p in prospects),
        drafts_ready=ready,
        approvals_pending=ready,
        contacts_sent=0,
        provider_accepted=0,
        delivered=0,
        replies=0,
        accepted_quotes=0,
        confirmed_revenue=0,
        revenue_status="zero verified; not reconciled",
        paid_api_cost=0,
        infrastructure_cost="unknown; check Actions billing",
        auto_send="blocked; delivery/compliance gates unverified",
    )
    report.update(outcome_metrics(state))
    approved = {}
    for item in state.get("business_events", []):
        if item["action"] == "approval":
            approved[item["entity_id"]] = item["status"] == "approved"
    report["approvals_pending"] = sum(
        bool(prospect["draft"]) and not approved.get(identity, False)
        for identity, prospect in state["prospects"].items()
    )
    return report


def private_state_path(path: Path) -> Path:
    """Only explicit checkpoint files inside the runner/system temporary directory."""
    root = Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())).resolve()
    path = Path(path).absolute()
    if (
        path.suffix != ".enc"
        or ".." in path.parts
        or path.is_symlink()
        or not path.parent.is_dir()
        or not path.resolve().is_relative_to(root)
        or path.parent.resolve() != path.parent
    ):
        raise ValueError("Checkpoint must be a regular .enc file inside runner temp")
    return path


def seal(state: dict, path: Path, key: str):
    from cryptography.fernet import Fernet

    path = private_state_path(path)
    raw = json.dumps(state, sort_keys=True).encode()
    if len(raw) > MAX_STATE_BYTES:
        raise ValueError("State capacity exceeded")
    encrypted = Fernet(key.encode()).encrypt(raw)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(encrypted)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def unseal(path: Path, key: str) -> dict:
    from cryptography.fernet import Fernet

    path = private_state_path(path)
    if path.stat().st_size > MAX_STATE_BYTES * 2:
        raise ValueError("Oversized checkpoint")
    state = json.loads(Fernet(key.encode()).decrypt(path.read_bytes()))
    if (
        state.get("schema_version") != 1
        or not isinstance(state.get("prospects"), dict)
        or not isinstance(state.get("events"), list)
        or len(state["prospects"]) > MAX_PROSPECTS
        or len(state["events"]) > MAX_EVENTS
    ):
        raise ValueError("Invalid checkpoint")
    return state


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--bootstrap", action="store_true")
    args = parser.parse_args(argv)
    try:
        _verify_safety(Path(__file__).resolve().parents[1])
        key = os.environ["WA_PIPELINE_STATE_KEY"]
        # Validate key before requests, even at bootstrap.
        from cryptography.fernet import Fernet

        Fernet(key.encode())
        if args.bootstrap and args.state.exists():
            raise ValueError("Refusing to replace an existing checkpoint")
        state = empty_state() if args.bootstrap else unseal(args.state, key)
        recovery = os.environ.get("WA_RECOVERY_RUN", "").strip()
        if recovery:
            if not recovery.isdecimal() or args.bootstrap:
                raise ValueError("Invalid explicit recovery")
            event(
                state,
                int(datetime.now(timezone.utc).timestamp()),
                os.environ.get("GITHUB_RUN_ID", "local"),
                "0" * 64,
                "recovery",
                "approved",
            )
        token = os.environ.get("WA_OUTCOMES_ENCRYPTED", "").strip()
        if token:
            if len(token) > 50_000:
                raise ValueError("Oversized outcome import")
            document = json.loads(Fernet(key.encode()).decrypt(token.encode()))
            import_outcomes(
                state,
                document,
                now=int(datetime.now(timezone.utc).timestamp()),
                run_id=os.environ.get("GITHUB_RUN_ID", "local"),
                actor=os.environ.get("GITHUB_ACTOR", "local-owner"),
            )
        rows = policy_rows(Path(__file__).resolve().parents[1])
        with tempfile.TemporaryDirectory(prefix="wa-pipeline-") as temporary:
            report = process(
                state,
                rows,
                now=int(datetime.now(timezone.utc).timestamp()),
                run_id=os.environ.get("GITHUB_RUN_ID", "local"),
                workspace=Path(temporary),
            )
        seal(state, args.state, key)
        summary = json.dumps(report, sort_keys=True, indent=2)
        print(summary)  # Counts only. Plaintext evidence never leaves temporary storage.
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as stream:
                stream.write("## Durable draft pipeline\n\n```json\n" + summary + "\n```\n")
        return 0
    except Exception:
        print("Pipeline blocked; inspect configuration privately. No raw errors logged.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

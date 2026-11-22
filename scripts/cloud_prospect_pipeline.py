"""Bounded, checkpointed audit-to-draft worker. No outreach/provider adapter exists."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from contextlib import ExitStack
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from urllib.robotparser import RobotFileParser

from auditor_toolkit.common import Fetcher
from scripts.cloud_pipeline_outcomes import import_outcomes, outcome_metrics
from scripts.cloud_review_only_opportunities import _verify_safety, run_review_sites
from scripts.cloud_scheduled_audits import HOST, load_sites

MAX_PROSPECTS = 100
MAX_EVENTS = 10000
MAX_STATE_BYTES = 5_000_000
ERRORS = {"none", "audit_incomplete", "audit_failed", "robots_blocked", "policy_blocked", "quota_exhausted"}
ACTIONS = {"discovery", "audit", "draft", "suppression", "approval_config", "recovery", "budget", "pause"}
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
        from scripts.cloud_discovery import canonical_domain

        canonical = canonical_domain(host)
        if canonical in seen:
            raise ValueError("Duplicate canonical website in reviewed intake")
        seen.add(canonical)
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
    state, rows, *, now, run_id, workspace, audit=run_review_sites, robots=robots_allowed, limit=3,
    daily_limit=6,
    opportunity_policy=None,
    attempt_reserver=None,
):
    if type(limit) is not int or not 1 <= limit <= 3:
        raise ValueError("Maximum three audits per run")
    if type(daily_limit) is not int or not 0 <= daily_limit <= 6:
        raise ValueError("Maximum six audits per UTC day")
    if opportunity_policy is not None:
        from scripts.cloud_opportunities import validate_policy

        validate_policy(opportunity_policy)
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
        # Curated intake is the permitted source adapter. Absent metadata remains
        # unknown; do not manufacture business names, sectors or source evidence.
        p["discovery"] = {
            key: row[key] for key in (
                "business_name", "category", "region", "source", "source_url",
                "reviewed_at", "policy_evidence_sha256", "review_basis",
            ) if key in row
        }
        p["discovery"].setdefault("source", "owner_reviewed_manifest")
        p["verification_status"] = "policy_reviewed_identity_unverified"
        p["service_context"] = {
            key: row[key] for key in (
                "delivery_feasibility", "business_service_fit", "contact_prohibited"
            ) if key in row
        }
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
    # Discovery alone never supplies audit queue entries. Link only records that
    # independently passed the tracked policy/allowlist gate above.
    from scripts.cloud_discovery import canonical_domain

    for identity, p in state["prospects"].items():
        candidate_id = hashlib.sha256(canonical_domain(p["domain"]).encode()).hexdigest()
        candidate = state.get("discovery_candidates", {}).get(candidate_id)
        if candidate is not None:
            p.setdefault("discovery", {})
            existing_link = candidate.get("prospect_id")
            if existing_link not in (None, identity):
                raise ValueError("Ambiguous canonical discovery link")
            candidate["prospect_id"] = identity
            p["discovery_candidate_id"] = candidate_id
            p["discovery_sources"] = candidate["sources"]
            for key in ("business_name", "region", "category"):
                if not p["discovery"].get(key):
                    p["discovery"][key] = candidate.get(key, "")
            candidate["eligibility_status"] = (
                "blocked" if p["status"] in {"suppressed", "removed"} else "reviewed_allowlist"
            )
    history = state.setdefault("audit_runs", [])
    if len(history) + limit > MAX_EVENTS:
        raise ValueError("Archive audit history before continuing")
    day = timestamp(now)[:10]
    # Count older checkpoint audit events too, so migration cannot reset usage.
    used_today = sum(
        e.get("action") == "audit" and e.get("timestamp_utc", "")[:10] == day
        for e in state["events"]
    )
    budget = min(limit, max(0, daily_limit - used_today))
    used = 0
    for identity, p in state["prospects"].items():
        if used >= budget or p["status"] not in {"queued", "retry"} or p["next_attempt"] > now:
            continue
        audit_id = hashlib.sha256(f"{identity}:{run_id}:{p['attempts'] + 1}".encode()).hexdigest()
        if attempt_reserver is not None and not attempt_reserver(
            identity, audit_id, now=now, daily_limit=daily_limit
        ):
            p["operational_status"] = "quota_blocked"
            event(state, now, run_id, identity, "budget", "blocked", "quota_exhausted")
            continue
        p.pop("operational_status", None)
        used += 1
        p["attempts"] += 1
        p["last_attempt"] = timestamp(now)
        attempt = dict(
            audit_id=audit_id,
            prospect_id=identity, domain=p["domain"], execution_timestamp=timestamp(now),
            pipeline_run_id=run_id,
            auditor_version=version("website-auditor"), status="failed",
            retry_count=p["attempts"] - 1, failure_category="audit_failed",
            canonical_run_id=None, evidence_references=[], finding_counts={},
            encrypted_artifact_reference=None,
            checks_completed=[],
        )
        history.append(attempt)
        error = "audit_failed"
        try:
            if not robots(p["url"]):
                error = "robots_blocked"
            else:
                entries = []
                result = audit([(p["domain"], p["url"])], workspace / identity, entries)[0]
                if result["status"] == "COMPLETE" and len(entries) == 1:
                    attempt.update(
                        status="complete", failure_category="none",
                        canonical_run_id=entries[0].get("run_id"),
                        checks_completed=entries[0].get("checks_completed", []),
                        evidence_references=sorted({
                            f["evidence_ref"] for f in entries[0].get("findings", [])
                            if f.get("evidence_ref")
                        }),
                        finding_counts={
                            severity: sum(f.get("severity") == severity
                                          for f in entries[0].get("findings", []))
                            for severity in ("low", "medium", "high", "critical")
                        },
                    )
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
        p["audit"] = None
        p["draft"] = None
        attempt["failure_category"] = error
        attempt["status"] = "partial" if error == "audit_incomplete" else "failed"
        p["next_attempt"] = now + 3600 * 2 ** (p["attempts"] - 1)
        event(state, now, run_id, identity, "audit", p["status"], error)
    for candidate in state.get("discovery_candidates", {}).values():
        if candidate.get("prospect_id") in state["prospects"]:
            candidate["audit_status"] = state["prospects"][candidate["prospect_id"]]["status"]
    if opportunity_policy is not None:
        from scripts.cloud_opportunities import enrich

        enrich(state, opportunity_policy, now=now)
    return metrics(state)


def metrics(state):
    prospects = list(state["prospects"].values())
    ready = sum(bool(p["draft"]) for p in prospects)
    def proposal_pending(prospect):
        version = prospect.get("proposal_version")
        decisions = [a for a in prospect.get("approvals", []) if a["action_type"] == "proposal"]
        return bool(version) and not (
            decisions and decisions[-1]["decision"] == "approved"
            and decisions[-1]["version_sha256"] == version
        )

    report = dict(
        prospects_found=len(prospects),
        encrypted_reports_indexed=len(state.get("report_artifacts", {})),
        audits_succeeded=sum(p["status"] == "complete" for p in prospects),
        audits_failed=sum(p["status"] == "failed" for p in prospects),
        retries_pending=sum(p["status"] == "retry" for p in prospects),
        drafts_ready=ready,
        qualified_opportunities=sum(
            p.get("opportunity", {}).get("status") == "qualified_for_internal_review" for p in prospects
        ),
        proposal_drafts_ready=sum(bool(p.get("proposal_version")) for p in prospects),
        proposal_reviews_pending=sum(proposal_pending(p) for p in prospects),
        active_projects=sum(
            project["status"] != "closed" for p in prospects for project in p.get("projects", {}).values()
        ),
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
    storage = parser.add_mutually_exclusive_group(required=True)
    storage.add_argument("--state", type=Path)
    storage.add_argument("--database", type=Path, help="Private durable SQLite; never an Actions artifact")
    storage.add_argument("--postgres", action="store_true", help="Private Postgres via server-only WA_POSTGRES_DSN")
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--max-audits", type=int, default=3)
    parser.add_argument("--daily-limit", type=int, default=6)
    parser.add_argument("--paused", action="store_true", help="Record a paused run without processing stages")
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.max_audits <= 3 or not 0 <= args.daily_limit <= 6:
            raise ValueError("Workload limits exceed hard caps")
        if args.paused and os.environ.get("WA_OUTCOMES_ENCRYPTED", "").strip():
            raise ValueError("Paused runs cannot import outcome changes")
        _verify_safety(Path(__file__).resolve().parents[1])
        from scripts.cloud_opportunities import load_policy

        opportunity_policy = load_policy(Path(__file__).resolve().parents[1])
        key = os.environ.get("WA_PIPELINE_STATE_KEY", "")
        if args.state or os.environ.get("WA_OUTCOMES_ENCRYPTED"):
            from cryptography.fernet import Fernet

            Fernet(key.encode())  # Validate before requests.
        with ExitStack() as stack:
            attempt_reserver = None
            if args.database or args.postgres:
                if os.environ.get("WA_RECOVERY_RUN"):
                    raise ValueError("Artifact recovery does not apply to a database")
                if args.postgres:
                    from scripts.postgres_store import PostgresPipelineStore

                    store = PostgresPipelineStore()
                else:
                    from scripts.pipeline_store import PipelineStore

                    store = PipelineStore(args.database)
                state = stack.enter_context(store.transaction(bootstrap=args.bootstrap))
                def attempt_reserver(prospect_id, audit_id, *, now, daily_limit):
                    # Use the actual request-reservation day if a batch crosses
                    # midnight; processing's explicit clock still drives scoring.
                    return store.reserve_attempt(
                        prospect_id, audit_id,
                        now=int(datetime.now(timezone.utc).timestamp()), daily_limit=daily_limit,
                    )
            else:
                if args.bootstrap and args.state.exists():
                    raise ValueError("Refusing to replace an existing checkpoint")
                state = empty_state() if args.bootstrap else unseal(args.state, key)
                if state.get("storage_authority") == "postgres":
                    raise ValueError("Use paired Postgres recovery; a snapshot cannot replace its quota ledger")
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
                if args.paused:
                    event(state, int(datetime.now(timezone.utc).timestamp()),
                          os.environ.get("GITHUB_RUN_ID", "local"), "0" * 64, "pause", "disabled")
                    report = metrics(state)
                else:
                    report = process(
                        state,
                        rows,
                        now=int(datetime.now(timezone.utc).timestamp()),
                        run_id=os.environ.get("GITHUB_RUN_ID", "local"),
                        workspace=Path(temporary),
                        opportunity_policy=opportunity_policy,
                        attempt_reserver=attempt_reserver,
                        limit=args.max_audits, daily_limit=args.daily_limit,
                    )
            if args.state:
                seal(state, args.state, key)
        summary = json.dumps(report, sort_keys=True, indent=2)
        print(summary)  # Counts only; detailed records stay in private storage.
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as stream:
                stream.write("## Durable draft pipeline\n\n```json\n" + summary + "\n```\n")
        return 0
    except Exception:
        print("Pipeline blocked; inspect configuration privately. No raw errors logged.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

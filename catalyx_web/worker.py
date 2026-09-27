"""Manual local staging worker. Never imported or started by the web app."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path

from .customer_audit import run_authorized_static_audit
from .db import Database, now_iso
from .egress import EgressCancelledError

MAX_ATTEMPTS = 2
LEASE_SECONDS = 60


def run_once(db_path: str | Path) -> dict:
    """Claim at most one reviewed request and prepare it for admin review."""
    database = Database(db_path)
    current_time = int(time.time())
    lease_token = str(uuid.uuid4())
    with database.connect() as db:
        row = db.execute(
            "SELECT a.id,a.workspace_id,a.site_id,s.origin,a.attempt_count "
            "FROM audit_requests a JOIN sites s ON s.id=a.site_id "
            "WHERE a.attempt_count<? AND (a.state='queued' OR (a.state='running' AND a.worker_lease_until<=?)) "
            "ORDER BY a.created_at LIMIT 1",
            (MAX_ATTEMPTS, current_time),
        ).fetchone()
        if not row:
            db.execute(
                "UPDATE audit_requests SET state='failed',updated_at=?,review_reason='Worker lease expired after the retry limit',worker_lease_until=NULL,worker_lease_token=NULL "
                "WHERE state='running' AND worker_lease_until<=? AND attempt_count>=?",
                (now_iso(), current_time, MAX_ATTEMPTS),
            )
            return {"status": "idle"}
        job_id = row["id"]
        next_attempt = row["attempt_count"] + 1
        updated = db.execute(
            "UPDATE audit_requests SET state='running',attempt_count=?,worker_lease_until=?,worker_lease_token=?,updated_at=? "
            "WHERE id=? AND attempt_count<? AND (state='queued' OR (state='running' AND worker_lease_until<=?))",
            (next_attempt, current_time + LEASE_SECONDS, lease_token, now_iso(), job_id, MAX_ATTEMPTS, current_time),
        )
        if updated.rowcount != 1:
            return {"status": "idle"}
        workspace_id, origin = row["workspace_id"], row["origin"]

    def lease_is_inactive() -> bool:
        with database.connect() as db:
            active = db.execute(
                "SELECT state,worker_lease_until,worker_lease_token FROM audit_requests WHERE id=?",
                (job_id,),
            ).fetchone()
        return (
            not active
            or active["state"] != "running"
            or active["worker_lease_token"] != lease_token
            or active["worker_lease_until"] is None
            or active["worker_lease_until"] <= int(time.time())
        )

    try:
        report = run_authorized_static_audit(origin, cancel_check=lease_is_inactive)
    except EgressCancelledError:
        with database.connect() as db:
            current = db.execute("SELECT state FROM audit_requests WHERE id=?", (job_id,)).fetchone()
        if current and current["state"] == "cancelled":
            return {"status": "cancelled", "audit_id": job_id}
        return {"status": "lease_lost"}
    except Exception:
        report = {
            "schema_version": 1,
            "profile": "customer_static_single_page_v1",
            "status": "failed",
            "site_host": origin.split("/", 3)[2].split(":", 1)[0],
            "started_at": now_iso(),
            "completed_at": now_iso(),
            "checks": {"fetch": {"status": "error", "reason": "The target could not be audited within the configured limits."}},
            "findings": [],
            "limitations": ["The scan did not complete."],
        }

    timestamp = now_iso()
    with database.connect() as db:
        if report["status"] == "blocked":
            changed = db.execute(
                "UPDATE audit_requests SET state='denied',updated_at=?,review_reason='Robots policy does not allow this audit',worker_lease_until=NULL,worker_lease_token=NULL "
                "WHERE id=? AND state='running' AND worker_lease_token=? AND worker_lease_until>?",
                (timestamp, job_id, lease_token, int(time.time())),
            )
            if changed.rowcount != 1:
                return {"status": "lease_lost"}
            return {"status": "denied", "audit_id": job_id}
        if report["status"] == "failed":
            changed = db.execute(
                "UPDATE audit_requests SET state='failed',updated_at=?,review_reason='The target could not be audited within the configured limits',worker_lease_until=NULL,worker_lease_token=NULL "
                "WHERE id=? AND state='running' AND worker_lease_token=? AND worker_lease_until>?",
                (timestamp, job_id, lease_token, int(time.time())),
            )
            if changed.rowcount != 1:
                return {"status": "lease_lost"}
            return {"status": "failed", "audit_id": job_id}
        report_json = json.dumps(report, sort_keys=True, separators=(",", ":"))
        report_hash = hashlib.sha256(report_json.encode()).hexdigest()
        changed = db.execute(
            "UPDATE audit_requests SET state='quality_review',updated_at=?,review_reason=NULL,worker_lease_until=NULL,worker_lease_token=NULL "
            "WHERE id=? AND state='running' AND worker_lease_token=? AND worker_lease_until>?",
            (timestamp, job_id, lease_token, int(time.time())),
        )
        if changed.rowcount != 1:
            return {"status": "lease_lost"}
        db.execute(
            "INSERT INTO audit_results(audit_id,workspace_id,schema_version,profile,report_json,report_hash,created_at) VALUES(?,?,?,?,?,?,?)",
            (job_id, workspace_id, report["schema_version"], report["profile"], report_json, report_hash, timestamp),
        )
    return {"status": "quality_review", "audit_id": job_id, "report_hash": report_hash}

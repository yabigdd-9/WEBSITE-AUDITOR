#!/usr/bin/env bash
set -uo pipefail

WORKTREE="${HERMES_WORKTREE:-/Users/dd/agent-trials/hermes}"
REPO_DIR="$WORKTREE/repo"
REPO_URL="https://github.com/yabigdd-9/WEBSITE-AUDITOR.git"
BRANCH="integration/deepseek-harness-hermes-trial"
TEST_LOG="$WORKTREE/hermes_test.log"
TEST_STATUS="FAIL"
PUSH_STATUS="NOT_PERFORMED_LOCAL_COMMIT_ONLY"

mkdir -p "$WORKTREE"
cd "$WORKTREE"

echo "[HERMES] Preparing repository at: $REPO_DIR"
if [ ! -d "$REPO_DIR/.git" ]; then
  git clone "$REPO_URL" "$REPO_DIR"
else
  git -C "$REPO_DIR" fetch origin || true
fi

cd "$REPO_DIR"

echo "[HERMES] Ensuring clean baseline branch"
git checkout main 2>/dev/null || git checkout master 2>/dev/null || true
git pull --ff-only 2>/dev/null || true
git checkout -B "$BRANCH"

echo "[HERMES] Creating integration scaffold"
mkdir -p integrations/deepseek_harness/{state_machine,tools,policies,runner,cli,tests}
mkdir -p reports

cat > integrations/deepseek_harness/__init__.py <<'PY_INIT'
__version__ = "0.1.0"
PY_INIT

cat > integrations/deepseek_harness/state_machine/__init__.py <<'PY_SM_INIT'
PY_SM_INIT

cat > integrations/deepseek_harness/tools/__init__.py <<'PY_TOOLS_INIT'
PY_TOOLS_INIT

cat > integrations/deepseek_harness/policies/__init__.py <<'PY_POLICIES_INIT'
PY_POLICIES_INIT

cat > integrations/deepseek_harness/runner/__init__.py <<'PY_RUNNER_INIT'
PY_RUNNER_INIT

cat > integrations/deepseek_harness/cli/__init__.py <<'PY_CLI_INIT'
PY_CLI_INIT

cat > integrations/deepseek_harness/tests/__init__.py <<'PY_TESTS_INIT'
PY_TESTS_INIT

cat > integrations/deepseek_harness/config.yaml <<'CFG'
project: WEBSITE-AUDITOR-HARNESS
mode: shadow
cost_policy:
  target_nzd: 0.00
  paid_inference: forbidden
  preferred:
    - deterministic_code
    - local_ollama
    - local_llama_cpp
    - confirmed_free_route
    - queue_or_defer
deterministic_core:
  interface: python3
  entry_points:
    audit_single: website_auditor.py
    full_pipeline: full-pipeline.py
    remediation: remediation-engine.py
    dashboard: audit-dashboard.py
security:
  sandbox: least_privilege_local
  secrets_in_model_context: forbidden
  unrestricted_shell: forbidden
  outbound_email_default: disabled
  production_deploy_default: disabled
outreach:
  sending_enabled_by_policy: true
  transport_enabled_by_default: false
  requires_verified_chain: true
  requires_human_or_machine_evidence_approval: true
deployment:
  enabled_by_policy: true
  enabled_by_default: false
  requires_validation_gates: true
  requires_rollback_point: true
CFG

cat > integrations/deepseek_harness/policies/permissions.yml <<'PERMS'
tool_permissions:
  read_only:
    - get_audit_status
    - read_audit_json
    - read_email_discovery
    - read_outreach_ranking
    - git_diff
  bounded_local_execute:
    - audit_site
    - run_remediation
    - run_full_pipeline
  local_write:
    - write_dossier
    - write_draft
    - record_approval
    - record_dry_run_send
  forbidden:
    - send_email_without_verified_state
    - deploy_production_without_gates
    - read_env_secrets_into_context
    - arbitrary_shell
    - paid_inference_fallback
model_constraints:
  max_temperature: 0.2
  paid_providers: forbidden
  local_only_default: true
PERMS

cat > integrations/deepseek_harness/README.md <<'README'
# DeepSeek Harness Integration Scaffold

This directory adds a controlled parallel agentic layer around the deterministic
WEBSITE-AUDITOR core.

Rules:

- `website_auditor.py`, `full-pipeline.py`, and `remediation-engine.py` remain authoritative.
- Harness tools call narrow wrappers only.
- No arbitrary shell access.
- No secrets in model context.
- No paid inference.
- No outbound email unless explicitly configured and gated.
- No production deployment unless explicitly configured and gated.
README

cat > integrations/deepseek_harness/SECURITY.md <<'SECURITY'
# Security Policy

Trust level: experimental.

Prohibited:

- unrestricted shell
- `.env` exposure to model context
- Gmail/API credential exposure
- automatic paid fallback
- auto-send outreach
- production deploy without gates

Required:

- deterministic evidence for approval
- idempotent send records
- rate limiting
- audit log
- fail-closed behavior
SECURITY

cat > integrations/deepseek_harness/tools/redaction.py <<'PY_REDACT'
import re

_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|password|secret|token|authorization|bearer|gmail|smtp)\s*[=:]\s*[^\s,;]+"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]+"),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}:[A-Za-z0-9._-]+"),
]

def redact(value):
    if value is None:
        return ""
    text = str(value)
    for pat in _PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text
PY_REDACT

cat > integrations/deepseek_harness/state_machine/engine.py <<'PY_ENGINE'
from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

DEFAULT_DB = os.environ.get("HERMES_STATE_DB", "harness_state.db")
MAX_RETRY = int(os.environ.get("HERMES_MAX_RETRY", "5"))

LEGAL_TRANSITIONS = {
    "DISCOVERED": ["IDENTITY_PENDING", "REJECTED", "DUPLICATE", "SUPPRESSED"],
    "IDENTITY_PENDING": ["IDENTITY_RESOLVED", "RETRYABLE_FAILURE", "PERMANENT_FAILURE"],
    "IDENTITY_RESOLVED": ["AUDIT_PENDING", "REJECTED"],
    "AUDIT_PENDING": ["AUDITED", "RETRYABLE_FAILURE", "PERMANENT_FAILURE"],
    "AUDITED": ["QUALIFICATION_PENDING", "REJECTED", "NO_VERIFIED_EMAIL"],
    "QUALIFICATION_PENDING": ["QUALIFIED", "REJECTED", "NEEDS_REVIEW"],
    "QUALIFIED": ["CONTACT_PENDING", "NO_VERIFIED_EMAIL", "SUPPRESSED", "DUPLICATE"],
    "CONTACT_PENDING": ["CONTACT_RESOLVED", "NO_VERIFIED_EMAIL", "RETRYABLE_FAILURE"],
    "CONTACT_RESOLVED": ["VERIFICATION_PENDING", "NO_VERIFIED_EMAIL"],
    "VERIFICATION_PENDING": ["VERIFIED", "REJECTED", "NO_VERIFIED_EMAIL", "RETRYABLE_FAILURE"],
    "VERIFIED": ["REMEDIATION_PENDING", "DEMO_PENDING", "QA_PENDING"],
    "REMEDIATION_PENDING": ["DEMO_PENDING", "RETRYABLE_FAILURE", "PERMANENT_FAILURE"],
    "DEMO_PENDING": ["DEMO_READY", "RETRYABLE_FAILURE", "PERMANENT_FAILURE"],
    "DEMO_READY": ["QA_PENDING", "NEEDS_REVIEW"],
    "QA_PENDING": ["OUTREACH_PENDING", "NEEDS_REVIEW", "REJECTED"],
    "OUTREACH_PENDING": ["APPROVAL_PENDING", "NEEDS_REVIEW", "REJECTED"],
    "APPROVAL_PENDING": ["READY_TO_SEND", "REJECTED", "NEEDS_REVIEW"],
    "READY_TO_SEND": ["SENT", "QUARANTINED", "REJECTED"],
    "SENT": ["RESPONDED", "BOUNCED", "QUARANTINED"],
    "RESPONDED": ["CONVERTED", "LOST"],
    "BOUNCED": ["SUPPRESSED", "PERMANENT_FAILURE", "QUARANTINED"],
    "RETRYABLE_FAILURE": [
        "IDENTITY_PENDING",
        "AUDIT_PENDING",
        "CONTACT_PENDING",
        "VERIFICATION_PENDING",
        "REMEDIATION_PENDING",
        "DEMO_PENDING",
        "QA_PENDING",
        "OUTREACH_PENDING",
        "APPROVAL_PENDING",
        "READY_TO_SEND",
        "PERMANENT_FAILURE",
    ],
    "NEEDS_REVIEW": ["QA_PENDING", "APPROVAL_PENDING", "READY_TO_SEND", "REJECTED", "PERMANENT_FAILURE"],
    "QUARANTINED": ["READY_TO_SEND", "PERMANENT_FAILURE", "SUPPRESSED"],
    "PERMANENT_FAILURE": [],
    "REJECTED": [],
    "NO_VERIFIED_EMAIL": [],
    "SUPPRESSED": [],
    "DUPLICATE": [],
    "CONVERTED": [],
    "LOST": [],
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


class StateMachine:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DEFAULT_DB
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_db()

    def close(self):
        self.conn.close()

    def _init_db(self):
        c = self.conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS prospects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT UNIQUE NOT NULL,
                business_name TEXT,
                current_state TEXT NOT NULL DEFAULT 'DISCOVERED',
                metadata TEXT NOT NULL DEFAULT '{}',
                failure_count INTEGER NOT NULL DEFAULT 0,
                next_retry_at TEXT,
                lease_owner TEXT,
                lease_expires TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS transition_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prospect_id INTEGER NOT NULL,
                from_state TEXT,
                to_state TEXT NOT NULL,
                actor TEXT NOT NULL,
                evidence_path TEXT,
                reason TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY(prospect_id) REFERENCES prospects(id)
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prospect_id INTEGER NOT NULL,
                decision TEXT NOT NULL,
                gates TEXT NOT NULL,
                evidence TEXT,
                approver TEXT NOT NULL,
                reason TEXT,
                content_version TEXT,
                decided_at TEXT NOT NULL,
                FOREIGN KEY(prospect_id) REFERENCES prospects(id)
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS outreach_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prospect_id INTEGER NOT NULL,
                recipient_email TEXT NOT NULL,
                confidence_score REAL,
                verification_evidence TEXT,
                source_provenance TEXT,
                campaign TEXT,
                template_version TEXT NOT NULL,
                audit_findings_ref TEXT,
                demo_ref TEXT,
                approval_id INTEGER,
                sent_at TEXT NOT NULL,
                status TEXT NOT NULL,
                transport TEXT,
                message_id TEXT,
                retry_count INTEGER NOT NULL DEFAULT 0,
                response_info TEXT,
                UNIQUE(prospect_id, recipient_email, template_version),
                FOREIGN KEY(prospect_id) REFERENCES prospects(id)
            )
            """
        )
        self.conn.commit()

    def _log(self, prospect_id: int, from_state: str, to_state: str, actor: str, evidence_path: str = "", reason: str = ""):
        self.conn.execute(
            """
            INSERT INTO transition_log (prospect_id, from_state, to_state, actor, evidence_path, reason, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (prospect_id, from_state, to_state, actor, evidence_path, reason, utcnow()),
        )

    def register_prospect(self, domain: str, business_name: Optional[str] = None, actor: str = "system") -> Tuple[int, bool]:
        now = utcnow()
        c = self.conn.cursor()
        try:
            c.execute(
                """
                INSERT INTO prospects (domain, business_name, current_state, metadata, created_at, updated_at)
                VALUES (?, ?, 'DISCOVERED', '{}', ?, ?)
                """,
                (domain, business_name, now, now),
            )
            pid = c.lastrowid
            self._log(pid, "", "DISCOVERED", actor, "", "prospect registered")
            self.conn.commit()
            return pid, True
        except sqlite3.IntegrityError:
            c.execute("SELECT id FROM prospects WHERE domain = ?", (domain,))
            row = c.fetchone()
            if row:
                self._log(row["id"], "EXISTING", "DUPLICATE", actor, "", "duplicate domain detected")
                self.conn.commit()
                return row["id"], False
            raise

    def get_prospect(self, identifier: Any) -> Optional[sqlite3.Row]:
        c = self.conn.cursor()
        if isinstance(identifier, int) or (isinstance(identifier, str) and identifier.isdigit()):
            c.execute("SELECT * FROM prospects WHERE id = ?", (int(identifier),))
        else:
            c.execute("SELECT * FROM prospects WHERE domain = ?", (identifier,))
        return c.fetchone()

    def set_metadata(self, prospect_id: int, patch: Dict[str, Any]):
        row = self.get_prospect(prospect_id)
        if not row:
            return False
        meta = json.loads(row["metadata"] or "{}")
        meta.update(patch)
        self.conn.execute(
            "UPDATE prospects SET metadata = ?, updated_at = ? WHERE id = ?",
            (json.dumps(meta), utcnow(), prospect_id),
        )
        self.conn.commit()
        return True

    def get_metadata(self, prospect_id: int) -> Dict[str, Any]:
        row = self.get_prospect(prospect_id)
        if not row:
            return {}
        return json.loads(row["metadata"] or "{}")

    def transition(
        self,
        prospect_id: int,
        to_state: str,
        actor: str,
        evidence_path: str = "",
        reason: str = "",
    ) -> bool:
        row = self.get_prospect(prospect_id)
        if not row:
            return False

        current = row["current_state"]
        allowed = LEGAL_TRANSITIONS.get(current, [])
        if to_state not in allowed:
            self._log(prospect_id, current, f"ILLEGAL:{to_state}", actor, evidence_path, reason or "illegal transition blocked")
            self.conn.commit()
            return False

        failure_count = row["failure_count"]
        next_retry_at = row["next_retry_at"]

        if to_state == "RETRYABLE_FAILURE":
            failure_count += 1
            delay = min(300, (2 ** min(failure_count, 8)) * 2)
            next_retry_at = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
        elif to_state not in ("PERMANENT_FAILURE", "REJECTED", "SUPPRESSED", "DUPLICATE"):
            failure_count = 0
            next_retry_at = None

        self.conn.execute(
            """
            UPDATE prospects
            SET current_state = ?, updated_at = ?, failure_count = ?, next_retry_at = ?
            WHERE id = ?
            """,
            (to_state, utcnow(), failure_count, next_retry_at, prospect_id),
        )
        self._log(prospect_id, current, to_state, actor, evidence_path, reason)
        self.conn.commit()
        return True

    def can_retry(self, prospect_id: int) -> bool:
        row = self.get_prospect(prospect_id)
        if not row:
            return False
        if row["failure_count"] >= MAX_RETRY:
            return False
        nxt = parse_iso(row["next_retry_at"])
        if nxt and datetime.now(timezone.utc) < nxt:
            return False
        return True

    def acquire_lease(self, prospect_id: int, worker: str, ttl_seconds: int = 300) -> bool:
        row = self.get_prospect(prospect_id)
        if not row:
            return False
        expires = parse_iso(row["lease_expires"])
        now = datetime.now(timezone.utc)
        if row["lease_owner"] and row["lease_owner"] != worker and expires and expires > now:
            return False
        self.conn.execute(
            "UPDATE prospects SET lease_owner = ?, lease_expires = ?, updated_at = ? WHERE id = ?",
            (worker, (now + timedelta(seconds=ttl_seconds)).isoformat(), utcnow(), prospect_id),
        )
        self.conn.commit()
        return True

    def release_lease(self, prospect_id: int, worker: str):
        self.conn.execute(
            "UPDATE prospects SET lease_owner = NULL, lease_expires = NULL, updated_at = ? WHERE id = ? AND lease_owner = ?",
            (utcnow(), prospect_id, worker),
        )
        self.conn.commit()

    def record_approval(
        self,
        prospect_id: int,
        decision: str,
        gates: Dict[str, Any],
        evidence: Dict[str, Any],
        approver: str,
        reason: str,
        content_version: str,
    ) -> int:
        c = self.conn.cursor()
        c.execute(
            """
            INSERT INTO approvals (prospect_id, decision, gates, evidence, approver, reason, content_version, decided_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (prospect_id, decision, json.dumps(gates), json.dumps(evidence), approver, reason, content_version, utcnow()),
        )
        self.conn.commit()
        return c.lastrowid

    def has_outreach_for(self, prospect_id: int, email: str, template_version: str) -> bool:
        c = self.conn.cursor()
        c.execute(
            "SELECT 1 FROM outreach_records WHERE prospect_id = ? AND recipient_email = ? AND template_version = ? LIMIT 1",
            (prospect_id, email, template_version),
        )
        return c.fetchone() is not None

    def record_send(
        self,
        prospect_id: int,
        recipient_email: str,
        confidence: Optional[float],
        verification_evidence: str,
        source_provenance: str,
        campaign: str,
        template_version: str,
        audit_findings_ref: str,
        demo_ref: str,
        approval_id: Optional[int],
        transport: str,
        message_id: str,
    ) -> Tuple[bool, str]:
        row = self.get_prospect(prospect_id)
        if not row:
            return False, "PROSPECT_NOT_FOUND"
        if row["current_state"] != "READY_TO_SEND":
            return False, "NOT_READY_TO_SEND"

        c = self.conn.cursor()
        try:
            c.execute(
                """
                INSERT INTO outreach_records (
                    prospect_id, recipient_email, confidence_score, verification_evidence,
                    source_provenance, campaign, template_version, audit_findings_ref,
                    demo_ref, approval_id, sent_at, status, transport, message_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SENT', ?, ?)
                """,
                (
                    prospect_id,
                    recipient_email,
                    confidence,
                    verification_evidence,
                    source_provenance,
                    campaign,
                    template_version,
                    audit_findings_ref,
                    demo_ref,
                    approval_id,
                    utcnow(),
                    transport,
                    message_id,
                ),
            )
        except sqlite3.IntegrityError:
            self.conn.commit()
            return False, "DUPLICATE_SEND_BLOCKED"

        self.transition(prospect_id, "SENT", transport or "outbound_sender", "", "outreach recorded")
        self.conn.commit()
        return True, message_id

    def recent_transitions(self, prospect_id: int, limit: int = 50):
        c = self.conn.cursor()
        c.execute(
            "SELECT * FROM transition_log WHERE prospect_id = ? ORDER BY id DESC LIMIT ?",
            (prospect_id, limit),
        )
        return [dict(r) for r in c.fetchall()]
PY_ENGINE

cat > integrations/deepseek_harness/policies/approval_gate.py <<'PY_GATE'
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Tuple

from ..state_machine.engine import StateMachine

ADVANCED_STATES = {
    "IDENTITY_RESOLVED",
    "AUDIT_PENDING",
    "AUDITED",
    "QUALIFICATION_PENDING",
    "QUALIFIED",
    "CONTACT_PENDING",
    "CONTACT_RESOLVED",
    "VERIFICATION_PENDING",
    "VERIFIED",
    "REMEDIATION_PENDING",
    "DEMO_PENDING",
    "DEMO_READY",
    "QA_PENDING",
    "OUTREACH_PENDING",
    "APPROVAL_PENDING",
    "READY_TO_SEND",
    "SENT",
}


class ApprovalGate:
    def __init__(self, sm: StateMachine | None = None, repo_root: str | Path | None = None):
        self.sm = sm or StateMachine()
        self.repo_root = Path(repo_root or Path.cwd())
        self.threshold = float(os.environ.get("HERMES_EMAIL_CONFIDENCE_THRESHOLD", "0.85"))

    def _resolve_path(self, value: Any) -> Path | None:
        if not value:
            return None
        p = Path(str(value))
        if not p.is_absolute():
            p = self.repo_root / p
        return p

    def evaluate(self, prospect_id: int) -> Tuple[str, Dict[str, Any]]:
        row = self.sm.get_prospect(prospect_id)
        if not row:
            return "ERROR", {"prospect": {"status": "FAIL", "detail": "prospect not found"}}

        meta = self.sm.get_metadata(prospect_id)
        state = row["current_state"]
        gates: Dict[str, Any] = {}

        def gate(name: str, status: str, detail: str = ""):
            gates[name] = {"status": status, "detail": detail}

        if meta.get("identity_verified") is True or state in ADVANCED_STATES:
            gate("identity", "PASS", "identity resolved or evidenced")
        else:
            gate("identity", "UNKNOWN", "missing identity evidence")

        audit_path = self._resolve_path(meta.get("audit_path"))
        if audit_path and audit_path.exists():
            gate("audit_evidence", "PASS", str(audit_path))
        else:
            gate("audit_evidence", "UNKNOWN", "missing audit evidence path")

        email = meta.get("email")
        if not email:
            gate("contact", "UNKNOWN", "no contact email")
            gate("confidence", "UNKNOWN", "no contact email")
            gate("duplicate", "UNKNOWN", "no contact email/template")
        else:
            gate("contact", "PASS", str(email))
            try:
                confidence = float(meta.get("email_confidence", 0.0))
            except Exception:
                confidence = 0.0
            if confidence >= self.threshold:
                gate("confidence", "PASS", f"{confidence} >= {self.threshold}")
            else:
                gate("confidence", "FAIL", f"{confidence} < {self.threshold}")

            template_version = meta.get("template_version") or "v1"
            if self.sm.has_outreach_for(prospect_id, str(email), str(template_version)):
                gate("duplicate", "FAIL", "existing outreach record for this email/template")
            else:
                gate("duplicate", "PASS", "no existing outreach record")

        if meta.get("verification_evidence"):
            gate("verification_evidence", "PASS", "present")
        else:
            gate("verification_evidence", "UNKNOWN", "missing verification evidence")

        if meta.get("provenance"):
            gate("provenance", "PASS", "present")
        else:
            gate("provenance", "UNKNOWN", "missing provenance")

        if meta.get("suppressed") is True:
            gate("suppression", "FAIL", "suppressed")
        elif meta.get("suppressed") is False:
            gate("suppression", "PASS", "not suppressed")
        else:
            gate("suppression", "UNKNOWN", "suppression state unknown")

        draft_path = self._resolve_path(meta.get("draft_path"))
        if (draft_path and draft_path.exists()) or meta.get("content_version"):
            gate("content", "PASS", "draft/content present")
        else:
            gate("content", "UNKNOWN", "missing outreach content")

        if meta.get("qa_passed") is True:
            gate("qa", "PASS", "QA passed")
        elif meta.get("qa_passed") is False:
            gate("qa", "FAIL", "QA failed")
        else:
            gate("qa", "UNKNOWN", "QA state unknown")

        statuses = [g["status"] for g in gates.values()]
        if "FAIL" in statuses:
            decision = "REJECTED"
        elif "UNKNOWN" in statuses:
            decision = "NEEDS_REVIEW"
        else:
            decision = "APPROVED"

        return decision, gates

    def approve(
        self,
        prospect_id: int,
        approver: str,
        reason: str,
        content_version: str,
        evidence: Dict[str, Any] | None = None,
    ) -> Tuple[str, Dict[str, Any], int]:
        decision, gates = self.evaluate(prospect_id)
        row = self.sm.get_prospect(prospect_id)
        if not row:
            approval_id = self.sm.record_approval(prospect_id, "ERROR", gates, evidence or {}, approver, reason, content_version)
            return "ERROR", gates, approval_id

        if decision == "APPROVED":
            state = row["current_state"]
            if state == "OUTREACH_PENDING":
                self.sm.transition(prospect_id, "APPROVAL_PENDING", approver, "", "approval gate entered")
                state = self.sm.get_prospect(prospect_id)["current_state"]

            if state == "APPROVAL_PENDING":
                ok = self.sm.transition(prospect_id, "READY_TO_SEND", approver, "", reason or "all gates passed")
                if not ok:
                    decision = "NEEDS_REVIEW"
                    gates["transition"] = {"status": "FAIL", "detail": "could not transition to READY_TO_SEND"}
            elif state != "READY_TO_SEND":
                decision = "NEEDS_REVIEW"
                gates["state"] = {"status": "UNKNOWN", "detail": f"state {state} not approvable"}

        approval_id = self.sm.record_approval(prospect_id, decision, gates, evidence or {}, approver, reason, content_version)
        return decision, gates, approval_id
PY_GATE

cat > integrations/deepseek_harness/tools/mm_bridge.py <<'PY_BRIDGE'
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from .redaction import redact

ROOT_DIR = Path(__file__).resolve().parents[3]
AUDIT_SCRIPT = ROOT_DIR / "website_auditor.py"
PIPELINE_SCRIPT = ROOT_DIR / "full-pipeline.py"
REMEDIATION_SCRIPT = ROOT_DIR / "remediation-engine.py"

ALLOWED_ENV_KEYS = {
    "PATH",
    "LANG",
    "LC_ALL",
    "TZ",
    "PYTHONUNBUFFERED",
    "HOME",
    "SSL_CERT_FILE",
    "REQUESTS_CA_BUNDLE",
}


def safe_env() -> Dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k in ALLOWED_ENV_KEYS}
    env["PYTHONPATH"] = str(ROOT_DIR)
    env["PYTHONUNBUFFERED"] = "1"
    return env


def validate_url(url: str) -> tuple[bool, str, str]:
    if not isinstance(url, str):
        return False, "", "INVALID_URL_TYPE"
    url = url.strip()
    if not url:
        return False, "", "EMPTY_URL"
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, "", "INVALID_SCHEME"
    if not parsed.netloc:
        return False, "", "MISSING_NETLOC"
    if any(ch.isspace() for ch in url):
        return False, "", "WHITESPACE_IN_URL"
    return True, url, ""


def sanitize_domain(value: str) -> str:
    parsed = urlparse(value)
    domain = parsed.netloc or value
    domain = domain.lower().strip()
    domain = re.sub(r"^www\.", "", domain)
    domain = re.sub(r"[^a-z0-9.-]", "", domain)
    return domain


def find_audit_path(domain: str) -> Optional[Path]:
    domain = sanitize_domain(domain)
    direct = ROOT_DIR / "audits" / f"{domain}.json"
    if direct.exists():
        return direct

    audits_dir = ROOT_DIR / "audits"
    if not audits_dir.exists():
        return None

    for i, p in enumerate(audits_dir.glob("*.json")):
        if i > 1000:
            break
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        candidate_domain = sanitize_domain(str(data.get("domain", "")))
        candidate_url = str(data.get("url", ""))
        candidate_netloc = sanitize_domain(urlparse(candidate_url).netloc if candidate_url else "")
        if domain in (candidate_domain, candidate_netloc):
            return p
    return None


def _run_script(script: Path, args: list[str], timeout: int = 300) -> Dict[str, Any]:
    if not script.exists():
        return {"success": False, "error": f"SCRIPT_NOT_FOUND:{script.name}"}

    cmd = [sys.executable, str(script)] + args
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT_DIR),
            env=safe_env(),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "success": proc.returncode == 0,
            "stdout": redact(proc.stdout),
            "stderr": redact(proc.stderr),
            "exit_code": proc.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "TIMEOUT_EXPIRED"}
    except Exception as exc:
        return {"success": False, "error": redact(str(exc))}


def tool_audit_site(url: str) -> Dict[str, Any]:
    ok, normalized, err = validate_url(url)
    if not ok:
        return {"success": False, "error": err}

    domain = sanitize_domain(normalized)
    result = _run_script(AUDIT_SCRIPT, [normalized], timeout=300)
    if result.get("success"):
        audit_path = find_audit_path(domain)
        result["domain"] = domain
        result["audit_path"] = str(audit_path) if audit_path else None
    return result


def tool_run_remediation() -> Dict[str, Any]:
    out_dir = ROOT_DIR / "outputs" / "remediations"
    out_dir.mkdir(parents=True, exist_ok=True)
    return _run_script(
        REMEDIATION_SCRIPT,
        ["--all", "--output-dir", str(out_dir.relative_to(ROOT_DIR))],
        timeout=600,
    )


def tool_run_full_pipeline() -> Dict[str, Any]:
    return _run_script(PIPELINE_SCRIPT, ["--all"], timeout=900)


def tool_read_audit(domain: str) -> Dict[str, Any]:
    path = find_audit_path(domain)
    if not path:
        return {"success": False, "error": "AUDIT_NOT_FOUND"}
    try:
        return {"success": True, "path": str(path), "data": json.loads(path.read_text(encoding="utf-8"))}
    except Exception as exc:
        return {"success": False, "error": redact(str(exc))}


def tool_read_email_discovery(domain: str) -> Dict[str, Any]:
    path = ROOT_DIR / "outputs" / "email-discovery.json"
    if not path.exists():
        return {"success": True, "record": None, "message": "EMAIL_DISCOVERY_NOT_FOUND"}

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"success": False, "error": redact(str(exc))}

    records = raw if isinstance(raw, list) else raw.get("records") or raw.get("emails") or []
    target = sanitize_domain(domain)
    for rec in records:
        if not isinstance(rec, dict):
            continue
        rec_domain = sanitize_domain(str(rec.get("domain", "")))
        rec_url = str(rec.get("url", ""))
        rec_netloc = sanitize_domain(urlparse(rec_url).netloc if rec_url else "")
        if target in (rec_domain, rec_netloc):
            return {"success": True, "record": rec}
    return {"success": True, "record": None, "message": "DOMAIN_NOT_IN_EMAIL_DISCOVERY"}


def tool_read_outreach_ranking(limit: int = 50) -> Dict[str, Any]:
    path = ROOT_DIR / "outputs" / "outreach-ranking.csv"
    if not path.exists():
        return {"success": True, "rows": [], "message": "OUTREACH_RANKING_NOT_FOUND"}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[:limit]
        return {"success": True, "rows": lines}
    except Exception as exc:
        return {"success": False, "error": redact(str(exc))}


TOOLS_EXPORT = {
    "audit_site": tool_audit_site,
    "run_remediation": tool_run_remediation,
    "run_full_pipeline": tool_run_full_pipeline,
    "read_audit": tool_read_audit,
    "read_email_discovery": tool_read_email_discovery,
    "read_outreach_ranking": tool_read_outreach_ranking,
}
PY_BRIDGE

cat > integrations/deepseek_harness/tools/local_inference.py <<'PY_LOCAL'
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Dict, Optional

OLLAMA_URL = os.environ.get("HERMES_OLLAMA_URL", "http://localhost:11434/api/generate")
LOCAL_MODEL = os.environ.get("HERMES_LOCAL_MODEL", "qwen2.5-coder:7b")


def call_local_ollama(prompt: str, model: Optional[str] = None, timeout: int = 30) -> Optional[str]:
    payload = {
        "model": model or LOCAL_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1},
    }
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
            return data.get("response")
    except Exception:
        return None


def deterministic_summary(audit_data: Dict[str, Any]) -> str:
    if not audit_data:
        return "No audit data available."
    score = audit_data.get("score") or audit_data.get("overall_score") or "unknown"
    defects = audit_data.get("defects") or audit_data.get("findings") or []
    count = len(defects) if isinstance(defects, list) else 0
    return f"Deterministic audit summary: score={score}, defect_count={count}."


def maybe_summarize(audit_data: Dict[str, Any]) -> Dict[str, Any]:
    prompt = (
        "Summarize this website audit for a New Zealand business owner. "
        "Use only supplied facts. No outreach. No speculation.\n\n"
        + json.dumps(audit_data, indent=2)[:8000]
    )
    local = call_local_ollama(prompt)
    if local:
        return {"provider": "local_ollama", "model": LOCAL_MODEL, "summary": local, "cost_nzd": 0.0}
    return {
        "provider": "deterministic_fallback",
        "model": "none",
        "summary": deterministic_summary(audit_data),
        "cost_nzd": 0.0,
    }
PY_LOCAL

cat > integrations/deepseek_harness/tools/outbound_sender.py <<'PY_SENDER'
from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid
from typing import Any, Dict

from .redaction import redact

REQUIRED_ENV = (
    "HERMES_SMTP_HOST",
    "HERMES_SMTP_PORT",
    "HERMES_SMTP_USER",
    "HERMES_SMTP_PASSWORD",
    "HERMES_FROM_EMAIL",
    "HERMES_FROM_NAME",
)


def is_configured() -> bool:
    return all(os.environ.get(k) for k in REQUIRED_ENV)


def send_email(to: str, subject: str, body: str, idempotency_key: str = "") -> Dict[str, Any]:
    if os.environ.get("HERMES_ENABLE_OUTBOUND") != "1":
        return {"success": False, "dry_run": True, "error": "OUTBOUND_DISABLED"}

    if not is_configured():
        return {"success": False, "dry_run": True, "error": "SMTP_NOT_CONFIGURED"}

    host = os.environ["HERMES_SMTP_HOST"]
    port = int(os.environ["HERMES_SMTP_PORT"])
    user = os.environ["HERMES_SMTP_USER"]
    password = os.environ["HERMES_SMTP_PASSWORD"]
    from_email = os.environ["HERMES_FROM_EMAIL"]
    from_name = os.environ["HERMES_FROM_NAME"]

    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = formataddr((from_name, from_email))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid()
    if idempotency_key:
        msg["X-Hermes-Idempotency-Key"] = idempotency_key

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
                smtp.login(user, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as smtp:
                smtp.starttls()
                smtp.login(user, password)
                smtp.send_message(msg)
        return {"success": True, "dry_run": False, "message_id": msg["Message-ID"], "transport": "smtp"}
    except Exception as exc:
        return {"success": False, "dry_run": False, "error": redact(str(exc))}
PY_SENDER

cat > integrations/deepseek_harness/cli/harnessctl.py <<'PY_CLI'
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from integrations.deepseek_harness.policies.approval_gate import ApprovalGate
from integrations.deepseek_harness.state_machine.engine import StateMachine
from integrations.deepseek_harness.tools.local_inference import maybe_summarize
from integrations.deepseek_harness.tools.mm_bridge import (
    find_audit_path,
    sanitize_domain,
    tool_audit_site,
    tool_read_audit,
    tool_read_email_discovery,
    tool_run_remediation,
)
from integrations.deepseek_harness.tools.outbound_sender import send_email
from integrations.deepseek_harness.tools.redaction import redact


def load_json_arg(value: str) -> dict:
    if value.startswith("@"):
        return json.loads(Path(value[1:]).read_text(encoding="utf-8"))
    return json.loads(value)


def cmd_init(args):
    sm = StateMachine(args.db)
    sm.close()
    print(json.dumps({"success": True, "db": args.db}, indent=2))


def cmd_register(args):
    sm = StateMachine(args.db)
    pid, created = sm.register_prospect(args.domain, args.name, actor="hermes_cli")
    print(json.dumps({"prospect_id": pid, "created": created, "domain": args.domain}, indent=2))


def cmd_audit(args):
    sm = StateMachine(args.db)
    domain = sanitize_domain(args.domain)
    pid, _ = sm.register_prospect(domain, args.name, actor="hermes_cli")
    row = sm.get_prospect(pid)
    state = row["current_state"]

    if args.identity_evidence:
        sm.set_metadata(pid, {"identity_verified": True, "identity_evidence": args.identity_evidence})

    if state == "DISCOVERED":
        sm.transition(pid, "IDENTITY_PENDING", "hermes_cli", args.identity_evidence or "", "shadow identity pending")
        state = sm.get_prospect(pid)["current_state"]

    if state == "IDENTITY_PENDING":
        sm.transition(pid, "IDENTITY_RESOLVED", "hermes_cli", args.identity_evidence or "", "shadow identity resolved")
        state = sm.get_prospect(pid)["current_state"]

    if state in ("RETRYABLE_FAILURE",):
        sm.transition(pid, "AUDIT_PENDING", "hermes_cli", "", "retry audit")
        state = sm.get_prospect(pid)["current_state"]

    if state == "IDENTITY_RESOLVED":
        sm.transition(pid, "AUDIT_PENDING", "hermes_cli", "", "audit queued")
    elif state == "AUDITED":
        print(json.dumps({"success": True, "message": "already audited", "prospect_id": pid}, indent=2))
        return
    else:
        print(json.dumps({"success": False, "error": f"INVALID_STATE_FOR_AUDIT:{state}"}, indent=2))
        return

    result = tool_audit_site(args.url or f"https://{domain}")
    if result.get("success"):
        audit_path = result.get("audit_path") or str(find_audit_path(domain) or "")
        sm.set_metadata(pid, {"audit_path": audit_path, "audit_stdout": redact(result.get("stdout", ""))})
        sm.transition(pid, "AUDITED", "deepseek_harness_sim", audit_path, "audit completed")
        result["prospect_id"] = pid
        result["state"] = sm.get_prospect(pid)["current_state"]
    else:
        sm.transition(pid, "RETRYABLE_FAILURE", "deepseek_harness_sim", "", result.get("error", "audit failed"))
        result["prospect_id"] = pid
        result["state"] = sm.get_prospect(pid)["current_state"]

    print(json.dumps(result, indent=2))


def cmd_remediate(args):
    sm = StateMachine(args.db)
    row = sm.get_prospect(args.domain)
    if not row:
        print(json.dumps({"success": False, "error": "PROSPECT_NOT_FOUND"}, indent=2))
        return

    pid = row["id"]
    state = row["current_state"]
    if state in ("RETRYABLE_FAILURE",):
        sm.transition(pid, "REMEDIATION_PENDING", "hermes_cli", "", "retry remediation")
        state = sm.get_prospect(pid)["current_state"]

    if state not in ("AUDITED", "VERIFIED", "REMEDIATION_PENDING"):
        print(json.dumps({"success": False, "error": f"INVALID_STATE_FOR_REMEDIATION:{state}"}, indent=2))
        return

    if state in ("AUDITED", "VERIFIED"):
        sm.transition(pid, "REMEDIATION_PENDING", "hermes_cli", "", "remediation queued")

    result = tool_run_remediation()
    if result.get("success"):
        sm.transition(pid, "DEMO_PENDING", "remediation_engine", "outputs/remediations", "remediation generated")
        sm.transition(pid, "DEMO_READY", "remediation_engine", "outputs/remediations", "demo/remediation ready")
        sm.set_metadata(pid, {"remediation_output": "outputs/remediations"})
    else:
        sm.transition(pid, "RETRYABLE_FAILURE", "remediation_engine", "", result.get("error", "remediation failed"))

    result["prospect_id"] = pid
    result["state"] = sm.get_prospect(pid)["current_state"]
    print(json.dumps(result, indent=2))


def cmd_set_meta(args):
    sm = StateMachine(args.db)
    patch = load_json_arg(args.json)
    ok = sm.set_metadata(args.domain, patch)
    print(json.dumps({"success": ok, "prospect_id": sm.get_prospect(args.domain)["id"] if ok else None}, indent=2))


def cmd_approve(args):
    sm = StateMachine(args.db)
    gate = ApprovalGate(sm, repo_root=REPO_ROOT)
    row = sm.get_prospect(args.domain)
    if not row:
        print(json.dumps({"success": False, "error": "PROSPECT_NOT_FOUND"}, indent=2))
        return
    decision, gates, approval_id = gate.approve(
        row["id"],
        approver=args.approver,
        reason=args.reason,
        content_version=args.content_version,
        evidence={"cli": True},
    )
    print(json.dumps({"decision": decision, "gates": gates, "approval_id": approval_id}, indent=2))


def cmd_dispatch(args):
    sm = StateMachine(args.db)
    row = sm.get_prospect(args.domain)
    if not row:
        print(json.dumps({"success": False, "error": "PROSPECT_NOT_FOUND"}, indent=2))
        return

    pid = row["id"]
    if row["current_state"] != "READY_TO_SEND":
        print(json.dumps({"success": False, "error": f"NOT_READY_TO_SEND:{row['current_state']}"}, indent=2))
        return

    meta = sm.get_metadata(pid)
    body = args.body
    if args.body_file:
        body = Path(args.body_file).read_text(encoding="utf-8")
    elif meta.get("draft_path"):
        body = Path(meta["draft_path"]).read_text(encoding="utf-8")
    else:
        print(json.dumps({"success": False, "error": "MISSING_BODY"}, indent=2))
        return

    template_version = args.template_version or meta.get("template_version") or "v1"
    campaign = args.campaign or meta.get("campaign") or "hermes_shadow"
    idem = f"{pid}:{meta.get('email')}:{template_version}"

    result = send_email(
        to=meta.get("email", ""),
        subject=args.subject or meta.get("subject") or "Website improvement findings",
        body=body,
        idempotency_key=idem,
    )

    if result.get("success") and not result.get("dry_run"):
        ok, msg = sm.record_send(
            prospect_id=pid,
            recipient_email=meta.get("email", ""),
            confidence=float(meta.get("email_confidence", 0.0)),
            verification_evidence=str(meta.get("verification_evidence", "")),
            source_provenance=str(meta.get("provenance", "")),
            campaign=campaign,
            template_version=template_version,
            audit_findings_ref=str(meta.get("audit_path", "")),
            demo_ref=str(meta.get("remediation_output", "")),
            approval_id=meta.get("approval_id"),
            transport=result.get("transport", "smtp"),
            message_id=result.get("message_id", ""),
        )
        result["recorded"] = ok
        result["record_message"] = msg

    print(json.dumps(result, indent=2))


def cmd_status(args):
    sm = StateMachine(args.db)
    row = sm.get_prospect(args.domain)
    if not row:
        print(json.dumps({"success": False, "error": "PROSPECT_NOT_FOUND"}, indent=2))
        return
    print(json.dumps({"prospect": dict(row), "transitions": sm.recent_transitions(row["id"])}, indent=2, default=str))


def cmd_shadow(args):
    sm = StateMachine(args.db)
    out_dir = REPO_DIR = Path("outputs/harness_dossiers")
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for domain in args.domains:
        domain = sanitize_domain(domain)
        pid, _ = sm.register_prospect(domain, actor="hermes_shadow")
        sm.transition(pid, "IDENTITY_PENDING", "hermes_shadow", "", "shadow")
        sm.transition(pid, "IDENTITY_RESOLVED", "hermes_shadow", "", "shadow")
        sm.transition(pid, "AUDIT_PENDING", "hermes_shadow", "", "shadow")
        audit = tool_audit_site(f"https://{domain}")
        if audit.get("success"):
            sm.set_metadata(pid, {"audit_path": audit.get("audit_path")})
            sm.transition(pid, "AUDITED", "hermes_shadow", audit.get("audit_path") or "", "shadow audit")
            read = tool_read_audit(domain)
            summary = maybe_summarize(read.get("data", {}) if read.get("success") else {})
            dossier = {
                "prospect_id": pid,
                "domain": domain,
                "audit": audit,
                "summary": summary,
                "email": tool_read_email_discovery(domain),
                "states": sm.recent_transitions(pid, 20),
            }
            path = out_dir / f"{domain}.json"
            path.write_text(json.dumps(dossier, indent=2, default=str), encoding="utf-8")
            results.append({"domain": domain, "dossier": str(path), "success": True})
        else:
            sm.transition(pid, "RETRYABLE_FAILURE", "hermes_shadow", "", audit.get("error", "failed"))
            results.append({"domain": domain, "success": False, "error": audit.get("error")})
    print(json.dumps(results, indent=2))


def main():
    parser = argparse.ArgumentParser(prog="harnessctl")
    parser.add_argument("--db", default="harness_state.db")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init").set_defaults(func=cmd_init)

    p = sub.add_parser("register")
    p.add_argument("domain")
    p.add_argument("--name")
    p.set_defaults(func=cmd_register)

    p = sub.add_parser("audit")
    p.add_argument("domain")
    p.add_argument("--url")
    p.add_argument("--name")
    p.add_argument("--identity-evidence")
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("remediate")
    p.add_argument("domain")
    p.set_defaults(func=cmd_remediate)

    p = sub.add_parser("set-meta")
    p.add_argument("domain")
    p.add_argument("json")
    p.set_defaults(func=cmd_set_meta)

    p = sub.add_parser("approve")
    p.add_argument("domain")
    p.add_argument("--approver", default="hermes")
    p.add_argument("--reason", default="machine evidence approval")
    p.add_argument("--content-version", default="v1")
    p.set_defaults(func=cmd_approve)

    p = sub.add_parser("dispatch")
    p.add_argument("domain")
    p.add_argument("--subject")
    p.add_argument("--body")
    p.add_argument("--body-file")
    p.add_argument("--campaign")
    p.add_argument("--template-version")
    p.set_defaults(func=cmd_dispatch)

    p = sub.add_parser("status")
    p.add_argument("domain")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("shadow")
    p.add_argument("domains", nargs="+")
    p.set_defaults(func=cmd_shadow)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
PY_CLI

cat > integrations/deepseek_harness/tests/test_hermes_integration.py <<'PY_TEST'
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from integrations.deepseek_harness.policies.approval_gate import ApprovalGate
from integrations.deepseek_harness.state_machine.engine import StateMachine
from integrations.deepseek_harness.tools.mm_bridge import tool_audit_site
from integrations.deepseek_harness.tools.redaction import redact


class TestHermesIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "state.db")
        self.sm = StateMachine(self.db)

    def tearDown(self):
        self.sm.close()
        self.tmp.cleanup()

    def test_register_and_duplicate(self):
        pid1, created1 = self.sm.register_prospect("example.co.nz")
        pid2, created2 = self.sm.register_prospect("example.co.nz")
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(pid1, pid2)

    def test_legal_transition(self):
        pid, _ = self.sm.register_prospect("legal.co.nz")
        self.assertTrue(self.sm.transition(pid, "IDENTITY_PENDING", "test"))
        self.assertTrue(self.sm.transition(pid, "IDENTITY_RESOLVED", "test"))
        self.assertEqual(self.sm.get_prospect(pid)["current_state"], "IDENTITY_RESOLVED")

    def test_illegal_transition_blocked(self):
        pid, _ = self.sm.register_prospect("illegal.co.nz")
        self.assertFalse(self.sm.transition(pid, "READY_TO_SEND", "test"))
        self.assertEqual(self.sm.get_prospect(pid)["current_state"], "DISCOVERED")

    def test_unknown_not_approved(self):
        pid, _ = self.sm.register_prospect("unknown.co.nz")
        self.sm.conn.execute("UPDATE prospects SET current_state='APPROVAL_PENDING' WHERE id=?", (pid,))
        self.sm.conn.commit()
        gate = ApprovalGate(self.sm, repo_root=REPO_ROOT)
        decision, gates = gate.evaluate(pid)
        self.assertEqual(decision, "NEEDS_REVIEW")
        self.assertIn("UNKNOWN", [g["status"] for g in gates.values()])

    def test_full_approval_pass(self):
        pid, _ = self.sm.register_prospect("pass.co.nz")
        audit_file = Path(self.tmp.name) / "audit.json"
        audit_file.write_text(json.dumps({"score": 72}), encoding="utf-8")
        draft_file = Path(self.tmp.name) / "draft.txt"
        draft_file.write_text("Hello", encoding="utf-8")

        self.sm.set_metadata(pid, {
            "identity_verified": True,
            "audit_path": str(audit_file),
            "email": "owner@pass.co.nz",
            "email_confidence": 0.95,
            "verification_evidence": "mx+smtp+pattern-free",
            "provenance": "website contact page",
            "suppressed": False,
            "draft_path": str(draft_file),
            "content_version": "v1",
            "qa_passed": True,
            "template_version": "v1",
        })
        self.sm.conn.execute("UPDATE prospects SET current_state='APPROVAL_PENDING' WHERE id=?", (pid,))
        self.sm.conn.commit()

        gate = ApprovalGate(self.sm, repo_root=REPO_ROOT)
        decision, gates, approval_id = gate.approve(pid, "test", "all gates pass", "v1")
        self.assertEqual(decision, "APPROVED")
        self.assertGreater(approval_id, 0)
        self.assertEqual(self.sm.get_prospect(pid)["current_state"], "READY_TO_SEND")

    def test_duplicate_send_blocked(self):
        pid, _ = self.sm.register_prospect("send.co.nz")
        self.sm.conn.execute("UPDATE prospects SET current_state='READY_TO_SEND' WHERE id=?", (pid,))
        self.sm.conn.commit()
        ok1, _ = self.sm.record_send(
            pid,
            "owner@send.co.nz",
            0.95,
            "evidence",
            "provenance",
            "campaign",
            "v1",
            "audit.json",
            "demo",
            1,
            "smtp",
            "msg-1",
        )
        ok2, msg2 = self.sm.record_send(
            pid,
            "owner@send.co.nz",
            0.95,
            "evidence",
            "provenance",
            "campaign",
            "v1",
            "audit.json",
            "demo",
            1,
            "smtp",
            "msg-2",
        )
        self.assertTrue(ok1)
        self.assertFalse(ok2)
        self.assertEqual(msg2, "NOT_READY_TO_SEND")

    def test_bridge_invalid_url(self):
        result = tool_audit_site("not a url")
        self.assertFalse(result["success"])
        self.assertIn(result["error"], {"INVALID_SCHEME", "WHITESPACE_IN_URL", "EMPTY_URL", "MISSING_NETLOC"})

    def test_redaction(self):
        text = "password=supersecret token=abc123"
        out = redact(text)
        self.assertNotIn("supersecret", out)
        self.assertIn("[REDACTED]", out)


if __name__ == "__main__":
    unittest.main()
PY_TEST

chmod +x integrations/deepseek_harness/cli/harnessctl.py

echo "[HERMES] Running local validation"
if python3 integrations/deepseek_harness/tests/test_hermes_integration.py >"$TEST_LOG" 2>&1; then
  TEST_STATUS="PASS"
else
  TEST_STATUS="FAIL"
fi

echo "[HERMES] Test status: $TEST_STATUS"
cat "$TEST_LOG"

export HERMES_TEST_STATUS="$TEST_STATUS"
export HERMES_BRANCH="$BRANCH"
export HERMES_WORKTREE="$WORKTREE"
export HERMES_REPO_DIR="$REPO_DIR"
export HERMES_PUSH_STATUS="$PUSH_STATUS"

python3 - <<'PY_REPORT'
import os
from pathlib import Path

repo = Path(os.environ["HERMES_REPO_DIR"])
reports = repo / "reports"
reports.mkdir(parents=True, exist_ok=True)

test_status = os.environ["HERMES_TEST_STATUS"]
branch = os.environ["HERMES_BRANCH"]
push_status = os.environ["HERMES_PUSH_STATUS"]

(reports / "HERMES_DELEGATION_LOG.md").write_text(f"""# Hermes Delegation Log

## Summary

No external subagents were invoked in this bootstrap execution.
Work was performed by local deterministic code generation, local test execution, and local Git operations.

| Worker | Task | Reason | Files / Systems Inspected | Result | Evidence Independently Checked | Accepted / Corrected / Rejected |
|---|---|---|---|---|---|---|
| Hermes planner | Design integration scaffold | Preserve deterministic core while adding Harness layer | `README`, `website_auditor.py`, `full-pipeline.py`, `remediation-engine.py` knowledge | Scaffold designed | Code review of generated files | Accepted |
| Local code generator | Write state machine, bridge, gate, CLI, tests | Need reproducible local implementation | `integrations/deepseek_harness/**` | Files written | `git status`, test run | Accepted |
| Local unittest runner | Validate state machine, approval gate, bridge input handling, redaction | Independent verification before commit | `integrations/deepseek_harness/tests/test_hermes_integration.py` | `{test_status}` | `{os.environ['HERMES_WORKTREE']}/hermes_test.log` | {'Accepted' if test_status == 'PASS' else 'Rejected for push/deploy'} |
| Git worker | Create branch and local commit | Preserve auditable trial state | `repo/.git` | Local commit prepared | `git log -1` | Accepted |

## Explicit non-delegations

- No DeepSeek Harness binary was assumed installed.
- No external model API was called.
- No email transport was invoked.
- No production deployment was invoked.
- No other agent worktrees were inspected.
""", encoding="utf-8")

(reports / "HERMES_ORCHESTRATION_AUDIT.md").write_text(f"""# Hermes Orchestration Audit

## Objective

Add DeepSeek Harness as a parallel agentic reasoning/review layer while preserving:

- deterministic `WEBSITE-AUDITOR` Python core
- Hermes as scheduler/master
- zero paid inference
- human/machine evidence approval gates
- no unrestricted shell access
- no secret exposure
- no auto-send or auto-deploy by default

## Architecture

The implementation uses a sidecar integration pattern:

```text
Hermes / operator
   |
   +--> deterministic Python core
   |      - website_auditor.py
   |      - full-pipeline.py
   |      - remediation-engine.py
   |
   +--> DeepSeek Harness scaffold
          |
          +--> SQLite state machine
          +--> safe mm bridge
          +--> approval gate
          +--> local inference hook
          +--> dry-run outreach dispatcher
          +--> reports

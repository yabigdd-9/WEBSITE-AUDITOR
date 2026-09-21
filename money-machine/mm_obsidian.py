#!/usr/bin/env python3
"""Read-mostly Obsidian operator workspace for WEBSITE-AUDITOR.

Renders human-facing Markdown from canonical runtime state. It never reads
approval intent from Markdown and never mutates SQLite, send state, suppression
state, pricing rules, or pipeline state.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

FOLDERS = (
    "00-DASHBOARD", "01-MASTER-PLAN", "02-LEADS", "03-PROSPECTS",
    "04-AGENTS", "05-APPROVALS", "06-EXPERIMENTS", "07-REPORTS", "08-RUNBOOK",
)

EXPECTED_FILES = (
    "00-DASHBOARD/CONTROL-CENTRE.md",
    "00-DASHBOARD/TODAY.md",
    "00-DASHBOARD/PIPELINE-STATUS.md",
    "00-DASHBOARD/SYSTEM-HEALTH.md",
    "01-MASTER-PLAN/MASTER-PLAN.md",
    "01-MASTER-PLAN/CURRENT-STATE.md",
    "01-MASTER-PLAN/CHANGELOG.md",
    "01-MASTER-PLAN/ROADMAP.md",
    "04-AGENTS/HERMES.md",
    "04-AGENTS/CODER.md",
    "04-AGENTS/RESEARCHER.md",
    "04-AGENTS/JUDGE.md",
    "04-AGENTS/PROOFER.md",
    "04-AGENTS/INTEGRATOR.md",
    "08-RUNBOOK/RECOVERY.md",
    "08-RUNBOOK/PROVIDERS.md",
    "08-RUNBOOK/EMAIL-VERIFICATION.md",
    "08-RUNBOOK/EMERGENCY-STOP.md",
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def default_vault(repo_root: Path) -> Path:
    configured = os.environ.get("MM_OBSIDIAN_VAULT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path(repo_root).resolve() / "WEBSITE-AUDITOR-BRAIN").resolve()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="." + path.name, dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _json_block(value) -> str:
    return "JSON snapshot:\n\n" + json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n"


def _header(title: str) -> str:
    return (
        "---\n"
        "generated_by: mm obsidian-sync\n"
        "generated_at: " + _now() + "\n"
        "runtime_authority: false\n"
        "send_authority: false\n"
        "approval_authority: false\n"
        "---\n\n"
        "# " + title + "\n\n"
        "> Read-mostly operator view. SQLite, ./mm, and runtime policy remain authoritative.\n\n"
    )


def ensure_structure(vault: Path) -> None:
    for folder in FOLDERS:
        (vault / folder).mkdir(parents=True, exist_ok=True)


def sync(repo_root: Path, snapshot: dict, vault: Path | None = None) -> dict:
    repo_root = Path(repo_root).resolve()
    vault = Path(vault).expanduser().resolve() if vault else default_vault(repo_root)
    ensure_structure(vault)

    status_data = snapshot.get("status") or {}
    metrics = status_data.get("metrics") or {}
    queue = status_data.get("human_queue") or []
    blocked = status_data.get("blocked") or []
    pipeline = snapshot.get("pipeline") or {}
    doctor = snapshot.get("doctor") or {}
    supervisor = snapshot.get("supervisor") or {}

    control = _header("WEBSITE-AUDITOR Control Centre")
    control += (
        "## Authority boundary\n\n"
        "- Canonical runtime state: SQLite + state files\n"
        "- Operator CLI: ./mm\n"
        "- Supervisor: launchd / ./mm supervisor\n"
        "- Obsidian: human-facing view only\n"
        "- Outreach sending: disabled by default\n"
        "- Paid model/API spend: forbidden by policy\n\n"
        "## Current snapshot\n\n"
    )
    control += _json_block({
        "generated_at": status_data.get("generated_at"),
        "real_prospects": metrics.get("real_prospects"),
        "verified_sends": metrics.get("verified_sends"),
        "verified_replies": metrics.get("verified_replies"),
        "net_received_nzd": metrics.get("net_received_nzd"),
        "blocked_count": len(blocked),
        "human_queue_count": len(queue),
        "pipeline": pipeline,
        "supervisor": supervisor,
    })

    today = _header("Today") + "## Human queue\n\n"
    if queue:
        for item in queue:
            today += "- **" + str(item.get("name", "Unknown")) + "** — " + str(item.get("action", "Review")) + "\n"
    else:
        today += "- No queued human actions in this snapshot.\n"
    today += "\n## Blocked\n\n"
    if blocked:
        for item in blocked:
            today += "- **" + str(item.get("name", "Unknown")) + "** — " + str(item.get("reason", "Blocked")) + "\n"
    else:
        today += "- No blocked items reported.\n"

    pipeline_md = _header("Pipeline Status") + _json_block(pipeline)
    health_md = _header("System Health") + _json_block({
        "doctor": doctor,
        "supervisor": supervisor,
        "runtime_note": "Obsidian may be closed or deleted without stopping WEBSITE-AUDITOR.",
    })

    current = _header("Current State")
    current += (
        "Canonical repository: /Users/dd/WEBSITE-AUDITOR\n\n"
        "Execution plan: WEBSITE-AUDITOR Master Merged Plan v32.\n\n"
        "This vault is generated from runtime state and is not a database, queue, "
        "pricing engine, approval gate, or send authority.\n\n"
    )
    current += _json_block({
        "metrics": metrics,
        "pipeline": pipeline,
        "external_send_allowed": False,
        "paid_allowed": False,
        "max_cost_usd": 0,
    })

    roadmap = _header("Roadmap")
    roadmap += (
        "1. Preserve canonical repository and data.\n"
        "2. Keep Python 3.11 and tests green.\n"
        "3. Prove continuous supervisor and restart recovery.\n"
        "4. Improve identity, deterministic audit evidence, and NZ discovery.\n"
        "5. Preserve Email Finder V2 provenance rules.\n"
        "6. Build remediation, demo, before-after, quote, and prospect-packet pipeline.\n"
        "7. Keep outreach draft-only until transport is deliberately enabled.\n"
        "8. Improve only through tested challenger branches.\n"
    )

    canonical_plan = repo_root / "MASTER_PLAN.md"
    canonical_changelog = repo_root / "CHANGELOG.md"
    master_plan_view = _header("Master Plan") + (
        canonical_plan.read_text(encoding="utf-8")
        if canonical_plan.is_file()
        else "Canonical MASTER_PLAN.md is unavailable.\n"
    )
    changelog_view = _header("Changelog") + (
        canonical_changelog.read_text(encoding="utf-8")
        if canonical_changelog.is_file()
        else "Canonical CHANGELOG.md is unavailable.\n"
    )

    agent_docs = {
        "HERMES": "Orchestrator. Delegates bounded work; does not bypass policy gates or paid-cost rules.",
        "CODER": "Implements one isolated task per branch/worktree and supplies test evidence.",
        "RESEARCHER": "Collects evidence and sources; does not mutate production state.",
        "JUDGE": "Reviews evidence, regressions, and measurable outcomes rather than agent confidence.",
        "PROOFER": "Checks factual support, copy quality, provenance, compliance, and unsupported claims.",
        "INTEGRATOR": "Only role permitted to promote accepted tested changes after gates are green.",
    }

    providers = _header("Providers")
    providers += (
        "Provider policy: deterministic code first, then local/free inference, then verified free external routes, otherwise DEFER.\n\n"
        "Silent paid fallback is forbidden. Do not place API keys or secrets in Obsidian notes.\n"
    )

    email_verification = _header("Email Verification")
    email_verification += (
        "Email Finder V2 rules:\n\n"
        "- Pattern guess is not verified.\n"
        "- Catch-all is not verified.\n"
        "- MX existence is not mailbox verification.\n"
        "- NO_VERIFIED_EMAIL is a valid final state.\n"
        "- Eligible contacts require provenance and explicit verification state.\n"
        "- SMTP evidence is optional and never the sole authority.\n"
    )

    recovery = _header("Recovery")
    recovery += (
        "1. Run ./mm --runtime.\n"
        "2. Run ./mm doctor.\n"
        "3. Run ./mm supervisor status.\n"
        "4. Run ./mm supervisor health.\n"
        "5. Inspect queue and dead-letter state before restarting work.\n"
        "6. Obsidian is optional; regenerate with ./mm obsidian-sync.\n"
        "7. Never recover by enabling live outreach or paid fallback.\n"
    )

    emergency = _header("Emergency Stop")
    emergency += (
        "1. Run ./mm supervisor stop.\n"
        "2. Keep outreach transport disabled.\n"
        "3. Do not edit SQLite directly.\n"
        "4. Preserve database and state backups before repair.\n"
        "5. Resume only after ./mm doctor and tests are green.\n"
    )

    files = {
        "00-DASHBOARD/CONTROL-CENTRE.md": control,
        "00-DASHBOARD/TODAY.md": today,
        "00-DASHBOARD/PIPELINE-STATUS.md": pipeline_md,
        "00-DASHBOARD/SYSTEM-HEALTH.md": health_md,
        "01-MASTER-PLAN/MASTER-PLAN.md": master_plan_view,
        "01-MASTER-PLAN/CURRENT-STATE.md": current,
        "01-MASTER-PLAN/CHANGELOG.md": changelog_view,
        "01-MASTER-PLAN/ROADMAP.md": roadmap,
        "08-RUNBOOK/RECOVERY.md": recovery,
        "08-RUNBOOK/PROVIDERS.md": providers,
        "08-RUNBOOK/EMAIL-VERIFICATION.md": email_verification,
        "08-RUNBOOK/EMERGENCY-STOP.md": emergency,
    }
    for role, description in agent_docs.items():
        files["04-AGENTS/" + role + ".md"] = _header(role) + description + "\n"
    for rel, body in files.items():
        _atomic_write(vault / rel, body)

    return {
        "status": "synced",
        "vault": str(vault),
        "generated_files": sorted(files),
        "runtime_authority": False,
        "send_authority": False,
        "approval_authority": False,
        "external_send_allowed": False,
    }


def status(repo_root: Path, vault: Path | None = None) -> dict:
    repo_root = Path(repo_root).resolve()
    vault = Path(vault).expanduser().resolve() if vault else default_vault(repo_root)
    files = {rel: (vault / rel).is_file() for rel in EXPECTED_FILES}
    return {
        "vault": str(vault),
        "exists": vault.is_dir(),
        "expected_files": files,
        "complete": all(files.values()),
        "runtime_dependency": False,
        "runtime_authority": False,
        "send_authority": False,
        "approval_authority": False,
        "sync_direction": "runtime_to_obsidian_only",
    }

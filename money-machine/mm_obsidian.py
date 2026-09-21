#!/usr/bin/env python3
"""Read-mostly Obsidian operator workspace for WEBSITE-AUDITOR.

Obsidian is presentation/documentation only. SQLite, ./mm and runtime policy remain
authoritative. This module never sends mail, changes approvals, pricing, suppression,
queue state or database records.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import mm_core as core

FOLDERS = (
    "00-DASHBOARD",
    "01-MASTER-PLAN",
    "02-LEADS",
    "03-PROSPECTS",
    "04-AGENTS",
    "05-APPROVALS",
    "06-EXPERIMENTS",
    "07-REPORTS",
    "08-RUNBOOK",
)

GENERATED = (
    "00-DASHBOARD/CONTROL-CENTRE.md",
    "00-DASHBOARD/TODAY.md",
    "00-DASHBOARD/PIPELINE-STATUS.md",
    "00-DASHBOARD/SYSTEM-HEALTH.md",
    "01-MASTER-PLAN/MASTER-PLAN.md",
    "01-MASTER-PLAN/CURRENT-STATE.md",
    "01-MASTER-PLAN/CHANGELOG.md",
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


def vault_root() -> Path:
    raw = os.environ.get("MM_OBSIDIAN_ROOT")
    return Path(raw).expanduser().resolve() if raw else (core.root() / "WEBSITE-AUDITOR-BRAIN").resolve()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _read(path: Path, fallback: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return fallback


def _json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def _last_jsonl(path: Path):
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, UnicodeError):
        return None
    for line in reversed(lines):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return None


def _frontmatter(title: str) -> str:
    return (
        "---\n"
        "generated_by: ./mm obsidian-sync\n"
        "authoritative: false\n"
        "runtime_authority: SQLite + ./mm + launchd\n"
        "send_authority: false\n"
        f"title: {title}\n"
        "---\n\n"
    )


def status() -> dict:
    vault = vault_root()
    missing_folders = [name for name in FOLDERS if not (vault / name).is_dir()]
    missing_files = [name for name in GENERATED if not (vault / name).is_file()]
    return {
        "vault": str(vault),
        "exists": vault.is_dir(),
        "canonical_runtime_state": False,
        "canonical_database": False,
        "canonical_queue": False,
        "canonical_send_authority": False,
        "runtime_dependency": False,
        "missing_folders": missing_folders,
        "missing_generated_files": missing_files,
        "ready": not missing_folders and not missing_files,
    }


def sync() -> dict:
    repo = core.root()
    vault = vault_root()
    for folder in FOLDERS:
        (vault / folder).mkdir(parents=True, exist_ok=True)

    health = _json(repo / "state" / "health.json")
    latest_metrics = _last_jsonl(repo / "state" / "metrics.jsonl")
    latest_error = _last_jsonl(repo / "state" / "errors.jsonl")
    daily = _read(repo / "reports" / "DAILY_OPERATOR.md", "_No daily operator report has been generated yet._\n")
    kpi = _read(repo / "reports" / "KPI_DASHBOARD.md", "_No KPI dashboard has been generated yet._\n")

    control = _frontmatter("WEBSITE-AUDITOR Control Centre") + """# WEBSITE-AUDITOR Control Centre

Human-facing workspace only. Editing this vault never authorizes outreach, changes
SQLite state, bypasses suppression, changes pricing, or overrides ./mm policy.

## Canonical controls

- ./mm supervisor status
- ./mm supervisor health
- ./mm status
- ./mm obsidian-sync
- ./mm obsidian-status

## Safety

- Paid model/API fallback: disabled
- Live outreach: disabled by default
- Canonical runtime state: SQLite + state files
- Runtime supervisor: launchd + ./mm supervisor
- Agent orchestrator: Hermes
- n8n default runtime dependency: none
"""
    _atomic_write(vault / "00-DASHBOARD" / "CONTROL-CENTRE.md", control)
    _atomic_write(vault / "00-DASHBOARD" / "TODAY.md", _frontmatter("Today") + "# Today\n\n" + daily)
    _atomic_write(vault / "00-DASHBOARD" / "PIPELINE-STATUS.md", _frontmatter("Pipeline Status") + "# Pipeline Status\n\n" + kpi)

    health_payload = {
        "health": health,
        "latest_metrics": latest_metrics,
        "latest_error": latest_error,
        "note": "Snapshot only; use ./mm supervisor health for live authority.",
    }
    _atomic_write(
        vault / "00-DASHBOARD" / "SYSTEM-HEALTH.md",
        _frontmatter("System Health") + "# System Health\n\n" + json.dumps(health_payload, indent=2, default=str) + "\n",
    )

    _atomic_write(vault / "01-MASTER-PLAN" / "MASTER-PLAN.md", _frontmatter("Master Plan") + _read(repo / "MASTER_PLAN.md", "# Master Plan\n\nMissing canonical source.\n"))
    _atomic_write(vault / "01-MASTER-PLAN" / "CURRENT-STATE.md", _frontmatter("Current State") + _read(repo / "CURRENT_STATE.md", "# Current State\n\nMissing canonical source.\n"))
    _atomic_write(vault / "01-MASTER-PLAN" / "CHANGELOG.md", _frontmatter("Changelog") + _read(repo / "CHANGELOG.md", "# Changelog\n\nMissing canonical source.\n"))

    roles = {
        "HERMES": "Orchestrator. Delegates bounded work; does not bypass policy gates.",
        "CODER": "Implements one isolated task per branch/worktree. Must provide tests.",
        "RESEARCHER": "Collects evidence and provenance. Does not invent unsupported facts.",
        "JUDGE": "Reviews evidence, tests and measurable outcomes rather than agent confidence.",
        "PROOFER": "Checks correctness, copy quality, evidence linkage and safety constraints.",
        "INTEGRATOR": "Promotes only tested, reviewed changes. No direct autonomous production edits.",
    }
    for role, body in roles.items():
        _atomic_write(vault / "04-AGENTS" / f"{role}.md", _frontmatter(role.title()) + f"# {role.title()}\n\n{body}\n")

    _atomic_write(vault / "08-RUNBOOK" / "RECOVERY.md", _frontmatter("Recovery") + """# Recovery

1. Check ./mm supervisor status.
2. Check ./mm supervisor health.
3. Review worker logs and dead-letter state.
4. Confirm SQLite/database integrity before changing state.
5. Restart with ./mm supervisor restart only after identifying the failure boundary.
6. Never use Obsidian edits as recovery commands.
""")
    _atomic_write(vault / "08-RUNBOOK" / "PROVIDERS.md", _frontmatter("Providers") + """# Providers

- Deterministic code first.
- Local/free model routes only.
- paid_allowed=false.
- max_cost_usd=0.
- If every free route is unavailable, defer the job.
- Never silently fall back to a paid provider.
""")
    _atomic_write(vault / "08-RUNBOOK" / "EMAIL-VERIFICATION.md", _frontmatter("Email Verification") + """# Email Verification

- Pattern guess != verified.
- MX exists != mailbox verified.
- Catch-all != verified.
- SMTP evidence is optional and is never the sole authority.
- Every eligible address requires provenance.
- NO_VERIFIED_EMAIL is an acceptable final state.
- Suppression, duplicate, bounce and stop-on-response controls remain authoritative outside Obsidian.
""")
    _atomic_write(vault / "08-RUNBOOK" / "EMERGENCY-STOP.md", _frontmatter("Emergency Stop") + """# Emergency Stop

For runtime issues, use the canonical operator:

./mm supervisor stop

Then verify:

./mm supervisor status

Obsidian is not a runtime dependency and closing it does not stop WEBSITE-AUDITOR.
Live outreach is disabled by default; do not add a Markdown-based send override.
""")

    result = status()
    result["synced"] = True
    result["generated_count"] = len(GENERATED)
    return result

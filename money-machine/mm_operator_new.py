#!/usr/bin/env python3
"""WEBSITES/BUISNESSaudits: deterministic local operator. Never sends or calls a model.

This is the refactored version using command modules.
"""

import argparse
import contextlib
import json
import sys

from commands import build_parser
from mm_core import connect, root


def validate_environment():
    """Fail-fast environment validation for runtime operations.

    Skipped for commands that do not touch the MoneyMachine database
    (e.g. ``supervisor stop``, ``init`` which creates the DB).
    """
    r = root()
    if not r.exists():
        raise OperationalError(f"MM_ROOT directory does not exist: {r}")
    if not (r / "database").exists():
        raise OperationalError("Database directory missing")


class OperatorError(Exception):
    """Base exception for mm_operator."""
    pass


class ValidationError(OperatorError):
    """Raised for input/data validation failures."""
    pass


class OperationalError(OperatorError):
    """Raised for runtime/operational failures."""
    pass


def backup():
    """Create a database backup and return the backup path."""
    import shutil
    from datetime import datetime

    r = root()
    db_path = r / "database" / "money_machine.db"
    if not db_path.exists():
        return "no_database"

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = r / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"money_machine_{ts}.db"
    shutil.copy2(db_path, backup_path)
    return str(backup_path)


def migrate(d, backup_path):
    """Run database migrations."""
    # Import and run migrations from mm_pipeline, mm_approval, etc.
    import mm_pipeline
    import mm_approval
    mm_pipeline.migrate(d)
    mm_approval.migrate(d)


def main(argv=None):
    """Main entry point for mm operator."""
    parser = build_parser()
    a = parser.parse_args(argv)

    # Check if command needs environment validation
    no_env_validation = a.cmd in ("supervisor", "init", "backup", "polish-status", "module-status")

    if not no_env_validation:
        validate_environment()

    # Route to appropriate handler
    result = None
    try:
        # Core commands
        if a.cmd in (
            "daily", "run-day", "status", "money", "learn", "backup", "init",
            "doctor", "experiment", "intake", "price", "audit", "contact",
            "draft", "draft-review", "draft-approve", "review", "record-sent",
            "receipt-import", "cash", "refund", "reply", "suppress", "stage",
            "quote", "score", "demo-qa", "model-request", "run-job"
        ):
            from commands.core import handle
            result = handle(a)

        # Observability commands
        elif a.cmd in ("health", "metrics", "errors", "queue", "observability-snapshot", "dead-letter"):
            from commands.observability import handle
            result = handle(a)

        # Data quarantine
        elif a.cmd == "data-quarantine":
            from commands.data_quarantine import handle
            result = handle(a)

        # Obsidian
        elif a.cmd in ("obsidian-sync", "obsidian-status"):
            from commands.obsidian import handle
            result = handle(a)

        # Smart reply
        elif a.cmd == "smart-reply":
            from commands.smart_reply import handle
            result = handle(a)

        # Transport
        elif a.cmd in ("transport-status", "transport-preflight", "transport-send"):
            from commands.transport import handle
            result = handle(a)

        # Outcomes
        elif a.cmd in ("outcomes", "outcome-record"):
            from commands.outcomes import handle
            result = handle(a)

        # Polish/Module status
        elif a.cmd in ("polish-status", "module-status"):
            from commands.polish_module import handle
            result = handle(a)

        # Audit workflow
        elif a.cmd == "audit-packet":
            from commands.audit_workflow import handle
            return handle(a)

        # Outreach
        elif a.cmd.startswith("outreach-"):
            from commands.outreach import handle, should_exit_with_error
            result = handle(a)
            if should_exit_with_error(a, result):
                return 2

        # Email
        elif a.cmd.startswith("email-"):
            from commands.email import handle
            result = handle(a)

        # Discovery
        elif a.cmd in ("discover-import", "discover-search"):
            from commands.discovery import handle
            result = handle(a)

        # Evidence
        elif a.cmd in ("audit-backfill", "discover-contacts"):
            from commands.evidence import handle
            result = handle(a)

        # Reporting
        elif a.cmd in ("report", "alerts", "rotate-logs"):
            from commands.reporting import handle
            result = handle(a)

        # Brain
        elif a.cmd in ("bottlenecks", "schedule", "brain", "decisions", "decision", "brain-replay", "brain-shadow", "db-check", "safe-mode"):
            from commands.brain import handle
            result = handle(a)

        # Supervisor
        elif a.cmd == "supervisor":
            from commands.supervisor_cmd import handle
            result = handle(a)

        # Model
        elif a.cmd in ("model-routes", "model-plan"):
            from commands.model import handle
            result = handle(a)

        # Agent policy
        elif a.cmd == "agent-policy-check":
            from commands.agent_policy import handle
            result = handle(a)

        # Challenger
        elif a.cmd == "challenger-eval":
            from commands.challenger import handle
            result = handle(a)

        # Deploy
        elif a.cmd == "deploy-check":
            from commands.deploy import handle
            result = handle(a)

        # Pipeline
        elif a.cmd.startswith("pipeline-"):
            from commands.pipeline_cmd import handle
            result = handle(a)

        # Approval
        elif a.cmd in ("approval-check", "approval-decide"):
            from commands.approval import handle
            result = handle(a)

        # Price
        elif a.cmd == "price":
            from commands.price import handle
            result = handle(a)

        else:
            print(json.dumps({"error": f"Unknown command: {a.cmd}"}, indent=2))
            return 2

        if result is not None:
            print(json.dumps(result, indent=2, default=str))
        return 0

    except OperatorError as e:
        print("BLOCKED: " + str(e), file=sys.stderr)
        return 2
    except (ValidationError, ValueError, sqlite3.Error, OSError, KeyError) as e:
        print("BLOCKED: " + str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    import sqlite3
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        sys.exit(130)
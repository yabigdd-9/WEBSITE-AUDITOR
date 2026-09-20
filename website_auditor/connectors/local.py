"""Safe local connector.

This connector creates/removes local artifacts only. It never edits live websites,
sends network messages, changes DNS/TLS or deploys production code.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..models import Action
from .base import ConnectorResult


class LocalConnector:
    name = "local"

    def __init__(self, root: str | Path = "outputs/actions/local"):
        self.root = Path(root)

    def _artifact(self, action: Action) -> Path:
        suffix = ".md" if action.action_type == "ticket.create" else ".json"
        return self.root / f"{action.action_id}{suffix}"

    def dry_run(self, action: Action) -> ConnectorResult:
        return ConnectorResult(
            ok=True,
            effect="dry_run",
            message="Local action planned only; no files changed.",
            artifacts=[],
            verification={"planned": True},
            rollback={"supported": action.reversible},
        )

    def execute(self, action: Action) -> ConnectorResult:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._artifact(action)
        if action.action_type == "ticket.create":
            payload = action.payload
            path.write_text(
                "# Remediation Ticket\n\n"
                f"- Domain: {action.domain}\n"
                f"- Check: {payload.get('check_id', 'unknown')}\n"
                f"- Finding: {payload.get('message', '')}\n"
                f"- Risk: {action.risk.value}\n"
                f"- Action ID: {action.action_id}\n"
            )
        else:
            path.write_text(json.dumps({
                "action": action.to_dict(),
                "note": "Local artifact only. No external change was performed.",
            }, indent=2, sort_keys=True, default=str))

        result = ConnectorResult(
            ok=True,
            effect="execute_local",
            message="Local artifact created.",
            artifacts=[str(path)],
            verification={},
            rollback={"supported": True, "delete_artifacts": [str(path)]},
        )
        result.verification = self.verify(action, result)
        return result

    def verify(self, action: Action, result: ConnectorResult) -> dict:
        existing = [path for path in result.artifacts if Path(path).exists()]
        return {
            "ok": len(existing) == len(result.artifacts) and bool(result.artifacts),
            "artifacts_exist": existing,
            "reaudit_required": "reaudit.required" in action.verification_checks,
        }

    def rollback(self, action: Action) -> ConnectorResult:
        path = self._artifact(action)
        existed = path.exists()
        path.unlink(missing_ok=True)
        return ConnectorResult(
            ok=True,
            effect="rollback_local",
            message="Local artifact removed." if existed else "Nothing to roll back.",
            artifacts=[],
            verification={"artifact_absent": not path.exists()},
            rollback=None,
        )


class UnavailableConnector:
    def __init__(self, name: str):
        self.name = name

    def _blocked(self) -> ConnectorResult:
        return ConnectorResult(
            ok=False,
            effect="blocked",
            message=f"Connector '{self.name}' is not configured for execution.",
            artifacts=[],
            verification={"ok": False},
            rollback=None,
        )

    def dry_run(self, action: Action) -> ConnectorResult:
        return ConnectorResult(
            ok=True,
            effect="dry_run",
            message=f"Connector '{self.name}' action simulated only.",
            artifacts=[],
            verification={"planned": True},
            rollback=None,
        )

    def execute(self, action: Action) -> ConnectorResult:
        return self._blocked()

    def verify(self, action: Action, result: ConnectorResult) -> dict:
        return {"ok": False, "reason": "connector unavailable"}

    def rollback(self, action: Action) -> ConnectorResult:
        return self._blocked()

"""Remediation lifecycle state tracking with guarded transitions."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .models import RemediationState, RemediationStatus


ALLOWED_TRANSITIONS: dict[RemediationStatus, set[RemediationStatus]] = {
    RemediationStatus.detected: {
        RemediationStatus.acknowledged,
        RemediationStatus.scheduled,
        RemediationStatus.false_positive,
        RemediationStatus.accepted_risk,
    },
    RemediationStatus.acknowledged: {
        RemediationStatus.scheduled,
        RemediationStatus.in_progress,
        RemediationStatus.false_positive,
        RemediationStatus.accepted_risk,
    },
    RemediationStatus.scheduled: {
        RemediationStatus.in_progress,
        RemediationStatus.accepted_risk,
    },
    RemediationStatus.in_progress: {
        RemediationStatus.patched,
        RemediationStatus.accepted_risk,
    },
    RemediationStatus.patched: {
        RemediationStatus.verified,
        RemediationStatus.regressed,
    },
    RemediationStatus.verified: {RemediationStatus.regressed},
    RemediationStatus.regressed: {
        RemediationStatus.acknowledged,
        RemediationStatus.scheduled,
        RemediationStatus.in_progress,
    },
    RemediationStatus.accepted_risk: {RemediationStatus.acknowledged},
    RemediationStatus.false_positive: {RemediationStatus.acknowledged},
}


def initial_remediation(*, verification_command: str | None = None) -> dict:
    return RemediationState(verification_command=verification_command).model_dump(mode="json")


class RemediationStateStore:
    """Small JSON state store keyed by stable finding identity."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        data = json.loads(self.path.read_text())
        return data if isinstance(data, dict) else {}

    def save(self, data: dict[str, dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
        tmp.replace(self.path)

    def transition(
        self,
        finding_key: str,
        target: RemediationStatus | str,
        **updates,
    ) -> dict:
        target = RemediationStatus(target)
        data = self.load()
        current = RemediationState.model_validate(data.get(finding_key, {}))
        if target != current.status and target not in ALLOWED_TRANSITIONS[current.status]:
            raise ValueError(f"invalid remediation transition: {current.status} -> {target}")
        next_state = current.model_copy(update={"status": target, **updates})
        if target == RemediationStatus.verified:
            next_state = next_state.model_copy(
                update={"last_verified_at": datetime.now(timezone.utc).isoformat()}
            )
        if target == RemediationStatus.regressed:
            next_state = next_state.model_copy(update={"regression_alert": True})
        data[finding_key] = next_state.model_dump(mode="json")
        self.save(data)
        return data[finding_key]

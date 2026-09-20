"""Atomic local stores for actions, approvals, authorization, idempotency and rate limits."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..models import Action, utc_now


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True, default=str))
    tmp.replace(path)


class ActionStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def all(self) -> list[Action]:
        raw = _read_json(self.path, {})
        return [Action.from_dict(item) for item in raw.values() if isinstance(item, dict)]

    def get(self, action_id: str) -> Action | None:
        item = _read_json(self.path, {}).get(action_id)
        return Action.from_dict(item) if isinstance(item, dict) else None

    def put(self, action: Action) -> Action:
        raw = _read_json(self.path, {})
        action.touch()
        raw[action.action_id] = action.to_dict()
        _write_json(self.path, raw)
        return action


class ApprovalStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def set(self, action_id: str, *, approved: bool, actor: str, reason: str = "") -> dict:
        raw = _read_json(self.path, {})
        record = {
            "action_id": action_id,
            "approved": bool(approved),
            "actor": actor,
            "reason": reason,
            "updated_at": utc_now(),
        }
        raw[action_id] = record
        _write_json(self.path, raw)
        return record

    def is_approved(self, action_id: str) -> bool:
        return bool(_read_json(self.path, {}).get(action_id, {}).get("approved"))


class AuthorizationStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def authorize(self, domain: str, *, scopes: list[str], actor: str, note: str = "") -> dict:
        raw = _read_json(self.path, {})
        key = domain.lower().strip()
        record = {
            "domain": key,
            "scopes": sorted(set(scopes)),
            "actor": actor,
            "note": note,
            "authorized_at": utc_now(),
        }
        raw[key] = record
        _write_json(self.path, raw)
        return record

    def is_authorized(self, domain: str, scope: str) -> bool:
        record = _read_json(self.path, {}).get(domain.lower().strip(), {})
        scopes = set(record.get("scopes", []))
        return "*" in scopes or scope in scopes


class IdempotencyStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def contains(self, key: str) -> bool:
        return key in _read_json(self.path, {})

    def mark(self, key: str, action_id: str) -> None:
        raw = _read_json(self.path, {})
        raw[key] = {"action_id": action_id, "completed_at": utc_now()}
        _write_json(self.path, raw)


class RateLimitStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _active(self) -> list[str]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        active: list[str] = []
        for value in _read_json(self.path, []):
            try:
                if datetime.fromisoformat(value) >= cutoff:
                    active.append(value)
            except (TypeError, ValueError):
                continue
        return active

    def allowed(self, limit: int) -> bool:
        return len(self._active()) < max(1, int(limit))

    def reserve(self) -> None:
        active = self._active()
        active.append(utc_now())
        _write_json(self.path, active)


class KillSwitch:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    @property
    def active(self) -> bool:
        return self.path.exists()

    def pause(self, actor: str = "local_user") -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"active": True, "actor": actor, "at": utc_now()}, indent=2))

    def resume(self) -> None:
        self.path.unlink(missing_ok=True)

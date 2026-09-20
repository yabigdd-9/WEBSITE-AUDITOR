"""Connector protocol for policy-controlled actions."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Protocol

from ..models import Action


@dataclass
class ConnectorResult:
    ok: bool
    effect: str
    message: str
    artifacts: list[str]
    verification: dict[str, Any]
    rollback: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Connector(Protocol):
    name: str

    def dry_run(self, action: Action) -> ConnectorResult: ...
    def execute(self, action: Action) -> ConnectorResult: ...
    def rollback(self, action: Action) -> ConnectorResult: ...
    def verify(self, action: Action, result: ConnectorResult) -> dict[str, Any]: ...

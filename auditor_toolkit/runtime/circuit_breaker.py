"""Circuit breakers — per-domain/tool failure isolation."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Literal

CBState = Literal["CLOSED", "OPEN", "HALF_OPEN"]


@dataclass
class CircuitBreaker:
    name: str
    threshold: int = 5
    window_seconds: int = 300
    cooldown_seconds: int = 900
    state: CBState = "CLOSED"
    failure_count: int = 0
    last_failure: float = 0.0
    last_success: float = 0.0

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure = time.monotonic()
        if self.failure_count >= self.threshold:
            self.state = "OPEN"

    def record_success(self) -> None:
        self.failure_count = 0
        self.last_success = time.monotonic()
        if self.state == "HALF_OPEN":
            self.state = "CLOSED"

    def can_execute(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if time.monotonic() - self.last_failure >= self.cooldown_seconds:
                self.state = "HALF_OPEN"
                return True
            return False
        return True  # HALF_OPEN

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state,
            "failure_count": self.failure_count,
            "threshold": self.threshold,
        }


class CircuitBreakerRegistry:
    _breakers: dict[str, CircuitBreaker] = {}

    @classmethod
    def get(cls, name: str, **kwargs) -> CircuitBreaker:
        if name not in cls._breakers:
            cls._breakers[name] = CircuitBreaker(name=name, **kwargs)
        return cls._breakers[name]

    @classmethod
    def record_failure(cls, name: str) -> None:
        cls.get(name).record_failure()

    @classmethod
    def record_success(cls, name: str) -> None:
        cls.get(name).record_success()

    @classmethod
    def can_execute(cls, name: str) -> bool:
        return cls.get(name).can_execute()

    @classmethod
    def status(cls) -> dict[str, dict[str, Any]]:
        return {k: v.to_dict() for k, v in cls._breakers.items()}

"""BrowserGym adapter stub.

BrowserGym (https://github.com/ServiceNow/BrowserGym) provides gym
environments for browser agents.  This stub defines the interface;
a full adapter would translate EvalCase → BrowserGym task config.

Not a core dependency — installed optionally via [evaluation.browsergym] extras.
"""

from __future__ import annotations

from ..schema import EvalCase, EvalResult


class BrowserGymAdapter:
    """Stub adapter for BrowserGym evaluation framework."""

    def __init__(self):
        self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def run(self, case: EvalCase, run_id: str = "") -> EvalResult:
        return EvalResult(
            case_id=case.case_id,
            run_id=run_id,
            overall="N/A",
            agent_output="BROWSERGYM_STUB: not implemented",
            agent_model="stub",
        )

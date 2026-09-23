"""Inspect AI adapter stub.

Inspect AI (https://github.com/UKGovernmentBEIS/inspect_ai) is a UK
government evaluation framework.  This stub defines the interface;
a full adapter would translate EvalCase → Inspect Sample and capture
Inspect logs as EvalResult data.

Not a core dependency — installed optionally via [evaluation.inspect] extras.
"""

from __future__ import annotations

from ..schema import EvalCase, EvalResult


class InspectAIAdapter:
    """Stub adapter for Inspect AI evaluation framework."""

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
            agent_output="INSPECT_AI_STUB: not implemented",
            agent_model="stub",
        )

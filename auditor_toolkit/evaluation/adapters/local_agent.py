"""Local agent adapter — runs a local/deterministic agent for evaluation.

This adapter executes a local agent function or script, captures its output,
claims, tool calls, and evidence selections, and returns them as structured
EvalResult-compatible data.
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable

from ..schema import EvalCase, EvalEvidenceRef, EvalResult, EvalToolCall


class LocalAgentAdapter:
    """Wraps a local callable (agent function) for evaluation.

    The callable must accept (case: EvalCase) and return a dict with keys:
      - claims: list[dict]
      - evidence: list[dict]   (each with finding_id / evidence_id / etc.)
      - tool_calls: list[dict] (each with tool_name, args, etc.)
      - output: str (raw agent output, typically JSON)
      - model: str
    """

    def __init__(self, agent_fn: Callable[[EvalCase], dict[str, Any]]):
        self.agent_fn = agent_fn

    def run(self, case: EvalCase, run_id: str = "") -> EvalResult:
        start = time.monotonic()
        try:
            raw = self.agent_fn(case)
        except Exception as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            result = EvalResult(
                case_id=case.case_id,
                run_id=run_id,
                overall="FAIL",
                duration_ms=elapsed,
                agent_output=f"AGENT_ERROR: {exc}",
            )
            result.add_grader("JSON_VALIDITY", "FAIL")
            return result

        elapsed = int((time.monotonic() - start) * 1000)

        claims = raw.get("claims", [])
        evidence = [EvalEvidenceRef(**ref) if isinstance(ref, dict) else ref for ref in raw.get("evidence", [])]
        tool_calls = [
            EvalToolCall(**tc) if isinstance(tc, dict) else tc
            for tc in raw.get("tool_calls", [])
        ]
        output = raw.get("output", json.dumps(raw.get("claims", [])))
        model = raw.get("model", "local")

        return EvalResult(
            case_id=case.case_id,
            run_id=run_id,
            claims=claims,
            evidence_selected=evidence,
            tool_calls=tool_calls,
            duration_ms=elapsed,
            agent_output=output,
            agent_model=model,
        )

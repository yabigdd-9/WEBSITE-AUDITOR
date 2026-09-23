"""Adapter to v36 AI evaluation harness.

Runs proof prototypes through existing v36 deterministic graders.
Reuses the v36 evaluation pipeline — does not implement its own
grading logic.
"""

from __future__ import annotations

from typing import Any

from auditor_toolkit.proof.prototype import PrototypeManifest


def evaluate_prototype(
    prototype: PrototypeManifest,
    finding: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate a prototype against its source finding.

    Attempts to import and reuse the v36 evaluation harness.  When the
    harness is not available, falls back to a basic deterministic check.

    Returns a dict with:
      - pass: bool
      - score: float (0.0–1.0)
      - grader: str
      - details: dict
    """
    # Try to use the v36 evaluation harness if available
    try:
        from auditor_toolkit.evaluation.harness import run_evaluation
        result = run_evaluation(prototype, finding)
        return {
            "pass": result.get("pass", False),
            "score": result.get("score", 0.0),
            "grader": "v36-harness",
            "details": result,
        }
    except ImportError:
        pass

    # Fallback: basic deterministic evaluation
    return _basic_evaluation(prototype, finding)


def _basic_evaluation(
    prototype: PrototypeManifest,
    finding: dict[str, Any],
) -> dict[str, Any]:
    """Minimal deterministic evaluation when v36 is unavailable.

    Checks that the prototype has non-empty before/after values and
    that the target matches the finding selector.
    """
    issues: list[str] = []

    if not prototype.target:
        issues.append("prototype has no target selector")

    if not prototype.after_value:
        issues.append("prototype has no after_value")

    finding_selector = finding.get("selector", "")
    if finding_selector and prototype.target != finding_selector:
        issues.append(
            f"target mismatch: prototype={prototype.target}, finding={finding_selector}"
        )

    if prototype.generated_by == "ai" and not any(
        v for v in [prototype.after_value] if v and v != "[AI-generated patch content]"
    ):
        issues.append("AI-generated prototype has no concrete output")

    passed = len(issues) == 0

    return {
        "pass": passed,
        "score": 1.0 if passed else 0.0,
        "grader": "basic-deterministic",
        "details": {
            "issues": issues,
            "patch_type": prototype.patch_type,
            "generated_by": prototype.generated_by,
        },
    }


def get_evaluation_verdict(eval_result: dict[str, Any]) -> str:
    """Convert an evaluation result dict to a simple verdict string.

    Returns one of: "PASS", "FAIL", "INCONCLUSIVE".
    """
    if eval_result.get("pass") is True:
        score = eval_result.get("score", 0.0)
        if score >= 0.8:
            return "PASS"
        return "INCONCLUSIVE"
    return "FAIL"

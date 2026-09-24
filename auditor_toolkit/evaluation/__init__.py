"""AI Evaluation Harness — deterministic evaluation of AI/browser agents.

P1-007 / v36: evaluates whether an AI agent makes correct claims, selects
valid evidence, abstains when uncertain, follows tool policies, and avoids
irreversible actions.  Results feed comparative metrics and human-gated
promotion proposals — never automatic deployment.
"""

from .schema import (
    EvalCase,
    EvalEvidenceRef,
    EvalFailure,
    EvalMetrics,
    EvalResult,
    EvalRun,
    EvalToolCall,
)

__all__ = [
    "EvalCase",
    "EvalEvidenceRef",
    "EvalFailure",
    "EvalMetrics",
    "EvalResult",
    "EvalRun",
    "EvalToolCall",
]

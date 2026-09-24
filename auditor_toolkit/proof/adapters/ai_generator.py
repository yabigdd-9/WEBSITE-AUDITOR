"""Optional AI prototype generator.

Uses the v36 evaluation harness for quality gating.  Disabled by
default — only activates when no deterministic patch is available AND
the finding confidence is >= 0.90.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from auditor_toolkit.proof.prototype import PrototypeManifest


@dataclass
class AIPrototypeConfig:
    """Configuration for the AI prototype generator."""

    enabled: bool = False
    min_confidence: float = 0.90
    model: str = ""
    api_key: str = ""


# Global config — disabled by default
_config = AIPrototypeConfig()


def configure(
    enabled: bool = False,
    min_confidence: float = 0.90,
    model: str = "",
    api_key: str = "",
) -> None:
    """Update the global AI generator configuration."""
    global _config  # noqa: PLW0602
    _config = AIPrototypeConfig(
        enabled=enabled,
        min_confidence=min_confidence,
        model=model,
        api_key=api_key,
    )


def is_available() -> bool:
    """Return True when the AI generator is enabled and configured."""
    return _config.enabled and bool(_config.api_key)


def generate_ai_prototype(
    finding: dict[str, Any],
    before_state: dict[str, Any] | None = None,
) -> PrototypeManifest | None:
    """Generate an AI-driven prototype patch for *finding*.

    Only activates when:
      - AI generator is enabled (configure(enabled=True, ...))
      - Finding confidence >= min_confidence (default 0.90)
      - No deterministic patch rule applies

    Returns None if the generator is disabled or confidence is too low.
    """
    if not is_available():
        return None

    confidence = finding.get("confidence", 0.0)
    if confidence < _config.min_confidence:
        return None

    # AI generation would go here — for now we return a placeholder
    # manifest that downstream code can recognise as AI-generated.
    import hashlib
    from datetime import datetime, timezone

    finding_id = finding.get("finding_id", "")
    claim = finding.get("claim", "")
    raw = f"ai|{finding_id}|{claim}"
    patch_id = f"patch_ai_{hashlib.sha256(raw.encode()).hexdigest()[:12]}"

    return PrototypeManifest(
        patch_id=patch_id,
        finding_id=finding_id,
        patch_type="CSS_PATCH",  # generic fallback
        target=finding.get("selector", ""),
        before_value=before_state.get("outer_html", "") if before_state else "",
        after_value="[AI-generated patch content]",
        affected_selectors=[finding.get("selector", "")],
        generated_by="ai",
        rationale="AI-generated prototype (confidence not verified).",
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def validate_with_evaluator(
    prototype: PrototypeManifest,
    finding: dict[str, Any],
) -> dict[str, Any]:
    """Run the generated prototype through the v36 evaluator.

    Returns a dict with pass/fail status and optional diagnostics.
    When the evaluator is not available, returns a neutral result.
    """
    try:
        from auditor_toolkit.proof.adapters.v36_evaluator import (
            evaluate_prototype,
        )
        result = evaluate_prototype(prototype, finding)
        return {
            "valid": result.get("pass", False),
            "evaluator": "v36",
            "details": result,
        }
    except ImportError:
        return {
            "valid": False,
            "evaluator": "unavailable",
            "details": {"reason": "v36 evaluator not installed"},
        }

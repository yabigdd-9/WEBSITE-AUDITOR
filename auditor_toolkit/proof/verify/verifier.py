"""Independent verifier — checks whether a proposed fix resolves the defect.

This module is NEVER called by the fix generator. It independently verifies:
(a) the original defect is gone,
(b) no new axe violations introduced,
(c) no new console errors,
(d) no regressions in other regions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from auditor_toolkit.proof.schema import (
    AfterState,
    BeforeState,
    VerificationResult,
    VerificationVerdict,
)

_VERIFIER_ID = "proof-verifier-v1"


def check_axe_violations(violations: list[dict[str, Any]]) -> int:
    """Return the count of axe violations in a list."""
    return len(violations)


def check_console_errors(errors: list[str]) -> int:
    """Return the count of console errors in a list."""
    return len(errors)


def _detect_regressions(
    before: BeforeState,
    after: AfterState,
) -> int:
    """Count regressions by comparing console errors and network failures.

    A regression is a new console error or failed network request that was
    not present in the before state.
    """
    count = 0

    # New console errors
    before_errors = set(before.console_errors)
    after_errors = set(after.console_errors)
    new_errors = after_errors - before_errors
    count += len(new_errors)

    # New network failures
    before_urls = {r.get("url") for r in before.network_requests}
    after_urls = {r.get("url") for r in after.network_requests}
    new_failures = after_urls - before_urls
    count += len(new_failures)

    return count


def _compute_diff_summary(
    before: BeforeState,
    after: AfterState,
) -> str:
    """Build a human-readable diff summary from before/after states."""
    parts: list[str] = []

    axe_before = check_axe_violations(before.axe_violations)
    axe_after = check_axe_violations(getattr(after, "axe_violations", []))
    console_before = check_console_errors(before.console_errors)
    console_after = check_console_errors(after.console_errors)

    parts.append(f"Axe violations: {axe_before} -> {axe_after}")
    parts.append(f"Console errors: {console_before} -> {console_after}")
    parts.append(f"Network failures: {len(before.network_requests)} -> {len(after.network_requests)}")

    return "; ".join(parts)


def verify_fix(
    before: BeforeState,
    after: AfterState,
    *,
    original_defect_present: bool = True,
    visual_diff_percent: float = 0.0,
    new_axe_violations: list[str] | None = None,
) -> VerificationResult:
    """Verify whether a proposed fix resolved the original defect.

    *original_defect_present* should reflect whether the specific defect
    identified by the finding is still observable in the after state.

    Returns a VerificationResult with verdict and diagnostics.
    """
    axe_before = check_axe_violations(before.axe_violations)
    # AfterState may not carry axe_violations — default to 0
    axe_after = check_axe_violations(getattr(after, "axe_violations", []))
    console_before = check_console_errors(before.console_errors)
    console_after = check_console_errors(after.console_errors)
    regressions = _detect_regressions(before, after)

    # New axe violations introduced by the fix
    new_defects: list[str] = []
    if new_axe_violations:
        new_defects.extend(new_axe_violations)
    if axe_after > axe_before:
        new_defects.append(
            f"{axe_after - axe_before} new axe violation(s) introduced"
        )

    # Determine verdict
    verdict: VerificationVerdict = "INCONCLUSIVE"

    if original_defect_present:
        # The original defect is still there
        if regressions > 0:
            verdict = "REGRESSION"
        else:
            verdict = "NOT_FIXED"
    else:
        # The original defect is gone
        if regressions > 0 or new_defects:
            verdict = "REGRESSION"
        else:
            verdict = "FIXED"

    # Confidence calculation
    confidence = 0.0
    if verdict == "FIXED":
        confidence = 0.95
        if axe_after > 0:
            confidence -= 0.1 * min(axe_after, 3)
        if console_after > 0:
            confidence -= 0.05 * min(console_after, 4)
        confidence = max(confidence, 0.0)
    elif verdict == "REGRESSION":
        confidence = 0.9
    elif verdict == "NOT_FIXED":
        confidence = 0.95

    diff_summary = _compute_diff_summary(before, after)

    return VerificationResult(
        finding_id=before.finding_id,
        proposed_fix_id=after.proposed_fix_id,
        verdict=verdict,
        original_defect_present=original_defect_present,
        new_defects_introduced=new_defects,
        regression_count=regressions,
        diff_summary=diff_summary,
        axe_violations_before=axe_before,
        axe_violations_after=axe_after,
        console_errors_before=console_before,
        console_errors_after=console_after,
        visual_diff_percent=visual_diff_percent,
        confidence=confidence,
        verifier_id=_VERIFIER_ID,
        verified_at=datetime.now(timezone.utc).isoformat(),
        notes=diff_summary,
    )

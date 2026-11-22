"""Assemble a ProofPackage from before, fix, after, and verification artifacts.

Validates completeness and ensures all required references are present
before marking a package as READY for human review.
"""

from __future__ import annotations

import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from auditor_toolkit.proof.schema import (
    AfterState,
    BeforeState,
    ProofPackage,
    ProposedFix,
    VerificationResult,
)

_default_output_dir = tempfile.mkdtemp(prefix="website-auditor-proof-")


def _validate_screenshot(path: str, label: str) -> str:
    """Validate that a screenshot file exists and is non-empty."""
    if not path:
        return f"{label}: screenshot path is empty"
    p = Path(path)
    if not p.exists():
        return f"{label}: file not found at {path}"
    if p.stat().st_size == 0:
        return f"{label}: file is empty at {path}"
    return ""


def build_proof_package(
    before: BeforeState,
    proposed_fix: ProposedFix,
    after: AfterState,
    verification: VerificationResult,
    diff_path: str = "",
    output_dir: str = _default_output_dir,
) -> ProofPackage:
    """Assemble a complete ProofPackage and validate its contents.

    Raises ValueError if required artifacts are missing.
    """
    errors: list[str] = []

    # Validate before state
    if before.status != "CAPTURED":
        errors.append(f"Before state status is '{before.status}', expected 'CAPTURED'")
    errors.append(_validate_screenshot(before.screenshot.path, "Before"))

    # Validate after state
    if after.status != "CAPTURED":
        errors.append(f"After state status is '{after.status}', expected 'CAPTURED'")
    errors.append(_validate_screenshot(after.screenshot.path, "After"))

    # Validate fix
    if not proposed_fix.fix_type:
        errors.append("Proposed fix type is empty")
    if not proposed_fix.finding_id:
        errors.append("Proposed fix finding_id is empty")

    # Validate verification
    if not verification.verifier_id:
        errors.append("Verification result has no verifier_id")

    # Validate diff if provided
    if diff_path:
        errors.append(_validate_screenshot(diff_path, "Diff"))

    if errors:
        actual_errors = [e for e in errors if e]
        if actual_errors:
            raise ValueError(
                "Proof package validation failed:\n" + "\n".join(actual_errors)
            )

    package_id = f"pkg_{uuid.uuid4().hex[:8]}"

    package = ProofPackage(
        package_id=package_id,
        finding_id=before.finding_id,
        url=before.url,
        before=before,
        proposed_fix=proposed_fix,
        after=after,
        verification=verification,
        before_screenshot_path=before.screenshot.path,
        after_screenshot_path=after.screenshot.path,
        diff_path=diff_path,
        status="READY",
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    return package

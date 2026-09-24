"""Verify sub-package with lazy browser-only issue-region extraction."""

from __future__ import annotations

from typing import Any

from .verifier import check_axe_violations, check_console_errors, verify_fix


def extract_issue_region(*args: Any, **kwargs: Any) -> Any:
    """Lazy-load Playwright only when live issue-region extraction is requested."""
    from .finder import extract_issue_region as _extract_issue_region

    return _extract_issue_region(*args, **kwargs)


__all__ = [
    "extract_issue_region",
    "verify_fix",
    "check_axe_violations",
    "check_console_errors",
]

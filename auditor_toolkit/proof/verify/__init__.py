"""Verify sub-package — issue region extraction and independent fix verification."""

from .finder import extract_issue_region
from .verifier import check_axe_violations, check_console_errors, verify_fix

__all__ = [
    "extract_issue_region",
    "verify_fix",
    "check_axe_violations",
    "check_console_errors",
]

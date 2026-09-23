"""
Third-party request inventory.
"""
from __future__ import annotations

from typing import List, Any

from auditor_toolkit.checks import Finding


def analyse_html(html: str, url: str, headers: dict) -> tuple[List[Finding], dict[str, Any]]:
    """Analyse HTML for third-party request findings."""
    findings = []
    # TODO: Implement third-party request inventory
    return findings, {}


"""
Browser console error collection.
"""
from __future__ import annotations

from typing import List, Any

from auditor_toolkit.checks import Finding


def analyse_html(html: str, url: str, headers: dict) -> tuple[List[Finding], dict[str, Any]]:
    """Analyse HTML for browser console findings."""
    findings = []
    # TODO: Implement browser console error collection
    return findings, {}


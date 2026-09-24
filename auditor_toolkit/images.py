"""
Image optimization analysis.
"""
from __future__ import annotations

from typing import Any, List

from auditor_toolkit.checks import Finding


def analyse_html(html: str, url: str, headers: dict) -> tuple[List[Finding], dict[str, Any]]:
    """Analyse HTML for image optimization findings."""
    findings = []
    # TODO: Implement image optimization analysis
    return findings, {}

"""Stub for cookie_consent check."""

from __future__ import annotations

from typing import Any, List, Tuple

from .checks import Finding


def analyse_html(html: str, url: str, headers: dict) -> Tuple[List[Finding], dict]:
    return [], {}

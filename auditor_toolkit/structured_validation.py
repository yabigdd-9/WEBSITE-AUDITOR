"""
Structured data validation.
"""
from __future__ import annotations

import json
from typing import Any, List

from bs4 import BeautifulSoup

from auditor_toolkit.checks import Finding


def analyse_html(html: str, url: str, headers: dict) -> tuple[List[Finding], dict[str, Any]]:
    """Analyse HTML for structured data validation findings."""
    findings = []
    soup = BeautifulSoup(html, "html.parser")
    scripts = soup.find_all("script", type="application/ld+json")
    for script in scripts:
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
            if isinstance(data, dict):
                if "@type" not in data:
                    findings.append(Finding(defect_key="structured_data_missing_type"))
            elif isinstance(data, list):
                for i, item in enumerate(data):
                    if not isinstance(item, dict) or "@type" not in item:
                        findings.append(
                            Finding(defect_key=f"structured_data_item_missing_type_{i}")
                        )
            else:
                findings.append(Finding(defect_key="structured_data_not_dict_or_list"))
        except json.JSONDecodeError:
            findings.append(Finding(defect_key="structured_data_invalid_json"))
    return findings, {"structured_data_scripts_found": len(scripts)}

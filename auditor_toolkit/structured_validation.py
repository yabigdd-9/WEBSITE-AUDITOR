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
            findings.extend(_validate_structured_data(data, url))
        except json.JSONDecodeError:
            findings.append(
                _finding(
                    "structured_data_invalid_json",
                    "Invalid JSON-LD syntax",
                    url,
                    "JSON-LD script content could not be parsed as JSON",
                )
            )
    return findings, {"structured_data_scripts_found": len(scripts)}


def _validate_structured_data(data: Any, url: str) -> list[Finding]:
    if isinstance(data, dict):
        if "@type" not in data:
            return [
                _finding(
                    "structured_data_missing_type",
                    "JSON-LD entity is missing @type",
                    url,
                    "JSON-LD object has no @type property",
                )
            ]
        return []
    if isinstance(data, list):
        return [
            _finding(
                f"structured_data_item_missing_type_{index}",
                "JSON-LD list item is missing @type",
                url,
                f"JSON-LD list item at index {index} is not an object with @type",
            )
            for index, item in enumerate(data)
            if not isinstance(item, dict) or "@type" not in item
        ]
    return [
        _finding(
            "structured_data_not_dict_or_list",
            "JSON-LD value has an unsupported top-level type",
            url,
            f"Parsed JSON-LD value has type {type(data).__name__}",
        )
    ]


def _finding(defect_key: str, defect: str, url: str, observed: str) -> Finding:
    return Finding(
        defect_key=defect_key,
        defect=defect,
        impact="Search engines may ignore or misinterpret the structured data.",
        source_url=url,
        check="structured_data",
        evidence_source="dom:script[type='application/ld+json']",
        observed=observed,
        business_impact="Invalid structured data can prevent enhanced search results.",
        remediation_action="Correct the JSON-LD syntax and provide a valid entity @type.",
    )

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
        # W3C JSON-LD 1.1 section 4.9 permits @context + @graph without
        # an entity @type on the container. Inspect graph nodes instead.
        if "@graph" in data:
            graph = data["@graph"]
            if isinstance(graph, (dict, list)):
                return _validate_structured_data(graph, url)
            return [_finding(
                "structured_data_invalid_graph_shape",
                "JSON-LD graph has an unsupported value shape",
                url,
                "@graph is not an object or array",
            )]
        if "@value" in data or set(data).issubset({"@context", "@id"}):
            return []
        if "@type" not in data:
            return [
                _finding(
                    "structured_data_missing_type",
                    "No explicit entity type observed; review intended schema use",
                    url,
                    "JSON-LD object has no @type property",
                    confidence="heuristic",
                )
            ]
        return []
    if isinstance(data, list):
        findings = []
        for index, item in enumerate(data):
            if isinstance(item, dict):
                findings.extend(_validate_structured_data(item, url))
            else:
                findings.append(_finding(
                    f"structured_data_item_missing_type_{index}",
                    "JSON-LD list item is not a node object",
                    url,
                    f"JSON-LD list item at index {index} is not an object",
                ))
        return findings
    return [
        _finding(
            "structured_data_not_dict_or_list",
            "JSON-LD value has an unsupported top-level type",
            url,
            f"Parsed JSON-LD value has type {type(data).__name__}",
        )
    ]


def _finding(defect_key: str, defect: str, url: str, observed: str, *, confidence="observed") -> Finding:
    return Finding(
        defect_key=defect_key,
        defect=defect,
        impact="Review intended structured-data use; rich-result eligibility is not assessed.",
        source_url=url,
        check="structured_data",
        confidence=confidence,
        evidence_source="dom:script[type='application/ld+json']",
        observed=observed,
        business_impact=("Confirm intended schema use before treating an untyped node as a defect."
                         if confidence == "heuristic" else "Invalid syntax can prevent structured data being parsed."),
        remediation_action=("Review the intended entity and schema requirements before adding a type."
                            if confidence == "heuristic" else "Correct the JSON-LD syntax or graph shape."),
    )

"""Evidence-bound website fault intelligence.

The helpers here are deterministic and local. They group correlated symptoms
without pretending that a likely cause is a proven cause.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

TAXONOMY = {
    "availability": {"fetch", "tls", "dns", "server_error", "client_error", "soft_404"},
    "browser_runtime": {"browser", "console_error", "failed_request", "javascript_error"},
    "visual_layout": {"visual_overflow", "visual_overlap", "visual_clipping", "responsive_layout"},
    "accessibility": {"axe", "image-alt", "missing_label", "keyboard_focus", "contrast"},
    "conversion": {"ux", "form", "cta", "contact_method", "booking_flow", "quote_flow"},
    "security_trust": {"headers", "mixed_content", "tls", "security"},
    "seo_content": {"page", "schema", "hygiene", "links", "metadata"},
}

SEVERITY_IMPACT = {
    "browser_runtime": 0.8,
    "availability": 1.0,
    "visual_layout": 0.3,
    "accessibility": 0.4,
    "conversion": 0.9,
    "security_trust": 0.7,
    "seo_content": 0.5,
}

def get_severity(taxonomy: str) -> float:
    return SEVERITY_IMPACT.get(taxonomy, 0.5)


def category(defect: dict[str, Any]) -> str:
    check = str(defect.get("check") or defect.get("defect_key") or "").lower()
    for name, keys in TAXONOMY.items():
        if check in keys or any(check.startswith(key + "_") for key in keys):
            return name
    return "unknown"


def confidence(defect: dict[str, Any]) -> dict[str, Any]:
    label = defect.get("confidence") or "unknown"
    observed = bool(defect.get("observed") or defect.get("evidence_summary") or defect.get("selector"))
    reproducible = bool(defect.get("reproducibility", observed))
    if label == "heuristic":
        # An explicit heuristic label must never masquerade as observed fact,
        # even when some evidence summary happens to exist.
        level = "WEAK"
    elif label == "observed" and observed and reproducible:
        level = "PROVEN"
    elif observed and reproducible:
        level = "STRONG"
    elif observed:
        level = "MODERATE"
    else:
        level = "UNKNOWN"
    return {"class": level, "observed": observed, "reproducible": reproducible}


def fault_key(defect: dict[str, Any]) -> str:
    return str(defect.get("defect_key") or defect.get("check") or "unknown")


def group_root_causes(defects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for defect in defects:
        taxonomy = category(defect)
        groups[ROOT_CAUSES.get(taxonomy, "unclassified_observation")].append(defect)
    result = []
    for root, members in sorted(groups.items()):
        ids = [str(member.get("finding_id") or fault_key(member)) for member in members]
        categories = sorted({category(member) for member in members})
        # Calculate composite severity for the group
        severities = [get_severity(cat) for cat in categories]
        composite_severity = max(severities) if severities else 0.5
        # Calculate weighted confidence
        confidences = [confidence(member)["class"] for member in members]
        conf_levels = {"PROVEN": 4, "STRONG": 3, "MODERATE": 2, "WEAK": 1, "UNKNOWN": 0}
        avg_conf = sum(conf_levels.get(c, 0) for c in confidences) / len(confidences) if confidences else 0
        if avg_conf >= 3.5:
            group_conf = "PROVEN"
        elif avg_conf >= 2.5:
            group_conf = "STRONG"
        elif avg_conf >= 1.5:
            group_conf = "MODERATE"
        elif avg_conf >= 0.5:
            group_conf = "WEAK"
        else:
            group_conf = "UNKNOWN"
        result.append({
            "root_cause_id": root,
            "taxonomy": categories,
            "finding_ids": ids,
            "symptom_count": len(members),
            "composite_severity": round(composite_severity, 2),
            "severity_label": _severity_label(composite_severity),
            "likely": len(members) > 1,
            "confidence": group_conf,
            "explanation": "Correlated symptoms suggest one root cause; verify before claiming causation.",
        })
    return result


def _severity_label(score: float) -> str:
    if score >= 0.8:
        return "CRITICAL"
    elif score >= 0.6:
        return "HIGH"
    elif score >= 0.4:
        return "MEDIUM"
    elif score >= 0.2:
        return "LOW"
    return "NEGLIGIBLE"


def regression(current: list[dict[str, Any]], previous: list[dict[str, Any]]) -> dict[str, list[str]]:
    def identity(item):
        return item.get("finding_id") or hashlib.sha256(
            (str(item.get("defect_key")) + "|" + str(item.get("source_url")) + "|" + str(item.get("selector"))).encode()
        ).hexdigest()[:16]
    now = {identity(item) for item in current}
    old = {identity(item) for item in previous}
    return {"new": sorted(now - old), "resolved": sorted(old - now), "unchanged": sorted(now & old)}


def enrich(defect: dict[str, Any]) -> dict[str, Any]:
    output = dict(defect)
    output["fault_taxonomy"] = category(output)
    output["confidence_assessment"] = confidence(output)
    output["reproducibility"] = bool(output.get("reproducibility", output.get("evidence_summary") or output.get("selector")))
    output["root_cause_candidate"] = ROOT_CAUSES.get(output["fault_taxonomy"], "unclassified_observation")
    return output

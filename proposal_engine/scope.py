"""
Scope mapping for the WEBSITE-AUDITOR proposal engine.
"""

from typing import List, Dict, Any
from .schema import ScopeItem


def map_finding_to_scope(finding: Dict[str, Any]) -> ScopeItem:
    """
    Map a single audit finding to a scope item.
    This is a placeholder implementation. In reality, this would use
    rules based on finding type, severity, URLs, etc.
    """
    # Extract relevant information from the finding
    # We assume the finding has at least: id, title, description, URLs, etc.
    scope_id = f"scope-{finding.get('id', 'unknown')}"
    title = finding.get("title", "Untitled Scope Item")
    problem = finding.get("description", "No description provided")
    evidence = finding.get("evidence", "See audit report")
    affected_urls = finding.get("urls", [])
    root_cause = finding.get("root_cause", "To be determined")
    proposed_work = finding.get("recommended_action", "To be determined")
    deliverables = finding.get("deliverables", [])
    verification = finding.get("verification_method", "Manual review")
    effort_band = finding.get("effort_band", "UNKNOWN")  # Should be XS, S, M, L, XL
    dependencies = finding.get("dependencies", [])
    risk = finding.get("risk", "LOW")
    finding_ids = [finding.get("id")] if finding.get("id") else []

    return ScopeItem(
        scope_id=scope_id,
        title=title,
        problem=problem,
        evidence=evidence,
        affected_urls=affected_urls,
        root_cause=root_cause,
        proposed_work=proposed_work,
        deliverables=deliverables,
        verification=verification,
        effort_band=effort_band,
        dependencies=dependencies,
        risk=risk,
        finding_ids=finding_ids,
    )


def map_findings_to_scope(findings: List[Dict[str, Any]]) -> List[ScopeItem]:
    """
    Map a list of findings to a list of scope items.
    """
    return [map_finding_to_scope(f) for f in findings]


def deduplicate_scope_items(scope_items: List[ScopeItem]) -> List[ScopeItem]:
    """
    Remove duplicate scope items based on scope_id or title.
    Keeps the first occurrence.
    """
    seen = set()
    unique_items = []
    for item in scope_items:
        # Use scope_id if available, otherwise title
        key = item.scope_id if item.scope_id else item.title
        if key not in seen:
            seen.add(key)
            unique_items.append(item)
    return unique_items

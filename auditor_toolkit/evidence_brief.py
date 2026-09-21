"""Structured evidence brief generation for drafting workflows.

This module creates a standardized, structured summary of audit evidence
that can be shared between different drafting workflows (AI-generated,
human-written, template-based) to improve the quality and effectiveness
of generated content.
"""

from typing import Dict, List, Any
from datetime import datetime, timezone


def create_evidence_brief(audit_report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a structured evidence brief from an audit report.

    Args:
        audit_report: The complete audit report from the Website Auditor

    Returns:
        A structured evidence brief suitable for use in drafting workflows
    """
    if not audit_report or audit_report.get("status") != "complete":
        return _create_empty_evidence_brief()

    defects = audit_report.get("defects", [])
    if not defects:
        return _create_empty_evidence_brief()

    # Group defects by severity for easier consumption
    defects_by_severity = {"critical": [], "high": [], "medium": [], "low": []}
    for defect in defects:
        severity = defect.get("severity", "low").lower()
        if severity in defects_by_severity:
            defects_by_severity[severity].append(defect)

    # Calculate key metrics
    total_defects = len(defects)
    critical_count = len(defects_by_severity["critical"])
    high_count = len(defects_by_severity["high"])
    medium_count = len(defects_by_severity["medium"])
    low_count = len(defects_by_severity["low"])

    # Generate evidence summary
    evidence_summary = _generate_evidence_summary(defects_by_severity)

    # Generate priority recommendations
    priority_recommendations = _generate_priority_recommendations(defects_by_severity)

    # Generate business impact assessment
    business_impact = _assess_business_impact(critical_count, high_count, total_defects)

    # Create the evidence brief
    evidence_brief = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_audit_id": audit_report.get("run_id"),
            "source_url": audit_report.get("url"),
            "source_domain": audit_report.get("domain"),
            "audit_timestamp": audit_report.get("timestamp"),
            "health_score": audit_report.get("health_score"),
            "total_defects": total_defects,
        },
        "summary": {
            "overall_assessment": _get_overall_assessment(
                audit_report.get("health_score", 0)
            ),
            "primary_concerns": _get_primary_concerns(defects_by_severity),
            "quick_wins": _get_quick_wins(defects_by_severity),
        },
        "evidence": {
            "by_severity": defects_by_severity,
            "key_findings": _extract_key_findings(defects),
            "evidence_samples": _collect_evidence_samples(defects_by_severity),
        },
        "recommendations": {
            "priority_actions": priority_recommendations,
            "quick_wins": _get_quick_wins_actions(defects_by_severity),
            "strategic_improvements": _get_strategic_improvements(defects_by_severity),
        },
        "business_impact": business_impact,
        "talking_points": {
            "opening_hook": _generate_opening_hook(
                audit_report.get("domain", ""), critical_count, high_count
            ),
            "closing_points": _generate_closing_points(
                audit_report.get("domain", ""), critical_count, high_count
            ),
            "evidence_phrases": _generate_evidence_phrases(defects_by_severity),
        },
    }

    return evidence_brief


def _create_empty_evidence_brief() -> Dict[str, Any]:
    """Create an empty evidence brief for error cases."""
    return {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "error": "No valid audit data available",
        },
        "summary": {
            "overall_assessment": "Unable to assess - no audit data",
            "primary_concerns": [],
            "quick_wins": [],
        },
        "evidence": {
            "by_severity": {"critical": [], "high": [], "medium": [], "low": []},
            "key_findings": [],
            "evidence_samples": [],
        },
        "recommendations": {
            "priority_actions": [],
            "quick_wins": [],
            "strategic_improvements": [],
        },
        "business_impact": {
            "level": "unknown",
            "description": "Unable to assess business impact",
        },
        "talking_points": {
            "opening_hook": "I noticed some issues with your website that could be affecting your online presence.",
            "closing_points": "Addressing these issues could help improve your website's effectiveness.",
            "evidence_phrases": [],
        },
    }


def _get_overall_assessment(health_score: int) -> str:
    """Convert health score to overall assessment."""
    if health_score >= 90:
        return "Excellent website with minor opportunities for improvement"
    elif health_score >= 80:
        return "Good website with some areas needing attention"
    elif health_score >= 70:
        return "Fair website requiring several improvements"
    elif health_score >= 60:
        return "Poor website with significant issues needing correction"
    else:
        return "Critical website requiring immediate attention"


def _get_primary_concerns(defects_by_severity: Dict[str, List]) -> List[str]:
    """Extract primary concerns from defects."""
    concerns = []
    if defects_by_severity["critical"]:
        concerns.append(
            f"{len(defects_by_severity['critical'])} critical issues requiring immediate attention"
        )
    if defects_by_severity["high"]:
        concerns.append(
            f"{len(defects_by_severity['high'])} high-priority issues impacting user experience"
        )
    if len(defects_by_severity["medium"]) > 5:
        concerns.append(
            f"{len(defects_by_severity['medium'])} medium-priority issues affecting overall quality"
        )
    return concerns[:3]  # Top 3 concerns


def _get_quick_wins(defects_by_severity: Dict[str, List]) -> List[str]:
    """Identify quick win opportunities."""
    quick_wins = []

    # Easy fixes with high impact
    easy_fixes = ["no_mobile_viewport", "no_title", "weak_title", "no_meta_description"]
    for severity in ["critical", "high", "medium"]:
        for defect in defects_by_severity[severity]:
            if defect.get("check") in easy_fixes:
                quick_wins.append(f"Fix {defect.get('check')} - {defect.get('finding')}")
                if len(quick_wins) >= 3:
                    return quick_wins

    # If we don't have enough quick wins from specific checks, add general ones
    if len(quick_wins) < 3:
        if defects_by_severity["medium"]:
            quick_wins.append(
                f"Address {len(defects_by_severity['medium'])} medium-priority items for quick impact"
            )
    if len(quick_wins) < 3 and defects_by_severity["low"]:
        quick_wins.append(
            f"Fix {min(5, len(defects_by_severity['low']))} low-priority issues for immediate improvement"
        )

    return quick_wins[:3]


def _generate_evidence_summary(defects_by_severity: Dict[str, List]) -> str:
    """Generate a text summary of the evidence."""
    parts = []
    total = sum(len(v) for v in defects_by_severity.values())

    if total == 0:
        return "No defects identified"

    if defects_by_severity["critical"]:
        parts.append(
            f"{len(defects_by_severity['critical'])} critical issue(s) requiring immediate attention"
        )
    if defects_by_severity["high"]:
        parts.append(
            f"{len(defects_by_severity['high'])} high-priority issue(s) impacting user experience"
        )
    if defects_by_severity["medium"]:
        parts.append(
            f"{len(defects_by_severity['medium'])} medium-priority issue(s) affecting quality"
        )
    if defects_by_severity["low"]:
        parts.append(
            f"{len(defects_by_severity['low'])} low-priority issue(s) for incremental improvement"
        )

    return ". ".join(parts) + "."


def _extract_key_findings(defects: List[Dict]) -> List[Dict[str, Any]]:
    """Extract the most significant defects as key findings."""
    # Sort by severity weight and take top 5
    severity_weights = {"critical": 4, "high": 3, "medium": 2, "low": 1}

    def get_weight(defect):
        return severity_weights.get(defect.get("severity", "low").lower(), 1)

    sorted_defects = sorted(defects, key=get_weight, reverse=True)
    top_defects = sorted_defects[:5]

    key_findings = []
    for defect in top_defects:
        key_findings.append(
            {
                "id": defect.get("finding_id"),
                "check": defect.get("check"),
                "severity": defect.get("severity"),
                "finding": defect.get("finding"),
                "evidence": defect.get("evidence"),
                "impact": _describe_impact(defect.get("check"), defect.get("severity")),
            }
        )

    return key_findings


def _collect_evidence_samples(
    defects_by_severity: Dict[str, List]
) -> List[Dict[str, Any]]:
    """Collect concrete evidence samples for each severity level."""
    samples = []

    for severity in ["critical", "high", "medium"]:
        defects = defects_by_severity[severity]
        if defects:
            # Take up to 2 examples from each severity level
            for defect in defects[:2]:
                samples.append(
                    {
                        "severity": severity,
                        "check": defect.get("check"),
                        "finding": defect.get("finding"),
                        "evidence": defect.get("evidence", "See website audit"),
                        "selector": defect.get("selector", ""),
                    }
                )

    return samples[:6]  # Limit total samples


def _describe_impact(check: str, severity: str) -> str:
    """Describe the business impact of a defect."""
    impact_map = {
        "no_mobile_viewport": "Poor mobile experience leading to lost mobile traffic and conversions",
        "weak_title": "Weak search engine visibility and lower click-through rates",
        "no_title": "Missing search engine listing and poor user orientation",
        "no_meta_description": "Poor search result snippets and lower click-through rates",
        "ssl_expired": "Security warnings destroying visitor trust and causing immediate bounce",
        "ssl_expiring_soon": "Upcoming security warnings that will disrupt user trust",
        "slow_response": "Frustrated users abandoning site due to poor performance",
        "broken_links": "Poor user experience and damaged SEO from dead ends",
        "no_contact_method": "Lost business opportunities from inability to contact",
        "no_form": "Lost lead generation opportunities",
    }

    base_impact = impact_map.get(
        check, f"{severity.upper()} priority issue requiring attention"
    )

    if severity == "critical":
        return f"URGENT: {base_impact}"
    elif severity == "high":
        return f"HIGH IMPACT: {base_impact}"
    elif severity == "medium":
        return f"MODERATE IMPACT: {base_impact}"
    else:
        return f"LOW IMPACT: {base_impact}"


def _generate_priority_recommendations(
    defects_by_severity: Dict[str, List]
) -> List[Dict[str, Any]]:
    """Generate priority recommendations based on defect patterns."""
    recommendations = []

    # Critical issues get immediate attention
    if defects_by_severity["critical"]:
        rec = {
            "priority": "IMMEDIATE",
            "timeline": "Within 24-48 hours",
            "action": "Address critical security and accessibility issues",
            "details": f"Fix {len(defects_by_severity['critical'])} critical issue(s) including:",
            "examples": [
                d.get("finding") for d in defects_by_severity["critical"][:2]
            ],
        }
        recommendations.append(rec)

    # High impact issues for short-term
    if defects_by_severity["high"]:
        rec = {
            "priority": "HIGH",
            "timeline": "Within 1-2 weeks",
            "action": "Fix high-priority usability and performance issues",
            "details": f"Address {len(defects_by_severity['high'])} high-priority issue(s) including:",
            "examples": [
                d.get("finding") for d in defects_by_severity["high"][:2]
            ],
        }
        recommendations.append(rec)

    # Medium issues for ongoing improvement
    if len(defects_by_severity["medium"]) > 3:
        rec = {
            "priority": "MEDIUM",
            "timeline": "Within 1 month",
            "action": "Implement ongoing quality improvements",
            "details": f"Address {len(defects_by_severity['medium'])} medium-priority issue(s)",
            "examples": [
                d.get("finding") for d in defects_by_severity["medium"][:2]
            ],
        }
        recommendations.append(rec)

    return recommendations


def _get_quick_wins_actions(defects_by_severity: Dict[str, List]) -> List[str]:
    """Get actionable quick wins."""
    actions = []

    # Specific easy fixes
    if any(
        d.get("check") == "no_mobile_viewport"
        for d in defects_by_severity.get("critical", [])
        + defects_by_severity.get("high", [])
        + defects_by_severity.get("medium", [])
    ):
        actions.append("Add mobile viewport meta tag")

    if any(
        d.get("check") == "no_title"
        for d in defects_by_severity.get("critical", [])
        + defects_by_severity.get("high", [])
        + defects_by_severity.get("medium", [])
    ):
        actions.Add("Add descriptive title tag")

    if any(
        d.get("check") == "no_meta_description"
        for d in defects_by_severity.get("critical", [])
        + defects_by_severity.get("high", [])
        + defects_by_severity.get("medium", [])
    ):
        actions.append("Add meta description tag")

    # Generic actions if we don't have specific ones
    if not actions:
        if defects_by_severity["high"]:
            actions.append("Fix top 3 high-priority issues identified in audit")
        if defects_by_severity["medium"] and len(actions) < 2:
            actions.append("Address 5 medium-priority items for quick improvement")

    return actions[:3]


def _get_strategic_improvements(defects_by_severity: Dict[str, List]) -> List[str]:
    """Get strategic, longer-term improvements."""
    improvements = []

    # Pattern-based strategic recommendations
    has_multiple_issues = sum(
        len(v) for v in defects_by_severity.values()
    ) > 10

    if has_multiple_issues:
        improvements.append(
            "Implement comprehensive website quality management program"
        )

    if defects_by_severity["critical"]:
        improvements.append(
            "Establish monthly security and compliance audit schedule"
        )

    total_defects = sum(len(v) for v in defects_by_severity.values())
    if total_defects > 15:
        improvements.append(
            "Consider website rebuild or major redesign for fundamental issues"
        )
    elif total_defects > 8:
        improvements.append(
            "Plan staged improvement approach over next quarter"
        )

    # Default recommendations
    if not improvements:
        improvements.append(
            "Implement quarterly website audits to maintain quality"
        )
        improvements.append(
            "Establish website maintenance and monitoring procedures"
        )

    return improvements[:3]


def _assess_business_impact(
    critical_count: int, high_count: int, total_defects: int
) -> Dict[str, str]:
    """Assess potential business impact of the defects."""
    # Simple scoring model
    impact_score = (critical_count * 3) + (high_count * 2) + (total_defects * 0.5)

    if impact_score >= 50:
        level = "SEVERE"
        description = (
            "Significant business impact likely - lost conversions, damaged reputation, "
            "and poor search visibility"
        )
    elif impact_score >= 25:
        level = "MODERATE"
        description = (
            "Moderate business impact - noticeable user experience issues "
            "affecting engagement and conversion rates"
        )
    elif impact_score >= 10:
        level = "LOW-MODERATE"
        description = (
            "Some business impact - minor issues that may frustrate users "
            "and slightly reduce effectiveness"
        )
    else:
        level = "MINIMAL"
        description = (
            "Minimal business impact - primarily cosmetic or technical issues "
            "with limited effect on business outcomes"
        )

    return {"level": level, "description": description}


def _generate_opening_hook(
    domain: str, critical_count: int, high_count: int
) -> str:
    """Generate an opening hook for outreach."""
    if critical_count > 0:
        return f"I noticed critical issues on {domain}'s website that could be costing you business."
    elif high_count > 0:
        return f"I found several important issues on {domain}'s website that could be improved."
    elif domain:
        return f"I reviewed {domain}'s website and identified some opportunities for enhancement."
    else:
        return "I noticed some issues with your website that could be affecting your online presence."


def _generate_closing_points(
    domain: str, critical_count: int, high_count: int
) -> List[str]:
    """Generate closing points for outreach."""
    points = []

    if critical_count > 0:
        points.append(
            f"Addressing the {critical_count} critical issue(s) should be your top priority"
        )
    if high_count > 0:
        points.append(
            f"Fixing the {high_count} high-priority issue(s) would significantly improve user experience"
        )
    if not points:
        points.append(
            "Making the recommended improvements will enhance your website's effectiveness"
        )

    points.append(
        "These changes are straightforward to implement and will provide measurable benefits"
    )

    return points


def _generate_evidence_phrases(
    defects_by_severity: Dict[str, List]
) -> List[str]:
    """Generate evidence-based phrases for use in drafts."""
    phrases = []

    # Add specific evidence from defects
    for severity in ["critical", "high"]:
        for defect in defects_by_severity[severity][:2]:  # Top 2 from each
            finding = defect.get("finding", "")
            evidence = defect.get("evidence", "")
            if finding and evidence:
                phrases.append(f"Specifically, I noticed {finding.lower()} - {evidence}")

    # Add general evidence phrases
    if defects_by_severity["critical"]:
        phrases.append(
            "During my review, I found critical issues that require immediate attention"
        )
    if defects_by_severity["high"]:
        phrases.append(
            "Several high-priority issues were identified that impact user experience"
        )
    if sum(len(v) for v in defects_by_severity.values()) > 5:
        phrases.append(
            "The audit revealed multiple opportunities for improvement across different areas"
        )

    # Ensure we have some phrases
    if not phrases:
        phrases.append("I conducted a thorough review of your website's current state")

    return phrases[:5]


if __name__ == "__main__":
    # Simple test
    sample_report = {
        "status": "complete",
        "run_id": "test_001",
        "url": "https://example.com",
        "domain": "example.com",
        "timestamp": "2026-09-22T10:00:00Z",
        "health_score": 65,
        "defects": [
            {
                "finding_id": "finding_001",
                "check": "no_mobile_viewport",
                "severity": "critical",
                "finding": "No mobile viewport tag",
                "evidence": "missing viewport meta tag",
                "selector": "head",
            },
            {
                "finding_id": "finding_002",
                "check": "ssl_expired",
                "severity": "critical",
                "finding": "SSL certificate expired",
                "evidence": "Certificate expired 15 days ago",
                "selector": "",
            },
            {
                "finding_id": "finding_003",
                "check": "weak_title",
                "severity": "medium",
                "finding": "Title is only 12 characters",
                "evidence": "title='Home Page'",
                "selector": "title",
            },
        ],
    }

    brief = create_evidence_brief(sample_report)
    print("Evidence Brief Generated:")
    print(f"Health Score: {brief['metadata']['health_score']}")
    print(f"Total Defects: {brief['metadata']['total_defects']}")
    print(f"Overall Assessment: {brief['summary']['overall_assessment']}")
    print(f"Primary Concerns: {brief['summary']['primary_concerns']}")
    print(f"Business Impact: {brief['business_impact']['level']}")
    print(f"Opening Hook: {brief['talking_points']['opening_hook']}")
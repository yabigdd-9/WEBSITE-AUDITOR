"""Legacy issue-list adapter to canonical static UX evidence."""

from dataclasses import asdict


def scan_dark_patterns(html_content, url=""):
    from auditor_toolkit.ux_static import analyse_html

    findings, _ = analyse_html(html_content, url)
    names = {"consent_prechecked": "Pre-ticked Consent", "confirmshaming_review": "Confirmshaming"}
    return [
        {
            "type": names[finding.defect_key],
            "severity": finding.severity.title(),
            "description": finding.defect + ": " + finding.observed,
            "finding": asdict(finding),
            "method": "static-ux-choice-evidence-v2",
            "consent_behaviour_verified": False,
            "legal_compliance_assessed": False,
        }
        for finding in findings
    ]

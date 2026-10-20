"""Compatibility adapter to canonical image markup evidence; no separate score."""

from dataclasses import asdict


def audit_image_performance(html_content, url=""):
    from auditor_toolkit.images import analyse_html

    findings, evidence = analyse_html(html_content, url, {})
    return {
        **evidence,
        "findings": [asdict(finding) for finding in findings],
        "legacy_compatibility": {
            "format_version": 2,
            "retired_fields": [
                "score",
                "optimization_score",
                "missing_lazy_load",
                "missing_responsive_srcset",
                "legacy_formats_count",
            ],
            "reason": "Old arithmetic and missing-lazy counts did not measure performance or establish defects.",
        },
    }

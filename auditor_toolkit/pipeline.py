from __future__ import annotations

from .browser import export_pdf, run_browser_checks
from .checks import analyse_html, classify_response, dedupe_findings, score_findings
from .common import Fetcher, atomic_write_json, atomic_write_text, validate_url
from .external_tools import run_lighthouse, run_lychee
from .faults import enrich as enrich_fault
from .faults import group_root_causes
from .faults import regression as fault_regression
from .hygiene import (
    check_mixed_content,
    check_robots,
    check_sitemap,
    detect_conversion_signals,
    discover_internal_links,
    grade_security_headers,
    validate_links,
)
from .network import crawl, inspect_dns, inspect_headers, inspect_schema, inspect_tls
from .pipeline_stages import AuditOptions, run_audit_staged
from .storage import History, finding_id

__all__ = [
    "AuditOptions",
    "run_audit",
    "run_browser_checks",
    "export_pdf",
    "analyse_html",
    "classify_response",
    "dedupe_findings",
    "score_findings",
    "Fetcher",
    "atomic_write_json",
    "atomic_write_text",
    "validate_url",
    "run_lighthouse",
    "run_lychee",
    "enrich_fault",
    "group_root_causes",
    "fault_regression",
    "check_mixed_content",
    "check_robots",
    "check_sitemap",
    "detect_conversion_signals",
    "discover_internal_links",
    "grade_security_headers",
    "validate_links",
    "crawl",
    "inspect_dns",
    "inspect_headers",
    "inspect_schema",
    "inspect_tls",
    "History",
    "finding_id",
]


def run_audit(url: str, options: AuditOptions | None = None, fetcher: "Fetcher | None" = None) -> dict:
    """Run a complete website audit using the staged pipeline.

    This is a wrapper around the new staged pipeline implementation.
    See pipeline_stages.run_audit_staged for the full implementation.
    """
    return run_audit_staged(url, options, fetcher)

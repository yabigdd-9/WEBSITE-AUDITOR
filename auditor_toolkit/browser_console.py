"""
Browser console error collection.

Static analysis of inline scripts and known anti-patterns that typically
produce browser console errors. Live console capture requires a browser
session and is handled by the browser checks pipeline.
"""
from __future__ import annotations

import re
from typing import Any

from auditor_toolkit.checks import Finding


def analyse_html(html: str, url: str, headers: dict) -> tuple[list[Finding], dict[str, Any]]:
    """Analyse HTML for browser console findings."""
    findings: list[Finding] = []
    evidence: dict[str, Any] = {"url": url, "patterns": {}}

    # Detect inline scripts that reference undefined globals
    inline_scripts = re.findall(
        r"<script(?![^>]*\bsrc\b)[^>]*>(.*?)</script>", html, re.DOTALL | re.IGNORECASE
    )
    evidence["inline_script_count"] = len(inline_scripts)

    # Check for document.write (deprecates, can block parsing)
    script_source = "\n".join(inline_scripts)
    if re.search(r"document\.write\s*\(", script_source):
        findings.append(
            Finding(
                "console-document-write",
                "document.write() usage detected",
                "document.write() can block parsing and is deprecated",
                "medium",
                url,
                check="browser_console",
                evidence_source="dom:inline script",
                observed="document.write() call found in page source",
                business_impact="document.write() delays parsing, is deprecated, and "
                "does not work asynchronously. It can cause content to be truncated or lost.",
                remediation_action="Replace document.write() with DOM manipulation "
                "methods like createElement and appendChild.",
                remediation_automation="AUTO_PREVIEW",
                effort_band="M",
            )
        )
        evidence["patterns"]["document_write"] = True

    # Check for http:// resources on https:// pages (mixed content warnings)
    if url.startswith("https://"):
        http_resources = re.findall(
            r"""(?:src|href|action)=["'](http://[^"']+)["']""", html, re.IGNORECASE
        )
        if http_resources:
            findings.append(
                Finding(
                    "console-mixed-content",
                    "Mixed content: HTTP resources on HTTPS page",
                    f"{len(http_resources)} HTTP resource(s) loaded on an HTTPS page",
                    "high",
                    url,
                    check="browser_console",
                    evidence_source="dom:resource attributes",
                    observed=f"HTTP resources on HTTPS page: {http_resources[:5]}",
                    business_impact="Mixed content triggers browser warnings, breaks "
                    "the padlock icon, and can expose resource integrity.",
                    remediation_action="Serve all resources over HTTPS.",
                    remediation_automation="AUTO_PREVIEW",
                    effort_band="XS",
                )
            )
            evidence["patterns"]["mixed_content"] = http_resources

    # Check for console.error / console.warn that may indicate known issues
    console_logs = re.findall(
        r"console\.(error|warn|trace)\s*\(\s*['\"]([^'\"]+)['\"]", script_source, re.IGNORECASE
    )
    if console_logs:
        evidence["console_log_calls"] = [
            {"level": level, "message": msg} for level, msg in console_logs
        ]

    return findings, evidence


def analyse_rendered(data: dict, url: str) -> tuple[list[Finding], dict[str, Any]]:
    """Use captured browser events; absent capture is an execution failure."""
    if not isinstance(data.get("console_errors"), list):
        raise ValueError("Browser console capture unavailable")
    errors = data["console_errors"]
    if not all(isinstance(error, str) for error in errors):
        raise ValueError("Malformed browser console capture")
    findings = [Finding(
        "browser-console-error", "Browser JavaScript error", error, "medium", url,
        check="browser_console", evidence_source="browser:pageerror/console.error",
        observed=error, remediation_action="Investigate the captured JavaScript error.",
    ) for error in sorted(set(errors))]
    return findings, {"url": url, "errors": errors,
                      "limitation": "Bounded lab visit; later interactions are not covered."}

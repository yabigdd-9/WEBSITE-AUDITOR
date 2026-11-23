"""Built-in check plugins for auditor_toolkit.

These plugins implement the standard checks as plugins for the new architecture.
"""

from __future__ import annotations

import logging

from .browser import run_browser_checks
from .checks import Finding, analyse_html, classify_response
from .external_tools import run_lighthouse, run_lychee
from .flows import flow_findings, run_flow_probe
from .hygiene import (
    check_mixed_content,
    check_robots,
    check_sitemap,
    detect_conversion_signals,
    discover_internal_links,
    grade_security_headers,
    validate_links,
)
from .models import Evidence
from .network import crawl, inspect_dns, inspect_headers, inspect_schema, inspect_tls
from .plugins import (
    CheckContext,
    CheckPlugin,
    CheckPluginMetadata,
    register_plugin,
)

logger = logging.getLogger(__name__)


# ─── Fetch Plugin ───
class FetchPlugin(CheckPlugin):
    """Fetch the target URL and classify HTTP response."""

    metadata = CheckPluginMetadata(
        id="fetch",
        name="HTTP Fetch",
        category="technical",
        description="Fetch target URL and classify HTTP response",
        mode="static",
    )

    def execute(self, context: CheckContext) -> tuple[list[Finding], Evidence]:
        from .common import validate_url

        url = context.url
        fetcher = context.fetcher

        try:
            validate_url(url, context.options.allow_private if context.options else False)
            response = fetcher.get(url)
            fetched_at = response.extensions.get("observed_at", context.timestamp)
            _, http_findings = classify_response(response.status_code, response.text)

            findings = [f for f in http_findings]
            if response.status_code >= 400:
                raise ValueError(f"HTTP {response.status_code}")

            evidence = Evidence(
                url=str(response.url),
                observed_at=fetched_at,
                mode="static",
                data={
                    "status_code": response.status_code,
                    "redirects": response.extensions.get("redirect_chain", []),
                    "revalidated_at": response.extensions.get("revalidated_at"),
                },
            )
            return findings, evidence

        except Exception:
            raise  # Let the caller handle it


# ─── Page Analysis Plugin ───
class PageAnalysisPlugin(CheckPlugin):
    """Analyze HTML content for SEO and content issues."""

    metadata = CheckPluginMetadata(
        id="page",
        name="Page Analysis",
        category="seo",
        description="Analyze HTML for SEO, content, and conversion signals",
        mode="static",
        limitation="Content and conversion observations require editorial review.",
    )

    def execute(self, context: CheckContext) -> tuple[list[Finding], Evidence]:
        response = context.response
        final_url = str(response.url)
        findings, data = analyse_html(response.text, final_url)

        evidence = Evidence(
            url=final_url,
            observed_at=context.timestamp,
            mode="static",
            data=data,
        )
        return findings, evidence


# ─── Schema Plugin ───
class SchemaPlugin(CheckPlugin):
    """Check for structured data (Schema.org, JSON-LD, microdata)."""

    metadata = CheckPluginMetadata(
        id="schema",
        name="Schema Markup",
        category="local",
        description="Check for Schema.org structured data",
        mode="static",
        limitation="Presence does not establish eligibility or business identity.",
    )

    def execute(self, context: CheckContext) -> tuple[list[Finding], Evidence]:
        response = context.response
        final_url = str(response.url)
        profile = context.options.profile if context.options else "static"
        findings, data = inspect_schema(response.text, final_url, profile)

        evidence = Evidence(
            url=final_url,
            observed_at=context.timestamp,
            mode="static",
            data=data,
        )
        return findings, evidence


# ─── Security Headers Plugin ───
class SecurityHeadersPlugin(CheckPlugin):
    """Grade security headers."""

    metadata = CheckPluginMetadata(
        id="headers",
        name="Security Headers",
        category="security",
        description="Grade HTTP security headers",
        mode="static",
    )

    def execute(self, context: CheckContext) -> tuple[list[Finding], Evidence]:
        response = context.response
        final_url = str(response.url)
        findings, data = inspect_headers(response)

        evidence = Evidence(
            url=final_url,
            observed_at=context.timestamp,
            mode="static",
            data=data,
        )
        return findings, evidence


# ─── Hygiene Plugin ───
class HygienePlugin(CheckPlugin):
    """Check robots.txt, sitemap, security headers, mixed content."""

    metadata = CheckPluginMetadata(
        id="hygiene",
        name="Technical Hygiene",
        category="technical",
        description="Check robots.txt, sitemap, security headers, mixed content",
        mode="static",
        limitation="Deterministic robots, sitemap, header and mixed-content checks.",
    )

    def execute(self, context: CheckContext) -> tuple[list[Finding], Evidence]:
        fetcher = context.fetcher
        response = context.response
        final_url = str(response.url)
        deep = context.options.deep if context.options else False

        robots_findings, robots_evidence = check_robots(fetcher, final_url)
        sitemap_findings, sitemap_evidence = check_sitemap(
            fetcher, final_url, robots_evidence.get("sitemaps_declared")
        )
        header_findings, header_evidence = grade_security_headers(
            response.headers, final_url, deep=deep
        )
        mixed_findings, mixed_evidence = check_mixed_content(response.text, final_url)

        all_findings = (
            robots_findings + sitemap_findings + header_findings + mixed_findings
        )
        evidence_data = {
            "robots": robots_evidence,
            "sitemap": sitemap_evidence,
            "security_headers": header_evidence,
            "mixed_content": mixed_evidence,
        }

        evidence = Evidence(
            url=final_url,
            observed_at=context.timestamp,
            mode="static",
            data=evidence_data,
        )
        return all_findings, evidence


# ─── UX Signals Plugin ───
class UXSignalsPlugin(CheckPlugin):
    """Detect conversion signals and UX issues."""

    metadata = CheckPluginMetadata(
        id="ux",
        name="UX & Conversion Signals",
        category="privacy",
        description="Detect conversion signals and UX patterns",
        mode="static",
        limitation="Observed behavior is not a legal determination.",
    )

    def execute(self, context: CheckContext) -> tuple[list[Finding], Evidence]:
        response = context.response
        final_url = str(response.url)
        findings, data = detect_conversion_signals(response.text, final_url)

        evidence = Evidence(
            url=final_url,
            observed_at=context.timestamp,
            mode="static",
            data=data,
        )
        return findings, evidence


# ─── Links Plugin ───
class LinksPlugin(CheckPlugin):
    """Validate internal links."""

    metadata = CheckPluginMetadata(
        id="links",
        name="Link Validation",
        category="technical",
        description="Validate internal links on the page",
        mode="static",
        limitation="Bounded same-origin link validation; not an exhaustive crawler.",
    )

    def execute(self, context: CheckContext) -> tuple[list[Finding], Evidence]:
        fetcher = context.fetcher
        response = context.response
        final_url = str(response.url)
        max_links = context.options.max_links if context.options else 50

        links = discover_internal_links(response.text, final_url, max_links)
        findings, data = validate_links(fetcher, final_url, links, limit=max_links)

        evidence = Evidence(
            url=final_url,
            observed_at=context.timestamp,
            mode="static",
            data=data,
        )
        return findings, evidence


# ─── TLS Plugin ───
class TLSPlugin(CheckPlugin):
    """Inspect TLS certificate."""

    metadata = CheckPluginMetadata(
        id="tls",
        name="TLS Certificate",
        category="security",
        description="Inspect TLS certificate and configuration",
        mode="static",
    )

    def execute(self, context: CheckContext) -> tuple[list[Finding], Evidence]:
        final_url = str(context.response.url)
        timeout = context.options.timeout if context.options else 8.0
        findings, data = inspect_tls(final_url, timeout)

        evidence = Evidence(
            url=final_url,
            observed_at=context.timestamp,
            mode="static",
            data=data,
        )
        return findings, evidence


# ─── DNS Plugin ───
class DNSPlugin(CheckPlugin):
    """Inspect DNS records."""

    metadata = CheckPluginMetadata(
        id="dns",
        name="DNS Inspection",
        category="technical",
        description="Inspect DNS records for the domain",
        mode="static",
    )

    def execute(self, context: CheckContext) -> tuple[list[Finding], Evidence]:
        final_url = str(context.response.url)
        timeout = context.options.timeout if context.options else 8.0
        findings, data = inspect_dns(final_url, timeout)

        evidence = Evidence(
            url=final_url,
            observed_at=context.timestamp,
            mode="static",
            data=data,
        )
        return findings, evidence


# ─── Crawl Plugin ───
class CrawlPlugin(CheckPlugin):
    """Crawl the website."""

    metadata = CheckPluginMetadata(
        id="crawl",
        name="Site Crawl",
        category="technical",
        description="Crawl the website for pages and issues",
        mode="static",
    )

    def execute(self, context: CheckContext) -> tuple[list[Finding], Evidence]:
        final_url = str(context.response.url)
        fetcher = context.fetcher
        options = context.options

        findings, data = crawl(final_url, fetcher, options)

        evidence = Evidence(
            url=final_url,
            observed_at=context.timestamp,
            mode="static",
            data=data,
        )
        return findings, evidence


# ─── Lychee Plugin ───
class LycheePlugin(CheckPlugin):
    """Run Lychee link checker."""

    metadata = CheckPluginMetadata(
        id="lychee",
        name="Lychee Link Checker",
        category="technical",
        description="Run Lychee link checker",
        mode="static",
        limitation="External local CLI check; bounded by Lychee configuration and network conditions.",
        requires_external=True,
    )

    def execute(self, context: CheckContext) -> tuple[list[Finding], Evidence]:
        final_url = str(context.response.url)
        findings, data = run_lychee(final_url)

        evidence = Evidence(
            url=final_url,
            observed_at=context.timestamp,
            mode="static",
            data=data,
        )
        return findings, evidence


# ─── Lighthouse Plugin ───
class LighthousePlugin(CheckPlugin):
    """Run Lighthouse performance audit."""

    metadata = CheckPluginMetadata(
        id="lighthouse",
        name="Lighthouse Performance",
        category="performance",
        description="Run Lighthouse performance audit",
        mode="rendered",
        limitation="Laboratory result; not field Core Web Vitals.",
        requires_external=True,
    )

    def execute(self, context: CheckContext) -> tuple[list[Finding], Evidence]:
        final_url = str(context.response.url)
        findings, data = run_lighthouse(final_url)

        evidence = Evidence(
            url=final_url,
            observed_at=context.timestamp,
            mode="rendered",
            data=data,
        )
        return findings, evidence


# ─── Browser Plugin ───
class BrowserPlugin(CheckPlugin):
    """Run browser-based checks (Playwright/Chromium)."""

    metadata = CheckPluginMetadata(
        id="browser",
        name="Browser Rendering",
        category="performance",
        description="Run browser-based checks (screenshots, Core Web Vitals)",
        mode="rendered",
        limitation="Laboratory observations, not field Core Web Vitals.",
    )

    def execute(self, context: CheckContext) -> tuple[list[Finding], Evidence]:
        final_url = str(context.response.url)
        run_dir = context.run_dir
        options = context.options

        result = run_browser_checks(
            final_url,
            run_dir / "artifacts" if run_dir else None,
            enabled=options.browser if options else True,
            allow_private=options.allow_private if options else False,
        )

        evidence = Evidence(
            url=final_url,
            observed_at=context.timestamp,
            mode="rendered",
            data=result.get("evidence", {}),
        )

        # Extract findings from browser result
        from .checks import Finding
        findings = []
        axe = result.get("evidence", {}).get("axe")
        if axe:
            for violation in axe.get("violations", []):
                for node in violation["nodes"]:
                    findings.append(
                        Finding(
                            "axe-" + violation["id"],
                            violation["help"],
                            node.get("failureSummary", ""),
                            {
                                "critical": "critical",
                                "serious": "high",
                                "moderate": "medium",
                                "minor": "low",
                            }.get(violation["impact"], "medium"),
                            final_url,
                            check="axe",
                            selector=" ".join(node["target"]),
                        )
                    )

        return findings, evidence


# ─── Axe Plugin ───
class AxePlugin(CheckPlugin):
    """Run Axe accessibility checks."""

    metadata = CheckPluginMetadata(
        id="axe",
        name="Axe Accessibility",
        category="accessibility",
        description="Run Axe accessibility checks",
        mode="rendered",
        limitation="Manual keyboard, screen-reader and content review remains necessary.",
    )

    def execute(self, context: CheckContext) -> tuple[list[Finding], Evidence]:
        # This is handled within BrowserPlugin
        # Kept for registry compatibility
        return [], Evidence(
            url=str(context.response.url),
            observed_at=context.timestamp,
            mode="rendered",
            data={"note": "Axe checks run as part of browser plugin"},
        )


# ─── Flow Probe Plugin ───
class FlowProbePlugin(CheckPlugin):
    """Run user flow probe."""

    metadata = CheckPluginMetadata(
        id="flow",
        name="User Flow Probe",
        category="technical",
        description="Probe user flows (forms, navigation)",
        mode="rendered",
    )

    def execute(self, context: CheckContext) -> tuple[list[Finding], Evidence]:
        final_url = str(context.response.url)
        run_dir = context.run_dir
        options = context.options

        result = run_flow_probe(
            final_url,
            run_dir / "artifacts" if run_dir else None,
            enabled=True,
            allow_private=options.allow_private if options else False,
        )

        flow_evidence = result.get("evidence", {})
        final_url_ev = result.get("final_url", final_url)

        findings = []
        if result["status"] in ("ok", "error"):
            flow_evidence.setdefault("reason", result.get("reason", ""))
            flow_findings_list, flow_summary = flow_findings(
                flow_evidence, final_url_ev, result["status"]
            )
            findings.extend(flow_findings_list)
            flow_evidence["summary"] = flow_summary

        evidence = Evidence(
            url=final_url_ev,
            observed_at=context.timestamp,
            mode="rendered",
            data=flow_evidence,
        )
        return findings, evidence


# ─── PDF Plugin ───
class PDFPlugin(CheckPlugin):
    """Generate PDF report."""

    metadata = CheckPluginMetadata(
        id="pdf",
        name="PDF Generation",
        category="reporting",
        description="Generate PDF report from HTML",
        mode="rendered",
    )

    def execute(self, context: CheckContext) -> tuple[list[Finding], Evidence]:
        # PDF generation happens after the audit
        # This plugin is a placeholder for the registry
        return [], Evidence(
            url=str(context.response.url),
            observed_at=context.timestamp,
            mode="rendered",
            data={"note": "PDF generated in pipeline"},
        )


# Auto-register all built-in plugins
_BUILTIN_PLUGINS = [
    FetchPlugin,
    PageAnalysisPlugin,
    SchemaPlugin,
    SecurityHeadersPlugin,
    HygienePlugin,
    UXSignalsPlugin,
    LinksPlugin,
    TLSPlugin,
    DNSPlugin,
    CrawlPlugin,
    LycheePlugin,
    LighthousePlugin,
    BrowserPlugin,
    AxePlugin,
    FlowProbePlugin,
    PDFPlugin,
]

for plugin_class in _BUILTIN_PLUGINS:
    register_plugin(plugin_class())

logger.info(f"Registered {len(_BUILTIN_PLUGINS)} built-in check plugins")

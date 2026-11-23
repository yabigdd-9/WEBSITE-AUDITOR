"""Pipeline stages for the audit process.

This module splits the monolithic run_audit function into discrete,
testable pipeline stages following the single responsibility principle.
"""

from __future__ import annotations

import hashlib
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# Module-level counter for ensuring unique run_ids in fast test runs
_run_id_counter = 0

from .browser import export_pdf, run_browser_checks
from .checks import Finding, analyse_html, classify_response, dedupe_findings, score_findings
from .common import Fetcher, atomic_write_json, atomic_write_text, validate_url
from .external_tools import run_lighthouse, run_lychee
from .faults import enrich as enrich_fault
from .faults import group_root_causes
from .faults import regression as fault_regression
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
from .logging_config import clear_correlation_id, get_logger, set_correlation_id
from .models import REGISTRY, SCHEMA_VERSION
from .network import crawl, inspect_dns, inspect_headers, inspect_schema, inspect_tls
from .quality_checks import run_quality_checks
from .reporting import render_trend_svg, write_html_report
from .storage import History, finding_id

logger = get_logger(__name__)


@dataclass
class AuditOptions:
    """Configuration options for an audit run.

    Attributes:
        output_root: Root directory for audit outputs (reports, artifacts, cache).
        allow_private: Allow auditing private/non-global IP addresses.
        browser: Enable browser-based checks (Playwright/Chromium).
        screenshot_diff: Generate visual diff screenshots against previous runs.
        use_gotenberg: Use Gotenberg for PDF generation (requires gotenberg service).
        tls: Perform TLS certificate inspection.
        timeout: HTTP request timeout in seconds.
        profile: Audit profile - one of "static", "rendered", "default", "service",
            "ecommerce", "publishing", "nz".
        deep: Enable deep checks (link validation, DNS, crawl).
        max_pages: Maximum pages to crawl (1-100).
        max_depth: Maximum crawl depth (0-5).
        max_links: Maximum links to validate per page.
        max_bytes: Maximum response body size in bytes.
        respect_robots: Respect robots.txt during crawling.
        cache: Enable HTTP response caching.
        ai: Enable AI-powered draft generation.
        ai_timeout: Timeout for AI generation in seconds.
        brand: Brand name for report headers.
        hourly_rate_nzd: Optional hourly rate in NZD for cost estimates.
        external_tools: Require external tools (Lighthouse, Lychee) to be installed.
    """
    output_root: Path = Path("outputs/toolkit")
    allow_private: bool = False
    browser: bool = False
    screenshot_diff: bool = False
    use_gotenberg: bool = False
    tls: bool = False
    timeout: float = 8.0
    profile: str = "static"
    deep: bool = False
    max_pages: int = 10
    max_depth: int = 2
    max_links: int = 50
    max_bytes: int = 2_000_000
    respect_robots: bool = True
    cache: bool = False
    ai: bool = False
    ai_timeout: float = 120.0
    brand: str = "Website Auditor"
    hourly_rate_nzd: float | None = None
    external_tools: bool = False

    def __post_init__(self):
        self.output_root = Path(self.output_root).resolve()
        if not 1 <= self.max_pages <= 100 or not 0 <= self.max_depth <= 5:
            raise ValueError("Limits: 1–100 pages, depth 0–5")
        if not 0 < self.timeout <= 60 or not 1024 <= self.max_bytes <= 10_000_000:
            raise ValueError("Invalid timeout or byte limit")
        if self.profile == "rendered":
            self.browser = True
        if self.profile not in {
            "static",
            "rendered",
            "default",
            "service",
            "ecommerce",
            "publishing",
            "nz",
        }:
            raise ValueError("Unknown profile")


@dataclass
class AuditContext:
    """Context passed between pipeline stages."""
    url: str
    opts: Any
    run_id: str
    run_dir: Path
    timestamp: str
    fetcher: Fetcher
    checks: dict = field(default_factory=dict)
    findings: list = field(default_factory=list)
    evidence: dict = field(default_factory=dict)
    response: Any = None
    fetched_at: str = ""
    final_url: str = ""
    started_at: float = field(default_factory=time.perf_counter)

    def perform_parallel(self, check_fns: list[tuple[str, callable, bool]]) -> None:
        """Execute multiple checks in parallel."""
        def run_check(name: str, fn: callable, required: bool):
            started = time.perf_counter()
            try:
                found, data = fn()
                self.findings.extend(found)
                self.evidence[name] = {
                    "url": self.final_url or self.url,
                    "observed_at": self.fetched_at or self.timestamp,
                    "mode": REGISTRY[name].mode if name in REGISTRY else "static",
                    "data": data,
                    "check_version": REGISTRY[name].version if name in REGISTRY else 1,
                }
                self.checks[name] = {"status": "ok", "required": required}
            except Exception as exc:
                logger.error(f"Check '{name}' failed: {exc}", exc_info=True)
                self.checks[name] = {"status": "error", "reason": str(exc), "required": required}
            finally:
                elapsed = int((time.perf_counter() - started) * 1000)
                self.checks[name]["elapsed_ms"] = self.checks[name].get("elapsed_ms", 0) + elapsed

        with ThreadPoolExecutor(max_workers=len(check_fns)) as executor:
            futures = [executor.submit(run_check, name, fn, required) for name, fn, required in check_fns]
            for future in futures:
                future.result()

    def skip(self, name: str, reason: str, required: bool = False) -> None:
        """Mark a check as skipped."""
        self.checks[name] = {"status": "skipped", "reason": reason, "required": required}


class PipelineStage:
    """Base class for pipeline stages."""

    name: str = "base"
    required: bool = True

    def execute(self, ctx: AuditContext) -> None:
        """Execute the stage. Override in subclasses."""
        raise NotImplementedError

    def skip(self, ctx: AuditContext, reason: str) -> None:
        """Mark stage as skipped."""
        ctx.checks[self.name] = {"status": "skipped", "reason": reason, "required": self.required}

    def error(self, ctx: AuditContext, error: Exception) -> None:
        """Mark stage as errored."""
        ctx.checks[self.name] = {"status": "error", "reason": str(error), "required": self.required}
        logger.error(f"Stage {self.name} failed: {error}")


class FetchStage(PipelineStage):
    """Fetch the target URL and classify HTTP response."""
    name = "fetch"
    required = True

    def execute(self, ctx: AuditContext) -> None:
        url = ctx.url
        opts = ctx.opts
        timestamp = ctx.timestamp
        checks = ctx.checks
        evidence = ctx.evidence
        findings = ctx.findings

        try:
            validate_url(url, opts.allow_private)
            response = ctx.fetcher.get(url)
            ctx.response = response
            fetched_at = response.extensions.get("observed_at", timestamp)
            _, http_findings = classify_response(response.status_code, response.text)
            findings.extend(http_findings)
            if response.status_code >= 400:
                raise ValueError(f"HTTP {response.status_code}")
            checks["fetch"] = {"status": "ok", "required": True}
            evidence["fetch"] = {
                "url": str(response.url),
                "observed_at": fetched_at,
                "mode": "static",
                "data": {
                    "status_code": response.status_code,
                    "redirects": response.extensions.get("redirect_chain", []),
                    "revalidated_at": response.extensions.get("revalidated_at"),
                },
            }
            ctx.fetched_at = fetched_at
            ctx.final_url = str(response.url)
            logger.info("Fetch successful", extra={"url": url, "status_code": response.status_code, "run_id": ctx.run_id})
        except Exception as exc:
            logger.error("Fetch failed", extra={"url": url, "error": str(exc), "run_id": ctx.run_id}, exc_info=True)
            checks["fetch"] = {"status": "error", "required": True, "reason": str(exc)}
            raise


class StaticAnalysisStage(PipelineStage):
    """Run static analysis checks (page, schema, headers)."""
    name = "static_analysis"
    required = True

    def execute(self, ctx: AuditContext) -> None:
        if ctx.checks.get("fetch", {}).get("status") != "ok":
            for name in ("page", "schema", "headers"):
                ctx.checks[name] = {"status": "skipped", "reason": "Fetch unavailable", "required": True}
            return

        final_url = ctx.final_url
        opts = ctx.opts
        evidence = ctx.evidence
        fetched_at = ctx.fetched_at

        def run_checks():
            ctx.perform_parallel([
                ("page", lambda: analyse_html(ctx.response.text, final_url), True),
                ("schema", lambda: inspect_schema(ctx.response.text, final_url, opts.profile), True),
                ("headers", lambda: inspect_headers(ctx.response), True),
            ])

        try:
            run_checks()
            for name in ("page", "schema", "headers"):
                if name in evidence:
                    evidence[name]["observed_at"] = fetched_at
        except Exception as exc:
            logger.error("Static analysis failed", extra={"url": ctx.url, "error": str(exc)}, exc_info=True)
            for name in ("page", "schema", "headers"):
                if name not in ctx.checks:
                    ctx.checks[name] = {"status": "error", "reason": str(exc), "required": True}
            raise


class HygieneStage(PipelineStage):
    """Run hygiene checks (robots, sitemap, security headers, mixed content)."""
    name = "hygiene"
    required = False

    def execute(self, ctx: AuditContext) -> None:
        if ctx.checks.get("fetch", {}).get("status") != "ok":
            ctx.skip("hygiene", "Fetch unavailable")
            return

        client = ctx.fetcher
        final_url = ctx.final_url
        opts = ctx.opts
        response = ctx.response

        def hygiene_checks():
            robots_findings, robots_evidence = check_robots(ctx.fetcher, final_url)
            sitemap_findings, sitemap_evidence = check_sitemap(
                client, final_url, robots_evidence.get("sitemaps_declared")
            )
            header_findings, header_evidence = grade_security_headers(
                response.headers, final_url, deep=opts.deep
            )
            mixed_findings, mixed_evidence = check_mixed_content(response.text, final_url)
            return (
                robots_findings + sitemap_findings + header_findings + mixed_findings,
                {
                    "robots": robots_evidence,
                    "sitemap": sitemap_evidence,
                    "security_headers": header_evidence,
                    "mixed_content": mixed_evidence,
                },
            )

        try:
            findings_list, evidence_data = hygiene_checks()
            ctx.findings.extend(findings_list)
            ctx.evidence["hygiene"] = evidence_data
            ctx.checks["hygiene"] = {"status": "ok", "required": False}
        except Exception as exc:
            logger.error("Hygiene check failed", extra={"url": ctx.url, "error": str(exc)}, exc_info=True)
            ctx.checks["hygiene"] = {"status": "error", "reason": str(exc), "required": False}


class UXStage(PipelineStage):
    """Run UX/conversion signal detection."""
    name = "ux"
    required = False

    def execute(self, ctx: AuditContext) -> None:
        if ctx.checks.get("fetch", {}).get("status") != "ok":
            ctx.skip("ux", "Fetch unavailable")
            return

        response = ctx.response
        final_url = ctx.final_url
        timestamp = ctx.timestamp
        findings = ctx.findings
        evidence = ctx.evidence
        checks = ctx.checks

        try:
            ux_findings, ux_evidence = detect_conversion_signals(response.text, final_url)
            findings.extend(ux_findings)
            evidence["ux"] = ux_evidence
            evidence["ux"]["observed_at"] = timestamp
            checks["ux"] = {"status": "ok", "required": False}
        except Exception as exc:
            logger.error("UX check failed", extra={"url": ctx.url, "error": str(exc)}, exc_info=True)
            checks["ux"] = {"status": "error", "reason": str(exc), "required": False}


class LinksStage(PipelineStage):
    """Validate internal links."""
    name = "links"
    required = False

    def execute(self, ctx: AuditContext) -> None:
        if ctx.checks.get("fetch", {}).get("status") != "ok":
            ctx.skip("links", "Fetch unavailable")
            return
        if not ctx.opts.deep:
            ctx.skip("links", "Enable deep checks")
            return

        client = ctx.fetcher
        final_url = ctx.final_url
        opts = ctx.opts

        try:
            links = discover_internal_links(ctx.response.text, final_url, opts.max_links)
            link_findings, link_evidence = validate_links(client, final_url, links, limit=opts.max_links)
            ctx.findings.extend(link_findings)
            ctx.evidence["links"] = link_evidence
            ctx.evidence["links"]["observed_at"] = ctx.timestamp
            ctx.checks["links"] = {"status": "ok", "required": False}
        except Exception as exc:
            logger.error("Link validation failed", extra={"url": ctx.url, "error": str(exc)}, exc_info=True)
            ctx.checks["links"] = {"status": "error", "reason": str(exc), "required": False}


class ExternalToolsStage(PipelineStage):
    """Run external tools (Lychee, Lighthouse)."""
    name = "external_tools"
    required = False

    def execute(self, ctx: AuditContext) -> None:
        if ctx.checks.get("fetch", {}).get("status") != "ok":
            for name in ("lychee", "lighthouse"):
                ctx.skip(name, "Fetch unavailable")
            return

        opts = ctx.opts

        if opts.external_tools:
            try:
                lychee_findings, lychee_evidence = run_lychee(ctx.final_url)
                ctx.findings.extend(lychee_findings)
                ctx.evidence["lychee"] = lychee_evidence
                lychee_evidence["observed_at"] = ctx.timestamp
                ctx.checks["lychee"] = {"status": "ok", "required": True}
            except Exception as exc:
                logger.error("Lychee failed", extra={"url": ctx.final_url, "error": str(exc)}, exc_info=True)
                ctx.checks["lychee"] = {"status": "error", "reason": str(exc), "required": True}

            try:
                lighthouse_findings, lighthouse_evidence = run_lighthouse(ctx.final_url)
                ctx.findings.extend(lighthouse_findings)
                ctx.evidence["lighthouse"] = lighthouse_evidence
                lighthouse_evidence["observed_at"] = ctx.timestamp
                ctx.checks["lighthouse"] = {"status": "ok", "required": True}
            except Exception as exc:
                logger.error("Lighthouse failed", extra={"url": ctx.final_url, "error": str(exc)}, exc_info=True)
                ctx.checks["lighthouse"] = {"status": "error", "reason": str(exc), "required": True}
        else:
            ctx.checks["lychee"] = {"status": "skipped", "reason": "Enable external local tools", "required": False}
            ctx.checks["lighthouse"] = {"status": "skipped", "reason": "Enable external local tools", "required": False}


class TLSSStage(PipelineStage):
    """TLS certificate inspection."""
    name = "tls"
    required = False

    def execute(self, ctx: AuditContext) -> None:
        if ctx.checks.get("fetch", {}).get("status") != "ok":
            ctx.skip("tls", "Fetch unavailable")
            return
        if not ctx.opts.tls:
            ctx.skip("tls", "Not requested")
            return

        final_url = ctx.final_url
        opts = ctx.opts
        checks = ctx.checks
        evidence = ctx.evidence
        timestamp = ctx.timestamp

        try:
            tls_findings, tls_evidence = inspect_tls(final_url, opts.timeout)
            ctx.findings.extend(tls_findings)
            evidence["tls"] = tls_evidence
            tls_evidence["observed_at"] = timestamp
            checks["tls"] = {"status": "ok", "required": True}
        except Exception as exc:
            logger.error("TLS check failed", extra={"url": ctx.final_url, "error": str(exc)}, exc_info=True)
            checks["tls"] = {"status": "error", "reason": str(exc), "required": True}


class DeepChecksStage(PipelineStage):
    """Run deep checks (DNS, crawl)."""
    name = "deep_checks"
    required = False

    def execute(self, ctx: AuditContext) -> None:
        if ctx.checks.get("fetch", {}).get("status") != "ok":
            for name in ("dns", "crawl"):
                ctx.skip(name, "Fetch unavailable")
            return
        if not ctx.opts.deep:
            for name in ("dns", "crawl"):
                ctx.skip(name, "Enable deep checks")
            return

        opts = ctx.opts
        checks = ctx.checks
        evidence = ctx.evidence
        timestamp = ctx.timestamp

        try:
            dns_findings, dns_evidence = inspect_dns(ctx.final_url, opts.timeout)
            ctx.findings.extend(dns_findings)
            evidence["dns"] = dns_evidence
            dns_evidence["observed_at"] = timestamp
            checks["dns"] = {"status": "ok", "required": True}
        except Exception as exc:
            logger.error("DNS check failed", extra={"url": ctx.final_url, "error": str(exc)}, exc_info=True)
            checks["dns"] = {"status": "error", "reason": str(exc), "required": True}

        try:
            crawl_findings, crawl_evidence = crawl(ctx.final_url, ctx.fetcher, ctx.opts)
            ctx.findings.extend(crawl_findings)
            evidence["crawl"] = crawl_evidence
            crawl_evidence["observed_at"] = timestamp
            checks["crawl"] = {"status": "ok", "required": True}
        except Exception as exc:
            logger.error("Crawl failed", extra={"url": ctx.final_url, "error": str(exc)}, exc_info=True)
            checks["crawl"] = {"status": "error", "reason": str(exc), "required": True}


class BrowserStage(PipelineStage):
    """Run browser-based checks."""
    name = "browser"
    required = False

    def execute(self, ctx: AuditContext) -> None:
        if ctx.checks.get("fetch", {}).get("status") != "ok":
            for name in ("browser", "axe"):
                ctx.skip(name, "Fetch unavailable")
            return
        if not ctx.opts.browser:
            for name in ("browser", "axe"):
                ctx.skip(name, "Rendered mode required")
            return

        final_url = ctx.final_url
        run_dir = ctx.run_dir
        opts = ctx.opts
        checks = ctx.checks
        evidence = ctx.evidence

        try:
            result = run_browser_checks(
                final_url,
                run_dir / "artifacts",
                enabled=opts.browser,
                allow_private=opts.allow_private,
            )
        except Exception as exc:
            result = {"status": "error", "reason": str(exc), "evidence": {}}

        if result["status"] != "skipped":
            try:
                flow_result = run_flow_probe(final_url, ctx.run_dir / "artifacts", enabled=True, allow_private=opts.allow_private)
                flow_evidence = flow_result.get("evidence", {})
                final_url_ev = flow_result.get("final_url", final_url)
                if flow_result["status"] in ("ok", "error"):
                    flow_evidence.setdefault("reason", flow_result.get("reason", ""))
                    flow_findings_list, flow_summary = flow_findings(flow_evidence, final_url_ev, flow_result["status"])
                    ctx.findings.extend(replace(f, source_url=final_url_ev) for f in flow_findings_list)
                    flow_evidence["summary"] = flow_summary
            except Exception as exc:
                logger.debug(f"Flow probe failed for {final_url}: {exc}")

            checks["browser"] = {
                "status": result["status"],
                "reason": result.get("reason", ""),
                "required": opts.browser,
            }
            evidence["browser"] = result.get("evidence", {})

            if opts.screenshot_diff and result.get("status") == "ok":
                try:
                    history = History(opts.output_root)
                    previous_run = history.get_latest_valid_audit(final_url, max_age_days=365)
                    if previous_run and previous_run["profile"] == opts.profile and previous_run["run_id"] != ctx.run_id:
                        screenshot_types = [
                            ("screenshot", "screenshot"),
                            ("mobile_screenshot", "mobile_screenshot"),
                        ]
                        for evidence_key, artifact_key in screenshot_types:
                            current_path = evidence["browser"].get(evidence_key)
                            if current_path and Path(current_path).exists():
                                prev_artifact = history.artifact(previous_run["run_id"], artifact_key)
                                if prev_artifact and Path(prev_artifact).exists():
                                    diff_path = run_dir / "artifacts" / f"{evidence_key}-diff.png"
                                    import subprocess
                                    result_odiff = subprocess.run(
                                        [
                                            "odiff",
                                            "--threshold", "0.1",
                                            "--output-type", "diff-image",
                                            str(prev_artifact),
                                            str(current_path),
                                            str(diff_path),
                                        ],
                                        capture_output=True,
                                        text=True,
                                        timeout=30,
                                    )
                                    if result_odiff.returncode == 0 and diff_path.exists():
                                        evidence["browser"][f"{evidence_key}_diff"] = str(diff_path)
                except (subprocess.SubprocessError, subprocess.TimeoutExpired, OSError, FileNotFoundError):
                    pass

        if opts.browser:
            axe = evidence.get("browser", {}).get("axe")
            ctx.checks["axe"] = {
                "status": "ok" if axe else "error",
                "required": True,
                "reason": evidence.get("browser", {}).get("axe_error", ""),
            }
            if axe:
                for violation in axe.get("violations", []):
                    for node in violation["nodes"]:
                        ctx.findings.append(
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
                for index, img in enumerate(evidence.get("browser", {}).get("images", [])):
                    if not img["loaded"]:
                        ctx.findings.append(
                            Finding(
                                "broken-rendered-image",
                                "Rendered image did not load",
                                str(img["src"]),
                                "medium",
                                final_url,
                                check="browser",
                                selector=f"image-{index}",
                            )
                        )
            else:
                ctx.skip("axe", "Rendered mode required")


class ScreenshotDiffStage(PipelineStage):
    """Generate screenshot diffs (separate stage for separation of concerns)."""
    name = "screenshot_diff"
    required = False

    def execute(self, ctx: AuditContext) -> None:
        # Handled in BrowserStage for now
        pass


class FlowProbeStage(PipelineStage):
    """Run flow probe."""
    name = "flow_probe"
    required = False

    def execute(self, ctx: AuditContext) -> None:
        # Handled in BrowserStage for now
        pass


class ReportGenerationStage(PipelineStage):
    """Generate final report and artifacts."""
    name = "report_generation"
    required = True

    def execute(self, ctx: AuditContext) -> None:
        from .actions import preview_report
        from .ai import generate_drafts
        from .evidence_brief import create_evidence_brief
        from .proofing import build_claim_ledger, proof_draft

        opts = ctx.opts
        url = ctx.url
        run_dir = ctx.run_dir
        timestamp = ctx.timestamp
        checks = ctx.checks
        evidence = ctx.evidence

        deduped = dedupe_findings(ctx.findings)
        defects = []
        for finding in deduped:
            record = asdict(finding)
            record["finding_id"] = finding_id(record)
            record["evidence_ref"] = finding.check if finding.check in evidence else "page"
            record["observed_at"] = evidence.get(record["evidence_ref"], {}).get("observed_at", timestamp)
            record["evidence_summary"] = (
                finding.observed or finding.evidence_source or finding.selector or record["evidence_ref"]
            )
            material = finding.severity in {"medium", "high", "critical"}
            if material and not (finding.observed or finding.evidence_source or finding.selector):
                record["confidence"] = "heuristic"
            defects.append(record)

        complete = all(c["status"] == "ok" for c in ctx.checks.values() if c["required"])
        from .scoring import score_from_findings as _score_from_findings

        breakdown = _score_from_findings(defects, complete)
        scores = score_findings(deduped, complete)
        scores["breakdown"] = breakdown.to_dict()
        defects = [enrich_fault(defect) for defect in defects]

        report = {
            "schema_version": SCHEMA_VERSION,
            "performance": {
                "total_elapsed_ms": int((time.perf_counter() - ctx.started_at) * 1000),
                "checks": {name: value.get("elapsed_ms", 0) for name, value in ctx.checks.items()},
                "slowest_checks": sorted(((name, value.get("elapsed_ms", 0)) for name, value in ctx.checks.items()), key=lambda item: -item[1])[:5],
            },
            "run_id": ctx.run_id,
            "url": ctx.url,
            "domain": urlparse(ctx.url).hostname,
            "timestamp": timestamp,
            "profile": ctx.opts.profile,
            "brand": opts.brand,
            "status": "complete" if complete else "partial",
            **scores,
            "defects": defects,
            "defect_count": len(defects),
            "fault_taxonomy": {
                "root_causes": group_root_causes(defects),
                "reproducible_count": sum(1 for defect in defects if defect.get("reproducibility")),
                "weak_or_unknown_count": sum(1 for defect in defects if defect.get("confidence_assessment", {}).get("class") in {"WEAK", "UNKNOWN"}),
            },
            "checks": ctx.checks,
            "evidence": ctx.evidence,
            "check_registry": {key: asdict(value) for key, value in REGISTRY.items()},
            "scoring": {
                "method": "severity sum capped at 100; health = 100 - severity",
                "weights": {"low": 4, "medium": 8, "high": 16, "critical": 30},
                "limitation": "Heuristic prioritization, not certification",
            },
            "financial_assumptions": [
                "No fines or measured lost revenue. Estimates require explicit rates."
            ],
            "artifacts": {},
        }

        categories = {definition.category for definition in REGISTRY.values()} - {"reporting"}
        report["category_scores"] = {}
        for category in sorted(categories):
            selected = [
                f for f in deduped if REGISTRY.get(f.check, REGISTRY["page"]).category == category
            ]
            assessed = [
                ctx.checks[k] for k, v in REGISTRY.items() if v.category == category and k in ctx.checks
            ]
            available = (
                bool(assessed)
                and all(c["status"] == "ok" for c in assessed if c["required"])
                and any(c["status"] == "ok" for c in assessed)
            )
            report["category_scores"][category] = score_findings(selected, available)

        history = History(opts.output_root)
        report["comparison"] = history.compare(report)
        previous_defects = []
        baseline_id = report["comparison"].get("baseline")
        if baseline_id:
            try:
                previous_defects = history.get(baseline_id).get("defects", [])
            except KeyError:
                previous_defects = []
        report["fault_regression"] = fault_regression(defects, previous_defects)


        evidence_brief = create_evidence_brief(report)
        report["claim_ledger"] = build_claim_ledger(report)
        report["drafts"] = generate_drafts(
            {
                "url": url,
                "evidence_brief": evidence_brief,
                "defects": defects[:10]
            },
            enabled=opts.ai,
            timeout=opts.ai_timeout
        )

        if opts.ai and report["drafts"]:
            report["quality_checks"] = run_quality_checks(report["drafts"], evidence_brief)
        report["proofing"] = {
            key: proof_draft(value.get("text", ""), report["claim_ledger"])
            for key, value in report.get("drafts", {}).get("drafts", {}).items()
            if isinstance(value, dict)
        }
        report["proposal"] = {
            "currency": "NZD",
            "hourly_rate": opts.hourly_rate_nzd,
            "assumptions": "Illustrative 1–3 hours per finding; scope and rates require review.",
            "hours_low": len(defects),
            "hours_high": len(defects) * 3,
            "estimate_low": len(defects) * opts.hourly_rate_nzd if opts.hourly_rate_nzd is not None else None,
            "estimate_high": len(defects) * 3 * opts.hourly_rate_nzd if opts.hourly_rate_nzd is not None else None,
        }
        report["action_preview"] = preview_report(report, run_dir / "actions")

        report_path, html_path, trend_path = (
            run_dir / name for name in ("report.json", "report.html", "trend.svg")
        )
        report["artifacts"] = {
            "json": str(report_path),
            "html": str(html_path),
            "trend": str(trend_path),
            "actions": str(run_dir / "actions/preview.json"),
        }
        for key in ("screenshot", "mobile_screenshot", "screenshot_diff", "mobile_screenshot_diff"):
            path = evidence.get("browser", {}).get(key)
            if path and Path(path).is_file():
                report["artifacts"][key] = path
        visual_pack = evidence.get("browser", {}).get("visual_pack", {})
        for viewport, artifact in visual_pack.get("viewports", {}).items():
            if artifact.get("path") and Path(artifact["path"]).is_file():
                report["artifacts"][f"visual_{viewport}"] = artifact["path"]
        for crop in visual_pack.get("crops", []):
            if crop.get("path") and Path(crop["path"]).is_file():
                report["artifacts"][f"visual_crop_{crop['name']}"] = crop["path"]
        write_html_report(report, html_path)

        if ctx.opts.browser:
            try:
                pdf_path = run_dir / "report.pdf"
                export_pdf(html_path, pdf_path, opts)
                report["artifacts"]["pdf"] = str(pdf_path)
                checks["pdf"] = {"status": "ok", "required": True}
            except Exception as exc:
                checks["pdf"] = {"status": "error", "required": True, "reason": str(exc)}
        else:
            ctx.skip("pdf", "Rendered mode required")

        complete = all(c["status"] == "ok" for c in checks.values() if c["required"])
        scores = score_findings(deduped, complete)
        report.update(scores)
        report["status"] = "complete" if complete else "partial"
        report["coverage"] = {
            "required": sum(c["required"] for c in checks.values()),
            "passed": sum(c["required"] and c["status"] == "ok" for c in checks.values()),
        }
        report["comparison"] = history.compare(report)
        write_html_report(report, html_path)

        if "pdf" in report["artifacts"]:
            try:
                export_pdf(html_path, Path(report["artifacts"]["pdf"]), opts)
            except Exception as exc:
                report["artifacts"].pop("pdf")
                checks["pdf"].update(status="error", reason=str(exc))
                report.update(status="partial", health_score=None)
                report["coverage"]["passed"] -= 1
                report["comparison"] = history.compare(report)
                write_html_report(report, html_path)

        atomic_write_text(trend_path, render_trend_svg(report))
        report["manifest"] = {
            key: {
                "path": path,
                "size": Path(path).stat().st_size,
                "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            }
            for key, path in report["artifacts"].items()
            if key != "json"
        }
        atomic_write_json(report_path, report)
        history.save(report)

        elapsed_ms = int((time.perf_counter() - ctx.started_at) * 1000)
        logger.info(
            "Audit completed",
            extra={
                "url": ctx.url,
                "run_id": ctx.run_id,
                "status": report["status"],
                "health_score": report.get("health_score"),
                "defect_count": len(defects),
                "elapsed_ms": elapsed_ms,
            },
        )


class PipelineOrchestrator:
    """Orchestrates the execution of pipeline stages."""

    def __init__(self, stages: list[PipelineStage]):
        self.stages = stages

    def run(self, ctx: AuditContext) -> dict:
        """Execute all stages in order."""
        for stage in self.stages:
            try:
                stage.execute(ctx)
            except Exception as exc:
                logger.error(f"Stage {stage.name} failed", extra={"url": ctx.url, "error": str(exc)}, exc_info=True)
                ctx.checks[stage.name] = {"status": "error", "reason": str(exc), "required": stage.required}
                if stage.required:
                    # For required stages, continue to report generation but mark as failed
                    logger.error(f"Required stage {stage.name} failed, continuing to report generation")

        return {
            "url": ctx.url,
            "run_id": ctx.run_id,
            "status": ctx.checks.get("fetch", {}).get("status", "unknown"),
            "checks": ctx.checks,
            "findings": ctx.findings,
            "evidence": ctx.evidence,
        }


def create_pipeline_stages(opts) -> list[PipelineStage]:
    """Create the standard pipeline stages for an audit."""
    return [
        FetchStage(),
        StaticAnalysisStage(),
        HygieneStage(),
        UXStage(),
        LinksStage(),
        ExternalToolsStage(),
        TLSSStage(),
        DeepChecksStage(),
        BrowserStage(),
        ReportGenerationStage(),
    ]


def run_audit_staged(url: str, options=None, fetcher=None) -> dict:
    """Run a complete website audit using the staged pipeline."""
    global _run_id_counter
    opts = options or AuditOptions()
    _run_id_counter += 1
    run_id = (
        datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        + "-"
        + uuid.uuid4().hex[:16]
        + f"-{os.getpid()}-{_run_id_counter}"
    )
    run_dir = opts.output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).isoformat()

    set_correlation_id(run_id)
    logger.info("Starting audit", extra={"url": url, "run_id": run_id, "profile": opts.profile})

    client = fetcher or Fetcher(
        opts.timeout,
        opts.max_bytes,
        opts.allow_private,
        cache_dir=opts.output_root / ".cache" if opts.cache else None,
        cache_namespace=f"schema:{SCHEMA_VERSION}:profile:{opts.profile}",
    )

    ctx = AuditContext(
        url=url,
        opts=opts,
        run_id=run_id,
        run_dir=run_dir,
        timestamp=timestamp,
        fetcher=client,
        started_at=time.perf_counter(),
    )

    stages = create_pipeline_stages(opts)
    orchestrator = PipelineOrchestrator(stages)

    try:
        orchestrator.run(ctx)
        # Load the full report from the database
        history = History(opts.output_root)
        return history.get(run_id)
    finally:
        clear_correlation_id()

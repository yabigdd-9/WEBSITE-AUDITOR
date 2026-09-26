from __future__ import annotations

import hashlib
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from . import (
    browser_console,
    cookie_consent,
    hreflang,
    images,
    language,
    social_meta,
    structured_validation,
    tech,
    third_party,
    vuln_js,
)
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
from .models import REGISTRY, SCHEMA_VERSION
from .network import crawl, inspect_dns, inspect_headers, inspect_schema, inspect_tls
from .quality_checks import run_quality_checks
from .reporting import render_trend_svg, write_html_report
from .storage import History, finding_id


@dataclass
class AuditOptions:
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


def run_audit(url, options=None, fetcher=None):
    opts = options or AuditOptions()
    started_at = time.perf_counter()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12]
    run_dir = opts.output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    timestamp = datetime.now(UTC).isoformat()
    checks, findings, evidence = {}, [], {}
    client = fetcher or Fetcher(
        opts.timeout,
        opts.max_bytes,
        opts.allow_private,
        cache_dir=opts.output_root / ".cache" if opts.cache else None,
        cache_namespace=f"schema:{SCHEMA_VERSION}:profile:{opts.profile}",
    )

    def perform(name, fn, required=True):
        started = time.perf_counter()
        try:
            found, data = fn()
            findings.extend(found)
            evidence[name] = {
                "url": url,
                "observed_at": timestamp,
                "mode": REGISTRY[name].mode,
                "data": data,
                "check_version": REGISTRY[name].version,
            }
            checks[name] = {"status": "ok", "required": required}
            return data
        except Exception as exc:
            checks[name] = {"status": "error", "reason": str(exc), "required": required}
            return None
        finally:
            checks[name]["elapsed_ms"] = int((time.perf_counter() - started) * 1000)

    def skip(name, reason, required=False):
        checks[name] = {"status": "skipped", "reason": reason, "required": required}

    def perform_parallel(specs):
        """Run independent local checks concurrently; merge deterministically.

        Each worker times itself so a slow check never inflates the measured
        elapsed time of faster checks that finish earlier.
        """
        def timed(fn):
            started = time.perf_counter()
            try:
                found, data = fn()
            except Exception:
                raise
            finally:
                elapsed = time.perf_counter() - started
            return found, data, elapsed

        with ThreadPoolExecutor(max_workers=min(4, len(specs))) as pool:
            futures = {name: pool.submit(timed, fn) for name, fn, _ in specs}
            for name, fn, required in specs:
                try:
                    found, data, elapsed = futures[name].result()
                    findings.extend(found)
                    evidence[name] = {"url": url, "observed_at": timestamp,
                                      "mode": REGISTRY[name].mode, "data": data,
                                      "check_version": REGISTRY[name].version}
                    checks[name] = {"status": "ok", "required": required,
                                    "elapsed_ms": int(elapsed * 1000)}
                except Exception as exc:
                    checks[name] = {"status": "error", "reason": str(exc),
                                    "required": required, "elapsed_ms": 0}

    response = None
    try:
        validate_url(url, opts.allow_private)
        response = client.get(url)
        fetched_at = response.extensions.get("observed_at", timestamp)
        _, http_findings = classify_response(response.status_code, response.text)
        findings.extend(replace(f, source_url=url) for f in http_findings)
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
    except Exception as exc:
        checks["fetch"] = {"status": "error", "required": True, "reason": str(exc)}
    try:
        if checks["fetch"]["status"] == "ok":
            final_url = str(response.url)
            perform_parallel([
                ("page", lambda: analyse_html(response.text, final_url), True),
                ("schema", lambda: inspect_schema(response.text, final_url, opts.profile), True),
                ("headers", lambda: inspect_headers(response), True),
                ("technology", lambda: tech.analyse_html(response.text, final_url, response.headers), True),
                ("js_vulnerabilities", lambda: vuln_js.analyse_html(response.text, final_url, response.headers), True),
                ("structured_validation", lambda: structured_validation.analyse_html(response.text, final_url, response.headers), True),
                ("hreflang", lambda: hreflang.analyse_html(response.text, final_url, response.headers), True),
                ("language", lambda: language.analyse_html(response.text, final_url, response.headers), True),
                ("images", lambda: images.analyse_html(response.text, final_url, response.headers), True),
                ("social_meta", lambda: social_meta.analyse_html(response.text, final_url, response.headers), True),
            ])
            def hygiene_checks():
                robots_findings, robots_evidence = check_robots(client, final_url)
                sitemap_findings, sitemap_evidence = check_sitemap(
                    client, final_url, robots_evidence.get("sitemaps_declared")
                )
                header_findings, header_evidence = grade_security_headers(
                    response.headers, final_url, deep=opts.deep
                )
                mixed_findings, mixed_evidence = check_mixed_content(response.text, final_url)
                return (
                    robots_findings
                    + sitemap_findings
                    + header_findings
                    + mixed_findings,
                    {
                        "robots": robots_evidence,
                        "sitemap": sitemap_evidence,
                        "security_headers": header_evidence,
                        "mixed_content": mixed_evidence,
                    },
                )

            perform("hygiene", hygiene_checks)
            perform("ux", lambda: detect_conversion_signals(response.text, final_url))
            if opts.deep:
                links = discover_internal_links(response.text, final_url, opts.max_links)
                perform(
                    "links",
                    lambda: validate_links(client, final_url, links, limit=opts.max_links),
                )
            else:
                skip("links", "Enable deep checks")

            for name in ("page", "schema", "headers", "hygiene", "ux", "links"):
                if name in evidence:
                    evidence[name]["observed_at"] = fetched_at
            if opts.external_tools:
                perform("lychee", lambda: run_lychee(final_url), required=True)
                perform("lighthouse", lambda: run_lighthouse(final_url), required=True)
            else:
                skip("lychee", "Enable external local tools")
                skip("lighthouse", "Enable external local tools")

            if opts.tls:
                perform("tls", lambda: inspect_tls(final_url, opts.timeout))
            else:
                skip("tls", "Not requested")
            if opts.deep:
                perform("dns", lambda: inspect_dns(final_url, opts.timeout))
                perform("crawl", lambda: crawl(final_url, client, opts))
            else:
                skip("dns", "Enable deep checks")
                skip("crawl", "Enable deep checks")
            try:
                result = run_browser_checks(
                    final_url,
                    run_dir / "artifacts",
                    enabled=opts.browser,
                    allow_private=opts.allow_private,
                )
            except Exception as exc:
                result = {"status": "error", "reason": str(exc), "evidence": {}}
            # Transaction-flow probe: rides on the same browser authorisation
            # (opts.browser) so the safe-action policy applies per profile.
            flow_started = time.perf_counter()
            try:
                flow_result = run_flow_probe(
                    final_url,
                    run_dir / "artifacts",
                    enabled=opts.browser,
                    allow_private=opts.allow_private,
                )
            except Exception as exc:
                flow_result = {"status": "error", "reason": str(exc), "evidence": {}}
            flow_evidence = flow_result.get("evidence", {})
            if flow_result["status"] == "ok":
                flow_findings_list, flow_summary = flow_findings(flow_evidence, final_url)
                findings.extend(replace(f, source_url=final_url) for f in flow_findings_list)
                flow_evidence["summary"] = flow_summary
            checks["flow"] = {
                "status": flow_result["status"],
                "reason": flow_result.get("reason", ""),
                "required": False,
                "elapsed_ms": int((time.perf_counter() - flow_started) * 1000),
            }
            evidence["flow"] = {
                "url": final_url,
                "observed_at": timestamp,
                "mode": REGISTRY["flow"].mode,
                "data": flow_evidence,
                "check_version": REGISTRY["flow"].version,
            }
            checks["browser"] = {
                "status": result["status"],
                "reason": result.get("reason", ""),
                "required": opts.browser,
            }
            evidence["browser"] = result.get("evidence", {})
            if opts.screenshot_diff and result.get("status") == "ok":
                try:
                    history = History(opts.output_root)
                    # Get previous complete runs for same URL and profile
                    previous_runs = [
                        r for r in history.list(url, 1000)
                        if r["url"] == url
                        and r["status"] == "complete"
                        and r["profile"] == opts.profile
                        and r["run_id"] != run_id
                    ]
                    if previous_runs:
                        previous_run = previous_runs[0]  # most recent
                        # Define screenshot types to check
                        screenshot_types = [
                            ("screenshot", "screenshot"),
                            ("mobile_screenshot", "mobile_screenshot"),
                        ]
                        for evidence_key, artifact_key in screenshot_types:
                            current_path = evidence["browser"].get(evidence_key)
                            if current_path and Path(current_path).exists():
                                # Retrieve previous artifact
                                prev_artifact = history.artifact(previous_run["run_id"], artifact_key)
                                if prev_artifact and Path(prev_artifact).exists():
                                    # Create diff image path
                                    diff_path = run_dir / "artifacts" / f"{evidence_key}-diff.png"
                                    # Run odiff
                                    import subprocess
                                    result_odiff = subprocess.run(
                                        [
                                            "odiff",
                                            "--threshold",
                                            "0.1",
                                            "--output-type",
                                            "diff-image",
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
                except Exception:
                    # Log warning but do not fail the audit
                    pass
            if opts.browser:
                # Rendered checks
                perform("cookie_consent", lambda: cookie_consent.analyse_html(response.text, final_url, response.headers))
                perform("third_party", lambda: third_party.analyse_html(response.text, final_url, response.headers))
                perform("browser_console", lambda: browser_console.analyse_html(response.text, final_url, response.headers))
                axe = evidence["browser"].get("axe")
                checks["axe"] = {
                    "status": "ok" if axe else "error",
                    "required": True,
                    "reason": evidence["browser"].get("axe_error", ""),
                }
                for violation in (axe or {}).get("violations", []):
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
                for index, img in enumerate(evidence["browser"].get("images", [])):
                    if not img["loaded"]:
                        findings.append(
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
                skip("axe", "Rendered mode required")
                skip("flow", "Rendered mode required")
        else:
            for name in (
                "page",
                "schema",
                "headers",
                "hygiene",
                "ux",
                "links",
                "tls",
                "dns",
                "crawl",
                "lychee",
                "lighthouse",
                "browser",
                "axe",
                "flow",
            ):
                skip(
                    name,
                    "Fetch unavailable",
                    name in {"page", "schema", "headers"}
                    or opts.browser
                    and name in {"browser", "axe", "flow"},
                )
    finally:
        if fetcher is None:
            client.close()
    deduped = dedupe_findings(findings)
    defects = []
    for finding in deduped:
        record = asdict(finding)
        record["finding_id"] = finding_id(record)
        record["evidence_ref"] = finding.check if finding.check in evidence else "page"
        record["observed_at"] = evidence.get(record["evidence_ref"], {}).get(
            "observed_at", timestamp
        )
        # P5: every material defect carries an evidence summary so scores,
        # quotes and drafts below can cite it instead of restating a number.
        record["evidence_summary"] = (
            finding.observed or finding.evidence_source or finding.selector or record["evidence_ref"]
        )
        material = finding.severity in {"medium", "high", "critical"}
        if material and not (
            finding.observed or finding.evidence_source or finding.selector
        ):
            record["confidence"] = "heuristic"
        defects.append(record)
    complete = all(c["status"] == "ok" for c in checks.values() if c["required"])
    from .scoring import score_from_findings as _score_from_findings

    breakdown = _score_from_findings(defects, complete)
    scores = score_findings(deduped, complete)
    scores["breakdown"] = breakdown.to_dict()
    defects = [enrich_fault(defect) for defect in defects]
    report = {
        "schema_version": SCHEMA_VERSION,
        "performance": {
            "total_elapsed_ms": int((time.perf_counter() - started_at) * 1000) if "started_at" in locals() else 0,
            "checks": {name: value.get("elapsed_ms", 0) for name, value in checks.items()},
            "slowest_checks": sorted(((name, value.get("elapsed_ms", 0)) for name, value in checks.items()), key=lambda item: -item[1])[:5],
        },
        "run_id": run_id,
        "url": url,
        "domain": urlparse(url).hostname,
        "timestamp": timestamp,
        "profile": opts.profile,
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
        "checks": checks,
        "evidence": evidence,
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
            checks[k] for k, v in REGISTRY.items() if v.category == category and k in checks
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
    from .actions import preview_report
    from .ai import generate_drafts

    # Create evidence brief for improved drafting workflows
    from .evidence_brief import create_evidence_brief
    from .proofing import build_claim_ledger, proof_draft
    evidence_brief = create_evidence_brief(report)
    report["claim_ledger"] = build_claim_ledger(report)

    report["drafts"] = generate_drafts(
        {
            "url": url,
            "evidence_brief": evidence_brief,
            "defects": defects[:10]  # Keep for backward compatibility
        },
        enabled=opts.ai,
        timeout=opts.ai_timeout
    )

    # Run quality checks on generated drafts
    if opts.ai and report["drafts"]:
        report["quality_checks"] = run_quality_checks(
            report["drafts"],
            evidence_brief
        )
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
        "estimate_low": len(defects) * opts.hourly_rate_nzd
        if opts.hourly_rate_nzd is not None
        else None,
        "estimate_high": len(defects) * 3 * opts.hourly_rate_nzd
        if opts.hourly_rate_nzd is not None
        else None,
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
    if opts.browser:
        try:
            pdf_path = run_dir / "report.pdf"
            export_pdf(html_path, pdf_path, opts)
            report["artifacts"]["pdf"] = str(pdf_path)
            checks["pdf"] = {"status": "ok", "required": True}
        except Exception as exc:
            checks["pdf"] = {"status": "error", "required": True, "reason": str(exc)}
    else:
        skip("pdf", "Rendered mode required")
    complete = all(c["status"] == "ok" for c in checks.values() if c["required"])
    report.update(score_findings(deduped, complete), status="complete" if complete else "partial")
    report["coverage"] = {
        "required": sum(c["required"] for c in checks.values()),
        "passed": sum(c["required"] and c["status"] == "ok" for c in checks.values()),
    }
    report["comparison"] = history.compare(report)
    write_html_report(report, html_path)
    # Regenerate PDF with final coverage, status and comparison after successful browser export.
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
    return report

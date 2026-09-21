from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from .browser import export_pdf, run_browser_checks
from .checks import Finding, analyse_html, classify_response, dedupe_findings, score_findings
from .common import Fetcher, atomic_write_json, atomic_write_text, validate_url
from .models import REGISTRY, SCHEMA_VERSION
from .network import crawl, inspect_dns, inspect_headers, inspect_schema, inspect_tls
from .hygiene import (
    check_robots,
    check_sitemap,
    detect_conversion_signals,
    discover_internal_links,
    validate_links,
)
from .reporting import render_trend_svg, write_html_report
from .storage import History, finding_id


@dataclass
class AuditOptions:
    output_root: Path = Path("outputs/toolkit")
    allow_private: bool = False
    browser: bool = False
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
            perform("page", lambda: analyse_html(response.text, final_url))
            perform("schema", lambda: inspect_schema(response.text, final_url, opts.profile))
            perform("headers", lambda: inspect_headers(response))
            if opts.deep:
                def run_hygiene():
                    robot_findings, robot_data = check_robots(client, final_url)
                    sitemap_findings, sitemap_data = check_sitemap(
                        client, final_url, robot_data.get("sitemaps_declared")
                    )
                    return robot_findings + sitemap_findings, {
                        "robots": robot_data,
                        "sitemap": sitemap_data,
                    }

                perform("hygiene", run_hygiene)
                perform("ux", lambda: detect_conversion_signals(response.text, final_url))
                links = discover_internal_links(response.text, final_url, opts.max_links)
                perform("links", lambda: validate_links(client, final_url, links))
            else:
                skip("hygiene", "Enable deep checks")
                skip("ux", "Enable deep checks")
                skip("links", "Enable deep checks")
            for name in ("page", "schema", "headers"):
                if name in evidence:
                    evidence[name]["observed_at"] = fetched_at
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
            checks["browser"] = {
                "status": result["status"],
                "reason": result.get("reason", ""),
                "required": opts.browser,
            }
            evidence["browser"] = result.get("evidence", {})
            if opts.browser:
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
        else:
            for name in ("page", "schema", "headers", "tls", "dns", "crawl", "browser", "axe"):
                skip(
                    name,
                    "Fetch unavailable",
                    name in {"page", "schema", "headers"}
                    or opts.browser
                    and name in {"browser", "axe"},
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
    report = {
        "schema_version": SCHEMA_VERSION,
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
    from .actions import preview_report
    from .ai import generate_drafts

    report["drafts"] = generate_drafts(
        {"url": url, "defects": defects[:10]}, enabled=opts.ai, timeout=opts.ai_timeout
    )
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
    for key in ("screenshot", "mobile_screenshot"):
        path = evidence.get("browser", {}).get(key)
        if path and Path(path).is_file():
            report["artifacts"][key] = path
    write_html_report(report, html_path)
    if opts.browser:
        try:
            pdf_path = run_dir / "report.pdf"
            export_pdf(html_path, pdf_path)
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
            export_pdf(html_path, Path(report["artifacts"]["pdf"]))
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

"""Generate Local SEO audit reports.

Produces JSON and Markdown reports to reports/local-seo/runs/<run_id>/.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LocalSEOReport:
    """Complete Local SEO audit report."""

    run_id: str
    generated_at: str
    site_url: str = ""
    findings: list[dict[str, Any]] = field(default_factory=list)
    contradictions: list[dict[str, Any]] = field(default_factory=list)
    location_pages: list[dict[str, Any]] = field(default_factory=list)
    service_area_classification: dict[str, Any] = field(default_factory=dict)
    entity: dict[str, Any] = field(default_factory=dict)
    corroboration: dict[str, Any] = field(default_factory=dict)
    geo_corroboration: list[dict[str, Any]] = field(default_factory=list)
    scoring_summary: dict[str, Any] = field(default_factory=dict)
    confidence_metrics: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_findings(self) -> int:
        return len(self.findings)

    @property
    def high_findings(self) -> int:
        return sum(1 for f in self.findings if f.get("impact") == "HIGH")

    @property
    def contradictions_count(self) -> int:
        return sum(1 for c in self.contradictions if c.get("status") == "CONTRADICTION")

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "site_url": self.site_url,
            "total_findings": self.total_findings,
            "high_findings": self.high_findings,
            "contradictions_count": self.contradictions_count,
            "findings": self.findings,
            "contradictions": self.contradictions,
            "location_pages": self.location_pages,
            "service_area_classification": self.service_area_classification,
            "entity": self.entity,
            "corroboration": self.corroboration,
            "geo_corroboration": self.geo_corroboration,
            "scoring_summary": self.scoring_summary,
            "confidence_metrics": self.confidence_metrics,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_report(
    run_id: str,
    site_url: str = "",
    findings: list[dict[str, Any]] | None = None,
    contradictions: list[dict[str, Any]] | None = None,
    location_pages: list[dict[str, Any]] | None = None,
    service_area_classification: dict[str, Any] | None = None,
    entity: dict[str, Any] | None = None,
    corroboration: dict[str, Any] | None = None,
    geo_corroboration: list[dict[str, Any]] | None = None,
    scoring_summary: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> LocalSEOReport:
    """Generate a complete Local SEO report."""
    now = datetime.now(timezone.utc).isoformat()

    # Compute confidence metrics
    confidence_metrics = _compute_confidence_metrics(findings or [], corroboration or {})

    return LocalSEOReport(
        run_id=run_id,
        generated_at=now,
        site_url=site_url,
        findings=findings or [],
        contradictions=contradictions or [],
        location_pages=location_pages or [],
        service_area_classification=service_area_classification or {},
        entity=entity or {},
        corroboration=corroboration or {},
        geo_corroboration=geo_corroboration or [],
        scoring_summary=scoring_summary or {},
        confidence_metrics=confidence_metrics,
        metadata=metadata or {},
    )


def _compute_confidence_metrics(
    findings: list[dict[str, Any]],
    corroboration: dict[str, Any],
) -> dict[str, Any]:
    """Compute aggregate confidence metrics."""
    if not findings:
        return {"avg_confidence": 0.0, "high_confidence_pct": 0.0}

    confidences = [f.get("confidence", 0.5) for f in findings]
    avg_conf = sum(confidences) / len(confidences)
    high_conf = sum(1 for c in confidences if c >= 0.8) / len(confidences) * 100

    ext_conf = corroboration.get("overall_confidence", 0.0)

    return {
        "avg_confidence": round(avg_conf, 2),
        "high_confidence_pct": round(high_conf, 1),
        "external_confidence": round(ext_conf, 2),
        "total_findings": len(findings),
    }


# ---------------------------------------------------------------------------
# File output
# ---------------------------------------------------------------------------


def save_report(
    report: LocalSEOReport,
    base_dir: str | Path | None = None,
) -> Path:
    """Save report to reports/local-seo/runs/<run_id>/.

    Writes both JSON and Markdown files.
    Returns the directory path.
    """
    if base_dir is None:
        base_dir = Path("reports") / "local-seo" / "runs" / report.run_id
    else:
        base_dir = Path(base_dir) / report.run_id

    base_dir.mkdir(parents=True, exist_ok=True)

    # JSON report
    json_path = base_dir / "report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, default=str)

    # Markdown report
    md_path = base_dir / "report.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_markdown_report(report))

    # Benchmark JSON
    bench_path = base_dir / "benchmark.json"
    with open(bench_path, "w", encoding="utf-8") as f:
        json.dump(generate_benchmark(report), f, indent=2, default=str)

    return base_dir


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def render_markdown_report(report: LocalSEOReport) -> str:
    """Render a human-readable Markdown report."""
    lines = [
        "# Local SEO Audit Report",
        "",
        f"**Run ID:** `{report.run_id}`",
        f"**Generated:** {report.generated_at}",
        f"**Site:** {report.site_url}",
        "",
    ]
    _append_summary_and_classification(lines, report)
    _append_findings(lines, report)
    _append_location_and_contradiction_sections(lines, report)
    _append_geo_section(lines, report)
    _append_corroboration_section(lines, report)
    lines.append("---")
    lines.append("*Generated by WEBSITE-AUDITOR Local SEO v38*")

    return "\n".join(lines)


def _append_summary_and_classification(lines: list[str], report: LocalSEOReport) -> None:
    lines.extend([
        "## Summary", "",
        f"- **Total findings:** {report.total_findings}",
        f"- **High impact:** {report.high_findings}",
        f"- **Contradictions:** {report.contradictions_count}",
    ])
    if report.scoring_summary:
        lines.append(f"- **Average confidence:** {report.scoring_summary.get('avg_confidence', 0):.0%}")
    lines.append("")
    classification = report.service_area_classification
    if classification:
        lines.extend([
            "## Business Classification", "",
            f"- **Type:** {classification.get('classification', 'UNKNOWN')}",
            f"- **Confidence:** {classification.get('confidence', 0):.0%}",
        ])
        lines.extend(f"  - {reason}" for reason in classification.get("reasons", []))
        lines.append("")


def _append_findings(lines: list[str], report: LocalSEOReport) -> None:
    lines.extend(["## Findings", ""])
    by_impact: dict[str, list[dict[str, Any]]] = {}
    for finding in report.findings:
        by_impact.setdefault(finding.get("impact", "UNKNOWN"), []).append(finding)
    for impact in ("HIGH", "MEDIUM_HIGH", "MEDIUM", "LOW", "INFO"):
        findings = by_impact.get(impact, [])
        if findings:
            _append_impact_findings(lines, impact, findings)


def _append_impact_findings(
    lines: list[str], impact: str, findings: list[dict[str, Any]]
) -> None:
    lines.extend([f"### {impact}", ""])
    for finding in findings:
        title = finding.get("title", finding.get("defect_key", "?"))
        confidence = finding.get("confidence", 0)
        lines.append(f"- **{title}** (confidence: {confidence:.0%})")
        if finding.get("page_url"):
            lines.append(f"  - Page: {finding['page_url']}")
        if finding.get("detail"):
            lines.append(f"  - {finding['detail']}")
    lines.append("")


def _append_location_and_contradiction_sections(
    lines: list[str], report: LocalSEOReport
) -> None:
    if report.location_pages:
        lines.extend(["## Location Pages", ""])
        for page in report.location_pages:
            lines.append(
                f"- **{page.get('url', '')}** — {page.get('classification', '?')} "
                f"({page.get('confidence', 0):.0%})"
            )
        lines.append("")
    if report.contradictions:
        lines.extend(["## Contradictions", ""])
        for item in report.contradictions:
            lines.append(f"- **{item.get('field', '?')}**: {item.get('status', '?')}")
            lines.append(f"  - Schema: `{item.get('schema_value', '')}`")
            lines.append(f"  - Visible: `{item.get('visible_value', '')}`")
        lines.append("")


def _append_geo_section(lines: list[str], report: LocalSEOReport) -> None:
    if not report.geo_corroboration:
        return
    lines.extend(["## Geographic Corroboration", ""])
    for item in report.geo_corroboration:
        lines.append(
            f"- **Status:** {item.get('status', '?')} "
            f"({item.get('distance_km', 0):.3f} km)"
        )
        if item.get("detail"):
            lines.append(f"  - {item['detail']}")
    lines.append("")


def _append_corroboration_section(lines: list[str], report: LocalSEOReport) -> None:
    if not report.corroboration:
        return
    corroboration = report.corroboration
    lines.extend([
        "## External Corroboration", "",
        f"**Overall external confidence:** {corroboration.get('overall_confidence', 0):.0%}",
        f"- **Matches:** {len(corroboration.get('matches', []))}",
        f"- **Conflicts:** {len(corroboration.get('conflicts', []))}",
        "",
    ])


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------


def generate_benchmark(report: LocalSEOReport) -> dict[str, Any]:
    """Generate a benchmark JSON for trend comparison."""
    return {
        "run_id": report.run_id,
        "generated_at": report.generated_at,
        "site_url": report.site_url,
        "metrics": {
            "total_findings": report.total_findings,
            "high_findings": report.high_findings,
            "contradictions_count": report.contradictions_count,
            "avg_confidence": report.confidence_metrics.get("avg_confidence", 0),
            "location_pages_found": len(report.location_pages),
            "business_type": report.service_area_classification.get("classification", ""),
        },
        "findings_by_impact": _count_by_field(report.findings, "impact"),
        "contradictions_by_field": _count_by_field(report.contradictions, "field"),
    }


def _count_by_field(items: list[dict[str, Any]], field_name: str) -> dict[str, int]:
    """Count items by a field value."""
    counts: dict[str, int] = {}
    for item in items:
        val = item.get(field_name, "unknown")
        counts[val] = counts.get(val, 0) + 1
    return counts

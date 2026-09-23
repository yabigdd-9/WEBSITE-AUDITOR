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
    lines: list[str] = []

    lines.append("# Local SEO Audit Report")
    lines.append("")
    lines.append(f"**Run ID:** `{report.run_id}`")
    lines.append(f"**Generated:** {report.generated_at}")
    lines.append(f"**Site:** {report.site_url}")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Total findings:** {report.total_findings}")
    lines.append(f"- **High impact:** {report.high_findings}")
    lines.append(f"- **Contradictions:** {report.contradictions_count}")
    if report.scoring_summary:
        avg = report.scoring_summary.get("avg_confidence", 0)
        lines.append(f"- **Average confidence:** {avg:.0%}")
    lines.append("")

    # Service Area Classification
    if report.service_area_classification:
        lines.append("## Business Classification")
        lines.append("")
        sa = report.service_area_classification
        lines.append(f"- **Type:** {sa.get('classification', 'UNKNOWN')}")
        lines.append(f"- **Confidence:** {sa.get('confidence', 0):.0%}")
        for reason in sa.get("reasons", []):
            lines.append(f"  - {reason}")
        lines.append("")

    # Findings by impact
    lines.append("## Findings")
    lines.append("")

    by_impact: dict[str, list[dict[str, Any]]] = {}
    for f in report.findings:
        impact = f.get("impact", "UNKNOWN")
        by_impact.setdefault(impact, []).append(f)

    for impact in ("HIGH", "MEDIUM_HIGH", "MEDIUM", "LOW", "INFO"):
        items = by_impact.get(impact, [])
        if not items:
            continue
        lines.append(f"### {impact}")
        lines.append("")
        for f in items:
            title = f.get("title", f.get("defect_key", "?"))
            detail = f.get("detail", "")
            conf = f.get("confidence", 0)
            page = f.get("page_url", "")
            lines.append(f"- **{title}** (confidence: {conf:.0%})")
            if page:
                lines.append(f"  - Page: {page}")
            if detail:
                lines.append(f"  - {detail}")
        lines.append("")

    # Location Pages
    if report.location_pages:
        lines.append("## Location Pages")
        lines.append("")
        for lp in report.location_pages:
            classification = lp.get("classification", "?")
            url = lp.get("url", "")
            conf = lp.get("confidence", 0)
            lines.append(f"- **{url}** — {classification} ({conf:.0%})")
        lines.append("")

    # Contradictions
    if report.contradictions:
        lines.append("## Contradictions")
        lines.append("")
        for c in report.contradictions:
            field_name = c.get("field", "?")
            status = c.get("status", "?")
            schema = c.get("schema_value", "")
            visible = c.get("visible_value", "")
            lines.append(f"- **{field_name}**: {status}")
            lines.append(f"  - Schema: `{schema}`")
            lines.append(f"  - Visible: `{visible}`")
        lines.append("")

    # Geo Corroboration
    if report.geo_corroboration:
        lines.append("## Geographic Corroboration")
        lines.append("")
        for g in report.geo_corroboration:
            status = g.get("status", "?")
            dist = g.get("distance_km", 0)
            lines.append(f"- **Status:** {status} ({dist:.3f} km)")
            if g.get("detail"):
                lines.append(f"  - {g['detail']}")
        lines.append("")

    # Corroboration
    if report.corroboration:
        lines.append("## External Corroboration")
        lines.append("")
        overall = report.corroboration.get("overall_confidence", 0)
        lines.append(f"**Overall external confidence:** {overall:.0%}")
        matches = report.corroboration.get("matches", [])
        conflicts = report.corroboration.get("conflicts", [])
        lines.append(f"- **Matches:** {len(matches)}")
        lines.append(f"- **Conflicts:** {len(conflicts)}")
        lines.append("")

    lines.append("---")
    lines.append("*Generated by WEBSITE-AUDITOR Local SEO v38*")

    return "\n".join(lines)


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

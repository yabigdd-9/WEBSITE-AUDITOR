"""Technology enrichment report generation — JSON and Markdown output."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schema import (
    SeverityLevel,
    TechEnrichmentResult,
    TechStack,
)


def generate_report(result: TechEnrichmentResult) -> str:
    """Generate Markdown technology report."""
    lines = [
        f"# Technology Report — {result.url}",
        "",
        f"**Run ID:** {result.run_id}",
        f"**Completed:** {result.completed_at}",
        f"**Duration:** {result.duration_seconds:.1f}s",
        "",
        "## Detected Technologies",
        "",
    ]

    _append_detections(lines, result.fingerprint)
    _append_versions(lines, result.versions)
    _append_vulnerabilities(lines, result.vulnerabilities)
    if result.errors:
        lines.extend(["", "## Errors", "", *(f"- {error}" for error in result.errors)])

    lines.append("")
    return "\n".join(lines)


def _append_detections(lines: list[str], fp) -> None:
    for label, detection in (
        ("CMS", fp.cms),
        ("Framework", fp.framework),
        ("Server", fp.server),
        ("CDN", fp.cdn),
        ("E-commerce", fp.ecommerce),
        ("Language", fp.language),
    ):
        if detection and detection.confidence > 0:
            confidence = (
                f" ({detection.confidence:.0%})"
                if label in {"CMS", "Framework", "Language"}
                else ""
            )
            lines.append(f"- **{label}:** {detection.name}{confidence}")
    if fp.analytics:
        lines.append(f"- **Analytics:** {', '.join(item.name for item in fp.analytics)}")
    if fp.payment:
        lines.append(f"- **Payment:** {', '.join(item.name for item in fp.payment)}")


def _append_versions(lines: list[str], versions) -> None:
    lines.extend(["", "## Version Status", ""])
    if not versions:
        lines.append("- No version information detected.")
        return
    for version in versions:
        status = "⚠️ OUTDATED" if version.is_outdated else "✅ Current"
        lines.append(
            f"- **{version.name}**: {version.detected_version or 'unknown'} "
            f"(latest: {version.latest_version or 'unknown'}) — {status}"
        )


def _append_vulnerabilities(lines: list[str], vulnerabilities) -> None:
    lines.extend(["", "## Vulnerability Advisories", ""])
    if not vulnerabilities:
        lines.append("- No known vulnerabilities detected.")
        return
    for advisory in vulnerabilities:
        lines.append(
            f"- **{advisory.severity.upper()}**: {advisory.component} "
            f"{advisory.version} — {advisory.cve_id}"
        )
        lines.append(f"  - {advisory.description}")
        lines.append(f"  - Remediation: {advisory.remediation}")


def save_report(
    result: TechEnrichmentResult,
    output_dir: Path,
    run_id: str | None = None,
) -> tuple[Path, Path]:
    """Save JSON and Markdown reports."""
    rid = run_id or result.run_id or "unknown"
    output_dir.mkdir(parents=True, exist_ok=True)

    # JSON report
    json_path = output_dir / f"{rid}.json"
    json_path.write_text(json.dumps(result.to_dict(), indent=2))

    # Markdown report
    md_path = output_dir / f"{rid}.md"
    md_path.write_text(generate_report(result))

    return json_path, md_path


# ---------------------------------------------------------------------------
# Additional report helpers
# ---------------------------------------------------------------------------


def _severity_icon(severity: SeverityLevel) -> str:
    return {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(severity, "⚪")


def _severity_rank(severity: SeverityLevel) -> int:
    return {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(severity, 0)


def generate_json_report(result: TechEnrichmentResult) -> str:
    """Generate a JSON report with summary metadata."""
    data = result.to_dict()
    data["report_type"] = "technology_enrichment"
    data["report_version"] = "1.0"
    data["generated_at"] = datetime.now(timezone.utc).isoformat()
    data["summary"] = _build_summary(result)
    return json.dumps(data, indent=2, default=str)


def _build_summary(result: TechEnrichmentResult) -> dict[str, Any]:
    sev: dict[str, int] = {}
    for v in result.vulnerabilities:
        sev[v.severity] = sev.get(v.severity, 0) + 1
    return {
        "total_technologies_detected": len(result.fingerprint.all_detections),
        "total_versions_detected": len(result.versions),
        "outdated_components": sum(1 for v in result.versions if v.is_outdated),
        "total_vulnerabilities": len(result.vulnerabilities),
        "severity_breakdown": sev,
    }


def generate_stack_summary_markdown(stack: TechStack) -> str:
    """Generate a concise Markdown summary from a TechStack."""
    lines = ["# Technology Stack Summary\n", "## Detected Technologies\n"]
    fp = stack.fingerprint
    _app(lines, "CMS", fp.cms)
    _app(lines, "Framework", fp.framework)
    _app(lines, "Language", fp.language)
    _app(lines, "Server", fp.server)
    _app(lines, "CDN", fp.cdn)
    _app(lines, "E-commerce", fp.ecommerce)
    _app(lines, "Hosting", fp.hosting)
    if fp.analytics:
        lines.append("- **Analytics:** " + ", ".join(a.name for a in fp.analytics))
    if fp.payment:
        lines.append("- **Payment:** " + ", ".join(p.name for p in fp.payment))
    lines.append("")

    if stack.versions:
        lines.append("## Version Status\n")
        for v in stack.versions:
            status = "⚠️ outdated" if v.is_outdated else "✅ current"
            lines.append(f"- **{v.name}:** {v.detected_version} ({status})")
        lines.append("")

    if stack.vulnerabilities:
        lines.append("## Vulnerabilities\n")
        for adv in stack.vulnerabilities:
            icon = _severity_icon(adv.severity)
            cve = f" ({adv.cve_id})" if adv.cve_id else ""
            lines.append(f"- {icon} **{adv.component}{cve}:** {adv.description[:100]}")
        lines.append("")

    return "\n".join(lines)


def _app(lines: list[str], label: str, det: Any | None) -> None:
    if det:
        lines.append(f"- **{label}:** {det.name} ({det.confidence:.0%})")
    else:
        lines.append(f"- **{label}:** Not detected")

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .common import atomic_write_text


def render_html_report(report: dict[str, Any]) -> str:
    rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(d.get('severity', ''))}</td>"
        f"<td>{html.escape(d.get('defect', ''))}</td>"
        f"<td>{html.escape(d.get('impact', ''))}</td>"
        f"<td>{html.escape(d.get('check', ''))}</td>"
        "</tr>"
        for d in report.get("defects", [])
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Website audit - {html.escape(str(report.get('domain') or 'site'))}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; margin: 2rem; color: #1f2933; }}
table {{ width: 100%; border-collapse: collapse; }}
th,td {{ border-bottom: 1px solid #e6eef6; padding: .55rem; text-align: left; vertical-align: top; }}
.score {{ display: inline-block; border: 1px solid #d9e2ec; border-radius: 8px; padding: 1rem; margin-right: .5rem; }}
</style></head><body>
<h1>{html.escape(str(report.get("brand", "Website Audit")))}</h1>
<p>Status: {html.escape(report["status"])} · Findings: {report["defect_count"]} · Coverage: {html.escape(str(report.get("coverage", "pending")))}</p>
<p><code>{html.escape(str(report.get('url') or ''))}</code></p>
<div class="score"><strong>Health</strong><br>{html.escape(str(report.get('health_score')))}</div>
<div class="score"><strong>Defect severity</strong><br>{html.escape(str(report.get('severity_score')))}</div>
<h2>Findings</h2>
<table><thead><tr><th>Severity</th><th>Finding</th><th>Evidence</th><th>Check</th></tr></thead><tbody>{rows}</tbody></table>
<h2>Checks and coverage</h2><pre>{html.escape(json.dumps(report.get("checks", {}), indent=2))}</pre>
<h2>Category scores</h2><pre>{html.escape(json.dumps(report.get("category_scores", {}), indent=2))}</pre>
<h2>Historical comparison</h2><pre>{html.escape(json.dumps(report.get("comparison", {}), indent=2))}</pre>
<h2>Evidence</h2><pre style="white-space:pre-wrap;overflow-wrap:anywhere">{html.escape(json.dumps(report.get("evidence", {}), indent=2, ensure_ascii=False))}</pre>
<h2>Drafts for review</h2><pre style="white-space:pre-wrap">{html.escape(json.dumps(report.get("drafts", {}), indent=2, ensure_ascii=False))}</pre>
<h2>Proposal Inputs</h2><pre>{html.escape(json.dumps(report.get("proposal", {}), indent=2))}</pre>
<p>Financial scenarios use explicit editable assumptions. They are not measured lost revenue or fines.</p>
</body></html>
"""


def render_trend_svg(report: dict[str, Any]) -> str:
    health = report.get("health_score")
    if health is None:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="220" height="40"><text x="10" y="25">Health unavailable — partial audit</text></svg>'
    width = max(4, int(health * 2))
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="220" height="40">'
        '<rect width="200" height="12" x="10" y="14" fill="#d9e2ec"/>'
        f'<rect width="{width}" height="12" x="10" y="14" fill="#0f766e"/>'
        f'<text x="10" y="38" font-size="10">Health {health}</text></svg>\n'
    )


def write_html_report(report: dict[str, Any], path: Path) -> None:
    atomic_write_text(path, render_html_report(report))


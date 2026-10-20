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
    root_causes = "".join(
        f"<li><strong>{html.escape(str(item.get('root_cause_id')))}</strong> — "
        f"{item.get('symptom_count', 0)} symptom(s), confidence "
        f"{html.escape(str(item.get('confidence', 'UNKNOWN')))}: "
        f"{html.escape(str(item.get('explanation', '')))}</li>"
        for item in report.get("fault_taxonomy", {}).get("root_causes", [])
    ) or "<li>No grouped root causes recorded.</li>"
    claims = "".join(
        f"<tr><td>{html.escape(str(item.get('claim_id')))}</td>"
        f"<td>{html.escape(str(item.get('claim')))}</td>"
        f"<td>{html.escape(str(item.get('confidence')))}</td>"
        f"<td>{html.escape(str(item.get('evidence_ref')))}</td></tr>"
        for item in report.get("claim_ledger", [])
    ) or '<tr><td colspan="4">No claim ledger entries.</td></tr>'
    proofing = "".join(
        f"<li>{html.escape(key)}: {html.escape(str(value.get('errors', [])))}; "
        f"references {html.escape(str(value.get('referenced_claim_ids', [])))}</li>"
        for key, value in report.get("proofing", {}).items()
    ) or "<li>Draft proofing was not requested.</li>"
    visual = report.get("evidence", {}).get("browser", {}).get("visual_pack", {})
    visual_rows = "".join(
        f"<li>{html.escape(str(name))}: {html.escape(str(item.get('path')))} "
        f"({html.escape(str(item.get('sha256', ''))[:16])}…)</li>"
        for name, item in visual.get("viewports", {}).items()
    ) or "<li>No rendered visual pack; enable the rendered profile.</li>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Website audit - {html.escape(str(report.get("domain") or "site"))}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; margin: 2rem; color: #1f2933; }}
table {{ width: 100%; border-collapse: collapse; }}
th,td {{ border-bottom: 1px solid #e6eef6; padding: .55rem; text-align: left; vertical-align: top; }}
.score {{ display: inline-block; border: 1px solid #d9e2ec; border-radius: 8px; padding: 1rem; margin-right: .5rem; }}
</style></head><body>
<h1>{html.escape(str(report.get("brand", "Website Audit")))}</h1>
<p>Status: {html.escape(report["status"])} · Findings: {report["defect_count"]} · Coverage: {html.escape(str(report.get("coverage", "pending")))}</p>
<p><code>{html.escape(str(report.get("url") or ""))}</code></p>
<div class="score"><strong>Health</strong><br>{html.escape(str(report.get("health_score")))}</div>
<div class="score"><strong>Defect severity</strong><br>{html.escape(str(report.get("severity_score")))}</div><h2>Findings</h2>
<table><thead><tr><th>Severity</th><th>Finding</th><th>Evidence</th><th>Check</th></tr></thead><tbody>{rows}</tbody></table>
<h2>Root-cause groups</h2><ul>{root_causes}</ul>
<h2>Visual evidence pack</h2><ul>{visual_rows}</ul>
<h2>Claim ledger</h2><table><thead><tr><th>Claim ID</th><th>Claim</th><th>Confidence</th><th>Evidence ref</th></tr></thead><tbody>{claims}</tbody></table>
<h2>Draft proofing</h2><ul>{proofing}</ul>
<h2>Checks and coverage</h2>
<pre>{html.escape(json.dumps(report.get("checks", {}), indent=2))}</pre>
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

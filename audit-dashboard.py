#!/usr/bin/env python3
"""Accessible, injection-safe client dashboard for Website Auditor results."""
from __future__ import annotations

import argparse
import html
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
AUDITS = ROOT / "audits"

SCORE_COLORS = {
    "HOT": "#00D4A3",
    "WARM": "#FF8A00",
    "NURTURE": "#FFC107",
    "COLD": "#FF1A1A",
}


def tier_for_opportunity(score: int | float) -> str:
    score = float(score or 0)
    return "HOT" if score >= 80 else "WARM" if score >= 60 else "NURTURE" if score >= 40 else "COLD"


def esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def safe_external_url(audit: dict) -> str:
    candidate = str(audit.get("url") or "")
    try:
        parsed = urlparse(candidate)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return candidate
    except Exception:
        pass
    domain = str(audit.get("domain") or "")
    return "https://" + domain if domain else "#"


def health_score(audit: dict) -> int | None:
    value = (audit.get("category_scores") or {}).get("overall_health_score")
    return int(value) if isinstance(value, (int, float)) else None


def load_audits(audits_dir: str | Path | None = None) -> list[dict]:
    audits_path = Path(audits_dir) if audits_dir else AUDITS
    results: list[dict] = []
    for path in sorted(audits_path.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            if isinstance(data, dict) and "domain" in data:
                results.append(data)
        except (OSError, json.JSONDecodeError):
            continue
    return results


def load_emails(email_path: str | Path | None = None) -> dict:
    path = Path(email_path) if email_path else ROOT / "email-discovery.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text())
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _finding_labels(audit: dict) -> list[str]:
    findings = audit.get("findings")
    if isinstance(findings, list) and findings:
        return [
            str(item.get("check_id") or item.get("message") or "unknown")
            for item in findings
            if isinstance(item, dict)
        ]
    return [
        str(item.get("defect_key") or item.get("defect") or "unknown")
        for item in audit.get("defects", [])
        if isinstance(item, dict)
    ]


def _top_issues(audit: dict, limit: int = 3) -> list[str]:
    findings = audit.get("findings")
    if isinstance(findings, list) and findings:
        return [
            str(item.get("message") or item.get("check_id") or "")
            for item in findings[:limit]
            if isinstance(item, dict)
        ]
    return [
        str(item.get("defect") or "")
        for item in audit.get("defects", [])[:limit]
        if isinstance(item, dict)
    ]


def generate_dashboard(audits: list[dict], emails: dict, title: str = "Website Audit Dashboard") -> str:
    total = len(audits)
    opportunity_scores = [float(a.get("score", 0) or 0) for a in audits]
    health_scores = [health_score(a) for a in audits]
    health_values = [value for value in health_scores if value is not None]
    avg_opportunity = sum(opportunity_scores) / total if total else 0
    avg_health = sum(health_values) / len(health_values) if health_values else None
    total_defects = sum(int(a.get("defect_count", len(a.get("defects", []))) or 0) for a in audits)

    tiers: dict[str, int] = defaultdict(int)
    for audit in audits:
        tiers[tier_for_opportunity(audit.get("score", 0))] += 1

    rows: list[str] = []
    for index, audit in enumerate(sorted(audits, key=lambda item: item.get("score", 0), reverse=True), 1):
        domain = str(audit.get("domain") or "unknown")
        opportunity = int(audit.get("score", 0) or 0)
        health = health_score(audit)
        tier = tier_for_opportunity(opportunity)
        color = SCORE_COLORS[tier]
        defect_count = int(audit.get("defect_count", len(audit.get("defects", []))) or 0)
        issues = "; ".join(_top_issues(audit))
        email_info = emails.get(domain, {}) if isinstance(emails, dict) else {}
        best_email = email_info.get("best", "N/A") if isinstance(email_info, dict) else "N/A"
        timestamp = str(audit.get("timestamp") or "")[:10]
        profile = (audit.get("audit_profile") or {}).get("name", "legacy")
        site_type = (audit.get("site_type") or {}).get("site_type", "unknown")
        url = safe_external_url(audit)
        health_text = str(health) if health is not None else "—"

        rows.append(
            f"""<tr class="tier-{tier.lower()}">
<td>{index}</td>
<td><a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(domain)}</a></td>
<td class="num" style="color:{color}">{opportunity}</td>
<td class="num">{health_text}</td>
<td><span class="badge">{esc(tier)}</span></td>
<td class="num">{defect_count}</td>
<td>{esc(profile)}</td>
<td>{esc(site_type)}</td>
<td class="issues">{esc(issues)}</td>
<td><code>{esc(best_email)}</code></td>
<td>{esc(timestamp)}</td>
</tr>"""
        )

    defect_counts: dict[str, int] = defaultdict(int)
    for audit in audits:
        for label in _finding_labels(audit):
            defect_counts[label] += 1

    defect_bars: list[str] = []
    for defect, count in sorted(defect_counts.items(), key=lambda item: (-item[1], item[0])):
        pct = (count / total * 100) if total else 0
        defect_bars.append(
            f"""<div class="defect-bar">
<span class="defect-name">{esc(defect)}</span>
<div class="bar-bg" role="img" aria-label="{esc(defect)} affects {count} sites">
<div class="bar-fill" style="width:{pct:.0f}%"></div></div>
<span class="defect-count">{count} ({pct:.0f}%)</span>
</div>"""
        )

    health_card = f"{avg_health:.0f}" if avg_health is not None else "—"
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'; object-src 'none'; frame-src 'none'">
<title>{esc(title)}</title>
<style>
:root {{ color-scheme: dark; }}
* {{ box-sizing: border-box; }}
body {{ font-family: system-ui,-apple-system,sans-serif; background:#0f0f1a; color:#e8e8ed; margin:0; padding:20px; }}
a {{ color:#7dd3fc; }}
a:focus,button:focus,input:focus,select:focus {{ outline:3px solid currentColor; outline-offset:2px; }}
h1,h2 {{ color:#fff; }}
.subtitle {{ color:#a1a1aa; }}
.stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(145px,1fr)); gap:12px; margin:20px 0; }}
.card {{ background:#191928; border:1px solid #35354a; border-radius:10px; padding:14px; }}
.card .value {{ font-size:2rem; font-weight:750; }}
.card .label {{ color:#b4b4c1; font-size:.85rem; }}
.section {{ margin:28px 0; }}
.controls {{ display:flex; gap:10px; flex-wrap:wrap; margin:12px 0; }}
input,select,button {{ background:#191928; color:#fff; border:1px solid #45455c; border-radius:6px; padding:9px 11px; }}
.table-wrap {{ overflow:auto; border:1px solid #35354a; border-radius:10px; }}
table {{ width:100%; border-collapse:collapse; min-width:1100px; background:#171725; }}
caption {{ text-align:left; padding:10px; color:#c4c4cf; }}
th,td {{ padding:9px 11px; border-bottom:1px solid #2d2d3f; text-align:left; vertical-align:top; }}
th {{ position:sticky; top:0; background:#242438; }}
.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
.issues {{ max-width:360px; color:#c4c4cf; }}
.badge {{ font-size:.78rem; font-weight:700; }}
code {{ white-space:nowrap; }}
.defect-bar {{ display:grid; grid-template-columns:minmax(180px,280px) 1fr 90px; gap:10px; align-items:center; margin:7px 0; }}
.defect-name {{ overflow-wrap:anywhere; }}
.bar-bg {{ background:#252536; height:18px; border-radius:4px; overflow:hidden; }}
.bar-fill {{ background:linear-gradient(90deg,#f87171,#fbbf24,#34d399); height:100%; }}
.footer {{ color:#8f8f9e; border-top:1px solid #35354a; padding-top:14px; margin-top:28px; }}
@media (max-width:700px) {{ .defect-bar {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<main>
<h1>{esc(title)}</h1>
<p class="subtitle">Generated {esc(generated)} · {total} sites. Opportunity score remains backward-compatible (100 = more defects/opportunity); health score uses the new transparent category model (100 = healthier).</p>

<div class="stats">
<div class="card"><div class="value">{avg_opportunity:.0f}</div><div class="label">Avg opportunity score</div></div>
<div class="card"><div class="value">{health_card}</div><div class="label">Avg health score</div></div>
<div class="card"><div class="value">{total_defects}</div><div class="label">Total findings</div></div>
<div class="card"><div class="value">{tiers.get("HOT",0)}</div><div class="label">HOT opportunities</div></div>
</div>

<section class="section" aria-labelledby="distribution-title">
<h2 id="distribution-title">Stable finding distribution</h2>
{"".join(defect_bars) or "<p>No findings loaded.</p>"}
</section>

<section class="section" aria-labelledby="sites-title">
<h2 id="sites-title">Sites</h2>
<div class="controls">
<label>Search <input id="search" type="search" autocomplete="off"></label>
<label>Tier <select id="tierFilter"><option value="">All</option><option>HOT</option><option>WARM</option><option>NURTURE</option><option>COLD</option></select></label>
<label>Sort <select id="sortBy"><option value="opp-desc">Opportunity ↓</option><option value="opp-asc">Opportunity ↑</option><option value="health-desc">Health ↓</option><option value="defects-desc">Findings ↓</option></select></label>
<button id="csvButton" type="button">Export visible CSV</button>
</div>
<div class="table-wrap">
<table id="auditTable">
<caption>Website audit portfolio. All audited strings are HTML-escaped before rendering.</caption>
<thead><tr><th>#</th><th>Domain</th><th>Opportunity</th><th>Health</th><th>Tier</th><th>Findings</th><th>Profile</th><th>Site type</th><th>Top issues</th><th>Email</th><th>Date</th></tr></thead>
<tbody>{"".join(rows)}</tbody>
</table>
</div>
</section>
<p class="footer">Evidence-first Website Auditor · self-contained dashboard · no external scripts or CDN dependencies.</p>
</main>
<script>
"use strict";
const table = document.getElementById("auditTable");
const tbody = table.tBodies[0];
function visibleRows() {{ return [...tbody.rows].filter(r => !r.hidden); }}
function filterRows() {{
  const q = document.getElementById("search").value.toLowerCase();
  const tier = document.getElementById("tierFilter").value;
  [...tbody.rows].forEach(row => {{
    const matchesText = row.cells[1].textContent.toLowerCase().includes(q);
    const matchesTier = !tier || row.cells[4].textContent.trim() === tier;
    row.hidden = !(matchesText && matchesTier);
  }});
}}
function num(row, index) {{
  const v = Number(row.cells[index].textContent.trim());
  return Number.isFinite(v) ? v : -1;
}}
function sortRows() {{
  const method = document.getElementById("sortBy").value;
  const rows = [...tbody.rows];
  rows.sort((a,b) => {{
    if (method === "opp-asc") return num(a,2)-num(b,2);
    if (method === "health-desc") return num(b,3)-num(a,3);
    if (method === "defects-desc") return num(b,5)-num(a,5);
    return num(b,2)-num(a,2);
  }});
  rows.forEach(row => tbody.appendChild(row));
}}
function csvCell(value) {{ return '"' + String(value).replaceAll('"','""') + '"'; }}
function exportCSV() {{
  const headers = [...table.tHead.rows[0].cells].map(c => csvCell(c.textContent.trim()));
  const lines = [headers.join(",")];
  visibleRows().forEach(row => lines.push([...row.cells].map(c => csvCell(c.textContent.trim())).join(",")));
  const blob = new Blob([lines.join("\\n")], {{type:"text/csv;charset=utf-8"}});
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url; anchor.download = "audit-export.csv"; anchor.click();
  URL.revokeObjectURL(url);
}}
document.getElementById("search").addEventListener("input", filterRows);
document.getElementById("tierFilter").addEventListener("change", filterRows);
document.getElementById("sortBy").addEventListener("change", sortRows);
document.getElementById("csvButton").addEventListener("click", exportCSV);
</script>
</body>
</html>"""


def run_dashboard(audits_dir=None, output=None, email_file=None) -> Path:
    audits = load_audits(audits_dir)
    emails = load_emails(email_file)
    destination = Path(output) if output else ROOT / "outputs" / "dashboard.html"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(generate_dashboard(audits, emails))
    print(f"Dashboard saved: {destination} ({len(audits)} sites)")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Dashboard Generator")
    parser.add_argument("--output", "-o", default="outputs/dashboard.html")
    parser.add_argument("--audits-dir", default="audits")
    parser.add_argument("--email-file")
    args = parser.parse_args()
    run_dashboard(args.audits_dir, args.output, args.email_file)


if __name__ == "__main__":
    main()

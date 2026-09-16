#!/usr/bin/env python3
"""Audit Dashboard — interactive HTML dashboard from audit data.

Usage:
    python3 audit-dashboard.py                  # dashboard from audits/
    python3 audit-dashboard.py --output report.html
    python3 audit-dashboard.py --email email-discovery.json

Generates a self-contained HTML file with:
  - Score distribution chart (color-coded)
  - Sortable/filterable defect table
  - Trend comparison (if multiple audits per domain)
  - Email contact list with verification status
  - Export buttons (CSV, JSON)
"""

import argparse, json, os, re, sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

ROOT = Path(__file__).resolve().parent
AUDITS = ROOT / "audits"

# Color mapping
SCORE_COLORS = {
    "HOT": "#00D4A3", "WARM": "#FF8A00", "NURTURE": "#FFC107", "COLD": "#FF1A1A"
}

TIER_MAP = lambda s: "HOT" if s >= 80 else "WARM" if s >= 60 else "NURTURE" if s >= 40 else "COLD"

def load_audits(audits_dir=None):
    """Load all audit JSON files."""
    audits_path = Path(audits_dir) if audits_dir else AUDITS
    results = []
    for aj in sorted(audits_path.glob("*.json")):
        try:
            data = json.loads(aj.read_text())
            if "domain" in data:  # skip non-audit JSON files
                results.append(data)
        except Exception:
            continue
    return results

def load_emails(email_path=None):
    """Load email discovery results."""
    if email_path:
        p = Path(email_path)
        if p.exists():
            return json.loads(p.read_text())
    email_path = ROOT / "email-discovery.json"
    if email_path.exists():
        return json.loads(email_path.read_text())
    return {}

def generate_dashboard(audits, emails, title="Website Audit Dashboard"):
    """Generate self-contained HTML dashboard."""

    # Stats
    total = len(audits)
    avg_score = sum(a.get("score", 0) for a in audits) / total if total > 0 else 0
    total_defects = sum(a.get("defect_count", 0) for a in audits)
    tiers = defaultdict(int)
    for a in audits:
        tiers[TIER_MAP(a.get("score", 0))] += 1

    # Build rows
    rows = ""
    for i, a in enumerate(sorted(audits, key=lambda x: x.get("score", 0)), 1):
        domain = a.get("domain", "unknown")
        score = a.get("score", 0)
        tier = TIER_MAP(score)
        color = SCORE_COLORS.get(tier, "#888")
        defects = a.get("defects", [])
        defect_list = "; ".join(d.get("defect", "")[:60] for d in defects[:3])
        email_info = emails.get(domain, {})
        best_email = email_info.get("best", "N/A")
        timestamp = a.get("timestamp", "")[:10]

        rows += f'''<tr class="tier-{tier.lower()}">
            <td>{i}</td>
            <td><a href="https://{domain}" target="_blank">{domain}</a></td>
            <td style="color:{color};font-weight:bold">{score}</td>
            <td><span class="badge tier-{tier.lower()}">{tier}</span></td>
            <td>{len(defects)}</td>
            <td class="defects">{defect_list}</td>
            <td><code>{best_email}</code></td>
            <td>{timestamp}</td>
        </tr>'''

    # Defect distribution
    defect_counts = defaultdict(int)
    for a in audits:
        for d in a.get("defects", []):
            key = d.get("defect_key", d.get("defect", "unknown"))
            defect_counts[key] += 1

    defect_bars = ""
    for defect, count in sorted(defect_counts.items(), key=lambda x: -x[1]):
        pct = count / total * 100 if total > 0 else 0
        defect_bars += f'''<div class="defect-bar">
            <span class="defect-name">{defect}</span>
            <div class="bar-bg"><div class="bar-fill" style="width:{pct:.0f}%"></div></div>
            <span class="defect-count">{count} ({pct:.0f}%)</span>
        </div>'''

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f0f1a; color: #e0e0e0; padding: 20px; }}
h1 {{ color: #fff; margin-bottom: 5px; }}
.subtitle {{ color: #888; margin-bottom: 20px; font-size: 0.9em; }}
.stats {{ display: flex; gap: 15px; flex-wrap: wrap; margin-bottom: 25px; }}
.stat-card {{ background: #1a1a2e; border-radius: 10px; padding: 15px 20px; min-width: 140px; text-align: center; border: 1px solid #333; }}
.stat-card .value {{ font-size: 2em; font-weight: bold; color: #fff; }}
.stat-card .label {{ color: #888; font-size: 0.8em; margin-top: 5px; }}
.stat-card.hot .value {{ color: #00D4A3; }}
.stat-card.warm .value {{ color: #FF8A00; }}
.stat-card.nurture .value {{ color: #FFC107; }}
.stat-card.cold .value {{ color: #FF1A1A; }}

.filters {{ display: flex; gap: 10px; margin-bottom: 15px; flex-wrap: wrap; align-items: center; }}
.filters input, .filters select {{ background: #1a1a2e; border: 1px solid #333; color: #e0e0e0; padding: 8px 12px; border-radius: 6px; font-size: 0.9em; }}
.filters input {{ width: 250px; }}

table {{ width: 100%; border-collapse: collapse; background: #1a1a2e; border-radius: 10px; overflow: hidden; }}
th {{ background: #2a2a3e; color: #fff; padding: 10px 12px; text-align: left; cursor: pointer; user-select: none; }}
th:hover {{ background: #3a3a4e; }}
td {{ padding: 8px 12px; border-bottom: 1px solid #222; font-size: 0.9em; }}
tr:hover {{ background: #222; }}
.defects {{ max-width: 300px; font-size: 0.85em; color: #aaa; }}
.badge {{ padding: 3px 8px; border-radius: 4px; font-size: 0.75em; font-weight: bold; }}
.badge.hot {{ background: #00D4A320; color: #00D4A3; }}
.badge.warm {{ background: #FF8A0020; color: #FF8A00; }}
.badge.nurture {{ background: #FFC10720; color: #FFC107; }}
.badge.cold {{ background: #FF1A1A20; color: #FF1A1A; }}
code {{ background: #222; padding: 2px 6px; border-radius: 3px; font-size: 0.85em; }}
a {{ color: #4fc3f7; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}

.defect-bar {{ display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }}
.defect-name {{ width: 220px; font-size: 0.85em; text-align: right; }}
.bar-bg {{ flex: 1; background: #222; border-radius: 4px; height: 18px; overflow: hidden; }}
.bar-fill {{ height: 100%; background: linear-gradient(90deg, #FF1A1A, #FF8A00, #00D4A3); border-radius: 4px; transition: width 0.5s; }}
.defect-count {{ width: 60px; font-size: 0.85em; color: #888; }}

.section {{ margin-bottom: 30px; }}
.section h2 {{ color: #fff; margin-bottom: 10px; font-size: 1.2em; }}

.export-btns {{ margin-top: 15px; display: flex; gap: 10px; }}
.export-btns button {{ background: #2a2a3e; color: #e0e0e0; border: 1px solid #333; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 0.9em; }}
.export-btns button:hover {{ background: #3a3a4e; }}

.footer {{ margin-top: 30px; padding-top: 15px; border-top: 1px solid #333; color: #666; font-size: 0.8em; text-align: center; }}
</style>
</head>
<body>
<h1>🔍 {title}</h1>
<p class="subtitle">Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")} | {total} sites audited</p>

<div class="stats">
    <div class="stat-card">
        <div class="value">{avg_score:.0f}</div>
        <div class="label">Average Score</div>
    </div>
    <div class="stat-card hot">
        <div class="value">{tiers.get("HOT", 0)}</div>
        <div class="label">🔥 Hot</div>
    </div>
    <div class="stat-card warm">
        <div class="value">{tiers.get("WARM", 0)}</div>
        <div class="label">🌡️ Warm</div>
    </div>
    <div class="stat-card nurture">
        <div class="value">{tiers.get("NURTURE", 0)}</div>
        <div class="label">📊 Nurture</div>
    </div>
    <div class="stat-card cold">
        <div class="value">{tiers.get("COLD", 0)}</div>
        <div class="label">❄️ Cold</div>
    </div>
    <div class="stat-card">
        <div class="value">{total_defects}</div>
        <div class="label">Total Defects</div>
    </div>
</div>

<div class="section">
    <h2>📊 Defect Distribution</h2>
    {defect_bars}
</div>

<div class="section">
    <h2>📋 Site Audit Table</h2>
    <div class="filters">
        <input type="text" id="search" placeholder="🔍 Filter domains..." onkeyup="filterTable()">
        <select id="tierFilter" onchange="filterTable()">
            <option value="">All Tiers</option>
            <option value="hot">🔥 Hot</option>
            <option value="warm">🌡️ Warm</option>
            <option value="nurture">📊 Nurture</option>
            <option value="cold">❄️ Cold</option>
        </select>
        <select id="sortScore" onchange="sortTable(this.value)">
            <option value="score-asc">Score ↑</option>
            <option value="score-desc">Score ↓</option>
            <option value="defects-asc">Fewest Defects</option>
            <option value="defects-desc">Most Defects</option>
        </select>
    </div>
    <table id="auditTable">
        <thead><tr>
            <th>#</th><th>Domain</th><th>Score</th><th>Tier</th><th>Defects</th><th>Top Issues</th><th>Email</th><th>Date</th>
        </tr></thead>
        <tbody>{rows}</tbody>
    </table>
    <div class="export-btns">
        <button onclick="exportCSV()">📥 Export CSV</button>
        <button onclick="exportJSON()">📥 Export JSON</button>
    </div>
</div>

<div class="footer">
    Generated by CATALYX Audit Dashboard | All data from public audits | <a href="https://github.com/yabigdd-9/WEBSITE-AUDITOR" target="_blank">GitHub Repo</a>
</div>

<script>
function filterTable() {{
    const search = document.getElementById('search').value.toLowerCase();
    const tier = document.getElementById('tierFilter').value;
    const rows = document.querySelectorAll('#auditTable tbody tr');
    rows.forEach(row => {{
        const domain = row.cells[1].textContent.toLowerCase();
        const rowTier = row.classList.contains('tier-' + tier);
        const matchSearch = domain.includes(search);
        const matchTier = !tier || rowTier;
        row.style.display = (matchSearch && matchTier) ? '' : 'none';
    }});
}}
function sortTable(method) {{
    const tbody = document.querySelector('#auditTable tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    rows.sort((a, b) => {{
        const scoreA = parseInt(a.cells[2].textContent) || 0;
        const scoreB = parseInt(b.cells[2].textContent) || 0;
        const defA = parseInt(a.cells[4].textContent) || 0;
        const defB = parseInt(b.cells[4].textContent) || 0;
        if (method === 'score-asc') return scoreA - scoreB;
        if (method === 'score-desc') return scoreB - scoreA;
        if (method === 'defects-asc') return defA - defB;
        if (method === 'defects-desc') return defB - defA;
        return 0;
    }});
    rows.forEach(r => tbody.appendChild(r));
}}
function exportCSV() {{
    const rows = document.querySelectorAll('#auditTable tbody tr');
    let csv = 'Rank,Domain,Score,Tier,Defects,Email\\n';
    rows.forEach(r => {{
        if (r.style.display !== 'none') {{
            csv += `${{r.cells[0].textContent}},${{r.cells[1].textContent}},${{r.cells[2].textContent}},${{r.cells[3].textContent.textContent}},${{r.cells[4].textContent}},${{r.cells[6].textContent}}\\n`;
        }}
    }});
    downloadFile(csv, 'audit-export.csv', 'text/csv');
}}
function exportJSON() {{
    const rows = document.querySelectorAll('#auditTable tbody tr');
    const data = [];
    rows.forEach(r => {{
        if (r.style.display !== 'none') {{
            data.push({{
                domain: r.cells[1].textContent,
                score: r.cells[2].textContent,
                tier: r.cells[3].querySelector('.badge').textContent,
                defects: r.cells[4].textContent,
                email: r.cells[6].textContent
            }});
        }}
    }});
    downloadFile(JSON.stringify(data, null, 2), 'audit-export.json', 'application/json');
}}
function downloadFile(content, filename, type) {{
    const blob = new Blob([content], {{type}});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
}}
</script>
</body>
</html>'''

    return html

def run_dashboard(audits_dir=None, output=None, email_file=None):
    """Generate and save dashboard."""
    audits = load_audits(audits_dir)
    emails = load_emails(email_file)

    print(f"📊 Dashboard: {len(audits)} sites, {len(emails)} email contacts loaded")

    html = generate_dashboard(audits, emails)

    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html)
        print(f"✅ Dashboard saved: {out_path}")
    else:
        out_path = ROOT / "outputs" / "dashboard.html"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html)
        print(f"✅ Dashboard saved: {out_path}")

    # Print summary
    if audits:
        scores = [a.get("score", 0) for a in audits]
        print(f"   Avg score: {sum(scores)/len(scores):.0f}/100")
        print(f"   Range: {min(scores)}-{max(scores)}")
        tiers = defaultdict(int)
        for a in audits:
            tiers[TIER_MAP(a.get("score", 0))] += 1
        for t in ["HOT", "WARM", "NURTURE", "COLD"]:
            print(f"   {t}: {tiers.get(t, 0)} sites")

def main():
    parser = argparse.ArgumentParser(description="Audit Dashboard Generator")
    parser.add_argument("--output", "-o", default="outputs/dashboard.html", help="Output HTML file")
    parser.add_argument("--audits-dir", default="audits", help="Audit JSON directory")
    parser.add_argument("--email-file", help="Email discovery JSON file")
    args = parser.parse_args()

    run_dashboard(args.audits_dir, args.output, args.email_file)

if __name__ == "__main__":
    main()
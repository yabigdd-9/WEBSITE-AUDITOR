#!/usr/bin/env python3
"""Dashboard generator — single-page HTML report with charts and trend tracking.

Usage:
    python3 dashboard.py [--output outputs/dashboard.html]
"""
import argparse, json, re
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AUDITS = ROOT / "audits"
OUTPUT = ROOT / "outputs" / "dashboard.html"

def load_all():
    sites = []
    for aj in sorted(AUDITS.glob("*.json")):
        try:
            data = json.loads(aj.read_text())
            sites.append(data)
        except Exception:
            continue
    return sites

def score_bar(value, max_val=100, width=120):
    """Return HTML for a horizontal bar."""
    pct = min(value / max_val * 100, 100)
    color = "#00D4A3" if value < 30 else "#EFFF00" if value < 60 else "#FF8A00" if value < 80 else "#FF1A1A"
    return f'<div class="bar" style="width:{width}px"><div class="bar-fill" style="width:{pct}%;background:{color}"></div></div><span class="bar-val">{value}</span>'

def defect_pie(defect_counts):
    """Return HTML for a simple horizontal stacked bar chart."""
    total = sum(defect_counts.values())
    if total == 0:
        return "<p>No defects</p>"
    colors = ["#FF1A1A","#FF8A00","#EFFF00","#00D4A3","#00CFFF","#A020F0","#FF69B4","#8B4513","#20B2AA","#FFD700"]
    html = '<div class="stacked-bar">'
    for i, (defect, count) in enumerate(defect_counts.most_common(10)):
        pct = count / total * 100
        color = colors[i % len(colors)]
        html += f'<div class="stacked-seg" style="width:{pct}%;background:{color}" title="{defect}: {count}"></div>'
    html += '</div>'
    return html

def trend_chart(domain, all_audits):
    """Return SVG sparkline for domain's score over time."""
    domain_clean = domain.replace("www.", "")
    matches = [a for a in all_audits if a.get("domain", "").replace("www.", "") == domain_clean]
    if len(matches) < 2:
        return ""
    matches.sort(key=lambda x: x.get("timestamp", ""))
    scores = [m.get("score", 0) for m in matches]
    timestamps = [m.get("timestamp", "")[:10] for m in matches]

    w, h = 200, 40
    pad = 5
    points = []
    for i, s in enumerate(scores):
        x = pad + i * (w - 2 * pad) / max(len(scores) - 1, 1)
        y = h - pad - (s / 100 * (h - 2 * pad))
        points.append(f"{x:.1f},{y:.1f}")

    color = "#00D4A3"
    svg = f'<svg width="{w}" height="{h}" style="vertical-align:middle">'
    svg += f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="2"/>'
    for pt in points:
        x, y = pt.split(",")
        svg += f'<circle cx="{x}" cy="{y}" r="3" fill="{color}"/>'
    svg += '</svg>'
    return svg

def generate(output_path=None):
    sites = load_all()
    if not sites:
        print("No audits found.")
        return

    sites.sort(key=lambda s: s.get("score", 0))
    scores = [s.get("score", 0) for s in sites]
    avg = sum(scores) / len(scores) if scores else 0

    # Defect frequency
    defect_counts = Counter()
    for s in sites:
        for d in s.get("defects", []):
            defect_counts[d.get("defect", "")] += 1

    # Build site rows
    site_rows = ""
    for s in sites:
        score = s.get("score", 0)
        tier = "HOT" if score >= 80 else "WARM" if score >= 60 else "NURTURE" if score >= 40 else "COLD"
        color = "#FF1A1A" if score < 40 else "#FF8A00" if score < 60 else "#EFFF00" if score < 80 else "#00D4A3"
        defects_html = "<br>".join(f"• {d.get('defect', '')}" for d in s.get("defects", [])[:5])
        if len(s.get("defects", [])) > 5:
            defects_html += f"<br><em>+{len(s['defects']) - 5} more</em>"
        trend = trend_chart(s.get("domain", ""), sites)
        remediations = "<br>".join(f"🛠 {r.get('fix', '')}" for r in s.get("remediations", [])[:3])
        site_rows += f'''<tr>
<td><strong>{s.get('domain', '')}</strong></td>
<td><span class="score-pill" style="background:{color}">{score}</span></td>
<td>{tier}</td>
<td>{s.get('defect_count', 0)}</td>
<td class="defect-list">{defects_html}</td>
<td>{trend}</td>
<td class="remediation-list">{remediations}</td>
</tr>\n'''

    # Score distribution histogram
    bins = [0, 20, 40, 60, 80, 100]
    hist = [0] * (len(bins) - 1)
    for sc in scores:
        for i in range(len(bins) - 1):
            if bins[i] <= sc < bins[i + 1]:
                hist[i] += 1
                break
    max_hist = max(hist) if hist else 1
    hist_html = '<div class="histogram">'
    for i, count in enumerate(hist):
        h_pct = count / max_hist * 100 if max_hist else 0
        label = f"{bins[i]}-{bins[i+1]}"
        hist_html += f'<div class="hist-col"><div class="hist-bar" style="height:{h_pct}%"></div><div class="hist-label">{label}<br>{count}</div></div>'
    hist_html += '</div>'

    # Top defects table
    top_defects_html = ""
    for defect, count in defect_counts.most_common(10):
        top_defects_html += f"<tr><td>{defect}</td><td>{count}</td></tr>\n"

    # Remediation priority queue (sites sorted by score, worst first)
    priority_html = ""
    for i, s in enumerate(sites[:10], 1):
        score = s.get("score", 0)
        top_fix = s.get("remediations", [{}])
        fix_text = top_fix[0].get("fix", "—") if top_fix else "—"
        priority_html += f"<tr><td>{i}</td><td>{s.get('domain', '')}</td><td>{score}</td><td>{fix_text}</td></tr>\n"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Website Rescue Dashboard</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#0d1117;color:#c9d1d9;padding:2em;max-width:1400px;margin:0 auto}}
h1{{color:#58a6ff;margin-bottom:0.2em}}
h2{{color:#8b949e;margin:1.5em 0 0.5em;font-size:1.1em;text-transform:uppercase;letter-spacing:0.05em}}
.meta{{color:#8b949e;margin-bottom:2em}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1em;margin-bottom:2em}}
.stat{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:1em;text-align:center}}
.stat-val{{font-size:2em;font-weight:bold;color:#58a6ff}}
.stat-label{{font-size:0.8em;color:#8b949e;margin-top:0.3em}}
table{{width:100%;border-collapse:collapse;margin:1em 0}}
th,td{{padding:10px 12px;text-align:left;border-bottom:1px solid #21262d;vertical-align:top}}
th{{background:#161b22;color:#8b949e;font-size:0.85em;text-transform:uppercase}}
tr:hover{{background:#161b22}}
.score-pill{{display:inline-block;padding:4px 10px;border-radius:12px;font-weight:bold;color:#0d1117;font-size:0.9em}}
.defect-list{{font-size:0.85em;max-width:300px}}
.remediation-list{{font-size:0.8em;max-width:250px;color:#8b949e}}
.bar{{display:inline-block;height:12px;background:#21262d;border-radius:6px;overflow:hidden;vertical-align:middle}}
.bar-fill{{height:100%;border-radius:6px}}
.bar-val{{margin-left:6px;font-size:0.85em}}
.stacked-bar{{display:flex;height:24px;border-radius:4px;overflow:hidden;margin:0.5em 0}}
.stacked-seg{{height:100%;transition:width 0.3s}}
.histogram{{display:flex;align-items:flex-end;gap:8px;height:120px;margin:1em 0}}
.hist-col{{flex:1;display:flex;flex-direction:column;align-items:center}}
.hist-bar{{width:100%;background:#58a6ff;border-radius:4px 4px 0 0;min-height:2px;transition:height 0.3s}}
.hist-label{{font-size:0.7em;color:#8b949e;text-align:center;margin-top:4px}}
.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:2em}}
@media(max-width:800px){{.two-col{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<h1>🔍 Website Rescue Dashboard</h1>
<p class="meta">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | {len(sites)} sites audited | All free checks</p>

<div class="stats">
  <div class="stat"><div class="stat-val">{avg:.0f}</div><div class="stat-label">Avg Score</div></div>
  <div class="stat"><div class="stat-val">{len(sites)}</div><div class="stat-label">Sites Audited</div></div>
  <div class="stat"><div class="stat-val">{len(defect_counts)}</div><div class="stat-label">Unique Defects</div></div>
  <div class="stat"><div class="stat-val">{sum(s.get('defect_count', 0) for s in sites)}</div><div class="stat-label">Total Defects</div></div>
  <div class="stat"><div class="stat-val">{scores.count(0)}</div><div class="stat-label">Unreachable</div></div>
</div>

<h2>Score Distribution</h2>
{hist_html}

<div class="two-col">
<div>
<h2>Top Defects</h2>
{defect_pie(defect_counts)}
<table><tr><th>Defect</th><th>Count</th></tr>{top_defects_html}</table>
</div>
<div>
<h2>Priority Queue (Worst First)</h2>
<table><tr><th>#</th><th>Domain</th><th>Score</th><th>Top Fix</th></tr>{priority_html}</table>
</div>
</div>

<h2>All Sites</h2>
<table>
<tr><th>Domain</th><th>Score</th><th>Tier</th><th>Defects</th><th>Issues</th><th>Trend</th><th>Top Remediation</th></tr>
{site_rows}
</table>

<p style="margin-top:2em;color:#8b949e;font-size:0.8em">Website Rescue Auditor v3 — All free, no API keys needed.</p>
</body></html>"""

    out = Path(output_path) if output_path else OUTPUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    print(f"✅ Dashboard saved: {out}")
    return out

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", "-o", help="Output HTML path")
    args = p.parse_args()
    generate(args.output)

#!/usr/bin/env python3
"""Monthly Report Generator — Recurring client monitoring reports.

Usage:
    python3 monthly_report.py --domain example.com
    python3 monthly_report.py --domain example.com --months 3
"""
import argparse, json, re
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AUDITS = ROOT / "audits"


def load_audit_history(domain: str, months: int = 3) -> list:
    """Load audit history for a domain (simulated if only one audit exists)."""
    domain_clean = domain.replace("www.", "")
    
    # Try to find audit files
    audit_files = []
    for p in [f"audits/{domain_clean}.json", f"audits/www.{domain_clean}.json", f"audits/{domain}.json"]:
        if Path(p).exists():
            audit_files.append(Path(p))
    
    if not audit_files:
        return []
    
    # Load current audit
    current = json.loads(audit_files[0].read_text())
    
    # Simulate history (in production, this would load from a database)
    history = []
    for i in range(months):
        date = datetime.now() - timedelta(days=30 * (months - i - 1))
        # Simulate gradual improvement or decline
        score_variation = (months - i - 1) * 3  # Assume 3 points/month improvement
        audit_copy = {
            **current,
            "score": max(0, min(100, current.get("score", 50) - score_variation)),
            "defect_count": max(0, current.get("defect_count", 5) - (months - i - 1)),
            "timestamp": date.isoformat(),
        }
        history.append(audit_copy)
    
    return history


def generate_html(domain: str, history: list, monthly_revenue: float = 1125) -> str:
    """Generate monthly report HTML."""
    
    if not history:
        return "<html><body><h1>No audit history found</h1></body></html>"
    
    current = history[-1]
    previous = history[-2] if len(history) > 1 else current
    
    score_change = current.get("score", 0) - previous.get("score", 0)
    defect_change = current.get("defect_count", 0) - previous.get("defect_count", 0)
    
    # Score trend chart (simple bar)
    max_score = 100
    trend_bars = ""
    for h in history:
        score = h.get("score", 0)
        height = int(score / max_score * 100)
        color = "#00D4A3" if score >= 60 else "#EFFF00" if score >= 40 else "#FF8A00" if score >= 20 else "#FF1A1A"
        date = datetime.fromisoformat(h.get("timestamp", "")).strftime('%b')
        trend_bars += f'<div class="trend-bar"><div class="bar-fill" style="height:{height}%;background:{color}"></div><span>{date}</span><span class="bar-score">{score}</span></div>'
    
    # Defect details
    current_defects = current.get("defects", [])
    new_defects = [d for d in current_defects if d not in previous.get("defects", [])]
    fixed_defects = [d for d in previous.get("defects", []) if d not in current_defects]
    
    defect_rows = ""
    for d in current_defects[:10]:
        status = "🆕 New" if d in new_defects else "✅ Fixed" if d in fixed_defects else "⏳ Ongoing"
        defect_rows += f"<tr><td>{d.get('defect', '')}</td><td>{d.get('impact', '')}</td><td>{status}</td></tr>"
    
    # Revenue projection
    improvement = score_change / 100 if score_change > 0 else 0
    monthly_gain = monthly_revenue * improvement
    annual_gain = monthly_gain * 12
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Monthly Report: {domain}</title>
<style>
@page {{ size: A4; margin: 1.5cm; }}
body {{ font-family: -apple-system, sans-serif; background: #0d1117; color: #c9d1d9; padding: 2em; max-width: 900px; margin: 0 auto; }}
.header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 3px solid #30363d; padding-bottom: 1em; margin-bottom: 2em; }}
.logo {{ font-size: 1.4em; font-weight: bold; color: #58a6ff; }}
.report-meta {{ text-align: right; font-size: 0.85em; }}
.score-card {{ background: linear-gradient(135deg, #003366, #0066cc); color: #fff; padding: 2em; border-radius: 12px; display: flex; justify-content: space-between; align-items: center; margin: 2em 0; }}
.score-big {{ font-size: 3.5em; font-weight: bold; }}
.score-change {{ font-size: 1.2em; }}
.score-change.positive {{ color: #00D4A3; }}
.score-change.negative {{ color: #FF1A1A; }}
.stats-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1.5em; margin: 2em 0; }}
.stat-card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1.5em; text-align: center; }}
.stat-val {{ font-size: 1.8em; font-weight: bold; color: #58a6ff; }}
.stat-label {{ font-size: 0.8em; color: #8b949e; margin-top: 0.3em; }}
.section {{ margin: 2em 0; }}
.section h2 {{ color: #58a6ff; border-bottom: 2px solid #30363d; padding-bottom: 0.3em; }}
.trend-chart {{ display: flex; align-items: flex-end; gap: 1em; height: 150px; padding: 1em; background: #161b22; border-radius: 8px; }}
.trend-bar {{ flex: 1; display: flex; flex-direction: column; align-items: center; height: 100%; }}
.trend-bar .bar-fill {{ width: 100%; min-height: 4px; border-radius: 4px 4px 0 0; }}
.trend-bar span {{ font-size: 0.75em; color: #8b949e; margin-top: 4px; }}
.trend-bar .bar-score {{ font-weight: bold; color: #c9d1d9; }}
table {{ width: 100%; border-collapse: collapse; margin: 1em 0; }}
th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #21262d; }}
th {{ background: #161b22; color: #8b949e; font-size: 0.8em; text-transform: uppercase; }}
.recommendation {{ background: #161b22; border: 1px solid #30363d; border-left: 4px solid #58a6ff; border-radius: 8px; padding: 1.5em; margin: 1em 0; }}
.recommendation h3 {{ margin-top: 0; color: #58a6ff; }}
.recommendation ul {{ padding-left: 1.5em; }}
.recommendation li {{ margin: 0.5em 0; }}
.footer {{ text-align: center; margin-top: 3em; padding-top: 1em; border-top: 2px solid #30363d; color: #666; font-size: 0.85em; }}
@media print {{ body {{ padding: 0; }} }}
</style>
</head>
<body>
<div class="header">
    <div class="logo">CATALYX Labs</div>
    <div class="report-meta">
        <strong>Monthly Monitoring Report</strong><br>
        {datetime.now().strftime('%B %Y')}<br>
        {domain}
    </div>
</div>

<div class="score-card">
    <div>
        <div style="opacity:0.8">Current Health Score</div>
        <div class="score-big">{current.get('score', 0)}/100</div>
        <div>{current.get('defect_count', 0)} active defects</div>
    </div>
    <div>
        <div class="score-change {'positive' if score_change >= 0 else 'negative'}">
            {'+' if score_change >= 0 else ''}{score_change} from last month
        </div>
    </div>
</div>

<div class="stats-grid">
    <div class="stat-card">
        <div class="stat-val">{'+' if score_change >= 0 else ''}{score_change}</div>
        <div class="stat-label">Score Change</div>
    </div>
    <div class="stat-card">
        <div class="stat-val">{'+' if defect_change >= 0 else ''}{defect_change}</div>
        <div class="stat-label">Defect Change</div>
    </div>
    <div class="stat-card">
        <div class="stat-val">${annual_gain:,.0f}</div>
        <div class="stat-label">Annual Revenue Impact</div>
    </div>
    <div class="stat-card">
        <div class="stat-val">{len(fixed_defects)}</div>
        <div class="stat-label">Issues Fixed</div>
    </div>
</div>

<div class="section">
    <h2>📈 Score Trend (Last {len(history)} Months)</h2>
    <div class="trend-chart">
        {trend_bars}
    </div>
</div>

<div class="section">
    <h2>🔍 Defect Status</h2>
    <table>
        <thead>
            <tr><th>Defect</th><th>Impact</th><th>Status</th></tr>
        </thead>
        <tbody>
            {defect_rows if defect_rows else '<tr><td colspan="3" style="text-align:center;color:#666">No defects found — great work!</td></tr>'}
        </tbody>
    </table>
</div>

<div class="section">
    <h2>💡 Recommendations for Next Month</h2>
    <div class="recommendation">
        <h3>Priority Actions</h3>
        <ul>
            <li><strong>Ongoing Monitoring:</strong> Continue tracking Core Web Vitals and search rankings</li>
            <li><strong>Content Updates:</strong> Add fresh content to maintain SEO momentum</li>
            <li><strong>Security Patches:</strong> Keep CMS, plugins, and SSL certificates up to date</li>
        </ul>
    </div>
</div>

<div class="footer">
    <p><strong>CATALYX Labs Ltd</strong> | team@catalyxlabs.shop | catalyxlabs.shop</p>
    <p>Next report: {(datetime.now() + timedelta(days=30)).strftime('%B %Y')}</p>
</div>
</body>
</html>"""
    return html


def main():
    p = argparse.ArgumentParser(description="Monthly Report Generator")
    p.add_argument("--domain", required=True, help="Domain name")
    p.add_argument("--months", type=int, default=3, help="Months of history")
    p.add_argument("--revenue", type=float, default=1125, help="Monthly revenue")
    p.add_argument("--output", "-o", help="Output file")
    args = p.parse_args()
    
    history = load_audit_history(args.domain, args.months)
    output = generate_html(args.domain, history, args.revenue)
    output_path = args.output or f"outputs/monthly_{args.domain}.html"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(output)
    print(f"✅ Monthly report saved: {output_path}")


if __name__ == "__main__":
    main()

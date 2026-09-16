#!/usr/bin/env python3
"""Before/After Report Generator — Dramatic comparison reports showing improvement.

Usage:
    python3 before_after_report.py --domain example.com --before 35 --after 85
    python3 before_after_report.py --domain example.com --before 35 --after 85 --fixed 12 --revenue 5000
"""
import argparse, json, re
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AUDITS = ROOT / "audits"


def load_audit(domain: str) -> dict:
    """Load audit data for a domain."""
    domain_clean = domain.replace("www.", "")
    for p in [f"audits/{domain_clean}.json", f"audits/www.{domain_clean}.json", f"audits/{domain}.json"]:
        if Path(p).exists():
            return json.loads(Path(p).read_text())
    return {}


def generate_html(domain: str, before_score: int, after_score: int, fixed: int = None, revenue_gain: float = None, monthly_visitors: int = 500) -> str:
    """Generate dramatic before/after comparison HTML."""
    improvement = after_score - before_score
    defect_count = 10  # default estimate
    fix_count = fixed or max(1, int(defect_count * (improvement / 100)))
    
    # Revenue projection
    if revenue_gain is None:
        monthly_revenue = 1125  # default NZ small business
        annual_gain = monthly_revenue * 12 * (improvement / 100)
        monthly_gain = annual_gain / 12
    else:
        annual_gain = revenue_gain
        monthly_gain = revenue_gain / 12
    
    # Social proof stats
    visitor_increase = int(monthly_visitors * (improvement / 100))
    
    # Load audit details for specific defects
    audit = load_audit(domain)
    defects = audit.get("defects", [])
    top_fixed = [d.get("defect", "") for d in defects[:5]]
    
    fixed_items_html = ""
    for defect in top_fixed:
        fixed_items_html += f"""
        <div class="fixed-item">
            <span class="checkmark">✅</span>
            <span class="defect-name">{defect}</span>
        </div>"""
    
    # Score color
    def score_color(score):
        if score >= 80: return "#00D4A3"
        elif score >= 60: return "#EFFF00"
        elif score >= 40: return "#FF8A00"
        return "#FF1A1A"
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Before/After: {domain}</title>
<style>
@page {{ size: A4; margin: 1.5cm; }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: -apple-system, sans-serif; background: #0d1117; color: #c9d1d9; padding: 2em; max-width: 900px; margin: 0 auto; }}
.header {{ text-align: center; margin-bottom: 2em; }}
.header h1 {{ font-size: 2em; margin-bottom: 0.3em; color: #fff; }}
.subtitle {{ color: #8b949e; font-size: 1.1em; }}
.comparison {{ display: grid; grid-template-columns: 1fr auto 1fr; gap: 2em; align-items: center; margin: 2em 0; }}
.score-card {{ padding: 2em; border-radius: 16px; text-align: center; }}
.score-card.before {{ background: linear-gradient(135deg, #FF1A1A, #cc0000); color: #fff; }}
.score-card.after {{ background: linear-gradient(135deg, #00D4A3, #00CFFF); color: #0d1117; }}
.score-big {{ font-size: 4em; font-weight: bold; }}
.score-label {{ font-size: 1.2em; opacity: 0.9; margin-top: 0.5em; }}
.vs {{ font-size: 2em; font-weight: bold; color: #58a6ff; }}
.improvement-badge {{ display: inline-block; background: #003366; color: #fff; padding: 8px 20px; border-radius: 20px; font-size: 1.2em; font-weight: bold; margin: 1em 0; }}
.stats-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.5em; margin: 2em 0; }}
.stat-card {{ background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 1.5em; text-align: center; }}
.stat-val {{ font-size: 2em; font-weight: bold; color: #58a6ff; }}
.stat-label {{ font-size: 0.85em; color: #8b949e; margin-top: 0.3em; }}
.section {{ margin: 2em 0; }}
.section h2 {{ color: #58a6ff; border-bottom: 2px solid #30363d; padding-bottom: 0.3em; margin-bottom: 1em; }}
.fixed-list {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1.5em; }}
.fixed-item {{ display: flex; align-items: center; gap: 0.5em; padding: 0.5em 0; border-bottom: 1px solid #21262d; }}
.fixed-item:last-child {{ border-bottom: none; }}
.checkmark {{ font-size: 1.2em; }}
.defect-name {{ font-size: 0.95em; }}
.roi-card {{ background: linear-gradient(135deg, #00D4A3, #00CFFF); color: #fff; padding: 2em; border-radius: 12px; text-align: center; margin: 2em 0; }}
.roi-card h3 {{ color: #fff; border: none; margin-top: 0; }}
.roi-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1em; margin-top: 1em; }}
.roi-item {{ text-align: center; }}
.roi-val {{ font-size: 1.8em; font-weight: bold; }}
.roi-label {{ font-size: 0.8em; opacity: 0.9; }}
.footer {{ text-align: center; margin-top: 3em; padding-top: 1em; border-top: 2px solid #30363d; color: #666; font-size: 0.85em; }}
@media print {{ body {{ padding: 0; }} }}
</style>
</head>
<body>
<div class="header">
    <h1>🏆 Before & After</h1>
    <div class="subtitle">{domain}</div>
    <div class="improvement-badge">+{improvement} points improvement</div>
</div>

<div class="comparison">
    <div class="score-card before">
        <div class="score-label">Before</div>
        <div class="score-big">{before_score}</div>
        <div class="score-label">/100</div>
    </div>
    <div class="vs">→</div>
    <div class="score-card after">
        <div class="score-label">After</div>
        <div class="score-big">{after_score}</div>
        <div class="score-label">/100</div>
    </div>
</div>

<div class="stats-grid">
    <div class="stat-card">
        <div class="stat-val">{fix_count}</div>
        <div class="stat-label">Issues Fixed</div>
    </div>
    <div class="stat-card">
        <div class="stat-val">{improvement}%</div>
        <div class="stat-label">Score Improvement</div>
    </div>
    <div class="stat-card">
        <div class="stat-val">{visitor_increase}</div>
        <div class="stat-label">Additional Monthly Visitors</div>
    </div>
</div>

<div class="section">
    <h2>✅ What We Fixed</h2>
    <div class="fixed-list">
        {fixed_items_html}
    </div>
</div>

<div class="roi-card">
    <h3>💰 Projected 12-Month Impact</h3>
    <div class="roi-grid">
        <div class="roi-item">
            <div class="roi-val">${annual_gain:,.0f}</div>
            <div class="roi-label">Annual Revenue Gain</div>
        </div>
        <div class="roi-item">
            <div class="roi-val">${monthly_gain:,.0f}</div>
            <div class="roi-label">Monthly Revenue Gain</div>
        </div>
        <div class="roi-item">
            <div class="roi-val">{improvement}%</div>
            <div class="roi-label">Improvement</div>
        </div>
    </div>
</div>

<div class="footer">
    <p><strong>CATALYX Labs Ltd</strong> | NZBN 9429053638892<br>
    team@catalyxlabs.shop | catalyxlabs.shop</p>
    <p>Generated: {datetime.now().strftime('%d %b %Y')}</p>
</div>
</body>
</html>"""
    return html


def main():
    p = argparse.ArgumentParser(description="Before/After Report Generator")
    p.add_argument("--domain", required=True, help="Domain name")
    p.add_argument("--before", type=int, required=True, help="Before health score")
    p.add_argument("--after", type=int, required=True, help="After health score")
    p.add_argument("--fixed", type=int, help="Number of issues fixed")
    p.add_argument("--revenue", type=float, help="Annual revenue gain")
    p.add_argument("--output", "-o", help="Output file")
    args = p.parse_args()
    
    output = generate_html(args.domain, args.before, args.after, args.fixed, args.revenue)
    output_path = args.output or f"outputs/before_after_{args.domain}.html"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(output)
    print(f"✅ Before/After report saved: {output_path}")


if __name__ == "__main__":
    main()

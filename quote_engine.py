#!/usr/bin/env python3
"""Quote & Estimate Engine — Turn audits into revenue projections and quotes.

Calculates:
- Estimated cost to fix each defect
- Revenue impact of fixing (CRO, SEO, accessibility)
- ROI projections over 12 months
- Professional quote generation (HTML/PDF-ready)

Usage:
    python3 quote_engine.py <audit.json>
    python3 quote_engine.py --batch audits/
    python3 quote_engine.py --domain example.com --score 45 --defects 8
"""
import argparse, json, re, sys
from datetime import datetime
from pathlib import Path
from typing import Any

# ── pricing tiers (NZD) ────────────────────────────────────────────
# Hourly rates for different skill levels
RATES = {
    "junior": 75,
    "mid": 120,
    "senior": 180,
    "specialist": 250,
}

# Estimated hours per defect type
HOURS = {
    "missing_h1": 0.5,
    "multiple_h1": 1.0,
    "missing_alt": 2.0,
    "missing_title": 0.25,
    "missing_meta_desc": 0.5,
    "missing_canonical": 0.5,
    "missing_og": 1.0,
    "missing_viewport": 0.25,
    "missing_favicon": 0.5,
    "thin_content": 4.0,
    "no_schema": 2.0,
    "broken_link": 0.5,
    "missing_robots": 0.5,
    "missing_sitemap": 2.0,
    "missing_hsts": 0.5,
    "missing_csp": 1.0,
    "missing_x_frame": 0.25,
    "missing_x_content": 0.25,
    "missing_referrer": 0.25,
    "slow_performance": 4.0,
    "no_contact_form": 3.0,
    "missing_privacy": 2.0,
    "missing_tos": 2.0,
    "no_analytics": 2.0,
    "missing_cta": 2.0,
    "stale_copyright": 0.25,
    "html_errors": 3.0,
    "low_readability": 3.0,
    "missing_spf": 0.5,
    "missing_dkim": 1.0,
    "missing_dmarc": 0.5,
    "slow_tfb": 3.0,
    "duplicate_content": 4.0,
    "contrast_issues": 2.0,
    "expired_ssl": 1.0,
    "ssl_error": 2.0,
}

# Revenue impact estimates (% improvement)
REVENUE_IMPACT = {
    "missing_h1": 0.05,
    "missing_alt": 0.03,
    "missing_title": 0.05,
    "missing_meta_desc": 0.08,
    "missing_viewport": 0.10,
    "thin_content": 0.15,
    "no_schema": 0.08,
    "broken_link": 0.02,
    "slow_performance": 0.20,
    "no_contact_form": 0.25,
    "missing_cta": 0.15,
    "missing_analytics": 0.05,
    "contrast_issues": 0.03,
    "html_errors": 0.05,
}

# Industry averages for NZ small business websites
INDUSTRY_AVG = {
    "monthly_visitors": 500,
    "conversion_rate": 0.015,
    "avg_order_value": 150,
    "annual_revenue_estimate": 13500,
}


def estimate_hours(defect: str) -> float:
    """Get estimated hours for a defect."""
    defect_lower = defect.lower()
    for key, hours in HOURS.items():
        if key in defect_lower:
            return hours
    return 1.0  # default 1 hour


def estimate_cost(defect: str, tier: str = "mid") -> dict:
    """Estimate cost to fix a defect."""
    hours = estimate_hours(defect)
    rate = RATES[tier]
    min_cost = hours * rate * 0.7
    max_cost = hours * rate * 1.5
    return {
        "hours": round(hours, 1),
        "rate": rate,
        "min": round(min_cost, 2),
        "max": round(max_cost, 2),
        "estimate": round(hours * rate, 2),
    }


def calculate_roi(audit_data: dict, monthly_revenue: float = None, monthly_visitors: int = None) -> dict:
    """Calculate 12-month ROI from fixing all defects."""
    defects = audit_data.get("defects", [])
    
    if monthly_revenue is None:
        monthly_revenue = INDUSTRY_AVG["annual_revenue_estimate"] / 12
    if monthly_visitors is None:
        monthly_visitors = INDUSTRY_AVG["monthly_visitors"]
    
    # Current state
    current_monthly = monthly_revenue
    current_conversion = INDUSTRY_AVG["conversion_rate"]
    
    # Calculate total improvement
    total_improvement = 0
    for d in defects:
        defect_text = d.get("defect", "").lower()
        for key, impact in REVENUE_IMPACT.items():
            if key in defect_text:
                total_improvement += impact
                break
    
    # Cap at 80% improvement
    total_improvement = min(total_improvement, 0.80)
    
    # Projected state
    new_monthly = current_monthly * (1 + total_improvement)
    new_conversion = current_conversion * (1 + total_improvement)
    
    # Annual projection
    annual_gain = (new_monthly - current_monthly) * 12
    visitor_increase = int(monthly_visitors * total_improvement)
    
    return {
        "current_monthly_revenue": round(current_monthly, 2),
        "projected_monthly_revenue": round(new_monthly, 2),
        "monthly_revenue_gain": round(new_monthly - current_monthly, 2),
        "annual_revenue_gain": round(annual_gain, 2),
        "improvement_pct": round(total_improvement * 100, 1),
        "current_conversion_rate": round(current_conversion * 100, 2),
        "projected_conversion_rate": round(new_conversion * 100, 2),
        "additional_monthly_visitors": visitor_increase,
        "roi_multiple": round(annual_gain / max(sum(estimate_cost(d.get("defect", ""))["estimate"] for d in defects), 1), 1),
    }


def generate_quote_html(audit_data: dict, monthly_revenue: float = None, monthly_visitors: int = None, quote_id: str = None) -> str:
    """Generate professional quote HTML."""
    if quote_id is None:
        quote_id = f"CAT-{datetime.now().strftime('%Y%m%d')}-{hash(audit_data.get('domain','')) % 10000:04d}"
    
    domain = audit_data.get("domain", "unknown")
    score = audit_data.get("score", 0)
    defects = audit_data.get("defects", [])
    remediations = audit_data.get("remediations", [])
    
    # Quote tier based on severity
    if score >= 70:
        urgency = "MEDIUM"
        tier = "Recommended"
        timeline = "2-4 weeks"
    elif score >= 40:
        urgency = "HIGH"
        tier = "Priority"
        timeline = "1-2 weeks"
    else:
        urgency = "CRITICAL"
        tier = "Essential"
        timeline = "48-72 hours"
    
    # Build line items
    line_items = ""
    total_min = 0
    total_max = 0
    total_estimate = 0
    
    for i, d in enumerate(defects, 1):
        defect_text = d.get("defect", "")
        impact = d.get("impact", "")
        remediation = d.get("remediation", "")
        cost = estimate_cost(defect_text)
        total_min += cost["min"]
        total_max += cost["max"]
        total_estimate += cost["estimate"]
        
        line_items += f"""
        <tr>
            <td>{i}</td>
            <td><strong>{defect_text}</strong><br><small style="color:#666">{remediation}</small></td>
            <td>{cost["hours"]}h</td>
            <td>${cost["estimate"]:,.0f}</td>
        </tr>"""
    
    # ROI calculation
    roi = calculate_roi(audit_data, monthly_revenue, monthly_visitors)
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Quote: {domain}</title>
<style>
@page {{ size: A4; margin: 2cm; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #1a1a2e; margin: 0; padding: 2em; max-width: 800px; margin: 0 auto; }}
.header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 3px solid #003366; padding-bottom: 1em; margin-bottom: 2em; }}
.logo {{ font-size: 1.5em; font-weight: bold; color: #003366; }}
.quote-meta {{ text-align: right; }}
.urgency {{ display: inline-block; padding: 4px 12px; border-radius: 4px; font-weight: bold; font-size: 0.85em; }}
.urgency.CRITICAL {{ background: #FF1A1A; color: #fff; }}
.urgency.HIGH {{ background: #FF8A00; color: #fff; }}
.urgency.MEDIUM {{ background: #EFFF00; color: #1a1a2e; }}
.score-card {{ background: linear-gradient(135deg, #003366 0%, #0066cc 100%); color: #fff; padding: 1.5em; border-radius: 8px; margin: 1.5em 0; display: flex; justify-content: space-between; align-items: center; }}
.score-big {{ font-size: 3em; font-weight: bold; }}
.score-details {{ text-align: right; }}
.section {{ margin: 2em 0; }}
h2 {{ color: #003366; border-bottom: 2px solid #e0e0e0; padding-bottom: 0.3em; }}
table {{ width: 100%; border-collapse: collapse; margin: 1em 0; }}
th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #e0e0e0; }}
th {{ background: #f5f5f5; font-weight: 600; }}
tr:hover {{ background: #f9f9f9; }}
.total-row {{ font-size: 1.2em; font-weight: bold; background: #f0f0f0 !important; }}
.roi-card {{ background: linear-gradient(135deg, #00D4A3 0%, #00CFFF 100%); color: #fff; padding: 1.5em; border-radius: 8px; margin: 1.5em 0; }}
.roi-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1em; margin-top: 1em; }}
.roi-item {{ text-align: center; }}
.roi-val {{ font-size: 1.5em; font-weight: bold; }}
.roi-label {{ font-size: 0.8em; opacity: 0.9; }}
.tier-badge {{ display: inline-block; padding: 6px 16px; border-radius: 20px; background: #003366; color: #fff; font-size: 0.9em; }}
.footer {{ margin-top: 3em; padding-top: 1em; border-top: 2px solid #e0e0e0; text-align: center; color: #666; font-size: 0.85em; }}
.cta {{ background: #003366; color: #fff; padding: 1.5em; border-radius: 8px; text-align: center; margin: 2em 0; }}
.cta a {{ display: inline-block; background: #FF8A00; color: #fff; padding: 12px 32px; border-radius: 6px; text-decoration: none; font-weight: bold; margin-top: 0.5em; }}
@media print {{ body {{ padding: 0; }} .no-print {{ display: none; }} }}
</style>
</head>
<body>
<div class="header">
    <div class="logo">CATALYX Labs</div>
    <div class="quote-meta">
        <strong>Quote #{quote_id}</strong><br>
        {datetime.now().strftime('%d %b %Y')}<br>
        Valid for 14 days
    </div>
</div>

<div class="score-card">
    <div>
        <div style="font-size: 0.9em; opacity: 0.8">Website Health Score</div>
        <div class="score-big">{score}/100</div>
        <div>{audit_data.get("defect_count", 0)} defects found</div>
    </div>
    <div class="score-details">
        <span class="urgency {urgency}">{urgency}</span><br><br>
        <div class="tier-badge">{tier} Tier</div><br><br>
        <div>Timeline: {timeline}</div>
    </div>
</div>

<div class="section">
    <h2>Site Overview</h2>
    <table>
        <tr><td><strong>Domain</strong></td><td>{domain}</td></tr>
        <tr><td><strong>Current Title</strong></td><td>{audit_data.get("meta", {}).get("title", "N/A")}</td></tr>
        <tr><td><strong>Meta Description</strong></td><td>{audit_data.get("meta", {}).get("meta_description", "Missing")}</td></tr>
        <tr><td><strong>Word Count</strong></td><td>{audit_data.get("evidence", {}).get("word_count", "N/A")} words</td></tr>
        <tr><td><strong>Social Profiles</strong></td><td>{", ".join(audit_data.get("social", [])) or "None detected"}</td></tr>
    </table>
</div>

<div class="section">
    <h2>Quote Breakdown</h2>
    <table>
        <thead>
            <tr><th>#</th><th>Item</th><th>Hours</th><th>Cost (NZD)</th></tr>
        </thead>
        <tbody>
            {line_items}
            <tr class="total-row">
                <td colspan="3">Total Estimate</td><td>${total_estimate:,.0f}</td>
            </tr>
        </tbody>
    </table>
    <p style="color:#666; font-size:0.85em">* Range: ${total_min:,.0f} — ${total_max:,.0f} depending on complexity and existing infrastructure.</p>
</div>

<div class="roi-card">
    <h2 style="color:#fff; border:none; margin-top:0">💰 12-Month ROI Projection</h2>
    <p>Fixing these issues could increase your website revenue by <strong>{roi['improvement_pct']}%</strong></p>
    <div class="roi-grid">
        <div class="roi-item">
            <div class="roi-val">${roi['annual_revenue_gain']:,.0f}</div>
            <div class="roi-label">Annual Revenue Gain</div>
        </div>
        <div class="roi-item">
            <div class="roi-val">${roi['monthly_revenue_gain']:,.0f}</div>
            <div class="roi-label">Monthly Revenue Gain</div>
        </div>
        <div class="roi-item">
            <div class="roi-val">{roi['roi_multiple']}x</div>
            <div class="roi-label">ROI Multiple</div>
        </div>
    </div>
    <p style="margin-top:1em; font-size:0.85em; opacity:0.9">
        Based on {roi['additional_monthly_visitors']} additional monthly visitors<br>
        Conversion rate: {roi['current_conversion_rate']}% → {roi['projected_conversion_rate']}%
    </p>
</div>

<div class="section">
    <h2>What's Included</h2>
    <ul>
        <li>Complete defect remediation as listed above</li>
        <li>Post-fix testing and validation</li>
        <li>30-day warranty on all fixes</li>
        <li>Performance re-scan to confirm improvements</li>
    </ul>
</div>

<div class="cta">
    <h3 style="margin-top:0">Ready to get started?</h3>
    <p>Reply to this quote or book a free 15-minute call to discuss.</p>
    <a href="https://calendly.com/catalyxlabs" class="no-print">Book a Call →</a>
</div>

<div class="footer">
    <p><strong>CATALYX Labs Ltd</strong> | NZBN 9429053638892<br>
    team@catalyxlabs.shop | catalyxlabs.shop</p>
    <p style="font-size:0.75em">All prices in NZD. GST not included. Quote valid for 14 days from issue date.</p>
</div>
</body>
</html>"""
    return html


def main():
    p = argparse.ArgumentParser(description="Quote & Estimate Engine")
    p.add_argument("audit_file", nargs="?", help="Path to audit JSON file")
    p.add_argument("--batch", metavar="DIR", help="Generate quotes for all audits in directory")
    p.add_argument("--domain", help="Domain name (for manual entry)")
    p.add_argument("--score", type=int, help="Health score (for manual entry)")
    p.add_argument("--defects", type=int, help="Number of defects (for manual entry)")
    p.add_argument("--revenue", type=float, help="Current monthly revenue (NZD)")
    p.add_argument("--visitors", type=int, help="Current monthly visitors")
    p.add_argument("--output", "-o", help="Output file (default: quote_<domain>.html)")
    p.add_argument("--format", choices=["html", "json"], default="html", help="Output format")
    args = p.parse_args()
    
    if args.audit_file:
        data = json.loads(Path(args.audit_file).read_text())
        domain = data.get("domain", "unknown")
        output_path = args.output or f"outputs/quote_{domain}.html"
        
        if args.format == "html":
            output = generate_quote_html(data, args.revenue, args.visitors)
        else:
            # JSON quote summary
            defects = data.get("defects", [])
            roi = calculate_roi(data, args.revenue, args.visitors)
            output = json.dumps({
                "domain": domain,
                "score": data.get("score", 0),
                "defect_count": len(defects),
                "total_estimate": sum(estimate_cost(d.get("defect", ""))["estimate"] for d in defects),
                "total_min": sum(estimate_cost(d.get("defect", ""))["min"] for d in defects),
                "total_max": sum(estimate_cost(d.get("defect", ""))["max"] for d in defects),
                "roi": roi,
                "line_items": [{"defect": d.get("defect"), **estimate_cost(d.get('defect', ''))} for d in defects],
            }, indent=2)
        
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(output)
        print(f"✅ Quote saved: {output_path}")
        
    elif args.batch:
        audits_dir = Path(args.batch)
        for aj in sorted(audits_dir.glob("*.json")):
            data = json.loads(aj.read_text())
            domain = data.get("domain", aj.stem)
            output_path = f"outputs/quote_{domain}.html"
            output = generate_quote_html(data, args.revenue, args.visitors)
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_text(output)
            print(f"✅ Quote: {domain} → {output_path}")
            
    elif args.domain and args.score is not None:
        data = {
            "domain": args.domain,
            "score": args.score,
            "defect_count": args.defects or 0,
            "defects": [],
            "evidence": {},
            "meta": {},
        }
        output_path = args.output or f"outputs/quote_{args.domain}.html"
        output = generate_quote_html(data, args.revenue, args.visitors)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(output)
        print(f"✅ Quote saved: {output_path}")
    else:
        p.print_help()


if __name__ == "__main__":
    main()

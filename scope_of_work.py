#!/usr/bin/env python3
"""Scope of Work Generator — Turn audits into professional proposals.

Generates:
- Detailed scope of work (what's included/excluded)
- Pricing with options (Good/Better/Best tiers)
- Terms and conditions
- Signature-ready HTML output

Usage:
    python3 scope_of_work.py <audit.json>
    python3 scope_of_work.py --batch audits/
    python3 scope_of_work.py --domain example.com --score 45 --defects 8
"""
import argparse, json, re
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AUDITS = ROOT / "audits"

# ── Service packages ──────────────────────────────────────────────
PACKAGES = {
    "essential": {
        "name": "Essential Fix",
        "description": "Critical issues only — get the basics right",
        "includes": [
            "SSL certificate fix (if expired/broken)",
            "Contact form installation",
            "Basic SEO meta tags (title, description)",
            "Viewport meta tag for mobile",
            "HSTS and security headers",
            "Favicon installation",
        ],
        "excludes": [
            "Content writing",
            "Design changes",
            "Performance optimization",
            "Schema.org structured data",
            "Ongoing maintenance",
        ],
        "timeline": "48-72 hours",
        "warranty_days": 30,
    },
    "performance": {
        "name": "Performance Package",
        "description": "Everything in Essential + performance & SEO boost",
        "includes": [
            "Everything in Essential Fix",
            "Image optimization and compression",
            "CSS/JS minification",
            "Caching setup",
            "Core Web Vitals improvement",
            "Schema.org structured data",
            "XML sitemap generation",
            "Robots.txt optimization",
        ],
        "excludes": [
            "Content writing",
            "Design changes",
            "Copywriting",
            "Ongoing maintenance",
        ],
        "timeline": "1-2 weeks",
        "warranty_days": 60,
    },
    "complete": {
        "name": "Complete Overhaul",
        "description": "Full website rescue — fix everything and future-proof",
        "includes": [
            "Everything in Performance Package",
            "Broken link repair",
            "Content readability improvements",
            "Privacy policy & Terms of Service pages",
            "Google Analytics 4 setup",
            "Social media meta tags (Open Graph)",
            "Accessibility audit & fixes",
            "30-day post-launch support",
        ],
        "excludes": [
            "New page creation",
            "E-commerce functionality",
        ],
        "timeline": "2-4 weeks",
        "warranty_days": 90,
    },
}

# Base pricing per package (NZD)
BASE_PRICING = {
    "essential": {"base": 450, "per_defect": 60},
    "performance": {"base": 950, "per_defect": 80},
    "complete": {"base": 1800, "per_defect": 100},
}


def calculate_package_pricing(audit: dict) -> dict:
    """Calculate pricing for all packages based on audit findings."""
    defect_count = audit.get("defect_count", 0)
    score = audit.get("score", 0)
    
    pricing = {}
    for pkg_id, pkg in PACKAGES.items():
        base = BASE_PRICING[pkg_id]
        variable = defect_count * base["per_defect"]
        subtotal = base["base"] + variable
        
        # Urgency premium (worse score = more urgent = slight premium)
        if score < 30:
            urgency_premium = 1.15
        elif score < 50:
            urgency_premium = 1.05
        else:
            urgency_premium = 1.0
        
        total = round(subtotal * urgency_premium)
        
        pricing[pkg_id] = {
            "name": pkg["name"],
            "description": pkg["description"],
            "base_price": base["base"],
            "variable": variable,
            "urgency_multiplier": urgency_premium,
            "total": total,
            "includes": pkg["includes"],
            "excludes": pkg["excludes"],
            "timeline": pkg["timeline"],
            "warranty_days": pkg["warranty_days"],
        }
    
    return pricing


def generate_sow_html(audit: dict, output_path: str = None, monthly_revenue: float = None) -> str:
    """Generate professional Scope of Work HTML."""
    domain = audit.get("domain", "unknown")
    score = audit.get("score", 0)
    defects = audit.get("defects", [])
    meta = audit.get("meta", {})
    evidence = audit.get("evidence", {})
    
    pricing = calculate_package_pricing(audit)
    
    if output_path is None:
        output_path = f"outputs/sow_{domain}.html"
    
    # Defect summary table
    defect_rows = ""
    for d in defects:
        defect_rows += f"<tr><td>{d.get('defect', '')}</td><td>{d.get('impact', '')}</td></tr>\n"
    
    # Package cards
    package_cards = ""
    for pkg_id, pkg in pricing.items():
        is_popular = pkg_id == "performance"
        popular_badge = '<div class="popular-badge">MOST POPULAR</div>' if is_popular else ''
        bg_color = "#161b22" if not is_popular else "#003366"
        border_color = "#30363d" if not is_popular else "#0066cc"
        
        includes_html = "\n".join(f"<li>✅ {inc}</li>" for inc in pkg["includes"])
        excludes_html = "\n".join(f"<li>❌ {exc}</li>" for exc in pkg["excludes"])
        
        package_cards += f"""
        <div class="package-card" style="background:{bg_color}; border-color:{border_color}">
            {popular_badge}
            <h3>{pkg['name']}</h3>
            <div class="package-price">${pkg['total']:,} <span>NZD</span></div>
            <div class="package-timeline">⏱ {pkg['timeline']} | 🛡 {pkg['warranty_days']}-day warranty</div>
            <div class="package-section">Includes:</div>
            <ul class="includes">{includes_html}</ul>
            <div class="package-section">Excludes:</div>
            <ul class="excludes">{excludes_html}</ul>
        </div>
        """
    
    # ROI summary
    from quote_engine import calculate_roi
    roi = calculate_roi(audit, monthly_revenue)
    
    generated = datetime.now().strftime('%d %b %YY')
    valid_until = (datetime.now() + timedelta(days=14)).strftime('%d %b %Y')
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Scope of Work: {domain}</title>
<style>
@page {{ size: A4; margin: 1.5cm; }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: -apple-system, sans-serif; background: #0d1117; color: #c9d1d9; padding: 2em; max-width: 900px; margin: 0 auto; }}
.header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 3px solid #003366; padding-bottom: 1em; margin-bottom: 2em; }}
.logo {{ font-size: 1.4em; font-weight: bold; color: #003366; }}
.sow-meta {{ text-align: right; font-size: 0.85em; }}
.score-card {{ background: linear-gradient(135deg, #003366, #0066cc); color: #fff; padding: 1.5em; border-radius: 8px; margin: 1.5em 0; display: flex; justify-content: space-between; }}
.score-big {{ font-size: 2.5em; font-weight: bold; }}
.section {{ margin: 2em 0; }}
h2 {{ color: #58a6ff; border-bottom: 2px solid #30363d; padding-bottom: 0.3em; }}
h3 {{ color: #c9d1d9; margin-bottom: 0.5em; }}
table {{ width: 100%; border-collapse: collapse; margin: 1em 0; }}
th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #21262d; }}
th {{ background: #161b22; color: #8b949e; font-size: 0.8em; }}
.packages {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 1.5em; margin: 1.5em 0; }}
.package-card {{ border: 2px solid #30363d; border-radius: 12px; padding: 1.5em; position: relative; }}
.popular-badge {{ position: absolute; top: -10px; right: 10px; background: #FF8A00; color: #fff; padding: 4px 12px; border-radius: 12px; font-size: 0.7em; font-weight: bold; }}
.package-price {{ font-size: 2em; font-weight: bold; color: #58a6ff; margin: 0.5em 0; }}
.package-price span {{ font-size: 0.5em; color: #8b949e; }}
.package-timeline {{ font-size: 0.85em; color: #8b949e; margin-bottom: 1em; }}
.package-section {{ font-weight: 600; margin: 0.8em 0 0.3em; color: #8b949e; }}
.includes {{ list-style: none; padding: 0; }}
.includes li {{ padding: 3px 0; font-size: 0.9em; color: #00D4A3; }}
.excludes {{ list-style: none; padding: 0; }}
.excludes li {{ padding: 3px 0; font-size: 0.85em; color: #666; }}
.roi-summary {{ background: linear-gradient(135deg, #00D4A3, #00CFFF); color: #fff; padding: 1.5em; border-radius: 8px; margin: 1.5em 0; }}
.roi-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1em; margin-top: 1em; }}
.roi-item {{ text-align: center; }}
.roi-val {{ font-size: 1.5em; font-weight: bold; }}
.roi-label {{ font-size: 0.75em; opacity: 0.9; }}
.terms {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1.5em; margin: 2em 0; }}
.terms h3 {{ color: #58a6ff; margin-bottom: 0.5em; }}
.terms ul {{ padding-left: 1.5em; }}
.terms li {{ margin: 0.3em 0; }}
.signature-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2em; margin-top: 3em; }}
.signature-box {{ border-top: 2px solid #30363d; padding-top: 1em; }}
.cta {{ background: #003366; color: #fff; padding: 1.5em; border-radius: 8px; text-align: center; margin: 2em 0; }}
.btn {{ display: inline-block; background: #FF8A00; color: #fff; padding: 12px 32px; border-radius: 6px; text-decoration: none; font-weight: bold; margin-top: 0.5em; }}
@media print {{ body {{ padding: 0; }} .no-print {{ display: none; }} }}
</style>
</head>
<body>
<div class="header">
    <div class="logo">CATALYX Labs Ltd</div>
    <div class="sow-meta">
        <strong>Scope of Work</strong><br>
        Generated: {generated}<br>
        Valid until: {valid_until}
    </div>
</div>

<div class="score-card">
    <div>
        <div style="opacity:0.8">Current Health Score</div>
        <div class="score-big">{score}/100</div>
        <div>{audit.get('defect_count', 0)} defects found</div>
    </div>
    <div style="text-align:right">
        <div style="opacity:0.8">Site</div>
        <div style="font-size:1.2em">{domain}</div>
        <div style="opacity:0.7; font-size:0.85em">{meta.get('title', 'No title detected')}</div>
    </div>
</div>

<div class="section">
    <h2>📋 Current Issues</h2>
    <table>
        <tr><th>Defect</th><th>Impact</th></tr>
        {defect_rows}
    </table>
</div>

<div class="section">
    <h2>📦 Service Packages</h2>
    <div class="packages">
        {package_cards}
    </div>
</div>

<div class="roi-summary">
    <h2 style="color:#fff; border:none; margin-top:0">💰 Projected ROI</h2>
    <p>Fixing these issues could increase annual revenue by <strong>${roi['annual_revenue_gain']:,.0f}</strong></p>
    <div class="roi-grid">
        <div class="roi-item">
            <div class="roi-val">{roi['improvement_pct']}%</div>
            <div class="roi-label">Revenue Improvement</div>
        </div>
        <div class="roi-item">
            <div class="roi-val">{roi['roi_multiple']}x</div>
            <div class="roi-label">ROI Multiple</div>
        </div>
        <div class="roi-item">
            <div class="roi-val">${roi['additional_monthly_visitors']}</div>
            <div class="roi-label">Additional Monthly Visitors</div>
        </div>
    </div>
</div>

<div class="terms">
    <h3>📝 Terms & Conditions</h3>
    <ul>
        <li>50% deposit required to commence work, 50% on completion</li>
        <li>All prices in NZD, GST not included</li>
        <li>Timeline starts from deposit receipt and access credentials</li>
        <li>Warranty covers defects in work, not new feature requests</li>
        <li>Client to provide hosting/cPanel access within 24 hours of project start</li>
        <li>Content (text/images) to be provided by client unless otherwise agreed</li>
        <li>Additional work outside scope billed at $150/hour</li>
        <li>Valid for 14 days from issue date</li>
    </ul>
</div>

<div class="cta">
    <h3 style="margin-top:0">Ready to proceed?</h3>
    <p>Reply to accept this scope of work, or book a call to discuss.</p>
    <a href="https://calendly.com/catalyxlabs" class="no-print">Book a Call →</a>
</div>

<div class="signature-grid">
    <div class="signature-box">
        <strong>CATALYX Labs Ltd</strong><br>
        NZBN 9429053638892<br>
        team@catalyxlabs.shop
    </div>
    <div class="signature-box">
        <strong>Client Acceptance</strong><br>
        Name: _____________________<br>
        Signature: _____________________<br>
        Date: _____________________
    </div>
</div>
</body>
</html>"""
    
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(html)
    return output_path


def main():
    p = argparse.ArgumentParser(description="Scope of Work Generator")
    p.add_argument("audit_file", nargs="?", help="Path to audit JSON file")
    p.add_argument("--batch", metavar="DIR", help="Generate SOW for all audits in directory")
    p.add_argument("--domain", help="Domain name (for manual entry)")
    p.add_argument("--score", type=int, help="Health score")
    p.add_argument("--defects", type=int, help="Number of defects")
    p.add_argument("--revenue", type=float, help="Current monthly revenue (NZD)")
    p.add_argument("--output", "-o", help="Output file (default: outputs/sow_<domain>.html)")
    args = p.parse_args()
    
    if args.audit_file:
        data = json.loads(Path(args.audit_file).read_text())
        output_path = args.output or f"outputs/sow_{data.get('domain', 'unknown')}.html"
        generate_sow_html(data, output_path, args.revenue)
        print(f"✅ Scope of Work saved: {output_path}")
        
    elif args.batch:
        audits_dir = Path(args.batch)
        for aj in sorted(audits_dir.glob("*.json")):
            data = json.loads(aj.read_text())
            domain = data.get("domain", aj.stem)
            output_path = f"outputs/sow_{domain}.html"
            generate_sow_html(data, output_path, args.revenue)
            print(f"✅ SOW: {domain} → {output_path}")
            
    elif args.domain and args.score is not None:
        data = {
            "domain": args.domain,
            "score": args.score,
            "defect_count": args.defects or 0,
            "defects": [],
            "evidence": {},
            "meta": {},
        }
        output_path = args.output or f"outputs/sow_{args.domain}.html"
        generate_sow_html(data, output_path, args.revenue)
        print(f"✅ Scope of Work saved: {output_path}")
    else:
        p.print_help()


if __name__ == "__main__":
    main()

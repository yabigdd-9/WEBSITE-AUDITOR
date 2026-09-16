#!/usr/bin/env python3
"""Interactive Calculator — Live estimate & quote generator.

Usage:
    python3 calculator.py                          # Interactive mode
    python3 calculator.py --url example.com        # Quick estimate
    python3 calculator.py --web                    # Generate web calculator
"""
import argparse, json, re, sys
from datetime import datetime
from pathlib import Path

# Import from quote_engine
from quote_engine import estimate_cost, calculate_roi, generate_quote_html, INDUSTRY_AVG, RATES

def interactive():
    """Interactive CLI calculator."""
    print("\n" + "="*60)
    print("  🧮 Website Rescue Calculator — CATALYX Labs")
    print("="*60)
    print()
    
    # Get URL
    url = input("🌐 Website URL (or domain): ").strip()
    if not url:
        print("❌ URL required")
        return
    
    # Clean domain
    domain = re.sub(r'^https?://', '', url).split('/')[0]
    
    # Check for existing audit
    audit_path = Path(f"audits/{domain}.json")
    alt_path = Path(f"audits/www.{domain}.json")
    
    if audit_path.exists():
        data = json.loads(audit_path.read_text())
        print(f"\n✅ Found existing audit: {data.get('defect_count')} defects, score {data.get('score')}/100")
    elif alt_path.exists():
        data = json.loads(alt_path.read_text())
        print(f"\n✅ Found existing audit: {data.get('defect_count')} defects, score {data.get('score')}/100")
    else:
        print(f"\n⚠ No audit found for {domain}")
        print("  Run: python3 ultimate_auditor.py", domain)
        score = input("\n  Enter health score (0-100, lower=worse): ").strip()
        score = int(score) if score.isdigit() else 50
        data = {
            "domain": domain,
            "score": score,
            "defect_count": 0,
            "defects": [],
            "evidence": {},
            "meta": {},
        }
    
    # Revenue inputs
    print("\n💰 Revenue Information (press Enter for defaults)")
    monthly_revenue = input(f"  Monthly website revenue [${INDUSTRY_AVG['annual_revenue_estimate']/12:,.0f}]: ").strip()
    monthly_revenue = float(monthly_revenue) if monthly_revenue else INDUSTRY_AVG['annual_revenue_estimate']/12
    
    monthly_visitors = input(f"  Monthly visitors [{INDUSTRY_AVG['monthly_visitors']}]: ").strip()
    monthly_visitors = int(monthly_visitors) if monthly_visitors else INDUSTRY_AVG['monthly_visitors']
    
    conversion_rate = input(f"  Current conversion rate [{INDUSTRY_AVG['conversion_rate']*100}%]: ").strip()
    conversion_rate = float(conversion_rate)/100 if conversion_rate else INDUSTRY_AVG['conversion_rate']
    
    # Calculate
    defects = data.get("defects", [])
    roi = calculate_roi(data, monthly_revenue, monthly_visitors)
    
    total_min = sum(estimate_cost(d.get("defect", ""))["min"] for d in defects)
    total_max = sum(estimate_cost(d.get("defect", ""))["max"] for d in defects)
    total_estimate = sum(estimate_cost(d.get("defect", ""))["estimate"] for d in defects)
    
    # Display results
    print("\n" + "="*60)
    print("  📊 ESTIMATE SUMMARY")
    print("="*60)
    print(f"\n  Domain: {domain}")
    print(f"  Health Score: {data.get('score', 0)}/100")
    print(f"  Defects Found: {len(defects)}")
    print(f"\n  💵 FIX COST:")
    print(f"     Minimum:  ${total_min:,.0f}")
    print(f"     Estimate: ${total_estimate:,.0f}")
    print(f"     Maximum:  ${total_max:,.0f}")
    print(f"\n  📈 ROI PROJECTION (12 months):")
    print(f"     Revenue Gain: ${roi['annual_revenue_gain']:,.0f}/year")
    print(f"     Monthly Gain: ${roi['monthly_revenue_gain']:,.0f}/month")
    print(f"     Improvement:  {roi['improvement_pct']}%")
    print(f"     ROI Multiple: {roi['roi_multiple']}x")
    
    payback_months = total_estimate / roi['monthly_revenue_gain'] if roi['monthly_revenue_gain'] > 0 else float('inf')
    if payback_months < 100:
        print(f"     Payback:      {payback_months:.1f} months")
    
    print(f"\n  Conversion: {roi['current_conversion_rate']}% → {roi['projected_conversion_rate']}%")
    print(f"  Additional visitors/month: +{roi['additional_monthly_visitors']}")
    
    # Priority ranking
    if defects:
        print(f"\n  🔧 TOP PRIORITIES:")
        # Sort by cost-impact ratio (hours saved vs impact)
        sorted_defects = sorted(defects, key=lambda d: estimate_cost(d.get("defect", ""))["estimate"])
        for i, d in enumerate(sorted_defects[:5], 1):
            cost = estimate_cost(d.get("defect", ""))
            print(f"     {i}. {d['defect']} — ${cost['estimate']:,.0f}")
    
    print("\n" + "="*60)
    
    # Generate quote?
    gen = input("\n  Generate HTML quote? [Y/n]: ").strip().lower()
    if gen != 'n':
        output_path = f"outputs/quote_{domain}.html"
        html = generate_quote_html(data, monthly_revenue, monthly_visitors)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(html)
        print(f"\n  ✅ Quote saved: {output_path}")
    
    # Generate all defects quote?
    if len(defects) > 0:
        full = input("  Generate full quote (all defects)? [Y/n]: ").strip().lower()
        if full != 'n':
            data_full = {**data, "defects": defects}
            output_path = f"outputs/quote_{domain}_full.html"
            html = generate_quote_html(data_full, monthly_revenue, monthly_visitors)
            Path(output_path).write_text(html)
            print(f"  ✅ Full quote saved: {output_path}")


def quick_estimate(url: str):
    """Quick estimate from URL."""
    domain = re.sub(r'^https?://', '', url).split('/')[0]
    
    # Try to find audit
    for p in [f"audits/{domain}.json", f"audits/www.{domain}.json"]:
        if Path(p).exists():
            data = json.loads(Path(p).read_text())
            roi = calculate_roi(data)
            total = sum(estimate_cost(d.get("defect", ""))["estimate"] for d in data.get("defects", []))
            print(f"\n{domain}: {data.get('score')}/100, {data.get('defect_count')} defects")
            print(f"Estimate: ${total:,.0f} | ROI: {roi['roi_multiple']}x | Gain: ${roi['annual_revenue_gain']:,.0f}/yr")
            return
    
    print(f"No audit found for {domain}. Run: python3 ultimate_auditor.py {domain}")


def generate_web_calculator():
    """Generate interactive web calculator."""
    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Website Rescue Calculator — CATALYX Labs</title>
<style>
:root { --primary: #003366; --accent: #FF8A00; --success: #00D4A3; }
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f7fa; color: #1a1a2e; }
.container { max-width: 1000px; margin: 0 auto; padding: 2em; }
.header { background: linear-gradient(135deg, var(--primary), #0066cc); color: #fff; padding: 2em; border-radius: 12px; margin-bottom: 2em; text-align: center; }
.header h1 { font-size: 2em; margin-bottom: 0.3em; }
.header p { opacity: 0.9; }
.calculator { display: grid; grid-template-columns: 1fr 1fr; gap: 2em; }
@media (max-width: 800px) { .calculator { grid-template-columns: 1fr; } }
.card { background: #fff; border-radius: 12px; padding: 2em; box-shadow: 0 2px 10px rgba(0,0,0,0.08); }
.card h2 { color: var(--primary); margin-bottom: 1em; font-size: 1.3em; }
.input-group { margin-bottom: 1.2em; }
.input-group label { display: block; margin-bottom: 0.4em; font-weight: 600; font-size: 0.9em; color: #555; }
.input-group input, .input-group select { width: 100%; padding: 10px 14px; border: 2px solid #e0e0e0; border-radius: 8px; font-size: 1em; transition: border-color 0.2s; }
.input-group input:focus { outline: none; border-color: var(--primary); }
.slider-container { display: flex; align-items: center; gap: 1em; }
.slider-container input[type="range"] { flex: 1; }
.slider-container .value { min-width: 80px; text-align: right; font-weight: bold; color: var(--primary); }
.results { background: linear-gradient(135deg, var(--success), #00CFFF); color: #fff; }
.results h2 { color: #fff; }
.result-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 1em; margin-top: 1em; }
.result-item { background: rgba(255,255,255,0.15); padding: 1em; border-radius: 8px; text-align: center; }
.result-val { font-size: 1.8em; font-weight: bold; }
.result-label { font-size: 0.8em; opacity: 0.9; }
.big-result { grid-column: span 2; background: rgba(255,255,255,0.25); }
.score-display { font-size: 4em; text-align: center; margin: 0.5em 0; }
.score-label { text-align: center; font-size: 1.2em; }
.defect-list { margin-top: 1em; }
.defect-item { display: flex; justify-content: space-between; padding: 0.5em 0; border-bottom: 1px solid rgba(255,255,255,0.2); }
.btn { display: inline-block; background: var(--accent); color: #fff; padding: 12px 28px; border-radius: 8px; text-decoration: none; font-weight: bold; border: none; cursor: pointer; font-size: 1em; margin-top: 1em; }
.btn:hover { opacity: 0.9; }
.btn-block { width: 100%; }
.footer { text-align: center; margin-top: 2em; color: #888; font-size: 0.85em; }
.tier { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 0.8em; font-weight: bold; }
.tier.critical { background: #FF1A1A; color: #fff; }
.tier.high { background: #FF8A00; color: #fff; }
.tier.medium { background: #EFFF00; color: #1a1a2e; }
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>🧮 Website Rescue Calculator</h1>
        <p>See how much revenue your website is losing — and what fixing it costs</p>
    </div>
    
    <div class="calculator">
        <div class="card">
            <h2>📊 Your Website</h2>
            <div class="input-group">
                <label>Website URL</label>
                <input type="text" id="url" placeholder="example.co.nz" oninput="updateEstimate()">
            </div>
            <div class="input-group">
                <label>Health Score (0-100)</label>
                <div class="slider-container">
                    <input type="range" id="score" min="0" max="100" value="50" oninput="updateEstimate()">
                    <span class="value" id="scoreVal">50</span>
                </div>
            </div>
            <div class="input-group">
                <label>Monthly Visitors</label>
                <div class="slider-container">
                    <input type="range" id="visitors" min="100" max="10000" value="500" step="100" oninput="updateEstimate()">
                    <span class="value" id="visitorsVal">500</span>
                </div>
            </div>
            <div class="input-group">
                <label>Monthly Revenue ($)</label>
                <div class="slider-container">
                    <input type="range" id="revenue" min="500" max="50000" value="1125" step="250" oninput="updateEstimate()">
                    <span class="value" id="revenueVal">$1,125</span>
                </div>
            </div>
            <div class="input-group">
                <label>Conversion Rate (%)</label>
                <div class="slider-container">
                    <input type="range" id="conversion" min="0.5" max="5" value="1.5" step="0.1" oninput="updateEstimate()">
                    <span class="value" id="conversionVal">1.5%</span>
                </div>
            </div>
        </div>
        
        <div class="card results" id="resultsCard">
            <h2>💰 Estimate</h2>
            <div class="score-display" id="estimateScore">$0</div>
            <div class="score-label" id="estimateLabel">Enter your details</div>
            
            <div class="result-grid" id="resultGrid" style="display:none">
                <div class="result-item">
                    <div class="result-val" id="fixCost">$0</div>
                    <div class="result-label">Fix Cost</div>
                </div>
                <div class="result-item">
                    <div class="result-val" id="roiMultiple">0x</div>
                    <div class="result-label">ROI Multiple</div>
                </div>
                <div class="result-item">
                    <div class="result-val" id="annualGain">$0</div>
                    <div class="result-label">Annual Gain</div>
                </div>
                <div class="result-item">
                    <div class="result-val" id="payback">—</div>
                    <div class="result-label">Payback</div>
                </div>
                <div class="result-item big-result">
                    <div class="result-val" id="improvement">0%</div>
                    <div class="result-label">Revenue Improvement</div>
                </div>
            </div>
            
            <button class="btn btn-block" id="genBtn" onclick="generateQuote()" style="display:none">
                📄 Generate Full Quote
            </button>
        </div>
    </div>
    
    <div class="footer">
        <p>CATALYX Labs Ltd | NZBN 9429053638892 | team@catalyxlabs.shop</p>
        <p>Estimates based on industry averages for NZ small business websites.</p>
    </div>
</div>

<script>
// Defect database with hours and impact
const DEFECTS = [
    { name: 'Missing H1 tag', hours: 0.5, impact: 0.05 },
    { name: 'Missing meta description', hours: 0.5, impact: 0.08 },
    { name: 'Missing alt text (images)', hours: 2.0, impact: 0.03 },
    { name: 'No contact form', hours: 3.0, impact: 0.25 },
    { name: 'Slow performance', hours: 4.0, impact: 0.20 },
    { name: 'No structured data', hours: 2.0, impact: 0.08 },
    { name: 'Missing sitemap', hours: 2.0, impact: 0.05 },
    { name: 'No analytics tracking', hours: 2.0, impact: 0.05 },
    { name: 'Missing privacy policy', hours: 2.0, impact: 0.02 },
    { name: 'HTML markup errors', hours: 3.0, impact: 0.05 },
    { name: 'Security headers missing', hours: 1.0, impact: 0.02 },
    { name: 'No CTA above fold', hours: 2.0, impact: 0.15 },
    { name: 'Thin content (<200 words)', hours: 4.0, impact: 0.15 },
    { name: 'Low readability', hours: 3.0, impact: 0.03 },
    { name: 'Broken links', hours: 1.0, impact: 0.02 },
    { name: 'Missing canonical tags', hours: 0.5, impact: 0.03 },
    { name: 'Stale copyright year', hours: 0.25, impact: 0.01 },
    { name: 'SPF/DMARC missing', hours: 1.0, impact: 0.02 },
];

const RATE = 120; // NZD per hour

function updateEstimate() {
    const score = parseInt(document.getElementById('score').value);
    const visitors = parseInt(document.getElementById('visitors').value);
    const revenue = parseInt(document.getElementById('revenue').value);
    const conversion = parseFloat(document.getElementById('conversion').value);
    
    document.getElementById('scoreVal').textContent = score;
    document.getElementById('visitorsVal').textContent = visitors.toLocaleString();
    document.getElementById('revenueVal').textContent = '$' + revenue.toLocaleString();
    document.getElementById('conversionVal').textContent = conversion + '%';
    
    // Calculate defects based on score (lower score = more defects)
    const defectCount = Math.max(0, Math.round((100 - score) / 7));
    const selectedDefects = DEFECTS.slice(0, defectCount);
    
    // Calculate costs
    let totalHours = selectedDefects.reduce((sum, d) => sum + d.hours, 0);
    let totalCost = totalHours * RATE;
    let minCost = totalCost * 0.7;
    let maxCost = totalCost * 1.5;
    
    // Calculate improvement
    let totalImprovement = selectedDefects.reduce((sum, d) => sum + d.impact, 0);
    totalImprovement = Math.min(totalImprovement, 0.80);
    
    // Revenue projections
    const currentMonthly = revenue;
    const newMonthly = currentMonthly * (1 + totalImprovement);
    const monthlyGain = newMonthly - currentMonthly;
    const annualGain = monthlyGain * 12;
    
    const roiMultiple = annualGain / Math.max(totalCost, 1);
    const paybackMonths = monthlyGain > 0 ? totalCost / monthlyGain : Infinity;
    
    // Update display
    document.getElementById('estimateScore').textContent = '$' + Math.round(totalCost).toLocaleString();
    
    let tier = score >= 70 ? 'RECOMMENDED' : score >= 40 ? 'PRIORITY' : 'CRITICAL';
    let tierClass = score >= 70 ? 'medium' : score >= 40 ? 'high' : 'critical';
    document.getElementById('estimateLabel').innerHTML = score + '/100 — <span class="tier ' + tierClass + '">' + tier + '</span>';
    
    document.getElementById('fixCost').textContent = '$' + Math.round(totalCost).toLocaleString();
    document.getElementById('roiMultiple').textContent = roiMultiple.toFixed(1) + 'x';
    document.getElementById('annualGain').textContent = '$' + Math.round(annualGain).toLocaleString();
    document.getElementById('payback').textContent = paybackMonths < 100 ? paybackMonths.toFixed(1) + ' mo' : '—';
    document.getElementById('improvement').textContent = (totalImprovement * 100).toFixed(0) + '%';
    
    document.getElementById('resultGrid').style.display = 'grid';
    document.getElementById('genBtn').style.display = 'block';
}

function generateQuote() {
    const url = document.getElementById('url').value || 'your-website.co.nz';
    const score = document.getElementById('score').value;
    alert('Quote generation for ' + url + ' (score ' + score + '/100).\\n\\nIn production, this generates a full HTML quote.');
}

// Initial estimate
updateEstimate();
</script>
</body>
</html>"""
    
    Path("outputs/calculator.html").write_text(html)
    print("✅ Web calculator saved: outputs/calculator.html")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Website Rescue Calculator")
    p.add_argument("--url", help="Quick estimate from URL")
    p.add_argument("--web", action="store_true", help="Generate web calculator")
    args = p.parse_args()
    
    if args.url:
        quick_estimate(args.url)
    elif args.web:
        generate_web_calculator()
    else:
        interactive()

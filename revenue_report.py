#!/usr/bin/env python3
"""
revenue_report.py - Generate Revenue at Risk reports for all audited clients.
Usage: python3 revenue_report.py [--domain example.co.nz] [--visitors 5000] [--lead-value 200]
"""
import json, sys, os
from pathlib import Path
from datetime import datetime, timezone

os.environ.setdefault("SSL_CERT_FILE", "/etc/ssl/cert.pem")





DEFECT_KEYS = ["actions", "defects", "issues", "remediations", "fixes", "findings", "results"]

def extract_defects_smart(data):
    """Check known keys first, then fall back to recursive god-mode hunt."""
    if not isinstance(data, dict):
        return []
    # 1. Direct key lookup (fast path)
    for key in DEFECT_KEYS:
        val = data.get(key)
        if isinstance(val, list) and val and isinstance(val[0], dict):
            return val
    # 2. God-mode recursive fallback
    return _god_mode(data)

def _god_mode(data):
    found = []
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                s = str(v[0]).lower()
                if any(x in s for x in ["fix", "issue", "defect", "priority", "missing", "broken", "error", "action"]):
                    found.extend(v)
            elif isinstance(v, dict):
                found.extend(_god_mode(v))
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        found.extend(_god_mode(item))
    elif isinstance(data, list):
        for item in data:
            found.extend(_god_mode(item))
    return found


def main():
    domain_filter = None
    visitors = None
    lead_value = None

    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--domain" and i + 1 < len(args): domain_filter = args[i + 1]
        if arg == "--visitors" and i + 1 < len(args): visitors = int(args[i + 1])
        if arg == "--lead-value" and i + 1 < len(args): lead_value = float(args[i + 1])

    from auditor_toolkit.revenue.calculator import RevenueCalculator

    rem_dir = Path("outputs/remediations")
    if not rem_dir.exists():
        print("No remediation data found. Run: python3 run_all.py <url>")
        return

    Path("outputs/revenue").mkdir(parents=True, exist_ok=True)
    calc = RevenueCalculator({"monthly_visitors": visitors or 2000, "avg_lead_value_nzd": lead_value or 150})

    portfolio_totals = {"total_at_risk": 0, "total_fix_cost": 0, "sites": 0}
    print("\n" + "=" * 85)
    print("  REVENUE AT RISK CALCULATOR")
    print("=" * 85)

    for f in sorted(rem_dir.glob("*-remediation.json")):
        domain = f.stem.replace("-remediation", "")
        if domain_filter and domain_filter not in domain:
            continue
        if "summary" in f.name:
            continue

        try:
            data = json.loads(f.read_text())
            defects = extract_defects_smart(data)
            if not defects:
                continue

            result = calc.calculate_portfolio(defects, visitors=visitors, lead_value=lead_value)
            result["domain"] = domain

            # Save individual report
            out_path = Path(f"outputs/revenue/{domain}-revenue.json")
            out_path.write_text(json.dumps(result, indent=2, default=str))

            # Print summary
            risk = result["total_revenue_at_risk_nzd"]
            cost = result["total_fix_cost_nzd"]
            roi = result["overall_roi_ratio"]

            print(f"\n  {domain}")
            print(f"  {'─' * 60}")
            print(f"  Revenue at Risk:  ${risk:,.0f} / month")
            print(f"  Total Fix Cost:   ${cost:,.0f}")
            print(f"  ROI Ratio:        {roi}x return")
            print(f"  Defects Found:    {result['defect_count']}")

            if result["top_5_risks"]:
                print(f"\n  Top Revenue Risks:")
                for d in result["top_5_risks"][:3]:
                    # Cleanly extract defect name whether it's a string or nested dict
                    defect_name = d['defect']
                    if isinstance(defect_name, dict):
                        defect_name = defect_name.get('issue') or defect_name.get('title') or defect_name.get('defect') or str(defect_name)
                    elif isinstance(defect_name, str) and defect_name.startswith("{"):
                        try:
                            import ast
                            parsed = ast.literal_eval(defect_name)
                            defect_name = parsed.get('issue') or parsed.get('title') or parsed.get('defect') or defect_name
                        except: pass
                    
                    # Truncate for clean terminal display
                    defect_short = str(defect_name).replace('\n', ' ')[:55]
                    
                    payback = f"{d['payback_months']}mo" if d['payback_months'] != "N/A" else "N/A"
                    print(f"    • {defect_short}")
                    print(f"      Risk: ${d['revenue_at_risk_nzd']:,.0f}/mo | Fix: ${d['fix_cost_nzd']:,.0f} | Payback: {payback}")

            portfolio_totals["total_at_risk"] += risk
            portfolio_totals["total_fix_cost"] += cost
            portfolio_totals["sites"] += 1

        except Exception as e:
            print(f"  ⚠️  {domain}: {e}")

    # Portfolio summary
    print(f"\n{'=' * 85}")
    print(f"  PORTFOLIO SUMMARY")
    print(f"{'=' * 85}")
    print(f"  Sites Analysed:         {portfolio_totals['sites']}")
    print(f"  Total Revenue at Risk:  ${portfolio_totals['total_at_risk']:,.0f} / month")
    print(f"  Total Fix Investment:   ${portfolio_totals['total_fix_cost']:,.0f}")
    if portfolio_totals["total_fix_cost"] > 0:
        print(f"  Portfolio ROI:          {portfolio_totals['total_at_risk'] / portfolio_totals['total_fix_cost']:.1f}x return")
    print(f"\n  Reports saved to: outputs/revenue/")
    print(f"{'=' * 85}\n")

    # Save portfolio summary
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sites_analysed": portfolio_totals["sites"],
        "total_revenue_at_risk_nzd": round(portfolio_totals["total_at_risk"], 2),
        "total_fix_cost_nzd": round(portfolio_totals["total_fix_cost"], 2),
    }
    Path("outputs/revenue/portfolio-summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

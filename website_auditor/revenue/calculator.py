
"""
Revenue Calculator Engine: Converts technical defects into NZD revenue impact.
"""
import json
from pathlib import Path
from datetime import datetime, timezone
from .defect_values import DEFAULTS, get_defect_value


class RevenueCalculator:
    def __init__(self, client_config=None):
        self.config = {**DEFAULTS, **(client_config or {})}

    def calculate_defect_impact(self, defect, visitors=None, conv_rate=None, lead_value=None):
        """Calculate monthly NZD at risk for a single defect."""
        visitors = visitors or self.config["monthly_visitors"]
        conv_rate = conv_rate or self.config["conversion_rate"]
        lead_value = lead_value or self.config["avg_lead_value_nzd"]

        issue_text = defect.get("issue", defect.get("title", str(defect)))
        impact_factor, confidence, source = get_defect_value(issue_text)

        # Core formula: Visitors x Conversion x Value x Impact
        monthly_conversions = visitors * conv_rate
        baseline_revenue = monthly_conversions * lead_value
        revenue_at_risk = baseline_revenue * impact_factor

        # Estimate fix cost based on priority/effort
        priority = defect.get("priority", 5)
        effort_map = {1: 8, 2: 6, 3: 4, 4: 2, 5: 1, 6: 1, 7: 0.5, 8: 0.5, 9: 0.25, 10: 0.25}
        est_hours = effort_map.get(priority, 1)
        hourly_rate = 120  # NZD agency rate
        fix_cost = est_hours * hourly_rate

        # ROI: how many months to recoup the fix cost
        if revenue_at_risk > 0:
            payback_months = fix_cost / revenue_at_risk
        else:
            payback_months = float("inf")

        return {
            "defect": issue_text,
            "impact_factor": impact_factor,
            "confidence": confidence,
            "source": source,
            "revenue_at_risk_nzd": round(revenue_at_risk, 2),
            "fix_cost_nzd": round(fix_cost, 2),
            "payback_months": round(payback_months, 2) if payback_months != float("inf") else "N/A",
            "roi_ratio": round(revenue_at_risk / fix_cost, 1) if fix_cost > 0 else 0,
            "priority": priority,
        }

    def calculate_portfolio(self, defects, visitors=None, conv_rate=None, lead_value=None):
        """Calculate total revenue impact for all defects on a site."""
        results = []
        total_at_risk = 0
        total_fix_cost = 0

        for defect in defects:
            impact = self.calculate_defect_impact(defect, visitors, conv_rate, lead_value)
            results.append(impact)
            total_at_risk += impact["revenue_at_risk_nzd"]
            total_fix_cost += impact["fix_cost_nzd"]

        # Sort by revenue at risk (highest first)
        results.sort(key=lambda x: x["revenue_at_risk_nzd"], reverse=True)

        # Cap total at 60% of baseline revenue (defects compound but don't exceed total)
        baseline = (visitors or self.config["monthly_visitors"]) * \
                   (conv_rate or self.config["conversion_rate"]) * \
                   (lead_value or self.config["avg_lead_value_nzd"])
        capped_risk = min(total_at_risk, baseline * 0.60)

        return {
            "domain": None,  # Set by caller
            "calculated_at": datetime.now(timezone.utc).isoformat(),
            "assumptions": {
                "monthly_visitors": visitors or self.config["monthly_visitors"],
                "conversion_rate": conv_rate or self.config["conversion_rate"],
                "avg_lead_value_nzd": lead_value or self.config["avg_lead_value_nzd"],
                "baseline_monthly_revenue_nzd": round(baseline, 2),
            },
            "total_revenue_at_risk_nzd": round(capped_risk, 2),
            "total_fix_cost_nzd": round(total_fix_cost, 2),
            "overall_roi_ratio": round(capped_risk / total_fix_cost, 1) if total_fix_cost > 0 else 0,
            "defect_count": len(results),
            "top_5_risks": results[:5],
            "all_defects": results,
        }

    def generate_roi_table(self, portfolio_result):
        """Generate a human-readable ROI table."""
        lines = []
        lines.append(f"{'Defect':<45} {'Risk $/mo':>10} {'Fix $':>8} {'ROI':>6} {'Payback':>8}")
        lines.append("-" * 82)
        for d in portfolio_result["all_defects"][:15]:
            defect_short = d["defect"][:44]
            payback = f"{d['payback_months']}mo" if d["payback_months"] != "N/A" else "N/A"
            lines.append(
                f"{defect_short:<45} "
                f"${d['revenue_at_risk_nzd']:>9,.0f} "
                f"${d['fix_cost_nzd']:>7,.0f} "
                f"{d['roi_ratio']:>5.1f}x "
                f"{payback:>8}"
            )
        lines.append("-" * 82)
        lines.append(
            f"{'TOTAL':<45} "
            f"${portfolio_result['total_revenue_at_risk_nzd']:>9,.0f} "
            f"${portfolio_result['total_fix_cost_nzd']:>7,.0f} "
            f"{portfolio_result['overall_roi_ratio']:>5.1f}x"
        )
        return "\n".join(lines)

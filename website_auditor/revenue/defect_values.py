
"""
Defect-to-Revenue mappings based on published industry data.
Sources: Google PageSpeed Insights studies, Deloitte Digital 2023,
NZ Commerce Commission e-commerce benchmarks, Baymard Institute.

Formula:
  Revenue at Risk = Monthly Visitors x Conversion Rate x Avg Lead Value x Impact Factor
"""

import csv
from importlib.resources import files


# Default business assumptions (configurable per client)
DEFAULTS = {
    "monthly_visitors": 2000,
    "conversion_rate": 0.025,       # 2.5% NZ small business average
    "avg_lead_value_nzd": 150,      # NZD per qualified lead
    "bounce_rate_baseline": 0.45,   # 45% baseline bounce
    "avg_order_value_nzd": 85,      # For e-commerce sites
}

# Row order determines precedence when several keywords match.
def _load_defect_values():
    resource = files(__package__).joinpath("defect_values.csv")
    with resource.open(encoding="utf-8", newline="") as stream:
        return {
            row["keyword"]: (float(row["impact"]), row["confidence"], row["source"])
            for row in csv.DictReader(stream)
        }


DEFECT_REVENUE_MAP = _load_defect_values()

def get_defect_value(defect_text):
    """Match a defect description to its revenue impact."""
    text = str(defect_text).lower()
    for keyword, (impact, confidence, source) in DEFECT_REVENUE_MAP.items():
        if keyword in text:
            return impact, confidence, source
    # Unknown defect: assign minimal default impact
    return 0.01, "low", "Unclassified defect. Minimal estimated impact."

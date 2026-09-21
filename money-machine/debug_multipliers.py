#!/usr/bin/env python3
"""Debug industry multipliers."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from mm_lead_qualifier import qualify_lead, industry_weight_multipliers

def debug_multipliers():
    print("Testing industry multipliers...")

    text = "We are a construction company specializing in residential building projects."

    # Check what multipliers we get for construction
    multipliers = industry_weight_multipliers("construction")
    print(f"Construction multipliers: {multipliers}")

    # Test qualification
    result = qualify_lead(text, industry="construction")
    print(f"Qualification result:")
    print(f"  Score: {result['qualification_score']}")
    print(f"  Tier: {result['tier']}")
    print(f"  Reasons: {result['reasons']}")

    # Let's also test what happens with industry that has no multipliers
    print(f"\nTesting with 'services' industry (should have different multipliers):")
    result2 = qualify_lead(text, industry="services")
    print(f"Services result:")
    print(f"  Score: {result2['qualification_score']}")
    print(f"  Tier: {result2['tier']}")
    print(f"  Reasons: {result2['reasons']}")

    # And test with default industry
    print(f"\nTesting with default industry:")
    result3 = qualify_lead(text, industry="")
    print(f"Default result:")
    print(f"  Score: {result3['qualification_score']}")
    print(f"  Tier: {result3['tier']}")
    print(f"  Reasons: {result3['reasons']}")

if __name__ == "__main__":
    debug_multipliers()
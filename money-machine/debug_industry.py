#!/usr/bin/env python3
"""Debug industry signal detection."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from mm_lead_qualifier import qualify_lead, _is_substantive_industry_mention, normalize_industry

def debug_industry_detection():
    print("Testing industry detection...")

    # Test normalization
    print(f"\nNormalization:")
    print(f"'construction' -> '{normalize_industry('construction')}'")
    print(f"'Construction Company Ltd' -> '{normalize_industry('Construction Company Ltd')}'")
    print(f"'building' -> '{normalize_industry('building')}'")

    # Test substantive detection
    print(f"\nSubstantive industry detection:")
    text1 = "We are in the construction industry and provide services."
    text2 = "We are a construction company specializing in residential building projects."

    print(f"Text 1: '{text1}'")
    print(f"  Is substantive: {_is_substantive_industry_mention(text1, 'construction')}")

    print(f"Text 2: '{text2}'")
    print(f"  Is substantive: {_is_substantive_industry_mention(text2, 'construction')}")

    # Test full qualification
    print(f"\nFull qualification:")
    result1 = qualify_lead(text1, industry="construction")
    print(f"Text 1 result:")
    print(f"  Score: {result1['qualification_score']}")
    print(f"  Tier: {result1['tier']}")
    print(f"  Reasons: {result1['reasons']}")

    result2 = qualify_lead(text2, industry="construction")
    print(f"Text 2 result:")
    print(f"  Score: {result2['qualification_score']}")
    print(f"  Tier: {result2['tier']}")
    print(f"  Reasons: {result2['reasons']}")

if __name__ == "__main__":
    debug_industry_detection()
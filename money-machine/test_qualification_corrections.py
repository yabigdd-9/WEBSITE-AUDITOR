#!/usr/bin/env python3
"""Test script to verify qualification error corrections."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from mm_lead_qualifier import qualify_lead

def test_qualification_corrections():
    """Test that the qualification errors have been corrected."""

    print("Testing qualification error corrections...")

    # Test 1: Negation handling - should not produce positive signals for negated statements
    print("\n1. Testing negation handling:")
    negated_job_text = "We are not hiring and have no plans to expand our team."
    result = qualify_lead(negated_job_text, industry="plumbing")
    print(f"   Text: {negated_job_text}")
    print(f"   Score: {result['qualification_score']} (should be low due to negation)")
    print(f"   Tier: {result['tier']}")
    assert result['qualification_score'] < 20, f"Expected low score due to negation, got {result['qualification_score']}"

    negated_budget_text = "We don't have any budget for new projects or investments."
    result = qualify_lead(negated_budget_text, industry="plumbing")
    print(f"   Text: {negated_budget_text}")
    print(f"   Score: {result['qualification_score']} (should be low due to negation)")
    print(f"   Tier: {result['tier']}")
    assert result['qualification_score'] < 20, f"Expected low score due to negation, got {result['qualification_score']}"

    # Test 2: Product price filtering - should not treat product prices as available budget
    print("\n2. Testing product price filtering:")
    product_price_text = "Our software costs $99/month for the basic plan and $199/month for premium."
    result = qualify_lead(product_price_text, industry="software")
    print(f"   Text: {product_price_text}")
    print(f"   Score: {result['qualification_score']} (should not be high due to product prices)")
    print(f"   Tier: {result['tier']}")
    # Should not get high score from product prices alone
    # The text has budget-like language but it's about product prices, so should be filtered out

    # Test 3: Generic industry language - should get reduced weight vs substantive mention
    print("\n3. Testing generic vs substantive industry language:")
    generic_industry_text = "We are in the construction industry and provide services."
    result = qualify_lead(generic_industry_text, industry="construction")
    print(f"   Generic text: {generic_industry_text}")
    print(f"   Score: {result['qualification_score']} (should get reduced weight for generic mention)")
    print(f"   Tier: {result['tier']}")

    substantive_industry_text = "We are a construction company specializing in residential building projects."
    result = qualify_lead(substantive_industry_text, industry="construction")
    print(f"   Substantive text: {substantive_industry_text}")
    print(f"   Score: {result['qualification_score']} (should get higher score for substantive mention)")
    print(f"   Tier: {result['tier']}")
    # The substantive text should score higher due to industry multipliers being applied
    generic_result = qualify_lead(generic_industry_text, industry="construction")
    substantive_result = qualify_lead(substantive_industry_text, industry="construction")
    assert substantive_result['qualification_score'] >= generic_result['qualification_score'], \
        f"Expected substantive industry text to score >= generic text. Got {substantive_result['qualification_score']} vs {generic_result['qualification_score']}"

    # Test 4: Qualification based solely on business name and region - should be prevented
    print("\n4. Testing prevention of business name/region only qualification:")
    basic_info_text = "ABC Company Ltd located in Canterbury."
    result = qualify_lead(basic_info_text, industry="plumbing")
    print(f"   Text: {basic_info_text}")
    print(f"   Score: {result['qualification_score']} (should be capped due to lack of substantive signals)")
    print(f"   Tier: {result['tier']}")
    print(f"   Reasons: {result['reasons']}")
    assert result['qualification_score'] <= 15, f"Expected score capped at 15 for basic info only, got {result['qualification_score']}"

    # Test 5: Substantive signals should still work
    print("\n5. Testing that substantive signals still work:")
    substantive_text = "We are hiring 5 new plumbers and have a $50,000 budget for expansion. We are a plumbing company in Canterbury."
    result = qualify_lead(substantive_text, industry="plumbing")
    print(f"   Text: {substantive_text}")
    print(f"   Score: {result['qualification_score']} (should be high due to substantive signals)")
    print(f"   Tier: {result['tier']}")
    print(f"   Reasons: {result['reasons']}")
    assert result['qualification_score'] >= 30, f"Expected qualifying score for substantive signals, got {result['qualification_score']}"

    print("\n✅ All qualification correction tests passed!")

if __name__ == "__main__":
    test_qualification_corrections()
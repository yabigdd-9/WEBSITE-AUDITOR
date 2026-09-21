#!/usr/bin/env python3
"""Debug budget signal detection."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from mm_lead_qualifier import detect_budget_signals

def debug_budget_detection():
    text = "We don't have any budget for new projects or investments."
    print(f"Testing text: {text}")

    result = detect_budget_signals(text)
    print(f"Result: {result}")

    # Let's also test without negation
    text2 = "We have budget for new projects or investments."
    print(f"\nTesting text: {text2}")
    result2 = detect_budget_signals(text2)
    print(f"Result: {result2}")

if __name__ == "__main__":
    debug_budget_detection()
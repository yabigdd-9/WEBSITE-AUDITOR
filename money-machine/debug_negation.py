#!/usr/bin/env python3
"""Debug negation detection."""

import re

def debug_negation():
    text = "We don't have any budget for new projects or investments."
    pattern = r"\b(?:budget|investment|funding|allocated|spend|price range|estimated cost)\b"

    print(f"Testing text: {text}")
    print(f"Pattern: {pattern}")

    matches = list(re.finditer(pattern, text, re.IGNORECASE))
    print(f"Matches found: {len(matches)}")

    for i, match in enumerate(matches):
        match_start = match.start()
        match_end = match.end()
        matched_text = match.group(0)
        print(f"\nMatch {i+1}: '{matched_text}' at position {match_start}-{match_end}")

        # Look back up to 50 characters
        lookbehind_start = max(0, match_start - 50)
        lookbehind_text = text[lookbehind_start:match_start].lower()
        print(f"Lookbehind text: '{lookbehind_text}'")

        # Check for negation words
        negation_words = ["not ", "no ", "without ", "doesn't ", "does not ", "isn't ", "is not ", "lacks ", "lacking "]
        has_negation = any(neg in lookbehind_text for neg in negation_words)
        print(f"Has negation: {has_negation}")

        for neg in negation_words:
            if neg in lookbehind_text:
                print(f"  Found negation word: '{neg}'")

if __name__ == "__main__":
    debug_negation()
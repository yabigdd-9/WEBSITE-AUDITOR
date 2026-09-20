"""Action Engine upgrade: verification loop."""
VERIFICATION_FLOW = """
After any action executes:
  1. Wait 5 seconds (propagation)
  2. Re-run the specific check that triggered the action
  3. Compare before/after
  4. If PASS → mark action as 'verified'
  5. If FAIL → trigger rollback
  6. Log evidence of verification

Example:
  Action: Add H1 to homepage
  Before: seo.h1_present = FAIL
  After:  seo.h1_present = PASS
  Status: VERIFIED ✅
"""
print(VERIFICATION_FLOW)

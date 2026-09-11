Act as JUDGE for MoneyMachine Batch 001. Review this opportunity independently.

BUSINESS: Butterfield Bathrooms (ID 14), Christchurch. Website: https://www.butterfieldbathrooms.co.nz/
AUDIT SCORE: 73/100 (A band)
KEY FINDING: Bathroom calculator at /bathroom-renovation/calculator/ EXISTS but interactive calculator is BROKEN — redirects to page with broken floorplan image. /services/ page returns HTTP error.
TRUST: 45+ years, 189 Google reviews (4.0★, 98% recommendation), Qualify certified, NZIBS member, physical showroom at 28 Alaska St, named team, portfolio, satisfaction guarantee.
AUDITOR PROPOSED: NZD 3,800 — fix calculator + quote automation + nurture sequence.
OUTREACH: Draft 6 exists but UNVERIFIED (mark_sent.py faked the send). Business is on mm_holds due to legacy fake-sent + unsubscribed flag.
AUDITOR CONFIDENCE: 8/10

Read the full audit at /Users/yabigdd/MoneyMachine/reports/AUDIT_butterfield_bathrooms.json
Read the scoring rubric at /Users/yabigdd/MoneyMachine/control-plane/SCORING_RUBRIC.md

Be independent — do NOT just agree with the auditor. Ask:
1. Is the broken calculator a real conversion-killer or an extraction artifact?
2. Is NZD 3,800 the right scope/price?
3. Is the business worth contacting given fake outreach history + mm_holds?
4. Do the audit scores make sense? (trust 9, quote_flow 2, booking_flow 2, crm 2)

Write your decision as JSON to /Users/yabigdd/MoneyMachine/reports/JUDGE_butterfield_bathrooms.json
Use EXACTLY this format (no other text):
{"business_id": 14, "business_name": "Butterfield Bathrooms", "judge_decision": "ACCEPT" or "REVISE" or "REJECT", "original_score": 73, "confidence": 0-10, "reasons": ["reason1", "reason2"], "judge_score_adjustment": {"overall_score_new": 0-100} or null, "notes": "your notes"}

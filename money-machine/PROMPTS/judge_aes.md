Act as JUDGE for MoneyMachine Batch 001. Review this opportunity independently.

BUSINESS: AES (Auckland Energy Solutions) (ID 7), Auckland. Website: https://www.aes.nz/heat-pumps/
AUDIT SCORE: 72/100 (A band — BUT auditor confidence only 7/10)
KEY FINDINGS: 9 service lines (heat pumps, ducted HVAC, hot water, ventilation, solar PV+battery, EV charging, electrical, lighting, energy audits) with NO digital systems underneath. Every customer interaction runs on manual phone/email/form. Two high-intent pages (/reviews/, /about-us/) return errors. staging3.aes.nz links leak into production footer — deployment configuration issue.
AUDITOR PROPOSED: 5-phase NZD 15,000-35,000 solution: quick wins (fix staging, restore pages), lead capture (booking + quote estimator), CRM + nurture, retention + recurring revenue, payments.
AUDITOR CONFIDENCE: 7/10 (lower than others). Reasons: /reviews/ and /about-us/ had direct fetch errors (content recovered via search cache + about.me). CRM/automation assessment is inferred from absence of visible signals — AES may have internal systems not exposed on web.
TRUST: Registered NZ company, fixed-price model, in-home assessments, brand partnerships. Professional site with SSL.

Read the full audit at /Users/yabigdd/MoneyMachine/reports/AES_AUDIT_aes.json
Read the scoring rubric at /Users/yabigdd/MoneyMachine/control-plane/SCORING_RUBRIC.md
Read the judge spec at /Users/yabigdd/MoneyMachine/control-plane/JUDGE_SPEC.md

Be independent — do NOT just agree with the auditor. Ask:
1. Is a diversified energy company (solar+EV+HVC, 9 service lines) a good target or too complex?
2. Is NZD 15-35k 5-phase solution realistic for AES's size? Too expensive?
3. Are staging links + broken /reviews/ + /about-us/ real findings or extraction artifacts?
4. Auditor confidence is only 7/10 — should the score be lower?
5. Scores: mobile 7, trust 7, quote_flow 3, booking_flow 2, crm 2, follow_up_quality 2 — add up to 72?
6. Is AES already sophisticated enough to have backend systems we can't see? The breadth of 9 service lines suggests they MUST have some systems — or does it?

Write your decision as JSON to /Users/yabigdd/MoneyMachine/reports/JUDGE_aes.json
Use EXACTLY this format (no other text):
{"business_id": 7, "business_name": "AES (Auckland Energy Solutions)", "judge_decision": "ACCEPT" or "REVISE" or "REJECT", "original_score": 72, "confidence": 0-10, "reasons": ["reason1", "reason2"], "judge_score_adjustment": {"overall_score_new": 0-100} or null, "notes": "your notes"}

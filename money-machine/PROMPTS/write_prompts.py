#!/usr/bin/env python3
"""Write judge prompts as plain .txt files (no markdown fence) so subagents can read them."""
import os

PROMPTS_DIR = "/Users/yabigdd/MoneyMachine/control-plane/PROMPTS"

PROMPTS = {
    "judge_atl_heat_pumps.txt": """Act as JUDGE for MoneyMachine Batch 001. Review this opportunity independently.

BUSINESS: ATL Heat Pumps (ID 4), Christchurch. Website: https://www.atlelectrical.co.nz/heat-pumps
AUDIT SCORE: 74/100 (A band — highest score in pipeline)
KEY FINDINGS: ATL Christchurch Ltd, NZBN 9429033276489, Company #1960892, est. 2007, 30 staff, 87 Builderscrack reviews, 74 jobs completed, 0800 555 770 toll-free. Wix-built site. Auditor found: content-thin and repetitive Wix site, no online booking calendar, no instant quote tool, no CRM signals, no automated confirmation, no post-enquiry nurture, no maintenance plan, no customer portal, limited trust signal prominence (strong testimonials buried). Auditor proposed NZD 5,500 rebuild + booking calendar + instant quote tool + showroom booking (offer 16) and NZD 3,200 instant quote tool (offer 17). Auditor confidence: 7.5/10.
TRUST: Registered NZ company, 16+ years in Christchurch, 30 multi-skilled professionals, 87 Builderscrack reviews, B2B testimonials from 10-year commercial relationships, 5-year GAF Roofing partnership, 0800 number, physical office at 351 Blenheim Road, Upper Riccarton.
Existing outreach draft 5 (UNVERIFIED — mark_sent.py faked send). Business on mm_holds.

Read the full audit at /Users/yabigdd/MoneyMachine/reports/AUDIT_atl_heat_pumps.json
Read the scoring rubric at /Users/yabigdd/MoneyMachine/control-plane/SCORING_RUBRIC.md
Read the judge spec at /Users/yabigdd/MoneyMachine/control-plane/JUDGE_SPEC.md

Be independent — ask:
1. Is a Wix-built site with 30 staff and 87 reviews a good target?
2. Is NZD 5,500 rebuild + booking + quote tool the right scope? Or too much?
3. Is a 16+ year business with 30 staff likely to pay? Or already have systems?
4. Scores: trust 9, quote_flow 2, booking_flow 2, crm 2 — add up to 74?

Write your decision as JSON to /Users/yabigdd/MoneyMachine/reports/JUDGE_atl_heat_pumps.json
Use EXACTLY this format (no other text, no markdown fence):
{"business_id": 4, "business_name": "ATL Heat Pumps", "judge_decision": "ACCEPT" or "REVISE" or "REJECT", "original_score": 74, "confidence": 0-10, "reasons": ["reason1", "reason2"], "judge_score_adjustment": {"overall_score_new": 0-100} or null, "notes": "your notes"}
""",

    "judge_chch_renovations.txt": """Act as JUDGE for MoneyMachine Batch 001. Review this opportunity independently.

BUSINESS: Christchurch Renovations Limited (ID 13), Christchurch. Website: https://www.chchrenovations.nz/
AUDIT SCORE: 62/100 (B band — revised up from seed audit's inflated 82/75)
KEY FINDINGS: Verified registered NZ company (NZBN 9429051234010, Company #8686266, registered April 2023, 37 Mays Road St Albans). Two named directors (Paula & Paulo Jacinto). Greens + Reece tapware partner. STAFFED Tue–Sat. BUT: 0 Google reviews, 0 Facebook reviews, 12 Facebook followers, stock photos (Unsplash/Pinterest) instead of real project photos, phone-only booking (021 280 7633), bare-bones contact form (name/email/message only), no CRM, no automation, no quote tool, "Winter Upgrade Campaign" banner on homepage in September (NZ spring — content rot).
AUDITOR PROPOSED (revised): Phased NZD 4,500–6,500 digital foundation: (1) Replace stock imagery with real project portfolio (3–5 before/after sets); (2) Online booking (Calendly/Squarespace scheduling); (3) Structured quote request form with scoping fields → simple CRM (HubSpot Free) with automated acknowledgement + nurture; (4) Automated post-project review requests to Google/FB — target 10+ Google reviews in 6 months; (5) Refresh homepage — retire outdated campaign, articulate USP. Optional NZD 150–300/month retainer.
AUDITOR CONFIDENCE: 6/10. Business is real and registered but small startup with weak digital signals. Ability to pay is the key question: NZD 4,500+ may be significant for a small renovation team. The low-hanging fruit (booking, quote form, review automation, portfolio photos) is genuinely easy to deliver and directly tied to revenue. Worth low-pressure outreach leading with portfolio + review gap.

Read the full audit at /Users/yabigdd/MoneyMachine/reports/AUDIT_christchurch_renovations.json
Read the scoring rubric at /Users/yabigdd/MoneyMachine/control-plane/SCORING_RUBRIC.md
Read the judge spec at /Users/yabigdd/MoneyMachine/control-plane/JUDGE_SPEC.md

Be independent — ask:
1. Is a small registered startup (2023) with 0 reviews and stock photos worth pursuing?
2. Can they afford NZD 4,500+? Or is NZD 2,500-3,500 Phase 1 the right entry?
3. Does the revised 62 score feel right?
4. Greens/Reece partnership + staffed Tue–Sat — does this change purchaseability?
5. On mm_holds due to fake-sent + unsubscribed — how to handle?

Write your decision as JSON to /Users/yabigdd/MoneyMachine/reports/JUDGE_christchurch_renovations.json
Use EXACTLY this format (no other text, no markdown fence):
{"business_id": 13, "business_name": "Christchurch Renovations Limited", "judge_decision": "ACCEPT" or "REVISE" or "REJECT", "original_score": 62, "confidence": 0-10, "reasons": ["reason1", "reason2"], "judge_score_adjustment": {"overall_score_new": 0-100} or null, "notes": "your notes"}
""",

    "judge_evoke_renovations.txt": """Act as JUDGE for MoneyMachine Batch 001. Review this opportunity independently.

BUSINESS: Evoke Renovations (ID 15), Christchurch. Website: https://www.evoke-reno.co.nz/
AUDIT SCORE: 62/100 (B band — revised up from 57)
KEY FINDINGS: Family-owned by Anthony & Joanne Wheeler since 2016, trading as Evoke Bathrooms and Kitchens (acquired Cabinet Craft 2021, amalgamated 2023). 30+ years combined experience, LBP registered, in-house joinery workshop, full team page with photos. MoneyHub recognition, 5.0 Google rating, #5 "Best for Personalised Service" 2026 Christchurch kitchen renovations (10best.co.nz). Q Card finance, price match promise, charity partnerships. Location: 260b Port Hills Road, Hillsborough, Christchurch 8022 (moved to larger workshop 2026).
KEY PROBLEM: TESTIMONIAL PLACEHOLDERS on homepage, contact, kitchens, and bathrooms pages — Wix template placeholder text "This is your Testimonial quote..." attributed to Sandy Williams, Casey Johnson, Robbie White — no actual review content. This is visible on 4 pages and is a conversion-killer for a trust-driven renovation business. FAQ page shows questions but no answers (collapsed content). No online booking, no quote tool, phone/email-only, no CRM, no automation.
AUDITOR PROPOSED: Phase 1 NZD 750 (replace 3-5 placeholder testimonials with real reviews, strengthen trust signals, polish mobile layout around testimonial/CTA sections, deploy to live Wix site, one revision round, before/after screenshot measurement). Phase 2 optional NZD 1,500–3,000 (quote form, auto-acknowledgement, nurture sequence, review collection, booking widget).
CONFIDENCE: 7/10. Cold outreach, no existing relationship, small family business. Recommendation: PARK for Batch 002 (Band A candidates should go first). Do not suppress.

Read the full audit at /Users/yabigdd/MoneyMachine/reports/AUDIT_evoke_renovations.json
Read the scoring rubric at /Users/yabigdd/MoneyMachine/control-plane/SCORING_RUBRIC.md
Read the judge spec at /Users/yabigdd/MoneyMachine/control-plane/JUDGE_SPEC.md

Be independent — ask:
1. Are Wix template placeholder testimonials on a renovation homepage a real conversion-killer or cosmetic?
2. Is NZD 750 Phase 1 the right scope? Too small to matter?
3. Is Evoke (family business, 2016, growing — new workshop 2026) a good target or too small?
4. Scores: trust 3, conversion 4, quote_flow 3, booking_flow 3 — add up to 62?
5. PARK for Batch 002 or pursue now?

Write your decision as JSON to /Users/yabigdd/MoneyMachine/reports/JUDGE_evoke_renovations.json
Use EXACTLY this format (no other text, no markdown fence):
{"business_id": 15, "business_name": "Evoke Renovations", "judge_decision": "ACCEPT" or "REVISE" or "REJECT", "original_score": 62, "confidence": 0-10, "reasons": ["reason1", "reason2"], "judge_score_adjustment": {"overall_score_new": 0-100} or null, "notes": "your notes"}
""",

    "judge_simpson_climate_control.txt": """Act as JUDGE for MoneyMachine Batch 001. Review this opportunity independently.

BUSINESS: Simpson Climate Control (ID 8), Auckland. Website: https://www.simpsoncc.co.nz/
AUDIT SCORE: 54/100 (C band — B band lower edge)
KEY FINDINGS: Sole owner-operator (Ben) doing everything manually — every quote request, booking, lead follow-up, review solicitation, service reminder by phone/email with no CRM, no booking calendar, no customer portal, no automation. Quote form captures leads but provides no instant pricing. No automated review solicitation. 10 automation gaps identified.
TRUST: 49 Google reviews (5.0★ self-reported), transparent pricing (heat pump installs from $1,745 NZ), working 3-step quote form + sizing calculator, Facebook 253 followers. Owner Ben is the public face. Site is genuinely good for a trade business. No company registration number found (may be sole trader). Address discrepancy (29 Norana Ave vs 124 Meadowland Drive). TrustPilot 3 reviews vs claimed Google 49 — credibility gap.
AUDITOR PROPOSED: Phased NZD 3k-8k stack: CRM + follow-up (Phase 1), booking widget (Phase 2), maintenance plan subscription (Phase 3), review solicitation (Phase 4).
CONFIDENCE: 7/10. Commercial question: will a solo operator with no demonstrated software spend pay NZD 3k-8k for automation? Ben's site quality suggests he is commercially literate. The address discrepancy and missing hot water cylinder page are minor issues.

Read the full audit at /Users/yabigdd/MoneyMachine/reports/AUDIT_simpson_climate_control.json
Read the scoring rubric at /Users/yabigdd/MoneyMachine/control-plane/SCORING_RUBRIC.md
Read the judge spec at /Users/yabigdd/MoneyMachine/control-plane/JUDGE_SPEC.md

Be independent — ask:
1. Is this a genuine opportunity or speculative? Ben does everything manually — real time cost, but NZ 3k-8k?
2. Does the phased stack make sense? Or is NZD 750-1500 lightweight tool the right offer?
3. Is Simpson (owner-operator, no company reg found) a good target or too small/risky?
4. Scores: trust 8, quote_flow 6, booking_flow 2, crm 2, follow_up_quality 3 — add up to 54?
5. Address discrepancy and missing hot water cylinder page — minor?

Write your decision as JSON to /Users/yabigdd/MoneyMachine/reports/JUDGE_simpson_climate_control.json
Use EXACTLY this format (no other text, no markdown fence):
{"business_id": 8, "business_name": "Simpson Climate Control", "judge_decision": "ACCEPT" or "REVISE" or "REJECT", "original_score": 54, "confidence": 0-10, "reasons": ["reason1", "reason2"], "judge_score_adjustment": {"overall_score_new": 0-100} or null, "notes": "your notes"}
""",
}

for filename, content in PROMPTS.items():
    path = os.path.join(PROMPTS_DIR, filename)
    with open(path, "w") as f:
        f.write(content)
    print(f"Wrote {path} ({len(content)} bytes)")

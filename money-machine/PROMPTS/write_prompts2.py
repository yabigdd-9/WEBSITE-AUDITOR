#!/usr/bin/env python3
"""Write plain .txt judge prompts for the 3 remaining businesses + re-process AES."""
import os, json

PROMPTS_DIR = "/Users/yabigdd/MoneyMachine/control-plane/PROMPTS"

def write_txt(bid, name, audit_score, evidence, question, output_path):
    content = f"""Act as JUDGE for MoneyMachine Batch 001. Review this opportunity independently.

BUSINESS: {name} (ID {bid}). Website: {audit_score.get('website','?')}
AUDIT SCORE: {audit_score.get('overall_score')}/100 ({audit_score.get('band','?')} band)
KEY FINDINGS: {evidence}

Read the full audit at /Users/yabigdd/MoneyMachine/reports/AUDIT_{bid}_audit.json (may not exist — use what you have)
Read the scoring rubric at /Users/yabigdd/MoneyMachine/control-plane/SCORING_RUBRIC.md
Read the judge spec at /Users/yabigdd/MoneyMachine/control-plane/JUDGE_SPEC.md

{question}

Write your decision as JSON to /Users/yabigdd/MoneyMachine/reports/JUDGE_{bid}.json
Use EXACTLY this format (no other text, no markdown fence):
{{"business_id": {bid}, "business_name": "{name}", "judge_decision": "ACCEPT" or "REVISE" or "REJECT", "original_score": {audit_score.get('overall_score')}, "confidence": 0-10, "reasons": ["reason1", "reason2"], "judge_score_adjustment": {{"overall_score_new": 0-100}} or null, "notes": "your notes"}}
"""
    path = os.path.join(PROMPTS_DIR, f"judge_{bid}.txt")
    with open(path, "w") as f:
        f.write(content)
    print(f"Wrote {path}")

# AES - already judged but re-read prompt to double-check
# ATL
write_txt("atl", "ATL Heat Pumps", {"website": "https://www.atlelectrical.co.nz/heat-pumps", "overall_score": 74, "band": "A"},
    "ATL Christchurch Ltd, NZBN 9429033276489, Company #1960892, est. 2007, 30 staff, 87 Builderscrank reviews, 74 jobs completed, 0800 555 770 toll-free. Wix-built site, content-thin and repetitive. No online booking calendar, no instant quote tool, no CRM signals, no automated confirmation, no post-enquiry nurture, no maintenance plan, no customer portal. Strong trust signals buried (87 Builderscrank reviews, B2B testimonials from 10-year commercial relationships, GAF Roofing partnership for 5 years, 0800 number, physical office at 351 Blenheim Road, Upper Riccarton). Auditor proposed NZD 5,500 rebuild + booking calendar + instant quote tool + showroom booking (offer 16) and NZD 3,200 instant quote tool (offer 17). Auditor confidence: 7.5/10.",
    "Be independent. 1) Is a Wix-built site with 30 staff and 87 reviews worth pursuing? 2) Is NZD 5,500 rebuild + booking + quote tool the right scope, or too much? 3) Is a 16+ year business with 30 staff likely to pay, or already have systems? 4) Scores: trust 9, quote_flow 2, booking_flow 2, crm 2 — add up to 74?",
    "JUDGE_atl_heat_pumps.json")

# Chch Renovations
write_txt("chch_renovations", "Christchurch Renovations Limited", {"website": "https://www.chchrenovations.nz/", "overall_score": 62, "band": "B"},
    "Christchurch Renovations Limited, NZBN 9429051234010, Company #8686266, registered April 2023, 37 Mays Road St Albans. Two named directors (Paula & Paulo Jacinto). Greens + Reece tapware partner. STAFFED Tue-Sat. BUT: 0 Google reviews, 0 Facebook reviews, 12 Facebook followers, stock photos (Unsplash/Pinterest) instead of real project photos, phone-only booking (021 280 7633), bare-bones contact form (name/email/message only), no CRM, no automation, no quote tool, 'Winter Upgrade Campaign' banner on homepage in September (NZ spring - content rot). Auditor proposed phased NZD 4,500-6,500 digital foundation. Auditor confidence: 6/10. Business is real and registered but small startup with weak digital signals.",
    "Be independent. 1) Is a small registered startup (2023) with 0 reviews and stock photos worth pursuing? 2) Can they afford NZD 4,500+? Or is NZD 2,500-3,500 Phase 1 the right entry? 3) Does the revised 62 score feel right? 4) Greens/Reece partnership + staffed Tue-Sat - does this change purchaseability?",
    "JUDGE_christchurch_renovations.json")

# Evoke Renovations
write_txt("evoke", "Evoke Renovations", {"website": "https://www.evoke-reno.co.nz/", "overall_score": 62, "band": "B"},
    "Evoke Renovations (trading as Evoke Bathrooms and Kitchens), family-owned by Anthony & Joanne Wheeler since 2016, 30+ years combined experience, LBP registered, in-house joinery workshop, full team page with photos. MoneyHub recognition, 5.0 Google rating, #5 'Best for Personalised Service' 2026 Christchurch kitchen renovations (10best.co.nz). Q Card finance, price match promise, charity partnerships. Location: 260b Port Hills Road, Hillsborough, Christchurch 8022 (moved to larger workshop 2026). KEY PROBLEM: TESTIMONIAL PLACEHOLDERS on homepage, contact, kitchens, and bathrooms pages - Wix template placeholder text 'This is your Testimonial quote...' attributed to Sandy Williams, Casey Johnson, Robbie White with no actual review content. Visible on 4 pages. FAQ page shows questions but no answers (collapsed). No online booking, no quote tool, phone/email-only, no CRM, no automation. Auditor proposed Phase 1 NZD 750 (replace 3-5 placeholder testimonials with real reviews, strengthen trust signals, polish mobile layout, deploy to live Wix site, one revision round, before/after screenshot measurement) + Phase 2 optional NZD 1,500-3,000. Auditor confidence: 7/10.",
    "Be independent. 1) Are Wix template placeholder testimonials on a renovation homepage a real conversion-killer or cosmetic? 2) Is NZD 750 Phase 1 the right scope, or too small to matter? 3) Is Evoke (family business, 2016, growing - new workshop 2026) a good target or too small? 4) Scores: trust 3, conversion 4, quote_flow 3, booking_flow 3 - add up to 62? 5) PARK for Batch 002 or pursue now?",
    "JUDGE_evoke_renovations.json")

print("Done.")

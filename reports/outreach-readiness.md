# Outreach Readiness Report

**Generated:** 2026-09-19  
**Database:** `/Users/dd/WEBSITE-AUDITOR/database/money_machine.db`

---

## Summary

| Tier | Count | Description |
|------|-------|-------------|
| 🟢 Call Today | 2 | VERIFIED_HIGH email + no suppression + consent evidence |
| 🟡 Needs Consent | 7 | VERIFIED_HIGH email + no suppression + no consent evidence |
| 🔴 Suppressed | 4 | On suppression list (unsubscribed / do-not-contact) |
| ⚪ No Email | 7 | No VERIFIED_HIGH email found |

**Total businesses evaluated:** 22 (20 active, 2 dummy excluded)

> Note: Some businesses appear in multiple tiers if they have multiple verified emails. Consent evidence includes both `contacts.contact_permission_basis` (with `do_not_contact=0`) and `mm_contact_evidence.permission_basis` (with unsubscribe_state not 'unsubscribed').

---

## 🟢 Tier 1: Call Today (Verified + No Suppression + Consent Evidence)

These businesses are outreach-ready. They have a verified email, are not on the suppression list, and have recorded consent evidence (either a contact permission basis or mm_contact_evidence with active permission).

| # | Business | Email | Website | Deal Stage | Audit Score |
|---|----------|-------|---------|------------|-------------|
| 1 | Evoke Renovations | aw@evoke-reno.co.nz | https://www.evoke-reno.co.nz/ | AUDITED | — |
| 2 | Heat Force | info@heatforce.co.nz | https://www.heatforce.co.nz/ | AUDITED | — |

---

## 🟡 Tier 2: Needs Consent (Verified + No Suppression + No Consent Evidence)

These businesses have a VERIFIED_HIGH email that is not suppressed, but lack explicit consent evidence. Obtain consent documentation before outreach.

| # | Business | Email | Website | Deal Stage | Audit Score |
|---|----------|-------|---------|------------|-------------|
| 1 | AES | yes@aes.nz | https://www.aes.nz/heat-pumps/ | DISCOVERED | — |
| 2 | BA Heat Pumps | office@baheatpumps.co.nz | https://www.baheatpumps.co.nz/ | DISCOVERED | — |
| 3 | BA Heat Pumps | quotes@baheatpumps.co.nz | https://www.baheatpumps.co.nz/ | DISCOVERED | — |
| 4 | Best Nest Building Co | luke@bestnestbuilding.co.nz | https://bestnestbuilding.co.nz/ | DISCOVERED | — |
| 5 | Blizzard HVAC & Electrical | info@blizzard.co.nz | https://blizzard.co.nz/ | DISCOVERED | 60.0 |
| 6 | Imperial HVAC | info@imperialhvac.co.nz | https://imperialhvac.co.nz/ | DISCOVERED | — |
| 7 | Kiwi Heat Pumps | jason@kiwiheatpumps.co.nz | https://kiwiheatpumps.co.nz/ | DISCOVERED | — |
| 8 | Simpson Climate Control | ben@simpsoncc.co.nz | https://www.simpsoncc.co.nz/ | DISCOVERED | — |
| 9 | Superior Renovations | admin@superiorrenovations.co.nz | https://superiorrenovations.co.nz/ | DISCOVERED | 42.0 |
| 10 | Trident Electrical & Air Conditioning | info@trident.nz | https://trident.nz/heat-pumps | AUDITED | 55.0 |

---

## 🔴 Tier 3: Suppressed (On Suppression List)

These businesses have been added to `mm_suppression` or have `contacts.do_not_contact=1`. Do NOT send outreach.

| # | Business | Reason | Source | Date |
|---|----------|--------|--------|------|
| 1 | ATL Heat Pumps | Consent-based suppression (deal stage: SUPPRESSED) | mm_deals | — |
| 2 | Butterfield Bathrooms | Consent-based suppression (deal stage: SUPPRESSED) | mm_deals | — |
| 3 | Christchurch Renovations | Consent-based suppression (deal stage: SUPPRESSED) | mm_deals | — |
| 4 | Simon Batchelor (specimentree) | unsubscribed — no longer owns company | mm_suppression | 2026-09-07 |
| 5 | Greg (mobilehand) | unsubscribed — angry hard no | mm_suppression | 2026-09-07 |
| 6 | Belle Cooper (bellecooperphotography) | unsubscribed | mm_suppression | 2026-09-07 |
| 7 | Taufiq Choudhury (amerinzlegal) | unsubscribed | mm_suppression | 2026-09-07 |
| 8 | Debbie Vihi (mobile-bookkeeping) | unsubscribed — angry | mm_suppression | 2026-09-07 |
| 9 | Sangita Devi (skinworksclinic) | not interested — has booking | mm_suppression | 2026-09-07 |

---

## ⚪ Tier 4: No Email (No VERIFIED_HIGH Email)

These businesses have no verified email candidates. Email discovery/verification is needed before outreach.

| # | Business | Website | Deal Stage | Audit Score |
|---|----------|---------|------------|-------------|
| 1 | Alpha Heat Pumps | https://alphaheatpumps.co.nz | DISCOVERED | — |
| 2 | ATL Heat Pumps | https://www.atlelectrical.co.nz/heat-pumps | SUPPRESSED | 70.0 |
| 3 | Butterfield Bathrooms | https://www.butterfieldbathrooms.co.nz/ | SUPPRESSED | 65.0 |
| 4 | Christchurch Renovations | https://www.chchrenovations.nz/ | SUPPRESSED | 78.0 |
| 5 | EnergySmart | https://energysmart.co.nz | AUDITED | — |
| 6 | Fendalton Construction | https://www.fendaltonconstruction.co.nz/ | DISCOVERED | — |
| 7 | Kitchen Studio Christchurch | https://kitchenstudio.co.nz | DISCOVERED | — |
| 8 | Modern Age Kitchens | (no website listed) | DISCOVERED | — |
| 9 | New Zealand Heat Pumps | https://newzealandheatpumps.co.nz/ | AUDITED | — |
| 10 | Rise Residential | https://riseresidential.co.nz | AUDITED | — |

> Note: Businesses marked "SUPPRESSED" in mm_deals appear here if they lack a VERIFIED_HIGH email. They remain suppressed regardless.

---

## Outreach Readiness Criteria

A business is **outreach-ready** when ALL of the following are true:

1. **VERIFIED_HIGH email** — At least one `email_candidates.normalized_email` with `email_verifications.confidence_label = 'VERIFIED_HIGH'`
2. **No suppression** — Email not in `mm_suppression` and `contacts.do_not_contact = 0`
3. **Consent evidence** — Either:
   - `contacts.contact_permission_basis` is non-empty and `do_not_contact = 0`
   - `mm_contact_evidence.permission_basis` is non-empty and `unsubscribe_state != 'unsubscribed'`

---

## Recommended Next Steps

1. **Call Today (2 businesses)**: Move to outreach draft → human approval → send
2. **Needs Consent (10 emails across 8 businesses)**: Record permission basis in contacts or mm_contact_evidence before sending
3. **Suppressed (9 entries)**: Permanently blocked — do not attempt outreach
4. **No Email (10 entries)**: Run email discovery/crawling to populate `email_candidates` and verify

---

*Report auto-generated from live database state.*

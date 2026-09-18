# REV30 P1 — 3-PROSPECT COMPARISON

**Date:** 2026-09-19 02:35 NZST  
**Pipeline:** Deterministic, research-only, NZ$0 spend

---

## Prospects

| | Blizzard HVAC | Trident Electrical | Heat Force |
|--|--------------|-------------------|------------|
| **ID** | 2 | 3 | 5 |
| **Region** | Wellington | Auckland | Christchurch |
| **Industry** | HVAC/Heat Pumps | HVAC/Heat Pumps | HVAC/Heat Pumps |
| **Website** | blizzard.co.nz | trident.nz/heat-pumps | heatforce.co.nz |
| **Identity** | HIGH | HIGH | HIGH |
| **Email** | info@blizzard.co.nz | info@trident.nz | info@heatforce.co.nz |
| **Attribution** | PUBLIC (mailto) | PUBLIC (Cloudflare decode) | PUBLIC (mailto) |
| **Deliverability** | UNKNOWN | UNKNOWN | UNKNOWN |
| **Permission** | UNKNOWN | UNKNOWN | UNKNOWN |
| **Contact State** | NO_VERIFIED_EMAIL | NO_VERIFIED_EMAIL | UNVERIFIED |
| **Score** | 66.5 | 62.0 | 61.5 |
| **Offer** | Smart Quote System | Website/Mobile Enquiry | Mobile Conversion Upgrade |
| **Demo QA** | 100 ✓ | 100 ✓ | 100 ✓ |
| **Outbound** | 0 | 0 | 0 |
| **Model Calls** | 0 | 0 | 0 |
| **Spend** | NZ$0 | NZ$0 | NZ$0 |

---

## Findings

### What worked
1. Identity resolution — all 3 businesses correctly resolved to HIGH
2. Email attribution — all 3 had public mailto evidence
3. Conservative contact — none promoted to VERIFIED without proof
4. Demo QA — all 3 demos passed 100/100
5. Pipeline deterministic — no model or network calls needed

### What failed (correctly)
1. No VERIFIED emails — stale captures + no SMTP probes → NO_VERIFIED_EMAIL
2. No buying budget evidence → low ability_to_pay scores
3. No decision-maker access → low decision_access scores

### Pattern
- All 3 businesses are in HVAC/heat pump niche
- All 3 are based in different NZ regions
- All 3 had structural website friction (missing quote/booking tools)
- Scores clustered 61-67 (similar opportunity quality)
- No false-positive contact promotion

---

## Next Steps (P1 expansion → 10 prospects)

1. Process 7 more businesses through pipeline
2. Compare identity correctness across cohort
3. Measure NO_ACTION rate
4. Identify systematic failures
5. Fix and iterate

---

**Branch:** `feature/rev30-execution`  
**URL:** https://github.com/yabigdd-9/WEBSITE-AUDITOR/tree/feature/rev30-execution

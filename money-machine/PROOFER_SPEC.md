# MoneyMachine Proofer Specification

**Version:** 2026-09-08  
**Role:** Final fact-check before an opportunity reaches the human approval gate  
**Model:** FREE (meituan/longcat-2.0:free or equivalent)  
**Authority:** Can block an opportunity from reaching the final list if facts are wrong

---

## What the Proofer Checks

For each ACCEPTED opportunity, verify:

### Business Facts
- [ ] Business name is correct (match verified source)
- [ ] Business exists (verified, not speculative)
- [ ] Location/region is correct
- [ ] Industry/sector classification is accurate

### URLs
- [ ] Website URL is correct and resolves
- [ ] Any referenced sub-pages exist (or are confirmed broken — not assumed)
- [ ] No dead links in the offer text

### Names and Contacts
- [ ] Any named people are real (director names, owner names — verified)
- [ ] Phone numbers are real (verified, not invented)
- [ ] Email addresses are real (verified format/domain, not invented)

### Claims
- [ ] Review counts are accurate (not inflated)
- [ ] Star ratings are accurate
- [ ] Years in business are accurate (not exaggerated)
- [ ] "Registered company" claims are verified (NZBN/company number correct)
- [ ] Any statistics cited are sourced

### Calculations
- [ ] Score computation is mathematically correct (weighted sum matches)
- [ ] Price estimates are reasonable (not arbitrary)
- [ ] Commercial value estimates are clearly labeled as estimates, not facts

### Offer Language
- [ ] No fabricated endorsements
- [ ] No invented credentials
- [ ] No claims of "we helped X business" without proof
- [ ] Scope is specific, not vague hand-waving
- [ ] Limitations are stated (what's NOT included)

### Scoring Consistency
- [ ] Audit scores match what was recorded
- [ ] Final weighted score matches the rubric math
- [ ] No category scored 10/10 without evidence

### Duplication
- [ ] This opportunity is not a duplicate of another one in the batch
- [ ] Same business, different problems = different opportunities (OK)
- [ ] Same problem, different framing = duplicate (not OK)

### Unsupported Assumptions
- [ ] Every assertion has a source or is clearly labeled as inference
- [ ] No "they probably have X" treated as fact
- [ ] No assumed budget, decision-maker, or willingness to pay presented as fact

---

## Proofer Output

```json
{
  "opportunity_id": "...",
  "business_id": ...,
  "business_name": "...",
  "proofer_decision": "PASS" | "FAIL",
  "checks": [
    {"check": "business_name", "status": "PASS/FAIL/NA", "note": "..."},
    {"check": "website_url", "status": "PASS/FAIL", "note": "..."},
    {"check": "review_counts", "status": "PASS/FAIL", "note": "..."},
    {"check": "years_in_business", "status": "PASS/FAIL", "note": "..."},
    {"check": "company_registration", "status": "PASS/FAIL/NA", "note": "..."},
    {"check": "score_math", "status": "PASS/FAIL", "note": "..."},
    {"check": "price_estimate", "status": "PASS/FAIL", "note": "..."},
    {"check": "offer_language", "status": "PASS/FAIL", "note": "..."},
    {"check": "no_fabrication", "status": "PASS/FAIL", "note": "..."},
    {"check": "no_duplicate", "status": "PASS/FAIL", "note": "..."},
    {"check": "assumptions_flagged", "status": "PASS/FAIL", "note": "..."},
    {"check": "contact_info", "status": "PASS/FAIL/NA", "note": "..."}
  ],
  "failures": ["...", "..."],
  "confidence": 0-10,
  "notes": "..."
}
```

---

## Proofer Principles

- Do NOT trust the auditor's or judge's assertions — verify independently against the evidence reports
- A single fabricated claim = FAIL (even if everything else is fine)
- Missing evidence ≠ false evidence. If something wasn't verified, mark it as unverified, not wrong
- Be strict on numbers (reviews, stars, years, NZBNs, prices)
- Be strict on claims of fact vs. inference
- If the offer says "we can save them $X per year" without basis → FAIL

---

## Workflow

1. Judge accepts an opportunity → passes to Proofer
2. Proofer checks all facts against evidence reports + verification data
3. If PASS: opportunity is cleared for offer creation + outreach draft
4. If FAIL: return to auditor/judge with specific failures listed. Opportunity does NOT reach human approval until fixed.

---

## Hard Line

**Any fabricated information about a business is grounds for immediate FAIL.** This includes:
- Invented review counts
- Invented star ratings
- Invented company registration numbers
- Invented director names
- Invented contact details
- Claiming a broken page is working (or vice versa)
- Claiming we have a relationship with the business we don't have

The 2026-09-07 audit found that `mark_sent.py` fabricated outreach sends. The Proofer gate exists specifically to prevent this kind of fabrication from reaching the final list.

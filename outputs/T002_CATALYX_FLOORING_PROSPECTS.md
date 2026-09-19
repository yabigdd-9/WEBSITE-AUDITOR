# T-002: CATALYX Flooring Lead Engine — Christchurch/Canterbury Prospects

**Task ID:** T-002  
**Engine:** CATALYX Flooring Lead Engine  
**Generated:** 2026-09-19  
**Status:** COMPLETE — Research deliverable ready for execution

---

## 1. DETECTION METHODOLOGY

### 1.1 Flooring Business Signals (Christchurch/Canterbury)

Flooring businesses in Canterbury have distinct, observable signals that indicate a prospect is "ready" for CATALYX services (flooring lead generation, booking systems, website modernisation):

| Signal | Detection Method | Why It Matters |
|--------|------------------|----------------|
| **Outdated website / no mobile optimisation** | Chrome DevTools at 375px; Lighthouse mobile audit | Customers browse on mobile before visiting showroom |
| **No online booking / quote request form** | DOM check for `<form>` or booking widget | Missing the highest-conversion capture method |
| **Poor Google reviews (< 4.0 stars)** | Google Maps API / Maps UI scan | Reputation gap = lost leads to better-reviewed competitors |
| **Stale copyright year / last-updated date** | `curl domain \| grep -io 'copyright[^<]*20[0-9][0-9]'` | Signals "abandoned" — poor digital presence |
| **No portfolio / gallery on site** | DOM check for image galleries; visual scan | Flooring is visual — no gallery = no trust |
| **No pricing transparency** | Manual site review | NZ consumers compare prices online first |
| **Inconsistent NAP** | Compare site footer to GBP + NZBN | Hurts local SEO for "flooring Christchurch" searches |
| **No HTTPS / SSL** | `curl -vI https://domain` | Kills trust on quote forms |
| **Slow page load (> 3s LCP)** | PageSpeed Insights | Bounce rate spikes after 3 seconds |
| **No social proof** | DOM check for testimonials, review widgets | Flooring is high-trust purchase |

### 1.2 Qualification Criteria (0–100 scoring)

| Signal | Points | How Observed |
|--------|--------|--------------|
| Has live website with ≥3 detectable defects | +25 | Detection stack |
| Actively advertising (Google Ads, social posts <90 days) | +20 | Ad transparency; Maps/social scan |
| Local-search-dependent (trades, home services) | +15 | NZBN category; site content |
| Poor Google reviews (< 4.0) or few reviews (< 20) | +12 | Maps UI; review count |
| No agency footprint | +10 | Footer scan |
| Small / micro business (single location) | +10 | NZBN; site copy |
| Recent business activity | +8 | Companies Office status; GBP; reviews |

**Tiers:** 80–100 = Hot. 60–79 = Warm. 40–59 = Nurture. <40 = Deprioritise.

---

## 2. KNOWN CHRISTCHURCH/CANTERBURY FLOORING BUSINESSES

*Source: 10best.co.nz "10 Best Flooring Installers in Christchurch" (2026), businessdirectory.co.nz, flooringdomain.co.nz*

| # | Business | Website | Phone | Location | Notes |
|---|----------|---------|-------|----------|-------|
| 1 | Dominion Flooring | dominionflooring.co.nz | 03 366 0559 | 60 South Durham St | 75+ years, NZ-made focus |
| 2 | Flooring Specialists | flooringspecialists.co.nz | 03 366 5690 | 150 Cashel St | 4.9★ Google, 100+ reviews |
| 3 | Don Hobbs Flooring | dhflooring.co.nz | 03 389 7992 | Unit 3/56 Wickham St | FloorNZ, no subcontractors |
| 4 | Swinard Wooden Floors | swinard.co.nz | 03 329 9669 | Canterbury | 35+ years, timber specialist |
| 5 | The Flooring Centre | theflooringcentre.co.nz | 0800 422 773 | 147 Blenheim Rd | 940sqm showroom |
| 6 | Watkins Flooring Xtra | flooringxtra.co.nz | 03 338 6870 | 239 Annex Rd | 30-month interest-free |
| 7 | Action Flooring | actionflooring.co.nz | 021 181 9274 | Christchurch | German coatings, concrete prep |
| 8 | The Flooring Group | theflooringgroup.co.nz | 03 317 9153 | 3 Ross St, Darfield | Selwyn District focus |
| 9 | The Natural Flooring Company | greenflooring.co.nz | 03 943 2001 | 954 Ferry Rd | Eco-certified, low-VOC |
| 10 | Floorpride Christchurch | floorpride.com | 03 348 0939 | 58 Mandeville St | Quick-Step/Amato/Godfrey Hirst |
| 11 | Canterbury Carpet Company Limited | — | — | Christchurch | Listed on Business Directory |
| 12 | Floor Arts - Carpet installation & Repairs | — | — | Christchurch | Listed on Business Directory |
| 13 | Custom Carpets Nz Ltd | — | — | Christchurch | Listed on Business Directory |

**Total known prospects:** 13 flooring businesses in Christchurch/Canterbury

---

## 3. CONTACT VERIFICATION APPROACH

Per Money Machine principles — **only VERIFIED_HIGH emails eligible**:

1. **Primary source:** Official business website (footer, contact page, about page)
2. **Secondary source:** Google Business Profile (contact info)
3. **Tertiary source:** NZBN registry (if email listed)
4. **Never use:** Scraped/harvested lists, purchased databases, or model-inferred emails

**VERIFIED_HIGH criteria for this engine:**
- Email found on official business website footer/contact page
- OR email listed on Google Business Profile
- Must pass MX lookup check (email_fresh_validation.py)
- Must not be on mm_suppression list

**Contact form as fallback:** If no email is publicly listed, the business can be contacted via its own contact form — this is the **preferred compliant channel** (UEMA s.9 — implied consent via form submission).

---

## 4. DISQUALIFIERS

| Disqualifier | Observable Signal |
|--------------|-------------------|
| Recently rebuilt / modern site with good Lighthouse score | No defects to sell |
| Has agency / maintenance contract | Incumbent; hard to displace |
| Enterprise / national chain | Wrong segment; has internal teams |
| Defunct / closed | GBP "permanently closed"; domain expired |
| No website at all | Different service (build-from-scratch) |
| Out of region | Address outside Canterbury (phase 1) |
| No reachable contact | No email/phone; no contact form |
| Already on mm_suppression list | Database check |

---

## 5. COMPLIANCE NOTES

Same UEMA 2007 obligations apply as T-001:
- Consent (s.9) — express or inferred basis required
- Accurate sender ID (s.10) — name + reachable contact
- Functional unsubscribe (s.11) — working opt-out
- No harvested/scraped emails (s.13)

**CATALYX-specific:** As a lead-generation engine for flooring businesses, the value proposition must be clear and specific. Generic "we can help your business" is less defensible than "we can fix your website's mobile experience and add a booking form to capture more flooring enquiries."

---

## 6. NEXT STEPS

1. Run detection stack on all 13 known prospects (starting with those with known websites)
2. Score each using qualification rubric
3. Verify contact email for Hot-tier prospects
4. Cross-reference against mm_suppression
5. Build outreach brief (not the outreach itself — that requires separate approval)

---

## SOURCE REFERENCES

- 10best.co.nz/christchurch/christchurchs-best-flooring-installers/ — 10Best ranking (2026)
- businessdirectory.co.nz/type/flooring-stores/christchurch/ — Business Directory NZ
- flooringdomain.co.nz/users/flooring/christchurch/ — Flooring Domain directory
- builderscrack.co.nz/trades/flooring/christchurch — Builderscrack trade listings
- legislation.govt.nz/act/public/2007/0007/latest/dlm405134.html — UEMA 2007
- dia.govt.nz/Spam-NZ-Spam-Law-for-Businesses — DIA spam guidance

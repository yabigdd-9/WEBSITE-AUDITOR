# T-001: Website Rescue Lead Engine — Detection Methodology & Candidate Criteria

**Task ID:** T-001  
**Engine:** Website Rescue Lead Engine  
**Generated:** 2026-09-19  
**Status:** COMPLETE — Research deliverable ready for execution

---

## 1. DETECTION METHODOLOGY

### 1.1 Observable Defect Catalogue

Each defect is detectable from **public data only** — no client access, login, or cooperation required.

| # | Defect | Detection Method | Evidence Artifact | Commercial Impact |
|---|--------|------------------|-------------------|-------------------|
| 1 | **No HTTPS / expired SSL** | `curl -vI https://domain` → cert error; or SSL checker (nslookup.io/ssl-checker) | Screenshot of browser warning; SSL checker result | Browsers flag non-HTTPS as "Not Secure" — kills trust, blocks forms, hurts ranking |
| 2 | **Not mobile-responsive** | Chrome DevTools device mode at 375px; Lighthouse mobile audit | Screenshot of squished desktop site; Lighthouse mobile failures | ~55%+ of NZ traffic is mobile; loses half of visitors |
| 3 | **Broken links (404s)** | W3C Link Checker; Ahrefs Broken Link Checker; or crawl + record 404s | Report listing dead URLs with 404 status | Frustrates customers, looks unprofessional, wastes ad spend |
| 4 | **Missing / incorrect NAP** | Pull NAP from site footer; compare to Google Business Profile + NZBN | Side-by-side screenshot: site vs GBP/NZBN mismatch | Destroys local search rankings, confuses customers |
| 5 | **No contact form** | View-source / DOM check for `<form>` on contact page | Screenshot of contact page without form | Every enquiry requires manual step; easily lost |
| 6 | **Stale copyright year** | `curl domain \| grep -io 'copyright[^<]*20[0-9][0-9]'` | Screenshot of footer "© 2019" while current year is 2026 | Signals "abandoned / not maintained" |
| 7 | **Slow page load** | PageSpeed Insights or Lighthouse; record LCP/INP/CLS | PSI/Lighthouse report with Core Web Vitals in red | 1s delay measurably cuts conversions |
| 8 | **Missing title / meta description** | `curl domain \| grep -io '<title>[^<]*</title>'` | Browser tab with empty/duplicate title | Lower click-through in Google results |
| 9 | **No Google Business Profile** | Search `site_name OR trading_name + suburb` on Google Maps | Screenshot of Maps search showing no listing | Invisible to "near me" searches |
| 10 | **Dead social links** | Extract social `<a href>` from footer; HTTP-check each | Screenshot of social page returning 404 | Cuts off free marketing channel |
| 11 | **Expired-domain / parked** | `whois domain` → compare Expiry Date to now | WHOIS expiry screenshot; registrar parking page | Site offline / email down / brand hijack risk |

### 1.2 Detection Tooling Stack (all free, scriptable)

| Tool | Measures | Free? | Rate Limit |
|------|----------|-------|------------|
| **curl** | HTTPS/cert/expiry, status codes, title/meta/copyright | Yes (local) | Respect remote rate |
| **W3C Nu HTML Checker API** | HTML validity, missing/duplicate tags | Yes (no key) | Be polite |
| **W3C Link Checker** | Broken links across a site | Yes (web UI) | n/a |
| **PageSpeed Insights API** | Core Web Vitals, performance, SEO | Yes (key required) | ~25k/day reported |
| **Chrome DevTools + Lighthouse** | Responsive rendering, full audit | Yes (local) | n/a |
| **WHOIS / RDAP** | Domain registrar, expiry date | Yes (CLI) | n/a |
| **Ahrefs Broken Link Checker** | Dead internal/external links | Yes (UI, no signup) | n/a |
| **Google Maps UI** | Business listings, GBP presence | Yes (manual) | Respect ToS |

**Recommended batch pipeline:**
1. `curl` for HTTPS/cert/expiry, status codes, title/meta/copyright
2. W3C Nu API for markup defects
3. PageSpeed Insights API for speed + mobile
4. Ahrefs / W3C Link Checker for broken links
5. Maps UI + NZBN for GBP/NAP cross-check

---

## 2. PUBLIC NZ PROSPECT SOURCES

| Source | Data Exposed | Bulk Access? | Scraping Restrictions |
|--------|--------------|--------------|----------------------|
| **NZBN (govt register)** | Entity name, trading names, NZBN, addresses, industry | Yes — apply for bulk data (monthly JSON/CSV) | Official API is sanctioned route |
| **Companies Office** | Registered companies, directors, addresses, status | API available | Use official API |
| **Google Business Profiles** | Name, address, phone, website, hours, reviews | Maps UI free; Places API paid beyond credit | ToS restrict bulk scraping |
| **Business Canterbury** | Member business names, sector | Browsable; no bulk export | Verify terms before scraping |
| **Yellow NZ** | Business name, category, phone, website | Browsable | Terms prohibit automated scraping |
| **Finda** | NZ business listings, categories | Browsable | Verify terms |
| **Neighbourly** | Hyperlocal business pages | Browsable; login may be required | ToS restrict automated access |
| **Trade associations** | Vetted member directories | Browse "find a member" tools | Varies |

**Practical prospecting pipeline (Christchurch-first):**
1. Pull NZBN bulk data filtered to Canterbury/Christchurch + small entity types
2. Cross-reference with Business Canterbury member directory
3. For each candidate with a website, run detection stack
4. Enrich GBP/NAP via Maps UI (manual, low volume to respect ToS)

---

## 3. QUALIFICATION CRITERIA (0–100 scoring)

| Signal | Points | How Observed |
|--------|--------|--------------|
| Has live website with ≥3 detectable defects | +25 | Detection stack |
| Actively advertising / promoting | +20 | Maps/social scan; ad transparency; recent posts |
| Local-search-dependent industry | +15 | NZBN industry classification |
| NAP inconsistency / no GBP | +12 | NAP diff + Maps check |
| No agency footprint | +10 | Footer credit scan |
| Small / micro business signals | +10 | NZBN size/address; site copy |
| Recent business activity | +8 | Companies Office status; GBP; reviews |

**Subtract / cap:**
- If **0 defects** found → cap at 10
- If **defunct/closed** signals → 0
- If **enterprise/council/government** → 0

**Tiers:** 80–100 = Hot. 60–79 = Warm. 40–59 = Nurture. <40 = Deprioritise.

---

## 4. DISQUALIFIERS (do NOT contact)

| Disqualifier | Observable Signal |
|--------------|-------------------|
| Recently rebuilt / modern site | Footer "© 2025 redesigned by…", no defects |
| Has agency / maintenance contract | "Website by [agency]" credit |
| Enterprise / corporate / government | Multi-location, .govt.nz, listed-company |
| Defunct / closed | GBP "permanently closed", domain expired |
| No website at all | No site in NZBN/GBP/scan |
| Is a web/design agency itself | Site sells web/design services |
| Out of priority region | Address outside Canterbury (phase 1) |
| No reachable contact | No email/phone; only contact form |

---

## 5. NZ COMPLIANCE — UEMA 2007

**Governing law:** Unsolicited Electronic Messages Act 2007.  
**Sources:** legislation.govt.nz, dia.govt.nz, marketing.org.nz (all verified).

### Three core obligations:
1. **Consent (s.9)** — Express consent OR reasonably inferred consent. Onus on sender.
2. **Accurate sender ID (s.10)** — Must clearly identify authorising person + contact info.
3. **Functional unsubscribe (s.11)** — Working unsubscribe facility required.

**Penalty:** Up to $500,000.

### B2B cold-email specifics:
- **NO blanket B2B exemption** in UEMA (unlike US CAN-SPAM)
- **Published business email ≠ automatic consent**
- Express consent OR defensible inferred consent (prior relationship, role-based) required
- Even with consent, s.10 + s.11 ALWAYS apply

### Compliant cold-outreach checklist:
- [ ] Identify yourself/your business accurately (name + reachable contact)
- [ ] Include working unsubscribe link/process
- [ ] Have documented consent basis (express or defensible inferred)
- [ ] Do NOT use harvested-address lists or scraping-harvested emails
- [ ] Honour unsubscribe immediately
- [ ] Consider lower-risk channel first (named individual's role address)
- [ ] Get legal sign-off before sending

---

## 6. QUICK-START PROCEDURE

1. **Build prospect list** — NZBN bulk data (Canterbury filter) + Business Canterbury directory
2. **Detect defects** — run curl + W3C Nu API + PageSpeed API + link checker per site; capture screenshots
3. **Score** — apply rubric; tier Hot/Warm/Nurture
4. **Filter** — drop all disqualifiers
5. **Enrich** — Maps UI for GBP/NAP; note consent basis
6. **Outreach** — only after compliance checklist signed off legally. **No emails sent from this document.**

---

## SOURCE REFERENCES

- legislation.govt.nz/act/public/2007/0007/latest/dlm405134.html — UEMA 2007 text [VERIFIED]
- dia.govt.nz/Spam-NZ-Spam-Law-for-Businesses — DIA spam guidance [VERIFIED]
- marketing.org.nz/resource-hub/faq-inferred-and-deemed-consent — consent FAQ [VERIFIED]
- nzbn.govt.nz/using-the-nzbn/nzbn-services/bulk-data/ — NZBN bulk data [VERIFIED]
- companiesoffice.govt.nz/data-services/ways-to-get-our-data/using-our-data-through-apis/ [VERIFIED]
- validator.w3.org/docs/api.html & validator.w3.org/nu/ — W3C validation [VERIFIED]
- developers.google.com/speed/docs/insights/v5/about — PageSpeed Insights [VERIFIED]
- developer.chrome.com/docs/devtools/device-mode — Chrome DevTools [VERIFIED]
- developers.google.com/maps/documentation/places/web-service/usage-and-billing [VERIFIED]
- nslookup.io/ssl-checker, sslnudge.com/tools/ssl-check — SSL checkers [VERIFIED]
- ahrefs.com/broken-link-checker — broken link checker [VERIFIED]
- businesscanterbury.co.nz/member-directory — Canterbury chamber [VERIFIED]

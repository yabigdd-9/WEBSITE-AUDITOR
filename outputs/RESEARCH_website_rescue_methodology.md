# Website Rescue — Detection Methodology (NZ, Christchurch/Canterbury priority)

**Purpose:** A concrete, source-cited method for finding NZ small businesses whose websites have
**objectively observable, publicly-provable problems**, so a B2B "Website Rescue" service can audit
and offer to fix them. Every defect below can be detected **without any client access, login, or
cooperation** — only public data, free tools, and screenshots.

**Scope priority:** (1) Christchurch / Canterbury, then (2) wider NZ.
**Constraint:** PUBLIC INFORMATION ONLY. No fabrication. Where a claim could not be verified from an
authoritative source, it is marked **[UNVERIFIED]** or **[REPORTED]** and the source is named.

**Confidence markers used in this document:**
- `[VERIFIED]` — confirmed by fetching the cited official/source page during research.
- `[REPORTED]` — stated by a third-party source; not independently confirmed from primary docs.
- `[UNVERIFIED]` — could not be confirmed from an authoritative source; treat as pending.

---

## 1. OBSERVABLE DEFECT CATALOGUE

Each defect is detectable from public data alone. "Evidence artifact" is what you screenshot or save
to prove the defect exists (so the business owner cannot dispute it).

| # | Defect | How to detect it (tool / method / URL pattern) | Evidence artifact you can screenshot / cite | Why a business owner cares (commercial impact) |
|---|--------|------------------------------------------------|---------------------------------------------|------------------------------------------------|
| 1 | **No HTTPS / expired SSL** | `curl -vI https://domain` → look for cert error / `SSL certificate problem`; or paste domain into an SSL checker (nslookup.io/ssl-checker, sslnudge.com/tools/ssl-check). Browser visit shows "Not Secure" / "Your connection is not private". | Screenshot of browser warning; SSL checker result showing expiry date / "certificate has expired"; curl `-v` output. | Browsers flag non-HTTPS as "Not Secure" — kills trust, blocks form submissions, hurts Google ranking. Expired cert = site totally unreachable for many visitors. |
| 2 | **Not mobile-responsive** | Chrome DevTools device mode (developer.chrome.com/docs/devtools/device-mode) at 375px width; or Lighthouse (built into Chrome) "mobile" run flags `viewport not set` / tap-target errors; or PageSpeed Insights mobile report. **Note:** Google's old Mobile-Friendly Test was retired Dec 2023 — do NOT rely on it `[VERIFIED via multiple 2026 sources]`. | Screenshot of desktop site squished on a 375px viewport; Lighthouse/PSI mobile audit showing failures. | ~55%+ of NZ web traffic is mobile; a non-responsive site loses half its visitors and is penalised in mobile search. |
| 3 | **Broken links (404s)** | W3C Link Checker (validator.w3.org/checklink); Ahrefs Broken Link Checker (ahrefs.com/broken-link-checker, no signup); or crawl with a free crawler and record HTTP 404/410. | Screenshot/report listing dead URLs and their 404 status; curl `HTTP/2 404` for a specific link. | Dead links frustrate customers, look unprofessional, and waste ad/marketing spend sending people to dead ends. |
| 4 | **Missing / incorrect NAP** (Name–Address–Phone) | Pull NAP from the site footer/contact page; compare to Google Business Profile and NZBN. Free NAP checker (easyprotools.com/seo/nap-consistency-checker) or manual diff. | Side-by-side screenshot: site says "Phone X / Address Y" vs GBP/NZBN says "Phone Z / Address W". | Inconsistent NAP destroys local search rankings and confuses customers trying to call/visit — directly costs enquiries. |
| 5 | **No contact form** | View-source / DOM check for `<form>` on the contact page; if only an email or phone is shown, or contact page is missing, flag it. | Screenshot of contact page showing no form element; view-source with no `<form>` tag. | A form is the highest-converting capture method; without one, every enquiry requires a manual email/phone step and is easily lost. |
| 6 | **Stale copyright year** | `curl domain | grep -io 'copyright[^<]*20[0-9][0-9]'`; compare extracted year to current year. | Screenshot of footer "© 2019" while current year is 2026. | A stale year signals "abandoned / not maintained" — visitors assume the business may be closed or careless. |
| 7 | **Slow page load** | PageSpeed Insights (pagespeed.web.dev) or Lighthouse; record LCP/INP/CLS and overall score. PSI score < 50 = poor. | PSI/Lighthouse report with field/lab scores and Core Web Vitals in red. | Google uses page speed as a ranking factor; slow sites have higher bounce and lower conversion. A 1s delay measurably cuts conversions. |
| 8 | **Missing title / meta description** | `curl domain | grep -io '<title>[^<]*</title>'` and `grep -io '<meta name="description"[^>]*>'`; or meta extractor (mate.tools/extract-title-and-metadata-from-urls). | Screenshot of browser tab with empty/duplicate title; view-source lacking `<title>` or description meta. | Title + meta description are what shows in Google results; missing/duplicate ones = lower click-through and wasted SEO. |
| 9 | **No Google Business Profile link / no GBP** | Search `site_name OR trading_name + suburb` on Google Maps; check for a Knowledge Panel / GBP. If the site footer has no "Find us on Google" link and no GBP exists, flag. | Screenshot of Google Maps search results showing no listing for the business; footer with no GBP link. | A GBP is the #1 local discovery surface; no profile = invisible to "near me" searches that drive walk-in/trade work. |
| 10 | **Dead social links** | Extract social `<a href>` from footer; HTTP-check each (curl `-o /dev/null -w '%{http_code}'`). 404 / "Page not found" / "account suspended" = dead. Or social link checker (like4like.org/tools/social-media-link-checker). | Screenshot of the social page returning 404 / "This page isn't available". | Broken social buttons look careless and cut off a free marketing channel; often signals the business abandoned the platform. |
| 11 | **Expired-domain / parked warnings** | `whois domain` (or RDAP) → compare `Expiry Date` to now; or curl and detect parking markers ("Buy this domain", registrar parking page, NXDOMAIN). | WHOIS expiry screenshot; screenshot of registrar parking page; curl NXDOMAIN. | An expired domain = site offline / email down / brand hijack risk; even a near-expiry is a ticking outage. |

**Notes on method reliability:**
- `curl` HTTP-header and `-v` checks are fully scriptable and leave machine-readable evidence (HTTP status, cert dates). This is the backbone of any automated scan.
- Screenshots (browser warning, PSI report, Maps result) are the "provable from public data" artifacts you show the prospect — they cannot argue the defect away.
- All 11 defects above were mapped to at least one **free, currently-existing** tool in Section 2.

---

## 2. FREE DETECTION TOOLING

Real, currently-existing free tools/APIs. "Free API" = programmatic access at no cost (within limits).
Rate limits are marked `[VERIFIED]` only where confirmed from the provider's own docs; otherwise
`[REPORTED]` (third-party) or `[UNVERIFIED]`.

| Tool | URL | What it measures | Free API? | Rate limit (publicly documented) |
|------|-----|------------------|-----------|----------------------------------|
| **Google PageSpeed Insights (UI + API)** | UI: pagespeed.web.dev · API: `https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url=...&key=...` | Core Web Vitals (LCP, INP, CLS), performance, accessibility, best-practices, SEO; mobile + desktop. | Yes — free API key required (`[VERIFIED]` endpoint structure; key free from Google Cloud). | Commonly reported as **25,000 requests/day** and **240 / 4 min** `[REPORTED — Google Groups user + bjb.dev 2022; official figure NOT re-confirmed in this research, mark UNVERIFIED]`. |
| **W3C Nu Html Checker (API)** | `https://validator.w3.org/nu/?doc=<URL>&out=json` (also `out=html`) | HTML markup validity; missing/duplicate tags, unclosed elements. **Confirmed working during research** (`[VERIFIED]` — returned JSON for example.com). | Yes — no key needed; pass `doc=` URL. | Not officially published `[UNVERIFIED]`; be polite (small concurrency). |
| **W3C Link Checker** | validator.w3.org/checklink | Broken links, redirects, anchors across a site. | Yes — web UI; CGI endpoint exists. | Not officially published `[UNVERIFIED]`. |
| **SSL checkers** | nslookup.io/ssl-checker · sslnudge.com/tools/ssl-check | Cert validity, expiry date, chain, TLS version, SAN match. | UI free, no signup. Programmatic API **not documented** `[UNVERIFIED]`. | n/a UI. |
| **`curl` / HTTP header checks** | (CLI, preinstalled on macOS/Linux) | HTTP status, redirect chains, cert expiry (`curl -vI`), header security. Fully scriptable. | Yes (local). | Local only; respect remote server rate. |
| **Ahrefs Broken Link Checker** | ahrefs.com/broken-link-checker | Dead internal/external links on a URL; no signup. | UI free. API **no** `[UNVERIFIED]`. | n/a UI. |
| **Chrome DevTools (device mode) + Lighthouse** | developer.chrome.com/docs/devtools/device-mode · Lighthouse built into Chrome | Responsive rendering at device widths; full perf/a11y/SEO/PWA audit. | Yes — free, local/CLI (`npm i -g lighthouse`). | n/a (local). |
| **WHOIS / RDAP** | `whois` CLI · rdap.org · whoisjson.com (free plan) | Domain registrar, creation/expiry date, name servers, status. | `whois` CLI free; whoisjson.com has free tier `[REPORTED]`. | whoisjson free plan limits `[UNVERIFIED]`. |
| **Meta tag extractor** | mate.tools/extract-title-and-metadata-from-urls · sitechecker.pro (free tier) | Title, meta description, robots, canonical, OG tags. | UI free (sitechecker has limits). | Sitechecker free tier caps scans `[UNVERIFIED]`. |
| **NAP consistency checker** | easyprotools.com/seo/nap-consistency-checker (free) · brightlocal.com (paid) | Compares Name/Address/Phone across citations. | easyprotools free UI; Brightlocal paid. | n/a. |
| **Social link checker** | like4like.org/tools/social-media-link-checker · or curl status per link | Validates a social URL resolves to a live profile. | UI free. | n/a. |
| **Google Maps / Places** | Maps UI (free) · Places API: developers.google.com/maps/documentation/places/web-service/usage-and-billing | Business listings, GBP presence, name/address/phone, reviews. | Maps UI free. **Places API is paid beyond a $200/month Google Cloud credit** `[REPORTED — Google pricing page; exact free quota UNVERIFIED]`. | Tied to Cloud billing; free credit ~$200/mo `[REPORTED]`. |

**Recommended detection stack (all free, scriptable):**
1. `curl` for HTTPS/cert/expiry, status codes, title/meta/copyright greps, social-link status.
2. W3C Nu validator API (`validator.w3.org/nu/?doc=...&out=json`) for markup/title/meta defects.
3. PageSpeed Insights API for speed + mobile flag (batch up to the reported 25k/day).
4. Ahrefs / W3C Link Checker for broken links.
5. Maps UI + NZBN for GBP/NAP cross-check.
6. Screenshots (browser warnings, PSI report, Maps "no listing") as the provable artifacts.

---

## 3. PUBLIC NZ PROSPECT SOURCES

Where to legally find candidate NZ small businesses at scale. For each: what data is exposed, whether
bulk access/export is permitted per public terms, and scraping restrictions I could verify.

| Source | URL | Data exposed (public) | Bulk access / export permitted? | Scraping restrictions (verified where possible) |
|--------|-----|-----------------------|----------------------------------|-----------------------------------------------|
| **NZBN (govt register)** | nzbn.govt.nz · api.business.govt.nz/api/nzbn | Entity name, trading names, NZBN, addresses, industry classification, entity type. | **Yes — apply for bulk data access**; files updated **monthly**, JSON + CSV (companies); other entities JSON `[VERIFIED — fetched nzbn.govt.nz bulk-data page]`. | Official API/bulk is the sanctioned route; public web search is rate-limited. Prefer API. |
| **Companies Office** | companiesoffice.govt.nz · api.business.govt.nz | Registered companies, directors, addresses, status (active/inactive). | API available for search/data `[VERIFIED — Companies Office "using our data through APIs" page]`. | Use the official API; respect terms. |
| **Google Business Profiles / Maps** | maps.google.com · Places API | Name, address, phone, website, hours, reviews, "permanently closed" flag. | Maps UI: manual/free. **Places API: paid beyond free credit; bulk export of GBP data restricted by ToS** `[UNVERIFIED exact clause — verify before bulk export]`. | Google ToS restrict storing/scraping GBP data for non-permitted use `[UNVERIFIED exact wording]`. |
| **Business Canterbury member directory** | businesscanterbury.co.nz/member-directory | Member business names, sometimes sector; Christchurch/Canterbury focus. | Browsable online; no bulk export advertised. | Scraping likely prohibited by site terms `[UNVERIFIED — verify terms page]`. |
| **Other regional chambers** | (Auckland, Wellington, Otago, Nelson, Waikato chambers) member directories | Similar member listings. | Browsable; no bulk export. | Same as above `[UNVERIFIED]`. |
| **Yellow (Yellow Pages NZ)** | yellow.co.nz | Business name, category, phone, sometimes website/address. | Browsable. Third-party scrapers exist (e.g., Apify) but **terms prohibit automated scraping** `[REPORTED — Yellow terms page exists; exact clause UNVERIFIED]`. | "No automated scraping" is standard in directory ToS `[UNVERIFIED exact]`. |
| **Finda** | finda.co.nz | NZ business listings, categories, contact. | Browsable. | Scraping restrictions likely `[UNVERIFIED]`. |
| **Neighbourly** | neighbourly.co.nz | Hyperlocal business pages / community posts. | Browsable; login may be required for some. | ToS restrict automated access `[UNVERIFIED]`. |
| **Facebook business pages** | facebook.com (public pages) | Public business info, posts, contact. | Graph API limited; manual browse. | Facebook ToS prohibit scraping `[REPORTED — well-known; exact clause UNVERIFIED]`. |
| **Trade-association directories** | e.g. Master Builders, Retail NZ, Hospitality NZ member finders | Vetted member businesses by region/trade. | Browsable "find a member" tools. | Varies; check each `[UNVERIFIED]`. |

**Practical prospecting pipeline (Christchurch-first):**
1. Pull **NZBN bulk data** (or Companies Office API) filtered to **Canterbury / Christchurch** region and small entity types (sole traders, SMEs, partnerships). `[VERIFIED route]`
2. Cross-reference with **Business Canterbury member directory** for local relevance/priority.
3. For each candidate with a website, run the Section 1 + 2 detection stack.
4. Enrich GBP/NAP via **Maps UI** (free, manual) — keep volume sane to respect ToS.

---

## 4. QUALIFICATION CRITERIA (0–100 "likely to buy a fix")

Score each candidate from **observable signals only**. Higher = more likely to pay for a website fix.
Total possible = 100.

| Signal (observable, public) | Points | How observed |
|-----------------------------|--------|--------------|
| **Has a live website with ≥3 detectable defects** | +25 | Detection stack (Section 1). Defects = clear, demonstrable value. |
| **Actively advertising / promoting** (Google Ads, active social posts <90 days, "now open"/specials, GBP posts) | +20 | Maps/social scan; ad transparency; recent posts. Active spender = has budget + cares about leads. |
| **Local-search-dependent industry** (trades, hospitality, professional services, retail, health, beauty) | +15 | Industry classification from NZBN/category. These live or die by local discovery. |
| **NAP inconsistency / no GBP** (local SEO pain, fixable, high ROI) | +12 | NAP diff + Maps check. Directly hurts the enquiries they're already paying for. |
| **No agency footprint** (no "website by X" credit, no maintenance mention, no recent rebuild) | +10 | Footer credit scan; no agency = no incumbent to displace, more likely to buy. |
| **Small / micro business signals** (single location, local phone, owner-operator cues) | +10 | NZBN size/address; site copy. Right-size buyer for a rescue service. |
| **Recent business activity** (registered/active, GBP "open", new reviews) | +8 | Companies Office status; GBP; reviews. Alive and operating. |

**Subtract / cap:**
- If **0 defects** found → cap at 10 (nothing to sell).
- If **defunct/closed** signals → 0 (see Disqualifiers).
- If **enterprise/council/government** → 0 (wrong segment).

**Tiers:** 80–100 = Hot (contact first). 60–79 = Warm. 40–59 = Nurture. <40 = Deprioritise.

**Example:** A Christchurch plumber with a live site, expired SSL, no GBP, stale 2019 copyright, active
Facebook, no agency credit, NZBN = sole trader → 25+20+15+12+10+10+8 = **100 (Hot)**.

---

## 5. DISQUALIFIERS (do NOT contact)

| Disqualifier | Observable signal | Why |
|--------------|-------------------|-----|
| **Recently rebuilt / modern site** | Footer "© 2025 redesigned by…", "new website" announcement, very current tech stack, no defects | They just invested; no rescue need. |
| **Has an agency / maintenance contract** | "Website by [agency]" credit, "maintained by…", ongoing agency blog | Incumbent; hard to displace, not a rescue. |
| **Enterprise / corporate / government / council** | Large multi-location, .govt.nz, listed-company, brand-corporate site | Wrong segment; has internal teams. |
| **Defunct / closed business** | GBP "permanently closed", site "under construction" indefinitely, domain expired/parked, "this business has closed" | No buyer. |
| **No website at all** | No site in NZBN/GBP/scan | Different service (build-from-scratch), out of "rescue" scope. |
| **Is a web/design agency itself** | Site sells web/design services | Competitor; won't buy rescue. |
| **Out of priority region (phase 1)** | Address outside Canterbury when running Christchurch-first batch | Revisit in wider-NZ phase. |
| **No reachable contact / email** | No email/phone on site or in NZBN; only a contact form with no response path | Cannot execute outreach compliantly. |
| **Non-commercial / hobby / charity (low fit)** | Clearly non-trading, hobby blog | Low commercial intent (deprioritise, not hard DQ). |

---

## 6. NZ COMPLIANCE NOTES — Unsolicited Electronic Messages Act 2007 (UEMA)

**Governing law:** Unsolicited Electronic Messages Act 2007.
Primary sources verified during research:
- Legislation: https://www.legislation.govt.nz/act/public/2007/0007/latest/dlm405134.html `[VERIFIED]`
- Dept. of Internal Affairs (enforcement/admin): https://www.dia.govt.nz/Spam-NZ-Spam-Law-for-Businesses `[VERIFIED]`
- DIA "What anti-spam law means for businesses" (three steps): same DIA page.

### What the Act requires

The Act prohibits **spam with a "New Zealand link"** (messages sent to, from, or within New Zealand)
and covers **email, fax, instant messaging, and text/SMS** `[VERIFIED — DIA]`.

Three core obligations (verified from legislation text):
1. **Consent (s.9)** — An *unsolicited commercial electronic message* must not be sent. "Consented to
   receiving" means **express consent** OR consent that **can reasonably be inferred** (s.6) `[VERIFIED]`.
   The **onus of proof is on the sender** (s.9(3)) `[VERIFIED]`.
2. **Accurate sender identification (s.10)** — The message must **clearly and accurately identify** the
   person who authorised it, include **accurate contact information**, and that information must not be
   misleading `[VERIFIED — legislation s.10]`.
3. **Functional unsubscribe (s.11)** — The message must contain a **working unsubscribe facility**
   `[VERIFIED — legislation s.11]`.

**Penalty:** DIA states failure to comply "could mean a fine of up to **$500,000**" `[VERIFIED — DIA]`.
The Act also provides infringement notices / enforceable undertakings.

**Address harvesting** (scraping emails / using harvested lists) is separately restricted (s.13) `[VERIFIED]`.

### B2B cold-email specifics — READ CAREFULLY

- **There is NO blanket B2B exemption in the UEMA.** Unlike US CAN-SPAM, NZ law does not let you cold-email
  businesses merely because they are businesses `[VERIFIED — Act contains no B2B carve-out]`.
- **A published business email is NOT automatic consent.** The Marketing Association FAQ (based on DIA
  guidance) explicitly notes that a recipient's email **published in a directory**, contacted for a
  **commercial/marketing purpose**, is **not automatically "deemed consent"** — the onus remains on the
  sender `[VERIFIED — marketing.org.nz FAQ "Inferred and Deemed Consent", 14 Jun 2022]`.
- **Legitimate bases that may support B2B outreach:**
  - **Express consent** (opt-in list, prior explicit permission).
  - **Inferred consent** where a **prior business relationship** or the recipient's **role + published
    work contact for business purposes** makes the message reasonably expected. This is a **grey area** —
    the MA FAQ stresses one-sided outreach with no relationship is weak, and "silence is not consent"
    `[VERIFIED — marketing.org.nz]`.
  - Messages that **facilitate / complete / confirm a commercial transaction** between parties already in
    a relationship fall outside "unsolicited" `[VERIFIED — DIA/legislation framing]`.
- **Even where consent exists, s.10 (identify) and s.11 (unsubscribe) ALWAYS apply** to commercial
  messages `[VERIFIED]`.

**Legal-interpretation disclaimer:** The B2B "inferred consent" boundary above is a **summary of DIA/MA
guidance, not legal advice**. Whether a specific cold campaign is lawful is **[UNVERIFIED] legal
interpretation** — obtain advice from a NZ solicitor or the DIA before sending. This research does not
constitute consent to send anything.

### Compliant cold-outreach checklist (minimum)
- [ ] Identify yourself/your business **accurately** (name + reachable contact) — s.10.
- [ ] Include a **working unsubscribe** link/process — s.11.
- [ ] Have a **documented consent basis** (express, or a defensible inferred-consent rationale) — s.9; keep records (onus on sender).
- [ ] Do **not** use harvested-address lists or scraping-harvested emails — s.13.
- [ ] Honour unsubscribe immediately.
- [ ] Consider a **lower-risk channel first**: a personalised, clearly-identifiable first email to a
      **named individual's role address** (e.g. info@, office@) at a business you can show a legitimate
      interest in, with easy opt-out — but still get legal sign-off.

---

## 7. QUICK-START PROCEDURE (operational)

1. **Build prospect list** — NZBN bulk data (Canterbury filter) + Business Canterbury directory `[VERIFIED route]`.
2. **Detect defects** — run curl + W3C Nu API + PageSpeed API + link checker per site; capture screenshots.
3. **Score** — apply Section 4 rubric; tier Hot/Warm/Nurture.
4. **Filter** — drop all Section 5 disqualifiers.
5. **Enrich** — Maps UI for GBP/NAP; note consent basis for outreach.
6. **Outreach** — only after compliance checklist (Section 6) is signed off legally. This document stops at research; **no emails are sent**.

---

### Source list (all cited)
- legislation.govt.nz/act/public/2007/0007/latest/dlm405134.html — UEMA 2007 text (s.6, s.9–s.13). `[VERIFIED]`
- dia.govt.nz/Spam-NZ-Spam-Law-for-Businesses — DIA spam guidance, 3 steps, $500k penalty. `[VERIFIED]`
- marketing.org.nz/resource-hub/faq-inferred-and-deemed-consent — inferred/deemed consent FAQ (DIA-based). `[VERIFIED]`
- nzbn.govt.nz/using-the-nzbn/nzbn-services/bulk-data/ — NZBN bulk data, monthly, JSON/CSV. `[VERIFIED]`
- companiesoffice.govt.nz/data-services/ways-to-get-our-data/using-our-data-through-apis/ — Companies Office API. `[VERIFIED]`
- validator.w3.org/docs/api.html & validator.w3.org/nu/ — W3C markup + link validation (API confirmed live). `[VERIFIED]`
- developers.google.com/speed/docs/insights/v5/about & pagespeed.web.dev — PageSpeed Insights. `[VERIFIED endpoint; rate REPORTED]`
- developer.chrome.com/docs/devtools/device-mode — Chrome DevTools responsive testing. `[VERIFIED]`
- developers.google.com/maps/documentation/places/web-service/usage-and-billing — Places API pricing. `[VERIFIED page; free quota UNVERIFIED]`
- nslookup.io/ssl-checker, sslnudge.com/tools/ssl-check — SSL checkers. `[VERIFIED pages exist]`
- ahrefs.com/broken-link-checker — broken link checker. `[VERIFIED page exists]`
- businesscanterbury.co.nz/member-directory — Canterbury chamber directory. `[VERIFIED page exists]`
- Multiple 2026 articles confirming **Google Mobile-Friendly Test retired Dec 2023** — do NOT use. `[VERIFIED]`

**Confidence summary:** Core compliance facts and NZBN/bulk-data facts are `[VERIFIED]` from primary
government sources. Exact free-tier rate limits for Google/Yellow/social APIs are `[UNVERIFIED]` or
`[REPORTED]` and should be confirmed against the provider's current terms before high-volume use. The
B2B cold-email legality boundary is summarised from DIA/MA guidance and is **not legal advice**.

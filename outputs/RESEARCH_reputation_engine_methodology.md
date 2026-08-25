# Detection Methodology — NZ SMB Reputation-Management Gaps

**Purpose.** A concrete, source-cited method for finding New Zealand small businesses that
publicly show reputation-management gaps (unanswered / negative Google reviews, low review
counts vs competitors, stale or incomplete Google Business Profiles), using **public
information only**.

**Hard constraints observed in this document.**
- No client access, no logged-in Google account, no ownership of any business profile.
- No business name, review count, or statistic is invented. Every factual claim carries a
  real source URL. Anything I could not verify is marked **UNVERIFIED** with a reason.
- No business was contacted, no email sent, no account created.

**Authoritative sources used (all fetched/verified 2026-08-18):**
- Google Places API (legacy web service) Place Details: https://developers.google.com/maps/documentation/places/web-service/details
- Google Business Profile API basic setup: https://developers.google.com/my-business/content/basic-setup
- Google Business Profile review data: https://developers.google.com/my-business/content/review-data
- Google Maps Platform Terms of Service (No Scraping, 3.2.3(a)): https://cloud.google.com/maps-platform/terms
- Trustpilot Business Units API (public): https://developers.trustpilot.com/business-units-api-(public)
- Meta Graph API Page ratings: https://developers.facebook.com/docs/graph-api/reference/page/ratings/
- NZ DIA — Spam law for businesses: https://www.dia.govt.nz/Spam-NZ-Spam-Law-for-Businesses
- NZ Unsolicited Electronic Messages Act 2007: https://www.legislation.govt.nz/act/public/2007/0007/latest/DLM405134.html
- Marketing Association NZ — UEMA consent guidance: https://marketing.org.nz/resource-hub/guidance-on-uem-act
- Sprintlaw NZ — UEMA explainer: https://sprintlaw.co.nz/articles/unsolicited-electronic-messages-act-nz-marketing-email-and-text-rules/
- Google Brand Resource Center guidance: https://about.google/brand-resource-center/guidance/
- NoCowboys: https://www.nocowboys.co.nz/ — Neighbourly: https://www.neighbourly.co.nz/

---

## 1. Observable Reputation Gap Catalogue

Each gap below is graded on whether it is detectable **(A)** via the legitimate Google Places
API, or **(M)** only by manual inspection of the live, public Google Maps/business page
(automated retrieval of which would breach ToS — see §2).

| # | Reputation gap | Detection method | Evidence artifact | Commercial pain for owner |
|---|----------------|------------------|-------------------|---------------------------|
| 1 | **Unanswered Google reviews (esp. negative)** | **(M)** API does *not* expose owner replies (see §2). Visible only on live page. | Screenshot of a 1–2★ review with no "Response from owner" block; public review URL. | Unanswered complaints are the single strongest buyer trigger; prospects feel ignored publicly. |
| 2 | **Low owner-response rate** | **(M)** Cannot be computed from API. Requires sampling reviews on the live page. | Count of reviews vs reviews with an owner reply, over a sampled window. | Shows they lack time/systems; core service you sell. |
| 3 | **Review recency gap** (stale — no new reviews in 12+ months) | **(A partial)** Place Details `reviews` includes `time` (unix) per review; `reviews_sort=newest` returns most recent up to 5. | Most-recent review timestamp; if oldest-of-5 is >12 months ago → stale signal. | Stale profile = low ranking + looks abandoned to customers. |
| 4 | **Rating below category average** | **(A)** `rating` (1.0–5.0) returned per place. | Numeric rating; compare against cohort median for same category/suburb. | Directly lowers click-through and trust. |
| 5 | **Low review count vs competitors** | **(A)** `user_ratings_total` (whole number) returned. | Count vs competitor counts in same area/category. | Few reviews = weak social proof even if rating is decent. |
| 6 | **No photos on profile** | **(A)** `photos` field present/absent; count via Place Details `fields=photos`. | Photo count = 0 (or field absent). | Listings with photos get materially more engagement; empty = neglected. |
| 7 | **Incomplete profile fields** (no website / phone / hours) | **(A)** Place Details returns `website`, `formatted_phone_number`, `opening_hours`, `current_opening_hours`. Absence = blank. | Which of website/phone/hours are missing. | Incomplete profiles rank lower and convert worse. |
| 8 | **No hours listed** | **(A)** `opening_hours` / `current_opening_hours` absent. | Missing hours field. | Customers can't tell if open; reduces calls. |
| 9 | **Unclaimed profile** | **(M / UNVERIFIED)** No API field distinguishes claimed vs unclaimed; both return identical data. Detectable only by live-page cues (e.g. "Claim this business" prompt) which require page render. | Live-page "Own this business?" prompt. | Unclaimed = owner unaware/uncaring → easy sale, but also may be unreachable. |
| 10 | **Permanently closed / wrong info** | **(A)** `business_status` = `CLOSED_PERMANENTLY` (or operational flag). | Status value. | Disqualifier, not a gap (see §5). |

**Honest summary of §1:** Of the ten catalogue items, **five (3,4,5,6,7,8)** are detectable
through the legitimate Places API; **owner-response rate and "unanswered" status (1,2) are
NOT** — they require live-page inspection that ToS prohibits automating. "Unclaimed" (9) is
**not determinable from API data at all**. This shapes the whole engine (§2 verdict).

---

## 2. Data Access Reality Check

### 2.1 Google Business Profile (GBP) API — what it does and does NOT allow
- The GBP APIs require **project approval** and an **OAuth 2.0 client ID** to "authorize
  access to location data." Access is scoped to the locations the authenticated account
  owns/manages. Source: https://developers.google.com/my-business/content/basic-setup
- The "Work with review data" tutorial covers listing, retrieving, replying to, and deleting
  reviews **for locations you manage** — there is **no endpoint to read another business's
  reviews**. Source: https://developers.google.com/my-business/content/review-data
- **Conclusion:** GBP API is unusable for prospecting third-party businesses. It only helps
  *after* a client signs and grants access.

### 2.2 Google Places API (legacy web service) — the only legitimate read path
- **Place Details** request with `fields=reviews,rating,user_ratings_total,website,
  formatted_phone_number,opening_hours,current_opening_hours,photos,business_status,
  editorial_summary` returns the public profile + reviews.
- **Review limit (verified):** the `reviews` field is documented as *"A JSON array of up to
  five reviews."* Source (verbatim from fetched doc):
  https://developers.google.com/maps/documentation/places/web-service/details
- **Sort:** `reviews_sort=most_relevant` (default) or `newest`. `newest` gives chronological
  order — useful for recency gap (gap 3).
- **What the review object contains:** `author_name`, `author_url`, `rating`, `text`,
  `time` (unix), `relative_time_description`, `language`, `profile_photo_url`. **It does
  NOT contain any owner-response/reply field.** (Verified by inspecting the `PlaceReview`
  object definition in the same doc.)
- **Counts/ratings:** `user_ratings_total` (total review count) and `rating` (aggregate
  1.0–5.0) are returned — these power gaps 4 and 5.
- **Discovery:** Places **Text Search / Nearby Search** return candidate places with
  `place_id`, `rating`, `user_ratings_total`, `business_status`, `types`. (The legacy
  web-service API documents a capped candidate set per query; verify the current per-query
  ceiling and quota against Google's live docs before scaling — **UNVERIFIED exact number
  here**; treat "dozens per query, paginated" as the working assumption.)

### 2.3 Scraping Google Maps — Terms of Service
- Google Maps Platform Terms of Service, **3.2.3(a) "No Scraping":** *"Customer will not
  export, extract, or otherwise scrape Google Maps Content for use outside the Services."*
  Examples given include pre-fetching, indexing, storing, resharing, or rehosting Maps
  Content outside the services. Source: https://cloud.google.com/maps-platform/terms
- **Legal nuance (from secondary analyses, not legal advice):** courts in some jurisdictions
  have treated scraping *public* data as not criminal, but a ToS breach is a contract matter
  — Google can issue IP bans, terminate API keys, and pursue civil remedies. Scraping is
  therefore a business-continuity risk, not a clean method. See §2.2 secondary commentary:
  https://thunderbit.com/blog/is-scraping-google-maps-legal and
  https://mapscraping.com/is-google-maps-scraping-legal

### 2.4 Viability verdict
- **VIABLE:** A "profile-completeness + low-volume + visible-negative-sentiment" scanner.
  Using legitimate Places API calls you can, at scale and lawfully, flag businesses that have
  (a) few reviews vs local peers, (b) a low aggregate rating, (c) at least one recent 1–2★
  review among the up-to-5 returned, and (d) missing website/phone/hours/photos.
- **NOT VIABLE as built:** an automated "unanswered review / owner-response-rate" engine.
  That signal is invisible to the API and prohibited to scrape. It must be confirmed
  *manually* on a shortlist before any outreach, and even then only as a human viewing a
  public page (not via bots).

---

## 3. Alternative Review Sources (NZ)

| Platform | NZ relevance | Public reviews? | API for prospecting? | Notes / URL |
|----------|--------------|-----------------|----------------------|-------------|
| **Trustpilot** | Moderate — more common for online retailers, SaaS, national brands than local trades. | Yes (public business-unit pages). | **Yes (public API, API key).** `GET /v1/business-units/{id}` returns `numberOfReviews` (total + 1★–5★ breakdown), `score.trustScore`, `stars`. Source: https://developers.trustpilot.com/business-units-api-(public) | Best for categories where Trustpilot matters. Needs businessUnitId (resolve via "Find a business unit" by domain). Free API key tier exists. |
| **Facebook Pages** | High reach in NZ; many SMBs have a Page with Recommendations. | Yes (Recommendations/reviews on Pages). | **No for third parties.** `/page/ratings` requires a **Page access token** (you must own/manage the Page). Source: https://developers.facebook.com/docs/graph-api/reference/page/ratings/ | Unusable for cold prospecting; only post-signup. |
| **NoCowboys** | High for NZ **trades** (builders, plumbers, painters, mechanics). | Yes — NZ-focused verified trades reviews. | **No verified public API.** Public review pages exist; automated collection would rely on scraping (ToS risk). Source: https://www.nocowboys.co.nz/ | Use for manual spot-checks in trades verticals; pair with Google signal. |
| **Yellow NZ** | High for business **discovery** (directory listings). | **UNVERIFIED** — Yellow is primarily a directory; consumer-star-reviews are not its core feature and I could not confirm a review API. | Directory lookup useful for finding businesses + contact emails, not for review gaps. | Treat as a *discovery/contact* source, not a review source. |
| **Neighbourly** | Niche/hyperlocal community network. | **UNVERIFIED** — businesses may appear but it is a private neighbourhood network, not a public review platform; no public review API. Source: https://www.neighbourly.co.nz/ | Not a viable public review source for this engine. | Deprioritise. (Note: Neighbourly suffered a reported data breach / site issue in Jan 2026 — another reason not to rely on it.) |
| **Industry-specific NZ directories** (e.g. professional bodies, trade associations) | Vertical-specific. | Varies. | Manual. | Add per-vertical as needed; manual only. |

**Practical takeaway:** Trustpilot is the only *programmatic* non-Google supplement (and only
for relevant categories). Facebook/NoCowboys/Neighbourly are manual cross-checks, not API
feeds.

---

## 4. Qualification Rubric (0–100)

Score uses **only observable signals** from §1–§3. Gate first, then add points, then read
tier. Do **not** score a business you cannot reach.

**Gate (must pass or score = 0 / disqualify):**
- `business_status` = OPERATING (not CLOSED_PERMANENTLY).
- A public contact channel exists (website with email, or directory-listed email/phone).

**Scoring (start at 0, add):**
| Signal | Points | Source of signal |
|--------|--------|------------------|
| `user_ratings_total` low (e.g. < 10) while ≥2 local competitors in same category have materially more | +20 | Places API `user_ratings_total` |
| ≥1 review among returned 5 is 1–2★ (visible negative sentiment) | +20 | Places API `reviews[].rating` |
| Aggregate `rating` below category/suburb cohort median | +15 | Places API `rating` |
| Profile missing ≥2 of {website, phone, hours, photos} | +15 | Places API fields |
| Most-recent returned review is ≤12 months old (business still gets traffic) | +10 | `reviews_sort=newest`, `time` |
| Review count between 0 and low AND no competitors to benchmark | 0 (insufficient hook) | — |
| On Trustpilot (relevant category) with `numberOfReviews` low + low `trustScore` | +10 (additive, optional) | Trustpilot API |

**Tiers:**
- **≥60 = HOT** — multiple objective gaps + reachable. Prioritise.
- **35–59 = WARM** — one or two gaps; personalise outreach.
- **<35 = SKIP** — insufficient observable pain or unreachable.

**Worked example (illustrative, no real business):** A Wellington café with 4 Google reviews
(competitors nearby have 40+), one 2★ review in the last 3 months, rating 3.4 vs suburb
median 4.3, no website, no photos = 20+20+15+15+10 = **80 → HOT**.

---

## 5. Disqualifiers (do NOT contact)

- **Permanently closed / `CLOSED_PERMANENTLY`** status.
- **No public contact channel** (no email on site/directory, no phone) — can't reach, and
  cold email needs a published address for deemed consent (§7).
- **Corporate chain / franchise with centralised marketing** (e.g. national QSR, major
  franchise brands) — the local "owner" is not the decision-maker; reviews handled
  corporately. Flag by brand recognition / many identical listings.
- **Government / council / not-for-profit** — different buying context; UEMA still applies
  but fit is poor.
- **Already evidently using a reputation/aggregator tool or agency** (e.g. review widgets,
  "Powered by [tool]" footers) — low willingness to pay for yours.
- **PO box / virtual-office-only address with no local presence** — likely not a local SMB.
- **No competitors nearby to benchmark against** — weakens the "you're behind" hook.

---

## 6. Proof Asset Design — the "Reputation Snapshot"

A single-page, honest, evidence-backed one-pager sent (compliantly) to the prospect. It must
persuade **without fabrication and without implying Google partnership.**

**Required components:**
1. **Business name** exactly as on the public profile (no edits).
2. **The specific observed public reviews** — quote 1–2 verbatim 1–2★ reviews *with their
   public review URL* and date (from `time`). Never paraphrase to exaggerate.
3. **Review count vs typical competitor count** in the same suburb/category (cite the
   comparison set you actually checked).
4. **Current aggregate rating** and how it compares to the local median.
5. **Missing profile fields** you observed (website/phone/hours/photos) — list exactly which
   are absent.
6. **Date stamp + source note:** "Based on publicly visible information as of [date]. Source:
   Google Business Profile (public) + [other public source URL]."
7. **Neutral framing:** describe the gap factually ("Your profile currently shows 3 reviews
   while similar [suburb] businesses show 30+"), not as an attack.
8. **Explicit disclaimer (Google branding compliance):** "We are not affiliated with, endorsed
   by, or partnered with Google." No Google logo, no coloured "G". "Google" may appear in
   plain text only (see §7).
9. **Soft CTA:** offer a free 15-minute walkthrough of their public profile; no pressure.

**Honesty rules (non-negotiable):**
- Only state what you actually observed via API/manual check. If you could not verify
  owner-response status, say "owner responses were not visible at the time of review" — do
  **not** assert "you never reply."
- Link to the live public source so the owner can verify your claims instantly.
- Never use "Google-certified," "Google partner," "official," or Google brand colours/logo.

---

## 7. NZ Compliance Notes

### 7.1 Unsolicited Electronic Messages Act 2007 (UEMA)
- The Act **prohibits sending an unsolicited commercial electronic message with a New Zealand
  link** (sent to, from, or within NZ). Covers **email, fax, instant messaging, and TXT**.
  It does **NOT** cover phone calls / telemarketing. Source:
  https://www.dia.govt.nz/Spam-NZ-Spam-Law-for-Businesses
- A message is "commercial" if it markets/promotes goods, services, land, investments, or
  links to those. A single message can be spam; bulk not required.
- **Three sender obligations:** (1) **consent**, (2) **clear identity**, (3) a **functional
  unsubscribe**. Breach fine up to **$500,000**. Source: same DIA page; full text:
  https://www.legislation.govt.nz/act/public/2007/0007/latest/DLM405134.html
- **Consent pathways (relevant to B2B cold email):**
  - *Express* — opt-in (best evidence).
  - *Inferred* — based on an existing relationship + context it's reasonable they'd want the
    message.
  - *Deemed* — address **conspicuously published** by a person in a **business/official
    capacity**, the message is **relevant** to their business/role/functions/duties, and there
    is **no statement prohibiting unsolicited messages**. Trade-directory and website-published
    business addresses qualify. Source:
    https://marketing.org.nz/resource-hub/guidance-on-uem-act and
    https://sprintlaw.co.nz/articles/unsolicited-electronic-messages-act-nz-marketing-email-and-text-rules/
- **Onus of proof is on the sender** (s9(3)): you must be able to show why consent existed.
  Keep records of where/when the address was published and why the message was relevant.
- **Address-harvesting software is specifically prohibited** (s9). Do not scrape emails.

**Practical compliance recipe for this engine:**
1. Only email addresses **published** on the business's own website or a trade/business
   directory (deemed consent), and only with an offer **relevant** to that business.
2. Always include your **real business name + contact** and a **working unsubscribe** link.
3. Never buy/scrape lists.
4. Keep a log of publication source + date per contact.

### 7.2 Google branding / trademark constraints (verified)
- Google's Brand Resource Center states you **may** "Use Google in plain text" to refer to
  Google or its products in an informational context (websites, etc.) under its Trademark
  Rules. Source: https://about.google/brand-resource-center/guidance/
- It **prohibits**: *"Don't imply endorsement. Don't use the Google logo or any of our brand
  elements in any way that implies affiliation, endorsement, or sponsorship where such a
  relationship does not exist,"* and *"Don't put our name in your name."* (Same source.)
- **Therefore:** In all copy and the Snapshot (§6), use the word "Google" in plain text only;
  never display the Google logo or multicolour "G"; never claim partnership, certification, or
  endorsement. The disclaimer "not affiliated with or endorsed by Google" is both honest and
  ToS-aligned.

---

## 8. Engine Viability Verdict (one paragraph)
The engine is **viable as a lawful, scalable "completeness + low-volume + visible-negative"
scanner** built on the legitimate Google Places API, cross-checked where relevant with the
Trustpilot public API, and refined manually for trades via NoCowboys. It is **not viable as a
fully automated "unanswered-review detector"** — owner-response data is invisible to the API
and prohibited to scrape, so that step must be a manual, human confirmation on a shortlist.
Cold outreach is lawful under UEMA **only** when sent to conspicuously-published business
addresses with a relevant offer, clear identity, and unsubscribe — and all Google references
stay plain-text with no partnership implication. Build the pipeline around the signals you
*can* verify, and pre-qualify the "unanswered" claim by hand before any send.

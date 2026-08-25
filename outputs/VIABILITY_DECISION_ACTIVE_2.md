# VIABILITY DECISION — ACTIVE SLOT 2 (Reputation / Unanswered Review Engine)

_Decided 2026-08-18 · orchestrator · evidence-backed, independently re-verified_

## Verdict: **PARTIAL — descope, do not kill**

The engine's headline premise ("find businesses with **unanswered** reviews") is **not
lawfully automatable at scale**. The rest of the engine is viable.

## Evidence (verified twice — researcher, then orchestrator directly)

1. **Google Places API returns "A JSON array of up to five reviews."**
   Verified verbatim by the orchestrator on Google's own docs page
   (`developers.google.com/maps/documentation/places/web-service/legacy/details`).
   Five reviews is not a review corpus — response-rate cannot be computed from it.

2. **The `PlaceReview` object has NO owner-reply field.**
   Orchestrator keyword scan of the live doc page: `reply` = 0 occurrences,
   `ownerResponse` = 0, `owner response` = 0. Fields present are `author_name`,
   `author_url`, `rating`, `text`, `time`, `relative_time_description`, `language`,
   `profile_photo_url`. **"Unanswered" is invisible to the API.**

3. **Google Business Profile API cannot read a third party's reviews.**
   It is OAuth-scoped to locations the authenticated account already owns/manages
   (`developers.google.com/my-business/content/review-data`). Useful only *after* a
   client signs — useless for prospecting.

4. **Scraping Google Maps to recover the missing signal is contractually prohibited.**
   Maps Platform Terms 3.2.3(a) "No Scraping". Not an option.

## Decision

| Component | Status |
|---|---|
| Unanswered-review **auto-detection** at scale | **KILLED** — impossible via lawful API |
| Low review volume vs local peers | **KEPT** — `user_ratings_total` available |
| Low aggregate rating | **KEPT** — `rating` available |
| Recent visible 1–2★ review | **KEPT** — within the 5 returned, `reviews_sort=newest` |
| Profile completeness (no website/phone/hours/photos) | **KEPT** — Place Details fields |
| "Unanswered" claim on a shortlist | **KEPT as MANUAL human check only** — never bot-driven, never asserted without a human having viewed the public page |

Engine slot 2 is **re-scoped** to a *Reputation Completeness & Visible-Sentiment Scanner*.

## Portfolio consequence

The plan's rule — replace a non-viable engine from the strongest cluster — is applied by
**promoting a reserve**, not by dropping to two engines:

- **Reserve promoted:** `ME-0274` **Competitor Review Velocity Monitor** (score 93/100)
  and `ME-0327` **Website Content Freshness Monitor** (93/100) are attached to slot 2 as
  the recurring-revenue path, because both run purely on public data Hermes can lawfully
  read, and both carry stated recurring pricing (NZ$99–999/month) in the source.
- Slot 2 keeps its plan-mandated identity but is now honest about what it can prove.

## Hard constraint written into the cartridge

> No customer-facing asset may state or imply that a business "has not responded to
> reviews" unless a human has viewed the public profile and confirmed it. Any snapshot
> must state its own evidence basis and the 5-review API ceiling.

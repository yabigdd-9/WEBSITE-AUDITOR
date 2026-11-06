# Accuracy holdout — status 2026-10-29 00:45 NZDT

**State: predictions frozen, 0 of 30 reviews completed. This is not an accuracy result.**

## What is ready

| Item | Value |
| --- | --- |
| Source under test | `40b2a6233ac079160d8ffcdcba755d9335524a02` |
| Cases | 30, exactly 10 per required stratum |
| Predicted observation units | 339 |
| Fixture bytes | SHA-256 frozen, all 30 distinct, none collides with the 120 development hashes |
| Raw auditor reports | 30, preserved in `raw-reports/` |
| Deterministic replay | 30/30 cases reproduce the live auditor's defect-key set exactly when the same modules run on the frozen bytes |
| Scorer | 22/22 synthetic contract tests pass against the bundled copy |
| Blank-template control | still correctly fails (no cases) |

## Selection provenance

- Universe: 44 unique NZ business URLs recovered from `state/contact-review/runs/*/` case
  records (first-party acquisition, no external scraping).
- 4 failed to fetch on retry (HTTP errors / timeout) and were replaced before freezing.
- Strata assigned by observed page character: brochure-service (10), commerce-catalogue (10),
  javascript-application (10) — the JS stratum is assigned on script-count and interaction
  cues, which is a **heuristic**, not a verified page-type label.
- No page was cherry-picked; all 40 successfully captured non-directory pages were considered.

## Known weaknesses (do not over-read this sample)

1. **44-URL universe is not representative.** It is a convenience frame drawn from the
   operator's own contact-review queue — NZ trades, mostly single-page brochure sites.
2. **Stratum labels are heuristic.** A page with many scripts is labelled
   `javascript-application` because it has many scripts, not because it was independently
   classified.
3. **Single-page snapshots.** Multi-page findings (broken internal links, sitemaps, robots)
   are out of scope and were excluded from the replay check; the reviewer guide says so.
4. **No negative-only cases.** Every case has at least one predicted finding; there is no
   case where the auditor predicted nothing and the reviewer must confirm a clean page.
   This biases the observable false-positive rate upward relative to a random sample.
5. **One case failed to fetch** (`holdout-004`, `www.excelsior.net.nz`, read timeout). Its
   predictions are empty and its review must record that the page is unverifiable.
6. **Two cases have viewport / meta-description discrepancies** between the frozen capture
   and the live run (`holdout-007`, `holdout-029`, `holdout-010`). The frozen capture is
   authoritative for this review; the live run captured a different response. Recorded as
   a known divergence, not a bug.

## What is still needed

1. **An independent human reviewer** — someone who did not produce the predictions — must
   label all 339 units with `present` / `absent` / `uncertain` plus a rationale. Reviews go
   in `reviews/holdout-XXX.json`. Guide: `REVIEWER-GUIDE.md`.
2. The reviewer must also hunt for **missed findings** (recall) on each page.
3. Once all 30 reviews exist, run `python3 accuracy_score.py holdout.json`. It prints
   TP/FP/FN, precision, recall and Wilson 95% intervals.
4. A pass does **not** authorize release. The scorer's `release_authorized` is always
   `false`.

## How to run it

```sh
cd /Users/dd/WEBSITE-AUDITOR/outputs/holdout-accuracy-20261029
python3 accuracy_score.py holdout.json
```
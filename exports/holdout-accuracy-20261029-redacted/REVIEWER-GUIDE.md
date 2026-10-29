# Independent accuracy review — reviewer guide

**Prepared:** 2026-10-29 00:30 NZDT (11:30 UTC)
**Source under test:** `40b2a6233ac079160d8ffcdcba755d9335524a02`
**Reviewer required:** a person who did **not** produce the predictions.

## Your job

Label every observation unit in the frozen pages **without seeing the predictions first**.
Then the scorer compares your labels against the deterministic predictions.

## Scope (what counts)

The auditor runs a **static HTML profile** — 57 static defect keys across these check
modules. Only observations produced by that profile are in scope. Anything that needs
rendering (performance scores, axe, cookie banners actually interacted with, JavaScript
execution results) is **out of scope** and must not be labelled.

## Observation identity

Each unit is identified by exactly three fields:

- `rule` — the defect key, e.g. `image-alt`, `header-hsts`, `missing_title`
- `url` — the page URL where it was observed
- `location` — the CSS selector or element descriptor, e.g. `img:nth-of-type(68)`,
  `head > meta[name="viewport"]`, or an empty string for page-level findings

**Duplicate identities are not allowed.** If the same rule appears twice on one page,
they are separate units only when the location differs.

## Verdicts

For each unit you review, choose exactly one:

- `present` — the finding is real on this page, as captured
- `absent` — the finding is wrong; the page does not have this problem
- `uncertain` — you cannot tell from the captured bytes

**A clean page still needs explicit negative labels.** Every unit must get a verdict.
`No predictions is not, by itself, a negative label` — but every predicted unit must be
reviewed.

## How to review

1. Read `cases-manifest.json` to get the list of 30 cases and their fixture paths.
2. For each case, open `cases/<case_id>.html` in a browser (or read the raw HTML).
3. Independently verify each claimed finding against the page, and also check for any
   finding the auditor **missed** that is clearly in scope (misses are counted against
   recall — be thorough here).
4. Write your verdict with a short rationale for every unit.
5. Fill `reviews/<case_id>.json` for every case.

## Output format

```json
{
  "fixture_sha256": "<must match cases-manifest.json>",
  "scope": "<stratum, must match>",
  "reviewer": "<your name or identifier>",
  "reviewed_at": "2026-10-29T...Z",
  "independence_attested": true,
  "exhaustive_within_scope": true,
  "observations": [
    {"rule": "image-alt", "url": "https://...", "location": "img:nth-of-type(68)",
     "verdict": "present", "rationale": "The 68th img has no alt attribute."}
  ]
}
```

`reviewed_at` must be a timezone-aware ISO-8601 timestamp. `independence_attested` and
`exhaustive_within_scope` must be `true` only if both are genuinely true.

## Known limitations to record

- Captures are single-page HTML snapshots. Multi-page findings (broken links to other
  pages) are out of scope for this review.
- The auditor does not render JavaScript. A finding about content that only appears
  after rendering cannot be verified from the snapshot.
- 4 of the 44 originally contacted domains failed to fetch (HTTP errors / timeout) and
  were replaced before freezing; see `selection.tsv`.

## After you finish

Run:

```sh
cd /Users/dd/WEBSITE-AUDITOR/outputs/holdout-accuracy-20261029
cp /Users/dd/Documents/Codex/2026-10-21/g/outputs/accuracy-review/accuracy_score.py .
cp /Users/dd/Documents/Codex/2026-10-21/g/outputs/accuracy-review/holdout-template.json holdout.json
# edit holdout.json: set thresholds.approved_by / approved_at, attach cases, set
# development_fixture_sha256 to the 120 known dev hashes, then:
python3 accuracy_score.py holdout.json
```

The scorer prints TP/FP/FN, precision, recall and Wilson 95% intervals. A passing result
**does not authorize release** — it measures the static auditor only.
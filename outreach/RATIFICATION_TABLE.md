# task-001 Per-Prospect Ratification Table

_Generated 2026-08-26. Source gate: outreach/consent_gate.py · refs APR-001/005/007._
_Evidence file: outreach/CONSENT_EVIDENCE_TASK001.json._

## Status: 0 of 9 RATIFIED — all correctly BLOCKED by the gate

The consent gate (`consent_gate.py --check`) was run against collected published-context
evidence for all 9 prospects. Every one returned **BLOCKED — INFERENCE_NOT_HUMAN_RATIFIED**,
plus `prodecorators.co.nz` also flagged `INFERENCE_UNSUPPORTED: published_address_does_not_invite_contact`.

**Hermes cannot self-ratify.** `human_ratified_by` is empty for all 9. The task cannot proceed
to send without Dion confirming each prospect's inferred-consent rationale.

## Evidence collected (real, from each business's own site via search index)
| # | Business | Address observed | Ratifiable? | Gate reason |
|---|----------|------------------|-------------|-------------|
| 1 | whiteandtaylor.co.nz | office@ (inferred from domain; phone published) | ❌ BLOCKED | not human-ratified |
| 2 | bcplumbers.co.nz | office@bcplumbers.co.nz | ❌ BLOCKED | not human-ratified |
| 3 | clyne-bennie.co.nz | service@clyne-bennie.co.nz | ❌ BLOCKED | not human-ratified |
| 4 | jcconstruction.co.nz | office@ (inferred) | ❌ BLOCKED | not human-ratified |
| 5 | tbir.co.nz | tbirgrass@gmail.com (personal gmail) | ❌ BLOCKED | not human-ratified; weaker (personal address) |
| 6 | greenscapes.co.nz | office@ (inferred) | ❌ BLOCKED | not human-ratified |
| 7 | dyerdecorating.co.nz | office@ (inferred) | ❌ BLOCKED | not human-ratified |
| 8 | prodecorators.co.nz | contact@prodecorators.co.nz | ❌ BLOCKED | not human-ratified; address does not invite contact |
| 9 | davidrobertson.co.nz | admin@ / david@ (contact page) | ❌ BLOCKED | not human-ratified — strongest rationale of the set |

## Data-quality caveats (honest)
- **Addresses for #1, #4, #6, #7 are domain-pattern inferences**, not directly observed emails.
  The search index surfaced phone/contact invitations but not the literal email. To fully clear
  these, read the actual contact page (needs a working page extractor or Chrome "Allow" click).
- **#5 (tbir) is a personal gmail** — weaker inferred-consent basis; recommend phone-first or skip.
- **#8 (prodecorators)** — gate says the published address does not invite contact; lowest priority.
- **#9 (davidrobertson)** — dedicated contact page explicitly inviting contact; strongest basis.

## What Dion must do to complete task-001
For each prospect you accept, open CONSENT_EVIDENCE_TASK001.json and set:
```
"human_ratified_by": "Dion",
"ratified_at": "<ISO timestamp>"
```
(Optionally upgrade inferred addresses to directly-observed ones by reading the real contact page.)
Until then the gate keeps everything BLOCKED and nothing sends. No Gmail app password exists for
yabigdd@gmail.com anyway, so send is physically impossible regardless.

## Infrastructure note
`web_extract` is configured on the search-only `ddgs` backend and cannot fetch page text; the
browser tool needs a one-time Chrome "Allow remote debugging" click on this Mac. `web_search`
(snippets) was used instead — sufficient to confirm contact invitations and surface emails, but
not to fully capture verbatim `surrounding_wording` for the inferred-address prospects.

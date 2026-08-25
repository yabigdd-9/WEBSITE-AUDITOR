# task-001 Per-Prospect Ratification Table (PREREQUISITE STATE)

_Generated 2026-08-26 from outreach/prospects_batch_001.json + evidence_summary.txt._
_Source gate: outreach/consent_gate.py · references APR-001 / APR-005 / APR-007._

## Status: 0 of 9 ratifiable

Per `outreach/COMPLIANCE_BASIS.md`, every mandatory consent-gate field must be present
AND human-ratified before a prospect can be emailed. The research that exists captures
**verified website defects** (the reason-for-contact basis) but has **not** collected the
consent evidence the gate requires. Therefore **all 9 are BLOCKED** — there is nothing to
ratify yet, only fields to fill.

## Mandatory gate fields (from COMPLIANCE_BASIS.md)
`address` · `address_source_url` · `address_found_where` · `surrounding_wording` ·
`invites_contact` · `refusal_statement_present` · `role_or_personal` ·
`relevance_to_role` · `prior_relationship` · `consent_type_claimed` ·
`why_consent_believed` · `human_ratified_by` + `ratified_at`

Missing ANY field ⇒ BLOCK. Unratified inference ⇒ BLOCK.

## Per-prospect row

| # | Prospect | Verified defects (collected) | Address found? | Consent fields filled? | Ratifiable? | What's needed before Dion can ratify |
|---|----------|------------------------------|----------------|------------------------|-------------|--------------------------------------|
| 1 | www.whiteandtaylor.co.nz | STALE_COPYRIGHT, HEAVY_HTML | none (0/0 inviting) | 0/12 | ❌ BLOCK | find + record contact address, surrounding wording, consent type, rationale |
| 2 | www.bcplumbers.co.nz | STALE_COPYRIGHT, BROKEN_LINKS | none (0/0 inviting) | 0/12 | ❌ BLOCK | same as above |
| 3 | www.clyne-bennie.co.nz | (not in defect json) | 1 found, 1 inviting | 0/12 | ❌ BLOCK | capture source_url + surrounding wording, record consent basis |
| 4 | www.jcconstruction.co.nz | HEAVY_HTML | 1 found, 1 inviting | 0/12 | ❌ BLOCK | capture source_url + surrounding wording, record consent basis |
| 5 | www.tbir.co.nz | HEAVY_HTML | 1 found, 1 inviting | 0/12 | ❌ BLOCK | capture source_url + surrounding wording, record consent basis |
| 6 | www.greenscapes.co.nz | STALE_COPYRIGHT, HEAVY_HTML | none (0/0 inviting) | 0/12 | ❌ BLOCK | find + record contact address, surrounding wording, consent type, rationale |
| 7 | dyerdecorating.co.nz | NO_WRITTEN_CONTACT, HEAVY_HTML, NO_SOCIAL_LINKS | none (0/0 inviting) | 0/12 | ❌ BLOCK | find + record contact address, surrounding wording, consent type, rationale |
| 8 | prodecorators.co.nz | NO_WRITTEN_CONTACT, HEAVY_HTML | 1 found, 0 inviting | 0/12 | ❌ BLOCK | capture source_url + surrounding wording, record consent basis |
| 9 | www.davidrobertson.co.nz | NO_CONTACT_ON_HOMEPAGE, BROKEN_LINKS, NO_SOCIAL_LINKS | none (0/0 inviting) | 0/12 | ❌ BLOCK | find + record contact address, surrounding wording, consent type, rationale |

## Notes
- Only 4 prospects (3,4,5,8) have any address harvested at all; 0 have the consent rationale
  (`why_consent_believed`) or a `human_ratified_by` recorded.
- The Website Rescue reason-for-contact (stale copyright, broken links, heavy HTML, no
  written contact) is solid evidence of a *defect worth fixing* — but a defect alone is not
  consent. The gate correctly separates "has a reason to contact" from "has a lawful basis
  to email."
- Because no Gmail app password exists (`yabigdd@gmail.com`), nothing can physically send
  even if ratified — ratification unblocks the *logic*, not the *capability*.

## Next step for Dion
Either: (a) authorise a research pass to fill the 12 mandatory fields per prospect from each
business's own published page (no purchased/scraped lists — s.13), then ratify each row; or
(b) switch first touch to phone (02904556680), which is outside UEMA email rules per the
existing APR-005 decision. Until then, this table is the blocker, not the gate.

## Infrastructure blocker on the auto-research pass (2026-08-26)
The research pass to fill the gate fields was attempted but is currently BLOCKED by tooling:
- `web_extract` is configured on the search-only backend (`ddgs`); it cannot fetch page
  content (returns len:0 for all 9 sites). No firecrawl/tavily/exa key is set in env.
- The browser tool (faithful DOM read) is blocked on Chrome's "Allow remote debugging?"
  popup — needs a one-time manual Approve on this Mac (or `browser-harness mac-approve`).

To unblock option (a), pick one:
1. Set a real extract backend key (FIRECRAWL/TAVILY/EXA) and re-run the research pass, OR
2. Click "Allow" on the Chrome remote-debugging prompt, then Hermes can drive the browser
   to read each business's own page text and fill the 12 fields (still unratified — you sign off).

Per the gate, Hermes will NOT self-ratify — `human_ratified_by` stays empty until you confirm
each prospect's inferred-consent rationale.

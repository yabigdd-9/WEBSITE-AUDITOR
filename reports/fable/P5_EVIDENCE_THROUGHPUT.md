# P5 — Evidence Throughput: Report & Gate Evidence
FABLE · 2026-09-22 · branch `upgrade/v32-canonical-execution` · $0 · stdlib only

## Shipped
1. **`mm audit-backfill [--id N ...] [--no-delay]`** (`mm_evidence_ops.audit_backfill`): batch evidence backfill for every real business with zero `mm_evidence` rows. Even `unreachable` outcomes are recorded honestly (status `unverified`, method `direct_fetch`, confidence `0.0`, the failure JSON itself as the nonempty capture). Advances `mm_deals` DISCOVERED→AUDITED via the canonical `change_stage` transition (event + timestamp). Businesses with no `public_website` are skipped with typed reason `BLOCKED_SITE_NO_URL` — never guessed. Idempotent: re-runs backfill 0 already-covered businesses.
2. **`mm discover-contacts --id N`** (`mm_evidence_ops.discover_own_site_contacts`): own-site-only crawl (homepage, /contact, /about, /contact-us) via stdlib `urllib` + `html.parser` (mailto:/tel:/email-regex/forms) → `mm_contact_evidence` rows with URL + timestamp + nonempty capture file provenance, confidence **0.0**, permission `Unconfirmed`. Per-domain politeness delay via `time.sleep`. Unsubscribed recipients can never be reset. **Never marks anything verified** (P8 policy).
3. **Typed `BLOCKED_SEARCH_*` errors** (`mm_discovery.SearchBlocked`, wrap-only; `searxng_candidates()` signature unchanged): `BLOCKED_SEARCH_SERVICE_ABSENT` / `_TIMEOUT` / `_BAD_STATUS` / `_BAD_RESPONSE` instead of raw URLError tracebacks. `mm discover-search --dry-run` now returns structured JSON with `blocked.code` and exits 0 when SearXNG is absent. Own-site lane has the parallel `BLOCKED_SITE_*` family (`OwnSiteBlocked`).
4. **`reports/fable/p5_trace.md`** (below): finding→delta score trace.

## GATE (raw outputs)
- Suite: `test_discovery.py test_evidence_ops.py test_quarantine.py test_dedupe.py` → **32 passed** (incl. `test_guess_alone_never_verified`, typed-error tests, idempotency tests).
- `./mm health` → `external_sends: 0`, `paid_calls: 0` — **SAFETY-OK**.
- Coverage: **20/21 real prospects (95.2%) have ≥1 evidence row** (target ≥85%); 21/21 attempted — the 1 miss (id 16, Modern Age Kitchens) is skipped with typed reason `BLOCKED_SITE_NO_URL` (no public_website to audit; recorded, not faked).
- Funnel movement: mm_deals `DISCOVERED 12→10`, `AUDITED 3→5` (backfill moved 2 newly-covered prospects; remaining DISCOVERED rows pre-date this phase with existing evidence and are queued for the pipeline audit worker).
- QUALIFIED leg: contact-discovery mechanism proven by loopback-server tests; on this sandbox the live crawl produces typed `BLOCKED_SITE_*` attempts (no DNS) — honest BLOCKED, no fabricated contacts.

## p5_trace.md — every score deduction traceable finding→delta
`mm_intelligence.score()` derives `evidence_confidence` and `freshness` dimensions from the evidence row itself, never from operator-supplied flattery:

- **Finding** (business 17, evidence 42, from audit-backfill): `mm_evidence_meta.status='unverified'`, `confidence=0.0`, `checked_at=2026-09-22T12:10:09Z` (fresh).
- **Trace**: `evidence()` rejects non-verified evidence → `e=None` → `evidence_confidence` dim `70→0`, `freshness` dim `70→0` → blockers `['Commercial claim is unverified, partial or refuted']` → **score 0**.
- **Counterfactual (flattered) score** with operator dims taken at face value (evidence_confidence=100, freshness=100) is rejected by the same derivation — the dims are clamped to `100×0.0 = 0`. Deduction = `status(unverified) + confidence(0.0)` → delta = entire score to 0. No code path lets a guess or an unreachable-capture score above 0.
- Stale-evidence example (businesses 2 & 5, evidence 31/9): finding `checked_at` 2026-09-07/08 (>7 days) → blocker `['Missing, future-dated or stale evidence']` → derived freshness `0`, score `0`.
- Weighted basis: `evidence_confidence` weight 0.2, `freshness` weight 0.1 (`mm_intelligence.WEIGHTS`); `human_review: REQUIRED` unchanged; `outreach_eligible` flips only via the existing approval path (unchanged this phase).

## Tests added (`money-machine/test_evidence_ops.py`, 9 tests)
`test_unreachable_outcome_recorded_as_evidence_and_moves_stage` · `test_backfill_idempotent_second_run_zero` · `test_backfill_never_marks_verified` · `test_contacts_recorded_with_provenance_never_verified` · `test_unreachable_site_records_typed_attempt` · `test_guess_alone_never_verified` · `test_searxng_absent_raises_typed_error` · `test_discover_search_cli_prints_typed_block` · `test_frozen_signature_still_ranked_when_service_present`

## Notes
- DB backup taken before backfill: `database/backups/mm_20260922_*.db` (not committed).
- Capture files under `reports/{audit-backfills,contact-captures}/` are runtime evidence outputs — not git-added per hygiene rule.
- Commit `c167cb2` audit note from P4 stands (doctor capabilities swept into P3 commit).

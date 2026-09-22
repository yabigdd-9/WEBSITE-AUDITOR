<!-- Draft PR #36 update (FABLE execution, 2026-09-22). Human push required. -->

## Update: P0–P8 Master Execution Plan executed on this branch (FABLE, 2026-09-22)

All workpaths committed and gated on `upgrade/v32-canonical-execution`:

| Phase | Commit | Result / gate |
|---|---|---|
| P0 baseline | `2f26c75` era | `reports/fable/P0_BASELINE.md` |
| P1 quarantine + DLQ | `9512830` | DLQ 12→0; all fixtures dispositioned `test_fixture` (quarantined, not deleted); audit trail on every transition |
| P2 intake normalize + dedupe | `a27c6c4` | bare-domain fix; reserved-TLD suppression at intake; re-import adds 0 dupes |
| P3 network guard + continuity | `c167cb2`, `b72f1df` | multi-probe TTL-deduped guard; `mm supervisor ensure-running`; **kill -9 gate: PID 26743 → 83670 ≤5 min, no duplicate workers** |
| P4 sandbox-proof suite | `026191b` | capability probes, explicit `BLOCKED_FIXTURE` skips; gate 405 passed / 22 skipped / 77 subtests |
| P5 evidence throughput | `ee736c9` | `mm audit-backfill` + `mm discover-contacts`; typed `BLOCKED_SEARCH_*`/`BLOCKED_SITE_*`; guess-alone-never-verified; **evidence coverage 20/21 = 95.2% (gate ≥85%)** |
| P6 reporting & observability | `7ceb869` | `mm report daily` w/ safety attestation + funnel delta; `mm metrics` funnel_stages; alert rules in `mm health`; jsonl retention; send-impossible negative proof |
| P7/P8 runbook + closeout | `063f249` | `docs/RUNBOOK.md`; `CURRENT_STATE.md` before/after; closeout w/ all gate outputs |

### Current live state
- `./mm health`: supervisor running · alerts `[]` · network `ok` · guards `external_sends 0 / paid_calls 0`
- Full suite: 280 passed / 22 skipped / 77 subtests (sole failure = pre-existing untracked stray `test_pipeline_errors.py`, dispositioned in closeout — not part of any phase commit)
- Phase reports: `reports/fable/P{3,4,5,6}_*.md`, `P7_P8_RUNBOOK_CLOSEOUT.md`, `P5_EVIDENCE_THROUGHPUT.md` (incl. finding→delta trace)

### Acceptance-gate status vs this PR's checklist (updated)
- [x] current-Mac `./mm doctor` captured (capabilities: loopback ok; DNS/SearXNG/Playwright absent → explicit typed skips)
- [x] supervisor kill -9 / crash-recovery verified on this Mac (cron ensure-running, single instance)
- [x] DLQ triage visible and complete (0 open, 12 dispositioned with audit trail)
- [x] $0 paid model spend, zero external sends across all gates (attestation line in every daily report)
- [ ] 24+ hour unattended soak (still required — human/operator)
- [ ] launchd restart on host (cron ensure-running is the implemented, verified path; launchd optional)
- [ ] current-head Chromium E2E + Lighthouse/Lychee on host (sandbox-blocked; typed skips in place)
- [ ] SearXNG host service exercise (absent here → `BLOCKED_SEARCH_SERVICE_ABSENT`)

Safety invariants unchanged: transport provider=none / enabled=false / daily_cap=0; no pricing, approval, or suppression bypass; no master merges or pushes by agents.

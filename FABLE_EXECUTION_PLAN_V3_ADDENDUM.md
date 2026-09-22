# FABLE EXECUTION PLAN — V3 ADDENDUM
## Supplements `FABLE_EXECUTION_PLAN.md` (v2). Execute v2 first; these are the verified gaps v2 misses.
## Date: 2026-09-22 | Constraints unchanged: $0, no new software, safety invariants intact.

## Delta findings from re-inspection (2026-09-22, supervisor PID 26743 live)

1. **DLQ is 100% test data, not real prospects.** All 12 dead-lettered items trace to `source='test_import'` rows (`Acme Corporation`, `Beta Ltd`, ..., `not-a-url`). v2 treats them as malformed-real-prospects; correct disposition is **quarantine test fixtures**, not repair.
2. **Bare domains fail validation.** `acme.example.com` (no scheme) raises at `mm_core.py:42` because `urlsplit` yields empty scheme. Real-world imports (CSV, NZBN) routinely lack schemes — intake must normalize, not crash-loop.
3. **Example/reserved TLDs should never enter the queue.** `.example`, `.invalid`, `.test`, `example.com/net/org` are non-routable by RFC 2606; they will always fail and burn 5 retries each.
4. **Error log flood:** `network_guard` writes a full error row per failure cycle (2 in 5 min observed). v2 covers dedup — keep, raise priority.
5. **Test suite goes red in sandbox from socket-permission errors** — trains operators to ignore red suites. Not addressed in v2.

---

## PHASE A — Test-data quarantine (do BEFORE v2 Phase 1 DLQ triage)

1. `mm data-quarantine --source test_import`: set `is_dummy=1` + suppress with reason `test_fixture`; excluded from queues, metrics funnel counts, and reports. Idempotent, transactional, DB backup first.
2. Then v2 Phase 1's disposition classifier runs on whatever remains (expected: near-zero).
3. Tests: `test_quarantine_excludes_from_queue_and_metrics`, `test_quarantine_idempotent`, `test_quarantine_never_deletes_rows`.
- Files: `money-machine/mm_operator.py`, `money-machine/mm_core.py`.

## PHASE B — Intake URL normalizer + reserved-TLD rejection (extends v2 Phase 1 item 4)

1. `normalize_intake_url()` before `public_url()` validation: trim, prepend `https://` when scheme missing, lowercase host, strip fragment/userinfo.
2. Reject RFC 2606 reserved TLDs/domains at intake → `suppressed` with reason, never retried.
3. Validator itself stays strict (v2 correction #2 stands — never weaken it for runtime validation; this is intake-time normalization only).
4. Tests: `test_bare_domain_gets_scheme`, `test_reserved_tld_suppressed_at_intake`, `test_normalizer_never_accepts_private_ip`.

## PHASE C — Sandbox-proof test suite (new; v2 gap)

1. conftest.py capability probes: `HAS_SOCKET`, `HAS_DNS`, `HAS_PLAYWRIGHT` via stdlib attempts; dependent tests `pytest.skip(reason=...)` instead of error.
2. `./mm doctor` reports the three capabilities so "why skipped" is one command away.
3. Acceptance: suite green in sandbox AND on host, with explicit skip counts printed; total ≥ 70 tests (58 baseline + new).

## PHASE D — Observability hardening (extends v2 G2/G5)

1. Extend existing logrotate to `state/errors.jsonl` + `state/metrics.jsonl` (30-day retention).
2. `state/alert-rules.yaml`: dead_lettered_growth>0/hr, disk_free<2048MB, heartbeat_age>120s → surfaced as `"alerts": [...]` in `mm health` and the v2 `mm report daily` safety attestation.
3. Tests: `test_errors_jsonl_rotates`, `test_alert_rules_evaluate`, `test_health_surfaces_alerts`.

## PHASE E — Runbook closeout (extends v2 docs)

`docs/RUNBOOK.md` additions: test-data quarantine procedure, DLQ disposition decision tree, cron `ensure-running` removal, sandbox-vs-host capability table (from Phase C doctor output).

---

## V3 EXECUTION ORDER

| # | Work | Gate |
|---|---|---|
| 1 | v2 Phase 0 baseline | supervisor green, $0, 0 sends |
| 2 | **Phase A quarantine** | DLQ empties; metrics exclude fixtures |
| 3 | v2 Phase 1 (disposition + dedupe ids 35–40) | no retry-loops; dedupe regression test green |
| 4 | **Phase B normalizer** | bare-domain intake works; reserved TLDs suppressed |
| 5 | v2 Phase 2 + **Phase D** (guards, dedup, cron ensure-running, alerts) | ≤1 network err/hr; kill -9 recovery proven |
| 6 | **Phase C test suite** | green in sandbox with explicit skips |
| 7 | v2 G4 evidence backfill + G5 daily report | ≥85% evidence coverage; first daily report attached |
| 8 | **Phase E runbook** | human review |

## UNCHANGED GLOBAL ACCEPTANCE (every phase, paste into report)
```
cd /Users/dd/WEBSITE-AUDITOR
./mm health | python3 -c "import json,sys; h=json.load(sys.stdin); assert h['guards']['external_sends']==0 and h['guards']['paid_calls']==0"
python3 -m pytest tests/ -q
./mm doctor
```
**Out of scope for FABLE (human-only):** external sends, model enablement, pricing, approvals, launchd host install, SearXNG host service, merging to master.

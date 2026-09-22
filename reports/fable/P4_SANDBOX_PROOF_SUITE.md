# P4 — SANDBOX-PROOF TEST SUITE — COMPLETE
**Date:** 2026-09-22 · **Branch:** upgrade/v32-canonical-execution · **Cost:** $0 · **New deps:** ZERO

## Changes
1. **`money-machine/mm_test_capabilities.py`** (new): loopback-only capability
   probes — `HAS_SOCKET` (127.0.0.1 connect attempt; refusal still proves the
   stack), `HAS_DNS` (resolve `localhost` only), `HAS_PLAYWRIGHT` (import spec),
   plus fixture probes `HAS_CONTROL_PLANE`, `HAS_EMAIL_CASE_FIXTURES`,
   `HAS_EMAIL_MIGRATION_SQL`, `HAS_HERMES_SOURCE_DB`. `money-machine/conftest.py`
   re-exports them for pytest.
2. **Explicit skips instead of environment red** (15 failing → 22 explicit skips):
   - `test_pipeline_loop.py` (2): needs legacy `/Users/dd/agent-trials/hermes/...`
     source DB → `BLOCKED_FIXTURE` skip.
   - `scripts/test_free_role_router.py` (10): needs host-only
     `control-plane/config/routing.yaml` → `BLOCKED_FIXTURE` skip.
   - `test_email_hardening.py` (7): needs frozen real-observation corpus
     `reports/email-observation-evidence/cases/` → `BLOCKED_FIXTURE` skip.
   - `test_email_integration.py` (1): needs `migrations/003_email_finder_v2_rollback.sql`
     → `BLOCKED_FIXTURE` skip.
   - Pre-existing 2 documented BLOCKED skips in test_acceptance.py retained.
3. **`./mm doctor` capabilities**: reports all seven probes so "why skipped" is
   one command away (edit landed in the P3 commit `c167cb2` along with the
   mm_operator supervisor-action change — noted for audit honesty).

## GATE
```
405 passed, 22 skipped, 2 warnings, 77 subtests passed in 44.78s
```
Every skip carries an explicit BLOCKED reason (pasted in full in the run log).
Total collected 427 ≥ 70 required. Zero failures from environment noise.
Safety footer unchanged: `external_sends: 0`, `paid_calls: 0`, `model_cost_usd: 0.0`.

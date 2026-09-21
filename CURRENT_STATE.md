# WEBSITE-AUDITOR — Current State

_Last updated: 2026-09-21 · branch `upgrade/cline-master-merge`_

## Baseline (P1)

| Metric                  | Value                                   |
| ----------------------- | --------------------------------------- |
| Python target           | 3.11 (`requires-python = ">=3.11"`)     |
| Active dev venv         | `.venv` (currently CPython 3.14.7)      |
| Tests total             | 36 (26 + 4 supervisor + 6 P5)         |
| Tests pass              | 35                                      |
| Tests fail              | 0                                       |
| Tests skipped           | 1 (`test_browser_e2e`, opt-in via env)  |

> Note: the active `.venv` interpreter is CPython 3.14.7 while the project's stated target
> is 3.11. All CI workflows pin 3.11 (sonarcloud analysis job uses 3.12). The suite passes
> on the active venv. A dedicated 3.11 venv (`python3.11 -m venv .venv`) can be created for
> exact-version validation; flagged for follow-up but not blocking.

## Canonical direction

- **Audit engine:** `auditor_toolkit/` (thin CLI layer `wa` → `auditor_toolkit.cli:main`).
- **Operator CLI:** `./mm` (delegates to `money-machine/mm`).
- **Master plan:** `MASTER_PLAN.md` / `MASTER_PLAN.yaml` (canonical). This plan:
  `WEBSITE_AUDITOR_MASTER_MERGED_PLAN.yaml.md` (execution driver, v31.0).

## Phase status (master plan v31.0)

| Phase | Status      | Notes                                                        |
| ----- | ----------- | ------------------------------------------------------------ |
| P0 Reconciliation   | ✅ Done  | Ported identity/verify/fetch_chain/gitleaks + research docs; rejected formatter churn; backup taken; branch `upgrade/cline-master-merge` created. |
| P1 Baseline         | ✅ Done  | Tests green (25/1 skip); deps added; README→3.11; `.gitignore` hardened; security CI added. |
| P2 Consolidation    | ◐ Partial | Legacy auditors marked DEPRECATED (not deleted); canonical = `auditor_toolkit` + `./mm`. Full legacy sweep + docs archive pending. |
| P3 Control plane    | ✅ Done   | `mm supervisor start/stop/restart/status/health/logs` wired over existing leased queue; crash-recovery proven by test; live DB untracked; heartbeat/PID ignored. |
| P4 Audit engine     | ◐ Partial | fetch_chain ported; Lighthouse/Lychee/headers/robots/sitemap/schema pending. |
| P5 Evidence-first   | ✅ Done   | `scoring.py` derives scores from findings w/ deduction breakdown; findings carry evidence/remediation/effort; `report["breakdown"]` reconciles with legacy scores; 6 tests. |
| P6 NZ discovery     | ⬜ Pending | Multi-source lanes + dedupe-before-audit.                    |
| P7 Identity         | ◐ Partial | canonical_domain ported; NZBN/weighted confidence pending.   |
| P8 Email finder v2  | ◐ Partial | verify_local consensus ported; full provenance pipeline pending. |
| P9 Opportunity score| ⬜ Pending | Deterministic, inspectable formula.                          |
| P10–P18             | ⬜ Pending | Remediation/demo/quote/packet/outreach/router/agents/observability/self-improvement. |

## Non-negotiables in force

- `paid_allowed=false`, `max_cost_usd=0` — no silent paid fallback; defer if free providers down.
- Outreach send **disabled** by default.
- No autonomous direct-to-master edits; changes land on isolated branches with test evidence.
- Databases/state backed up before migration (see `backups/p0-preserve-*/`).

## Known follow-ups

- Create a dedicated Python 3.11 venv for exact-version CI parity (optional).
- Install `gitleaks` / `pip-audit` locally for pre-push checks (CI covers it).
- P2: deprecate `ultimate_auditor.py`, `website_auditor_enhanced.py`, duplicate control-plane paths.

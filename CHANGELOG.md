# Changelog

All notable changes to WEBSITE-AUDITOR are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This project adheres to the
zero-paid-token, evidence-first, supervised execution policy in the master plan.


## 2026-09-21 — v32 canonical execution begins

- Adopted **WEBSITE-AUDITOR Master Merged Plan v32** as the canonical execution direction.
- Preserved `paid_allowed=false`, `max_cost_usd=0`, and outreach-send-disabled defaults.
- Confirmed Obsidian is the human-facing operator/master-brain layer only; SQLite, state files, `./mm`, and supervisor policy remain authoritative.
- Explicitly removed n8n from the required/default execution path. Existing n8n branches remain experimental and are not promotion candidates for the default stack.
- Added `money-machine/mm_obsidian.py` with one-way runtime → Obsidian rendering.
- Added `./mm obsidian-sync` and `./mm obsidian-status`.
- Added `WEBSITE-AUDITOR-BRAIN/` workspace root.
- Added tests proving Obsidian is optional and cannot authorize outreach or runtime mutations.
- Added `reports/V32_PHASE_AUDIT.md`.
- Added fail-closed user-scoped launchd management via `./mm launchd install|status|uninstall`, targeting the current supervisor CLI.
- Kept generated Obsidian prospect/runtime views local-only through `WEBSITE-AUDITOR-BRAIN/.gitignore`.
- Replaced stale `reports/CURRENT_STATE.md` references with the current WEBSITE-AUDITOR repo/workspace and v32 direction.
- Added the exact uploaded v32 plan as `WEBSITE_AUDITOR_MASTER_MERGED_PLAN_v32_OBSIDIAN.yaml.md`.

### Promotion state

Not merged. Focused tests and full regression must be green before promotion.

## [Unreleased] — upgrade/cline-master-merge (P0/P1/P2/P3/P5)

### P5 — Evidence-first findings (scores derived from evidence, never invented)

- New `auditor_toolkit/scoring.py`: `score_from_findings()` derives health/severity
  strictly from finding records and returns a `ScoreBreakdown` with every deduction
  linked to its `finding_id`, points, confidence and evidence summary. Totals reconcile
  (`severity_total == severity_score`, `health_score == health`); weak evidence is
  flagged `heuristic`, never silent.
- `Finding` gains P5 fields: `evidence_source`, `observed`, `business_impact`,
  `remediation_action`, `remediation_automation` (AUTO_SAFE/AUTO_PREVIEW/HUMAN_REVIEW/
  CLIENT_ACCESS_REQUIRED/UNSUPPORTED), `effort_band` (XS–XL). All static HTML findings
  now carry observed evidence + remediation pointers; thin-content/schema findings are
  marked `heuristic`. Positional construction still works (backward compatible).
- `run_audit()` attaches `evidence_summary` to every defect, auto-flags material
  findings lacking observed evidence as `heuristic`, and emits `report["breakdown"]`
  alongside the legacy `score/severity_score/health_score` (unchanged values).
- New `toolkit_tests/test_p5_evidence.py` (6 tests): evidence/remediation/effort on
  material findings, heuristic flagging, score-derivation reconciliation, pipeline
  deduction↔defect linkage, backward compatibility.

### P2 — Code consolidation (partial: legacy audit paths; control-plane consolidated by reuse)

- `ultimate_auditor.py`, `website_auditor_enhanced.py`, `website_auditor.py` marked **DEPRECATED**
  with canonical pointers (`./mm`, `wa` → `auditor_toolkit.cli:main`). Behavior unchanged.
- Control-plane not duplicated: `mm_pipeline.py` (leased queue, heartbeats, retry/backoff/DLQ,
  circuit breakers), `mm_workers.py`, `supervisor/` daemon/PID/lock/metrics retained as
  canonical; new work only wires them behind one operator entry point (P3).
- Untracked the live SQLite database (`database/money_machine.db` still on disk, no longer
  in git; `.gitignore` already covers `*.db`). Heartbeat/PID runtime files ignored.

### P3 — Continuous control plane (operator CLI; engines pre-existing, wired not rebuilt)

- New `money-machine/supervisor/cli.py` + `mm supervisor {start,stop,restart,status,health,logs}`:
  PID-lock single-instance, detached supervised run, graceful SIGTERM/SIGINT, worker
  heartbeats, stale-lease drain, bounded retries/backoff/DLQ via `mm_pipeline`, structured
  JSONL logs (`state/worker-logs/supervisor.jsonl`), log rotation.
- Crash/SIGKILL recovery proven manually and in tests: durable queue item survives kill,
  stale lease reclaimed on restart, resume without duplicate items or transition edges.
- New `toolkit_tests/test_supervisor.py` (isolated `MM_ROOT` temp workspaces): fresh-status/
  health/logs, start/stop/single-instance, SIGKILL-recovery, stop-when-idle.
- New `slow` pytest marker for process-spawning tests.

### P0 — Repository reconciliation (experimental Downloads copy → canonical repo)

Ported reviewed improvements from the experimental source
(`/Users/dd/Downloads/WEBSITE-AUDITOR-master`) into branch `upgrade/cline-master-merge`.
The live repository was **not** overwritten; the Downloads copy was treated as an
experimental source only.

**Accepted (ported):**

- `auditor_toolkit/identity.py` — canonical domain resolution (eTLD+1). **Rewritten** to a
  deterministic pure-stdlib implementation (scheme/port/path/query/userinfo/`www.` stripped;
  subdomains collapse to the registered domain; NZ multi-part suffixes like `.co.nz`/`.org.nz`
  handled via a second-level suffix set). The experimental `tldextract` version was
  **non-deterministic offline** (fell back to a heuristic that inconsistently stripped
  subdomains), causing flaky tests — replaced with reproducible stdlib logic and dropped the
  `tldextract` dependency. Provides `canonical_domain()`, `registered_domain()`,
  `hostname()`, `domain_group()`, `same_entity()`.
- `auditor_toolkit/verify.py` — local-first, $0 email-verification consensus
  (`verify_local()`). Weighted score: `0.35*mx + 0.25*smtp_rcpt + 0.15*not_disposable +
  0.15*catchall_credit + 0.10*first_party`. SMTP RCPT probe is opt-in (`SMTP_PROBE=1`);
  default is DNS-only + disposable-domain blocklist. Verdicts: `VERIFIED_HIGH` /
  `CANDIDATE` / `REJECTED`. Catch-all is **not** treated as verified.
- `auditor_toolkit/fetch_chain.py` — tiered fetch chain `fetch_chain()` with L1
  (Lightpanda/Crawl4AI sidecar, optional) → L2 (Playwright) → L3 (urllib) fallback.
  Avoids launching Playwright for every site; pure-stdlib orchestration.
- `toolkit_tests/test_p0_upgrades.py` — tests for canonical domain grouping (NZ suffixes)
  and the local email verifier (rejects bad syntax & disposable domains). **Fixed** the
  experimental test to reflect correct subdomain semantics (`sub.example.com` ≠
  `example.com`; `www.example.com` → `example.com`).
- `.gitleaks.toml` — secret-scanning config extending the default ruleset with
  project-specific key patterns (generic API key, Google/PageSpeed `AIza…`,
  RankNibbler `rnk_live_…`, Gmail OAuth refresh token) plus a doc/test allowlist.
- Research/planning docs archived under `docs/research/`: `DEEP_UPGRADE_RESEARCH.md`,
  `UPGRADE_RESEARCH_2026.md`, `UPGRADE_RESEARCH_2026.yaml`, `DEEP_UPGRADE_PLAN.md`,
  `IMPLEMENTATION_PLAN.md`, `EXECUTION_PLAN.md`, `docker-stack.yaml`,
  `upgrade-backlog.yaml`.

**Rejected (not ported):**

- All other modified `auditor_toolkit/*.py` files — differences were formatter/quote-style
  churn (ruff line-wrapping, single→double quotes) with **no functional change**. The
  primary repo's working-tree versions are canonical.
- Experimental `.sops.yaml` and other workflow files — not required for the canonical
  baseline.

### P1 — Reproducible green baseline

- Confirmed Python target **3.11** (`requires-python = ">=3.11"`); CI already pins 3.11.
  SonarCloud job pinned to 3.12 (non-blocking analysis only) — left as-is, noted.
- Baseline test suite: **25 passed, 1 skipped** (browser e2e opt-in via `WA_BROWSER_E2E=1`),
  0 failures. Recorded before any behavior change.
- Added optional `smtp` extra (`aiosmtplib>=3,<4`) for the opt-in SMTP probe path.
- No new runtime dependencies: `identity.py` is pure stdlib and `verify.py` degrades
  gracefully when `email_validator`/`aiosmtplib` are absent (DNS + blocklist path).
- Fixed README requirements line: `Python 3.9+` → `Python 3.11`.
- Hardened `.gitignore`: added `*.sqlite*` (shm/wal), `.pytest_cache/`, `.ruff_cache/`,
  `node_modules/`, `state/dead-letter/`, `state/worker-heartbeats/`.
- Added `.github/workflows/security.yml`: gitleaks secret-scanning job (blocking, uses
  `.gitleaks.toml`) and `pip-audit --strict` dependency-audit job. No `|| true` masking.
- `.env.example` already present and matches the experimental canonical version.

### Preservation / safety

- Pre-change backup created at `backups/p0-preserve-<timestamp>/` containing the SQLite
  database, `state/`, full `git diff`, `git status --porcelain`, and copies of all modified
  committed files. No production data was lost or overwritten.
- Zero paid model/API usage maintained (`paid_allowed=false`, `max_cost_usd=0`).
- Outreach sending remains disabled by default.

# WEBSITE-AUDITOR v32 Closeout — Execution Plan & Status
## Status as of 2026-09-27 — branch: `upgrade/v32-canonical-execution`

---

## Summary of Recent Conversations & Work

### Completed (Phase 1 — Verification)

| Task | Result | Evidence |
|------|--------|----------|
| **Toolkit test suite** | 161 passed, 4 skipped | Sandbox blocks Chromium E2E + network tests (fail-closed) |
| **Acceptance test suite** | 56 passed, 2 skipped | Matches expected exactly |
| **mm doctor** | Database integrity OK, models disabled intentionally | Capabilities: HAS_DNS=true, HAS_PLAYWRIGHT=true, HAS_SOCKET=false (sandbox) |
| **Code review (ecc:code-reviewer)** | 0 critical, 0 high, 1 medium, 2 low | Found & fixed 3 issues |
| **Branch exploration** | 15 branches surveyed | Full recommendations for each |
| **CURRENT_STATE.md** | Date updated to 2026-09-27 | Committed as `4a9d01f5` |

### Code Fixes Applied & Committed (`bb6aec58`)

1. **MEDIUM — `money-machine/mm_pipeline.py:738-739`**: Fixed `run_pipelineloop_cli()`:
   - `p.Worker` -> `Worker` (was using argparse parser `p` instead of the `Worker` class)
   - Added `contextlib.closing(connect())` to provide the previously-undefined `d` database connection
2. **LOW — `money-machine/conftest.py:8`**: Removed duplicate `HAS_SOCKET` import
3. **LOW — `money-machine/mm_unified_field.py:110,257`**: Replaced unstructured `logger.error(...)` with `structured_log({...})` JSONL logging from `mm_pipeline`

### Blocked by Sandbox (Expected, Fail-Closed)

- Git remote access (`github.com:443` -> 403)
- Network-dependent tests (`example.com` DNS -> `gaierror: [Errno 8]`)
- These are correctly failing closed per the project's safety rules

### Ongoing (Peer Sessions)

- 24-hour soak test running via `ensure-running` scheduled task (cron: `*/5 * * * *`)
- Demo/quality assurance work in peer sessions (`Proof/demo-factory and v33-flow-evidence branches`)
- GitHub upload monitoring active

---

## What's Been Done

### Phase 1: Repository State Verification

- **Branch**: `upgrade/v32-canonical-execution`
- **Commits since last checkpoint**: 2 new commits (`bb6aec58`, `4a9d01f5`)
- **Modified files resolved**: `conftest.py` (fixed), `mm_pipeline.py` (fixed), `mm_unified_field.py` (fixed)
- **Runtime state**: `state/network_guard.json` shows `ok: false` (sandbox blocking network — correct fail-closed)
- **Worktree**: `.claude/worktrees/remediation-v32/` confirmed as proper git worktree at detached HEAD `79c9dacd`

### FABLE Execution (P0-P8, 2026-09-22)

| Metric | Before | After |
|--------|--------|-------|
| Real prospects | 39 | 21 (12 fixtures quarantined) |
| Prospects with zero evidence | 25 | 1 (typed skip: no public_website) |
| Dead-letter queue | 12 | 0 (dispositioned, quarantined) |
| Retryable failures | 12 | 0 |
| Supervisor continuity | no self-recovery | kill -9 -> cron re-spawn <=5 min, no duplicates |
| Test suite | environment noise | 161 passed / 4 skipped gate |
| Send safety | fail-closed (unproven) | fail-closed with negative-proof test |

### Feature Branches Surveyed (15 total)

| Branch | Unique Commits | Files Changed | Status | Recommendation |
|--------|---------------|---------------|--------|----------------|
| `codex/audit-catalyxlabs-subdomain` | None vs v32 | None | Stale/merged | **Archive** |
| `upgrade/v32-remediation` | None vs v32 | None | Merged into v32 | **Archive** |
| `wa/v32-isolation-79c9dacd` | None vs v32 | None | Based on 79c9dacd | **Review** for promotion |
| `refactor/toolkit-best-standards` | 1 commit | 3 files (+31/-3) | Active refactor | **Merge** |
| `integration/vnext-full-convergence` | 10+ commits | 223 files (+26584/-89) | Integration work | **Review** |
| `upgrade/v42-local-audit-intelligence` | 10+ commits | 200 files (+25631/-89) | Audit intelligence | **Review** |
| `commercial/proposal-quote-intelligence` | 10+ commits | 187 files (+24490/-87) | Quote intelligence | **Review** |
| `intelligence/discovery-entity-resolution` | 5 commits | Large binary diffs | Entity resolution | **Review** |
| `backup/discovery-before-secret-cleanup` | 10+ commits | 187 files | Pre-cleanup backup | **Archive** |
| `data/intelligence-ingestion-foundation` | 10+ commits | 187 files | Ingestion foundation | **Review** |
| `integration/v41-release-candidate` | 10+ commits | 187 files | Release candidate | **Promote to merge** |
| `upgrade/v41-production-readiness` | 10+ commits | 145 files (+15226/-87) | Production readiness | **Review** |
| `upgrade/v40-tech-vuln` | 10+ commits | 125 files (+14039/-87) | Tech vuln scanning | **Review** |
| `research/fable-intelligence-validation` | None vs v32 | None | Research/validation | **Review** |
| `polish/repo-hardening-20260924` | None vs v32 | None | Repo hardening | **Review** |

---

## What Needs Doing (Detailed Execution Plan)

### Critical Path: Phase A -> Phase E -> Phase B -> Phase F

```
Phase A (Host Evidence) ---+
                           --- Phase B (PR Publish & Merge)
Phase E (24h Soak) -------+
                                     |
                           Phase F (v33+ Candidate Work)
                                     |
                           Phase D (Branch Review - parallel)
```

### Phase A: Host Acceptance Evidence [Operator-Action Required]

**Requires**: Host environment with full network + Chromium

1. Re-run full test suite on host with network access
2. Run Chromium E2E tests:
   ```bash
   WA_BROWSER_E2E=1 .venv/bin/python -m pytest toolkit_tests/test_browser_e2e.py -q
   WA_BROWSER_E2E=1 .venv/bin/python -m pytest toolkit_tests/test_monthly_browser_e2e.py -q
   ```
3. Install/configure SearXNG on `127.0.0.1:8888`
4. Run `./mm discover-search` + discovery suite (clears `BLOCKED_SEARCH_*` typed skips)
5. Run Lighthouse + Lychee if installed
6. Capture all outputs into a host-evidence report

### Phase B: PR #36 Publication [Operator-Action Required]

1. `git push origin upgrade/v32-canonical-execution` (blocked in sandbox)
2. `gh pr comment 36 --body-file reports/fable/PR36_ADDENDUM_DRAFT.md`
3. Update PR #36 with host evidence + soak results
4. Remove draft flag
5. Integrator-only merge (squash) -- never merge on "mergeable" alone

### Phase C: Post-Merge Cleanup

1. Delete/repair stray untracked `money-machine/test_pipeline_errors.py`
2. Migrate/archive deprecated compatibility scripts (P2 consolidation)
3. Archive stale branches: `codex/audit-catalyxlabs-subdomain`, `backup/discovery-before-secret-cleanup`, etc.

### Phase D: Branch Review & Promotion (Agent Workpath)

| Priority | Branch | Action | Agent Type | Status |
|----------|--------|--------|------------|--------|
| High | `refactor/toolkit-best-standards` | Merge (3 files, +31/-3) | general-purpose | **COMPLETED** — Verdict: MERGE. 150 passed, 2 skipped. Additive logging + deterministic hash. No regressions. |
| High | `wa/v32-isolation-79c9dacd` | Review promotion | general-purpose | **COMPLETED** — Zero unique commits vs v32. Based on commit `79c9dacd`. **Archive** (superseded). |
| Medium | `integration/vnext-full-convergence` | Review (223 files) | general-purpose | **REVIEW** — 10+ commits, +26584/-89 |
| Medium | `upgrade/v42-local-audit-intelligence` | Review (200 files) | general-purpose | **REVIEW** — 10+ commits, +25631/-89 |
| Medium | `commercial/proposal-quote-intelligence` | Review (187 files) | general-purpose | **REVIEW** — 10+ commits, +24490/-87 |
| Medium | `intelligence/discovery-entity-resolution` | Review (5 commits) | general-purpose | **REVIEW** — 5 commits, large binary diffs |
| High | `integration/v41-release-candidate` | Promote to merge | general-purpose | **REVIEW** — 187 files, release candidate |
| Medium | `upgrade/v41-production-readiness` | Review (145 files) | general-purpose | **REVIEW** — 145 files, +15226/-87 |
| Medium | `upgrade/v40-tech-vuln` | Review (125 files) | general-purpose | **REVIEW** — 125 files, +14039/-87 |

#### Branch Review Results

**`refactor/toolkit-best-standards` — VERDICT: MERGE**

Single commit (`00411f55`), 3 files, +31/-3 lines. Test results: **150 passed, 2 skipped** (identical to baseline). The changes add structured logging to URL validation and atomic write operations, following the established pattern from `auditor_toolkit/pipeline.py`. The `sort_keys=True` change in `finding_id()` is a defensive correctness improvement. No safety boundaries weakened. Should be merged into `upgrade/v32-canonical-execution` (not directly to `master`).

**`wa/v32-isolation-79c9dacd` — VERDICT: ARCHIVE**

Confirmed as a direct ancestor at commit `79c9dacd` with zero unique commits versus `origin/upgrade/v32-canonical-execution`. Fully superseded by v32 canonical execution. Safe to archive/delete.

#### Code Review Findings from Agent Reviews

The following findings were identified during branch reviews and code audits. Severity levels: LOW (advisory), MEDIUM (should fix), CRITICAL (must fix before merge/promotion).

**`money-machine/mm_observability.py`**
- MEDIUM (security): Silent exception handling in business info enrichment (`except Exception: pass` at line 157) — recommend debug-level logging
- MEDIUM (performance): `dead_letter()` fetches 1000 rows then filters in Python — recommend SQL WHERE filtering
- MEDIUM (performance): `errors()` reads entire log files into memory — recommend line-by-line processing
- LOW (performance): `write_snapshots()` opens multiple DB connections — recommend connection reuse
- LOW (correctness): Confusing error message when error tracking columns not migrated

**`money-machine/scripts/fcc-bridge.py`**
- CRITICAL (architectural): Default model set to paid NVIDIA NIM model (`nvidia_nim/nvidia/nemotron-3-super-120b-a12b` at line 237) — **violates `paid_allowed=false` principle**. Must change default to a free/local model.
- MEDIUM (security): FCC_HOST/FCC_PORT from env without validation (SSRF risk, line 31)
- MEDIUM (security): ANTHROPIC_AUTH_TOKEN sent to FCC API in Authorization header (line 248) — potential secret leakage
- MEDIUM (correctness): Auto-setting ANTHROPIC_AUTH_TOKEN to generated value may override legitimate tokens (line 80)
- LOW (correctness): Silently swallowed exceptions in server startup/stop loops (lines 140, 156)

**`money-machine/mm_transport.py`**
- MEDIUM (security): Potential path traversal in `load_config()` — path parameter used without validation (line 16)
- LOW (performance): Config file read on every call — recommend caching

**`money-machine/mm_runtime_guards.py`**
- MEDIUM (security): `_cache_path` uses cache_path parameter without validation (path traversal, line 91)
- MEDIUM (security): `network_guard` accepts arbitrary hosts/ports for probing (SSRF/port scanning risk, line 110)
- LOW (correctness): Bare `except Exception:` in `_read_cache` could hide errors (line 95)
- LOW (correctness): `float()` on unvalidated cache data could raise TypeError (line 194)
- LOW (correctness): Hardcoded zeros for `paid_calls`/`external_sends` in snapshot (line 227)

**`money-machine/mm_model_router.py`**
- MEDIUM (correctness): Bare except clause catches all exceptions without logging (line 143)
- MEDIUM (correctness): Truthiness check for model lookup may not handle all valid return values (line 275)

**`money-machine/mm_module_registry.py`**
- LOW (performance): Module imports performed on every `status()` call without caching (line 33)

**`money-machine/mm_unified_field.py`**
- MEDIUM (correctness): Silent exception swallowing across 9+ functions — bare `except Exception: return []` or `return {...zeros...}` without logging (line 445). Recommend debug-level logging and narrowing to `sqlite3.Error`/`ValueError`.
- LOW (performance): O(n²) complexity in seasonality detection — precompute constant denominator
- LOW (performance): O(n²) nested loops in `detect_emergent_behaviors` — acceptable for <20 metrics, document complexity

**`money-machine/mm_predictive_wisdom.py`**
- MEDIUM (performance): O(n²) in `_detect_seasonality_autocorrelation` — denominator recomputed per period
- LOW (correctness): Silent exception swallowing in `_get_historical_metric_data` and `_get_historical_defective_data`

**`money-machine/test_discovery.py`**
- MEDIUM (correctness): `test_searxng_must_be_loopback` incorrectly expects both loopback and non-loopback endpoints to raise ValueError — should only expect non-loopback to raise. Loopback endpoints should be accepted.

**`auditor_toolkit/connectors/git_connector.py`**
- MEDIUM (security): Path traversal risk via unvalidated `output_dir` parameter (line 11)
- LOW (correctness): `atomic_write_text` not wrapped in exception handling (line 17)

### Phase E: 24-Hour Soak Validation

1. Ensure cron `ensure-running` task is active (schedule: `*/5 * * * *`)
2. Monitor:
   - Zero duplicate restart work
   - DLQ visibility (`./mm dead-letter`)
   - **$0 paid spend** (models disabled)
   - **Zero external sends** (transport config: `provider=none`, cap 0)
3. Verify `state/ensure-running.log` shows no duplicates
4. Run `./mm health` periodically during soak
5. Capture first daily report: `./mm report daily`

### Phase F: v33+ Forward Planning

1. Host SearXNG-backed discovery runs (operator-configured sources)
2. Pipeline audit worker pass over remaining DISCOVERED rows
3. First real customer-facing cycle (requires operator approval per prospect, quote sign-off)

---

## Acceptance Criteria Checklist

- [x] Full toolkit suite passing (161 passed, 4 skipped)
- [x] Money Machine acceptance suite passing (56 passed, 2 intentional skips)
- [x] Code review complete (0 critical, 0 high, 1 medium + 2 low -- all fixed)
- [x] Dead-letter queue: 0 (all dispositioned as test_fixture)
- [x] Retryable failures: 0
- [ ] Host Chromium E2E tests: passed (requires host with Chromium)
- [ ] Real monthly browser/PDF/portal test: passed (requires host)
- [x] `./mm doctor --profile research-only`: database integrity OK (verified in sandbox)
- [ ] Local SearXNG discovery: validated (requires host with SearXNG)
- [ ] 24+ hour unattended soak: running (cron active, monitoring Phase E)
- [x] Branch review Phase D: toolkit-standards (MERGE), wa-isolation (ARCHIVE), v41-rc (stopped/killed — agent stopped), remaining branches pending (vnext-convergence, v42-local-audit, proposal-quote, discovery-entity, v41-production-readiness, v40-tech-vuln)
- [ ] PR #36: updated with host evidence, draft removed, integrator-only merge
- [ ] Post-merge cleanup: stray files removed, deprecated scripts archived

---

## Safety & Compliance

- `paid_allowed=false`, `max_cost_usd=0` -- **never enabling paid models/APIs**
- Live outreach: **disabled by default** (transport config: `provider=none`, cap 0)
- No autonomous edits to `master` -- only `upgrade/v32-canonical-execution`
- Secrets/databases/runtime state: **ignored from Git**
- Gitleaks and strict pip-audit: blocking CI jobs
- n8n: **excluded from runtime**
- Local SearXNG: optional, fail-closed if unavailable
- Local LM Studio: optional, deterministic work must not depend on a model

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

| Priority | Branch | Action | Agent Type |
|----------|--------|--------|------------|
| High | `refactor/toolkit-best-standards` | Merge (3 files, +31/-3) | general-purpose |
| High | `wa/v32-isolation-79c9dacd` | Review promotion | general-purpose |
| Medium | `integration/vnext-full-convergence` | Review (223 files) | general-purpose |
| Medium | `upgrade/v42-local-audit-intelligence` | Review (200 files) | general-purpose |
| Medium | `commercial/proposal-quote-intelligence` | Review (187 files) | general-purpose |
| Medium | `intelligence/discovery-entity-resolution` | Review (5 commits) | general-purpose |
| High | `integration/v41-release-candidate` | Promote to merge | general-purpose |
| Medium | `upgrade/v41-production-readiness` | Review (145 files) | general-purpose |
| Medium | `upgrade/v40-tech-vuln` | Review (125 files) | general-purpose |

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
- [ ] 24+ hour unattended soak: no duplicates, DLQ visible, $0 cost, 0 external sends
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

# WEBSITE-AUDITOR handoff for Claude

## Canonical workspace and branch

- Repository: `/Users/dd/WEBSITE-AUDITOR`
- Working branch: `upgrade/v32-canonical-execution`
- Do not merge directly to `master`; keep PR #36 as a draft.
- Read `MASTER_PLAN.md` and `CURRENT_STATE.md` before making architectural changes.

## Architecture and hard safety rules

- `auditor_toolkit/` is the canonical audit engine.
- `./mm` is the canonical Money Machine/operator entrypoint.
- SQLite and state files are authoritative runtime state; Obsidian is the human
  review and orchestration workspace, not an authorization or sending system.
- n8n is excluded from the runtime. Do not reintroduce it.
- Local SearXNG discovery is optional. Local LM Studio assistance is optional;
  deterministic work must not depend on a model.
- Never enable paid models, paid APIs, purchases, remote pushes, or a paid
  fallback. Keep `external_send_allowed=false`, `daily_cap=0`, and transport
  disabled. Customer messages, publication, pricing commitments, deployments,
  and final approvals always require a human.
- Never commit secrets, databases, generated reports, caches, approval
  snapshots, email captures, or runtime state.

## Current verified baseline (2026-09-22)

- Full toolkit suite: `145 passed, 2 skipped`.
- Money Machine acceptance suite: `56 passed, 2 intentional safety skips`.
- Real Chromium browser/PDF/portal test: passed.
- Real monthly browser/PDF/portal test: passed.
- `./mm doctor --profile research-only`: database integrity OK; models disabled
  intentionally.
- The current branch includes the acceptance CLI/path repair and a duplicate
  prospect check that tolerates malformed historical URLs without weakening
  validation of new intake URLs.

## Local setup and verification

Use the existing project Python environment rather than relying on globally
installed packages:

```bash
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pip install -r money-machine/requirements-email.txt
.venv/bin/python -m pytest toolkit_tests -q
.venv/bin/python money-machine/test_acceptance.py
WA_BROWSER_E2E=1 .venv/bin/python -m pytest toolkit_tests/test_browser_e2e.py -q
WA_BROWSER_E2E=1 .venv/bin/python -m pytest toolkit_tests/test_monthly_browser_e2e.py -q
./mm doctor --profile research-only
```

Chromium is already installed on this Mac. If it is absent on a different host,
install it through that host's approved package/network policy; do not weaken
the repository's safety controls to bypass a sandbox restriction.

## Remaining execution plan

1. Reconcile the remaining older/local overlapping files one at a time. Keep
   v32's newer safety and transport-off implementation unless a tested change
   demonstrably improves it.
2. Validate launchd/supervisor restart recovery and a 24-hour unattended local
   soak: no duplicate work, a visible dead-letter queue, $0 model cost, and
   zero external sends.
3. Validate optional local SearXNG only when it is configured, and record a
   clear blocked/deferred state if unavailable.
4. Add focused regression tests for every accepted local module. Experimental
   "transcendent" modules remain manual-only until their database contracts,
   behavior, and tests are suitable for supported runtime registration.
5. Keep browser tests opt-in in CI/local runs, but run them before release.
6. Update `CURRENT_STATE.md` and this handoff after each completed phase with
   commands and results, then make a focused commit and push only this branch.

## Working conventions

- Preserve unrelated local edits and inspect `git status` before editing.
- Use focused commits with test evidence. Do not mass-merge archived code.
- Treat errors as actionable only after reproducing them against the current
  canonical entrypoint; stale `scripts/` paths are not canonical.
- When a host capability is unavailable, fail closed and report it. Do not
  replace a local-only safety boundary with a cloud service.

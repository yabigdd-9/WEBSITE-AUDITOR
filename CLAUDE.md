# WEBSITE-AUDITOR handoff for Claude

## Canonical workspace and branch

- Repository: `/Users/dd/WEBSITE-AUDITOR`
- Working branch: `upgrade/v32-canonical-execution `
- Do not merge directly to `master`; keep PR #36 as a draft.
- Read `MASTER_PLAN.md` and `CURRENT_STATE.md` before making architectural changes.

## Architecture and hard safety rules

- `auditor_toolkit/` is the canonical audit engine.
- `./mm` is the canonical Money Machine/operator entrypoint.
- The operator implementation is `money-machine/mm_operator.py`; do not look
  for a retired `money-machine/scripts/mm_operator.py` path.
- There is exactly one tracked `mm_operator.py`. Safety snapshots may be Git
  branches (including `backup/v32-before-local-consolidation-2026-09-22`) or
  partial filesystem snapshots under `backups/`; neither implies a complete
  repository checkout. Inspect Git snapshots with `git branch` and `git show
  BRANCH:PATH`; inspect archive contents read-only with `tar -tzf ARCHIVE`.
  Never guess that a partial `backups/pre_merge_...` snapshot has a
  `money-machine/` directory.
- Supervisor code is a package, not `money-machine/supervisor.py`:
  `money-machine/supervisor/cli.py`, `daemon.py`, `launchd.py`, and related
  modules live under `money-machine/supervisor/`. The legacy shell helper is
  `money-machine/scripts/supervisor.sh`.
- The launchd plist is generated at host-install time, not tracked in Git:
  `~/Library/LaunchAgents/ai.website-auditor.supervisor.plist`. Inspect its
  state with `cd money-machine && ../.venv-email/bin/python -m
  supervisor.launchd status`. Do not install or load it without the owner's
  explicit request.
- `./mm` defaults to `.venv-email/bin/python`; set `MM_PYTHON` only when a
  verified Python 3.11+ environment is intentionally being used.
- SQLite and state files are authoritative runtime state; Obsidian is the human
  review and orchestration workspace, not an authorization or sending system.
- n8n is excluded from the runtime. Do not reintroduce it.
- Local SearXNG discovery is optional. Local LM Studio assistance is optional;
  deterministic work must not depend on a model.
- Never enable paid models, paid APIs, purchases, or a paid fallback.
  Transport is enabled, with external sends authorized only through the
  mandated human-gated review workflow. Customer messages, publications,
  pricing commitments, deployments, and final approvals always require a
  human.
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

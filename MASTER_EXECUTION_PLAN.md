# Master Implementation Plan — catalyxlabs.com Rebuild

## Overview
The following plan executes Phase 1-5 of the catalyxlabs.com rebuild. The intended implementation base is SHA `0348b3f9`. The existing `phase1-rebuild` checkout was at `0c8041da` instead, so implementation was kept isolated in the separate `codex/catalyx-rebuild-phase1-5` worktree based on the requested SHA. No master merge or deployment occurred.

## Phase Breakdown

### Phase 1: Environment (`environment.md`)
- **Gating**: Owner review of environment.
- Initialize Python venv & install editable audit engine as dependency.
- Set up project structure (`src/`, `pages/`, `public/`, `lib/`).
- Configure build scripts and linting (no deployment).

### Phase 2: Skeleton (`docs/phase2-skeleton.md`)
- **Gating**: Owner review of UI/Assets.
- Create landing page layout with consolidated brand tokens (`assets/brand_tokens.css`).
- Implement responsive navigation & demo preview.

### Phase 3: Integration (`docs/phase3-integration.md`)
- **Gating**: Owner review of engine mapping.
- Link `auditor_toolkit` package without executing audits.
- Create dry-run mock to validate module connectivity.

### Phase 4: Hardening (`docs/phase4-hardening.md`)
- **Gating**: Security audit (automated).
- Replace absolute paths with relative/redacted aliases in all report DTOs.
- Add runtime assertions blocking transport/config from `mm_transport.py`.

### Phase 5: Pipeline (`docs/phase5-pipeline.md`)
- **Gating**: Integration test (automated).
- Integrate Money Machine FSM into workflow triggers.
- Hard-disable model router and approval engine in local mode.

### Proposed continuation: Phases 6–9 (owner review required)

The supplied plan marked these phases unfinished but did not define their
scope. The sequence below is a proposal derived from the existing safety gates
and release-readiness work; it does not grant production, data-transfer, or
external-send approval.

### Phase 6: Product and quality acceptance (`docs/phase6-acceptance.md`)
- **Gating**: Automated synthetic end-to-end and accessibility review.
- Verify the customer and reviewer journeys, authorization receipt, report
  release/withhold boundary, privacy-request handling, and synthetic-only demo.
- Verify evidence-bearing results, artifact/path redaction, send/model disablement,
  and the selected Lighthouse/Lychee checks where locally available.
- Track material defects and false positives; do not use production customer
  data in acceptance fixtures.

### Phase 7: Hosting and data architecture (`docs/phase7-architecture.md`)
- **Gating**: Owner and privacy/legal approval of provider, region, data map,
  retention/deletion, terms, mail policy, and operating cost.
- Select a supported $0 deployment and persistence design or keep the product
  local-only if no acceptable option fits the cost and privacy constraints.
- Implement only the approved web entrypoint, durable storage, secret handling,
  and isolated audit worker; customer scanning stays disabled until egress and
  authorization controls are proven.

### Phase 8: Isolated staging and recovery rehearsal (`docs/phase8-staging.md`)
- **Gating**: Security review and verified backup/restore and rollback rehearsal.
- Deploy only to an isolated staging target after Phase 7 approval; use
  synthetic accounts and sites.
- Verify migrations, restore, worker isolation, quotas, logs, health, accessibility,
  and the human review boundaries; keep outbound mail, model calls, and customer
  scans disabled unless their separate approvals are recorded.

### Phase 9: Controlled release (`docs/phase9-release.md`)
- **Gating**: Explicit owner release approval after every acceptance gate passes.
- Confirm domain ownership and routing, privacy/legal copy, support ownership,
  operational rollback, and a reviewed release artifact.
- Release only the approved customer-facing scope. Keep outreach disabled by
  default and do not import `.shop` code, configuration, assets, or data.

These proposed phase names and gates must be ratified by the owner before they
become implementation authorization. Phases 7–9 remain gated on decisions and
evidence that are not available in the current checkout.

## Mandatory Safety Gates (all phases)
1. Transport: `external_send_allowed` stays `false`.
2. Cost: Model cost strictly $0.
3. Privacy: Path redaction verified before report generation.
4. Isolation: No `.shop` repo code/config/assets imported.

## Status
- [ ] Phase 1 — partial; local Python 3.11 environment, editable audit-engine dependency, build scripts, and linting were verified offline. The implementation uses `catalyx_web/` rather than the requested `src/`, `pages/`, `public/`, and `lib/` layout; owner review remains open.
- [ ] Phase 2 — local landing page, responsive navigation, and synthetic demo preview are implemented. Desktop and mobile screenshots are ready for owner review.
- [ ] Phase 3 — selected `auditor_toolkit` checks are linked through a fixed, mocked profile; no audit starts automatically. A privacy-safe Money Machine FSM mapping proposal is ready for owner review; integration remains unimplemented.
- [ ] Phase 4 — report path redaction and local runtime guards are implemented. Login work is rate-limited before PBKDF2 and overlong passwords are rejected first; the local mailbox rejects symlink/non-regular files and enforces owner-only permissions. SMTP has persistent per-purpose hourly budgets (30 registrations, 30 verification resends, 40 resets), with external delivery disabled unless both explicit flags are enabled. The exact-diff review reported two medium availability findings. A broader current-commit source scan reported five residual findings (two medium, three low): distributed PBKDF2 capacity, login lockout, per-address recovery quota exhaustion, unbounded rate-state cardinality, and conditional registration timing inference. Its practical rate-state capacity question is deferred; all findings and owner threshold decisions remain open.
- [ ] Phase 5 — model-router and approval-engine boundaries are hard-disabled in the local app and covered by startup-guard tests. The Money Machine FSM is not connected until its mapping and retention decisions are approved.
- [ ] Phase 6 — proposed scope awaits owner ratification. At baseline `b1bf406e`, the synthetic Catalyx web suite passed (68 tests), the customer/admin Chromium journey passed (1 test), Lychee found zero broken links across 17 checks, and eight local routes scored 100 in Lighthouse accessibility, best practices, and SEO, and 99–100 in performance. Follow-up commit `a8f73a72` adds a legal-draft stylesheet 77.8% smaller than the shared CSS and extends browser accessibility checks to `/privacy` and `/terms`. The updated `/privacy` run has no unused CSS, lower render blocking (159 ms versus 356 ms), and LCP 0.8 s versus 1.06 s; its performance score remains 99. Human screen-reader/WCAG sign-off remains open. Evidence: `docs/catalyx-platform/phase-6-acceptance.md` and the Lighthouse JSON reports under `/Users/dd/Documents/Codex/2026-09-27/i-ll-generate-the-master-execution/outputs/`.
- [ ] Phase 7 — proposed hosting/data architecture; provider, cost, privacy, retention, and mail decisions await owner approval.
- [ ] Phase 8 — proposed isolated staging and restore rehearsal; depends on Phase 7 approval and still requires execution evidence.
- [ ] Phase 9 — proposed controlled release; requires explicit owner release approval and verified rollback evidence.

## Execution evidence (2026-09-28)

- Proposed Phase 6 local acceptance is recorded in
  `/Users/dd/Documents/Codex/2026-09-27/build-me-a-new-website-with/work/catalyx-auditor-rebuild/docs/catalyx-platform/phase-6-acceptance.md`.
  The scope remains a proposal until owner ratification; automated results do
  not close human accessibility or production gates.

- At that checkpoint, implementation branch `codex/catalyx-rebuild-phase1-5` was
  pushed through application commit `a8f73a72`.
  This code lives in
  `/Users/dd/Documents/Codex/2026-09-27/build-me-a-new-website-with/work/catalyx-auditor-rebuild`.
- Historical full local suite at that checkpoint: **259 passed, 5 opt-in browser
  tests skipped, 3 upstream deprecation warnings**. Focused mail/web tests: **98
  passed**; synthetic Catalyx browser journey on `b1bf406e`: **1 passed**.
  Scoped Ruff, diff check, and staged-content Gitleaks passed. The user reports
  that the 24+ hour soak completed in Claude; Codex will not repeat it. The
  tested SHA and run artifacts were not independently inspected.
- UI review files:
  - `/Users/dd/Documents/Codex/2026-09-27/i-ll-generate-the-master-execution/outputs/catalyx-homepage-desktop.png`
  - `/Users/dd/Documents/Codex/2026-09-27/i-ll-generate-the-master-execution/outputs/catalyx-sample-report-desktop.png`
  - `/Users/dd/Documents/Codex/2026-09-27/i-ll-generate-the-master-execution/outputs/catalyx-homepage-mobile.png`
- Safety evidence: no model call, paid inference, external outreach, real SMTP
  delivery, deployment, `.shop` import, or master merge occurred in this slice.
  No `.env` values were loaded or used. Local tests use synthetic data and
  mocked SMTP; production transport and provider settings remain unconfigured.
- Security review: completed Codex Security scan
  `870780cc-2cdc-459d-9c25-47f88682948a`, exact diff
  `9775a3d79cb992c4f85bc915515a90e2ba3593e4..b1bf406e113deee6239ef07e5ad44988ca3ffde3`,
  complete changed-file coverage, two medium availability findings. Report:
  `/Users/dd/.codex/state/plugins/codex-security/scans/catalyx-auditor-rebuild/b1bf406e113deee6239ef07e5ad44988ca3ffde3_20260927T210148Z_6l475v9i/report.md`.
- Broader source review: completed Codex Security scan
  `8639b614-d74d-4358-8aa5-b83efef9d487` reviewed all 14 `catalyx_web` files
  at immutable commit `b1bf406e`. It recorded five findings (two medium,
  three low) and partial coverage because rate-state capacity impact remains
  deferred. Report:
  `/Users/dd/.codex/state/plugins/codex-security/scans/catalyx-auditor-rebuild/b1bf406e113deee6239ef07e5ad44988ca3ffde3_20260927T210448Z_tno1dbmw/report.md`.
- Rate-state capacity evidence: a bounded synthetic benchmark against the
  implementation recorded 10,000 distinct SQLite subjects in 24.13 seconds
  and a 2,428,928-byte database (about 243 bytes per row including schema
  overhead). The disposable `/tmp` database and sidecars were removed. This
  narrows the SQLite sizing question but does not establish production growth,
  PostgreSQL behavior, or a safe hard cap; the finding remains open.
- FSM proposal: `docs/catalyx-platform/money-machine-fsm-mapping-proposal.md`.
  Approval is pending for the authority split, event fields, retention/deletion,
  and `quality_review` versus `released` semantics.
- Other owner gates: review the environment structure and UI/assets; confirm
  account login/email rate limits; privately assess historical secret
  candidates; approve hosting, region, mail, retention, legal, administrator,
  and worker-isolation decisions. The live supervisor ownership issue belongs
  to the canonical Website Auditor runtime, not this Catalyx app worktree.
- Recovery links remain available after a synchronous delivery failure, but a
  successful SMTP handoff does not prove inbox delivery. Each message-purpose
  budget can be exhausted within its hourly window; category isolation ensures
  signup traffic cannot consume reset capacity. The new scan confirms that the
  same-purpose exhaustion can delay legitimate mail for up to an hour. The
  pre-verification login bucket can similarly delay a targeted account's sign-in.
  Rate-table capacity, provider/edge behavior, and the account recovery policy
  need owner and deployment review. The untracked `experiments/` directory was
  preserved and excluded from the commit.
- The `phase1-rebuild` plan worktree is still based on `0c8041da`, not the
  requested implementation base `0348b3f9`. The implementation was therefore
  performed in the separate isolated branch above. This file remains in its
  original importer worktree and records that distinction.

## Latest execution update (2026-09-28)

- Catalyx implementation is pushed on `codex/catalyx-rebuild-phase1-5` through
  `7891c9ae`, based on the requested `0348b3f9`. The code change adds bounded
  cleanup of expired authentication buckets across dormant scopes and a robots
  matcher step budget. The current implementation checkout has only existing
  owner documentation edits and an untracked `experiments/` directory; those
  were preserved and excluded from commits and scans.
- The full toolkit suite passed **264 tests, 5 opt-in browser skips, and 2
  warnings** on the dirty source/test state immediately before the latest code
  commit. After that commit, the Catalyx web module passed **74 tests**; Ruff
  and `git diff --check` passed on the changed source/test files. The full suite
  was not rerun after the robots matcher update. No 24-hour soak was repeated;
  the owner reports completing it in Claude, and its tested SHA/artifacts have
  not been independently inspected.
- The exact-diff security scan `2bbaf29c-6a9c-49d8-a4d5-8709693ceaae` found no
  findings in `catalyx_web/db.py` and `toolkit_tests/test_catalyx_web.py`, with
  partial coverage. It excluded `docs/catalyx-platform/**` and `experiments/**`;
  PostgreSQL execution was deferred. This does not close the earlier broader
  source-review findings or establish production readiness.
- Local gates remain separate from owner/release gates. Owner decisions are
  still needed for the proposed FSM authority/event/retention mapping, shared
  login and recovery thresholds, hosting/region/cost, privacy/legal terms,
  worker isolation, human accessibility review, isolated staging/restore, and
  controlled release. Customer scans, external mail, model inference, and
  deployment remain disabled. No `.env` file or values were needed or read.
- The canonical Website Auditor plan records the implementation and release
  gates in `MASTER_PLAN.yaml`; the latest plan branch is
  `codex/canonical-plan-execution` at `c1f0ee7`. The Website Auditor pipeline
  review branch `codex/review-integration` is a separate change set and is not
  merged into the live runtime branch.


## Latest execution update (2026-09-28, Codex continuation)

- Implementation branch `codex/catalyx-rebuild-phase1-5` is pushed through
  `51b543f8`, based on the requested `0348b3f9` and merged with the canonical
  v32 base. The branch remains separate from `master`; PR #46 is draft.
- Hosted run `36394486651` passed 279 toolkit tests, Ruff, package checks/build,
  Chromium installation, and real Chromium/PDF browser tests. Five opt-in tests
  were skipped and two upstream warnings were reported. At `51b543f8`, Gitleaks
  and pip-audit passed. The Catalyx web suite passed 81 tests, followed by 3
  focused TOTP migration/vector/login regressions after the final compatibility
  edit; the explicit `ssl.PROTOCOL_TLS_CLIENT` regression and Ruff passed locally.
- Sonar CI reaches the bound project but fails because SonarCloud Automatic
  Analysis is enabled concurrently. The job log confirms the service rejects
  simultaneous Automatic and CI-based analysis. The last completed code scan
  predates the explicit TLS client protocol and versioned TOTP digest changes;
  their security effects are not yet confirmed by Sonar. Select one analysis
  mode in project settings before rerunning.
- The earlier source review's shared-login availability finding remains open.
  Production login and scanning stay gated on a verified ingress/client-IP and
  rate-control design. FSM integration, hosting/region/retention/mail decisions,
  accessibility sign-off, isolated staging, backup/restore/rollback, and release
  approval remain open.
- `MASTER_PLAN.yaml` is current through plan commit `e45090ff` on
  `codex/master-plan-pr`; PR #45 remains draft. PR #43 is also draft and
  unmerged. No master merge or deployment occurred.
- The owner reports the 24-hour soak was completed in Claude; it was not rerun.
  Hosted fixtures, Gitleaks and pip-audit passed at `51b543f8`; the Sonar CI job
  failed because Automatic Analysis is enabled concurrently. No `.env` file was
  needed or read. Existing
  uncommitted security notes and the
  untracked `experiments/` directory were preserved and excluded from commits.

### Latest execution update (2026-09-28, hosted customer browser journey)

- Implementation branch `codex/catalyx-rebuild-phase1-5` now points to
  `b0567644`, with commits `1bc25c11` and `b0567644` adding the dedicated
  Catalyx customer/admin browser journey to hosted fixture CI and making the
  accessibility check tolerate Chromium's implicit focus stop on an overflow
  container. The journey also waits for route navigation before inspecting the
  next page.
- The dedicated browser journey passed locally on the same `uv run --no-sync`
  invocation used by CI. Hosted run `36396949329` passed the full toolkit
  fixture job, including the generic browser tests and the Catalyx journey;
  Ruff, package/dependency checks, Gitleaks, and pip-audit passed as well.
- Vercel preview is again rate-limited for 24 hours. Sonar CI remains blocked
  by the project setting that enables Automatic Analysis alongside CI analysis.
  No code-side workaround was applied because it would remove the required
  code scan. PR #46 remains a draft, with no merge or deployment.
- The isolated test uses a temporary SQLite database and local mailbox, binds
  Uvicorn to loopback, and only queues the synthetic `example.invalid` request;
  it does not start a scan worker or contact an external target. No `.env` file
  was needed or read. Existing dirty owner notes and untracked `experiments/`
  remain preserved and excluded from commits.

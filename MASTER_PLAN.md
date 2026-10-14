# WEBSITE-AUDITOR Master Plan v44.0

**Status:** CANONICAL_EXECUTION_PLAN  
**Reviewed:** 8 October 2026 · baseline `b349cd9f` · isolated candidate locally committed and unpublished
**Workspace:** `/Users/dd/WEBSITE-AUDITOR`  
**Mode:** local-first · zero-paid-token · evidence-first · supervised · Obsidian operator workspace  
**Target release:** PR #52 — v44 local-machine convergence

This file is the human-readable canonical companion to `MASTER_PLAN.yaml`. [CURRENT_STATE.md](CURRENT_STATE.md) records current acceptance; [docs/GITHUB_TODO_REGISTER.md](docs/GITHUB_TODO_REGISTER.md) records sourced follow-up work.

## Current work order

PR #52 remains open/draft at b349cd9f, with 13 successful latest GitHub checks. CodeRabbit skipped draft review. SonarCloud identified 39 maintenance suggestions: 33 compound assertions, four exception-assertion scopes and two technology suggestions. The 8 October isolated candidate covers these suggestions, explicit skipped statuses for seven audit stubs, audit-cache coverage guards, unsupported secret listing, quote safety and canonical documentation. Five precommit fixes cover malformed falsey effort bands, invalid JSON CLI errors, screenshot comparisons for valid partial browser captures, stale verification/resolution guards and contradictory rendered/browser coverage metadata. The seven analyzer bodies remain unimplemented; the candidate prevents their no-op results from appearing complete. Agreed CI validation includes package build/import verification. The candidate is implemented and tested locally, committed locally on the isolated branch, unpublished and separate from the authoritative service checkout. Recorded checks include 82 focused tests, 424 portable tests with 45 subtests, six freshly passing Chromium journeys, 29 retained tier-1 tests, scoped Ruff, compilation, pip check, wheel build and both dependency audits. Final canonical regression passed 1,048 tests with three skips and three warnings; the rebuilt wheel passed 17 installed imports, CLI help/local doctor and axe-asset checks. The fresh full Chromium suite passed in 47.98 seconds; all 39 Sonar suggestions were locally reverified against 19 current source hashes; the external bundle records the local commit SHA and retains earlier 1,029/63-test receipts as historical. Missing local llama_cpp/model remains explicit, and no model generation was tested; there is no new hosted candidate Sonar result.

Supervisor, health/log/metrics, rotation, DLQ and Lighthouse/Lychee adapters already exist; remaining exact-head host evidence is not a request to rebuild them. Current b349 runtime acceptance is blocked after an uncached public-network timeout. The accepted e83121b 24-hour soak is historical and does not validate b349 or this candidate. Controller recovery requires exact new authorization and one new uninterrupted window. Independent human labels/holdout, future analyzer implementation, code review and `master` integration remain separately tracked.

Historical secret static assessment is complete: the exit-1 full-history scan produced 87 inputs, all assessed individually with duplicate-looking inputs retained. Disposition is 71 not_actionable, 16 needs_review and 0 confirmed. The 16 comprise 14 captured Maps-key observations, one historical Stripe test-key-shaped example and one WPForms form token; owner/restriction/purpose review remains open. See review-bundle `follow-up/HISTORICAL_SECRET_TRIAGE.md` and `historical-secrets-triage.json`. This is not clearance. No credential values, provider calls, rotation, history rewrite or allow-list expansion are included; any confirmed credential requires exact remediation/rotation authorization.

## Non-negotiables

- Paid model/API usage remains disabled: `paid_allowed=false`, `max_cost_usd=0`.
- No silent paid fallback. When free/local providers are unavailable, defer work.
- Live outreach remains disabled by default.
- Experimental code is reviewed and selectively ported; it never overwrites the live repo.
- Databases/state are backed up before migrations.
- No autonomous direct-to-master edits.
- Every promoted code change requires test evidence.
- One writer per file; coding agents work on isolated branches/worktrees.

## Canonical architecture

`auditor_toolkit` is the canonical audit engine. `./mm` is the canonical operator interface. SQLite plus state files are authoritative for durable state and the leased queue. launchd + `./mm supervisor` own runtime supervision. Hermes orchestrates agents. Obsidian is the human-facing master brain and review workspace, but it is never the runtime database, queue, pricing authority, or send authority.

n8n is **not** part of the default stack. SearXNG is the optional zero-cost discovery service and, when enabled, runs natively as a user-scoped launchd service bound to `127.0.0.1:8888`; Docker is not required.

## Execution phases

1. **P0 Repository reconciliation** — preserve the canonical repo and selectively port only reviewed experimental improvements.
2. **P1 Green baseline** — Python 3.11, one dependency source, full tests, gitleaks, strict dependency audit, clean working tree.
3. **P2 Consolidation** — one audit engine, one operator CLI, archived legacy paths.
4. **P3 Continuous control plane** — leased SQLite queue, PID/single-instance protection, graceful shutdown, heartbeats, stale recovery, retries/backoff/jitter, circuit breakers, DLQ, log rotation, disk/network guards, crash recovery.
5. **P4 Audit engine** — deterministic checks plus efficient HTTP/lightweight/Playwright fetch chain, implemented Lighthouse/Lychee adapters, schema/TLS/mobile checks; record skipped coverage for unimplemented audit stages; future analyzer implementation and real-tool host acceptance are separate.
6. **P5 Evidence-first findings** — evidence before scoring; every score deduction traces to a finding.
7. **P6 NZ discovery** — NZBN, SearXNG, directories, public sites/search/OSM-derived sources, early dedupe.
8. **P7 Identity** — weighted confidence across legal/trading identity, NZBN, domain, website, email domain, region.
9. **P8 Email Finder V2** — provenance-first verification; guessed pattern/MX/catch-all alone never equals verified.
10. **P9 Opportunity scoring** — deterministic commercial score separate from technical weakness.
11. **P10 Remediation engine** — AUTO_SAFE / AUTO_PREVIEW / HUMAN_REVIEW / CLIENT_ACCESS_REQUIRED / UNSUPPORTED.
12. **P11 Demo factory** — tested local improvement + before/after evidence.
13. **P12 Quote engine** — versioned deterministic pricing rules; no price is generated until the operator explicitly supplies an hourly rate.
14. **P13 Prospect packet** — one local reviewable unit per qualified prospect; priced draft material is generated only when an explicit operator rate exists.
15. **P14 Outreach** — evidence-backed drafting and QA; send remains disabled until intentionally enabled.
16. **P15 Free model router** — deterministic first, local/free models second, defer rather than pay.
17. **P16 Agent team** — Hermes plus researcher/coder/operator/judge/proofer/integrator roles with isolated branches.
18. **P17 Observability** — lightweight state/metrics/errors/heartbeats/DLQ before heavier observability stacks.
19. **P18 Self improvement** — challenger branches, shadow evaluation, measured promotion only.

## Obsidian operator workspace

Recommended vault: `WEBSITE-AUDITOR-BRAIN` with:

- `00-DASHBOARD`
- `01-MASTER-PLAN`
- `02-LEADS`
- `03-PROSPECTS`
- `04-AGENTS`
- `05-APPROVALS`
- `06-EXPERIMENTS`
- `07-REPORTS`
- `08-RUNBOOK`

Runtime → Obsidian is automatic/read-mostly. Obsidian → runtime happens only through explicit gated `./mm` commands. Closing Obsidian must never stop the pipeline.

## Final target flow

discover → dedupe → identity → audit → verify → score → select → remediate → demo → screenshot → quote → draft → review → approved action → measure → learn → repeat

## Acceptance

The system is complete only when the exact final revision runs unattended in one independently verified 24+ hour window, survives restart without duplicate work, exposes dead-letter triage, produces evidence-backed findings and contact provenance, creates deterministic demo/quote/draft outputs, keeps paid spend at $0, keeps live outreach disabled by default, and has one canonical repo/auditor/control plane/master plan.

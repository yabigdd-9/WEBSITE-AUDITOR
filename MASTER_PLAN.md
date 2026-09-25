# WEBSITE-AUDITOR Master Plan v32.0

**Status:** CANONICAL_EXECUTION_PLAN  
**Workspace:** `/Users/dd/WEBSITE-AUDITOR`  
**Mode:** local-first · zero-paid-token · evidence-first · supervised · Obsidian operator workspace

This file is the human-readable canonical companion to `MASTER_PLAN.yaml`.

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

n8n is **not** part of the default stack. SearXNG may run as an optional Docker service.

## Execution phases

1. **P0 Repository reconciliation** — preserve the canonical repo and selectively port only reviewed experimental improvements.
2. **P1 Green baseline** — Python 3.11, one dependency source, full tests, gitleaks, strict dependency audit, clean working tree.
3. **P2 Consolidation** — one audit engine, one operator CLI, archived legacy paths (COMPLETED 2026-09-26).
4. **P3 Continuous control plane** — leased SQLite queue, PID/single-instance protection, graceful shutdown, heartbeats, stale recovery, retries/backoff/jitter, circuit breakers, DLQ, log rotation, disk/network guards, crash recovery.
5. **P4 Audit engine** — deterministic checks plus efficient HTTP/lightweight/Playwright fetch chain, Lighthouse, Lychee, schema/TLS/mobile checks.
6. **P5 Evidence-first findings** — evidence before scoring; every score deduction traces to a finding.
7. **P6 NZ discovery** — NZBN, SearXNG, directories, public sites/search/OSM-derived sources, early dedupe.
8. **P7 Identity** — weighted confidence across legal/trading identity, NZBN, domain, website, email domain, region.
9. **P8 Email Finder V2** — provenance-first verification; guessed pattern/MX/catch-all alone never equals verified.
10. **P9 Opportunity scoring** — deterministic commercial score separate from technical weakness.
11. **P10 Remediation engine** — AUTO_SAFE / AUTO_PREVIEW / HUMAN_REVIEW / CLIENT_ACCESS_REQUIRED / UNSUPPORTED.
12. **P11 Demo factory** — tested local improvement + before/after evidence.
13. **P12 Quote engine** — versioned deterministic pricing rules.
14. **P13 Prospect packet** — one complete reviewable unit per qualified prospect.
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

The system is complete only when it runs unattended for 24+ hours, survives restart without duplicate work, exposes dead-letter triage, produces evidence-backed findings and contact provenance, creates deterministic demo/quote/draft outputs, keeps paid spend at $0, keeps live outreach disabled by default, and has one canonical repo/auditor/control plane/master plan.

# WEBSITE-AUDITOR Deep-Dive Upgrade & Execution Plan

**Date:** 2026-09-21  
**Target branch:** `integration/consolidated-2026-09-21`  
**Operating constraint:** zero paid AI/API spend by default; external sending remains disabled until explicit approval gates are complete.

## Execution principles

1. Deterministic code before AI.
2. Evidence before scoring.
3. First-party identity before contact enrichment.
4. `NO_VERIFIED_EMAIL` is a valid terminal result.
5. No paid-provider fallback.
6. Live outreach stays disabled until exact recipient/message/attachment hashes have explicit approval.
7. Long-running workers must be restart-safe, idempotent, observable, and resource-bounded.
8. Runtime data, DB WAL files, caches, credentials, and evidence dumps are never source code.

## P0 — Quality, security and coverage gate

- Canonical Sonar project: `yabigdd-9_website-auditor`.
- Remove pytest failure swallowing.
- Generate `coverage.xml`.
- Analyze core MoneyMachine source; exclude runtime/generated data instead.
- Add bridge/supervisor/workflow security tests.
- Exit: CI green, quality gate materially repaired, no new high/critical security defect.

## P1 — Security automation

Add CodeQL v4 `security-extended`, Dependency Review, Gitleaks v3, OSV-Scanner, Dependabot and generated/runtime exclusions.

## P2 — Browser evidence engine

Playwright Chromium default:
- desktop/mobile full-page screenshots;
- requested/final URL;
- redirect/status/viewport/browser version;
- console errors;
- SHA-256 hashes;
- timestamp and auditor version.

## P3 — Unified technical audit

Add Lighthouse + `@axe-core/playwright` and normalize browser evidence, performance, accessibility, SEO/best-practices and existing auditor findings into one JSON artifact.

## P4 — Discovery V2

`NZBN + self-hosted SearXNG + existing DB + first-party discovery -> identity -> canonical domain -> dedupe -> region -> industry -> audit eligibility`

## P5 — Email Finder V2 enforcement

`identity -> canonical site -> first-party contact evidence -> candidates -> MX/DNS -> company/person match -> provenance -> VERIFIED_HIGH / NO_VERIFIED_EMAIL`

Legacy guessed-email logic becomes hints only.

## P6/P7 — Continuous runtime

Expose `./mm run-pipeline --once|--daemon` plus supervisor start/status/restart/stop/logs. Use launchd, `fcntl.flock`, heartbeat, leases, retry/backoff, stale-worker recovery.

## P8 — n8n hardening

Pin tested n8n version, localhost only, USB runtime, run `n8n audit`, import-test workflows. Never expose send/record-sent/raw SQL/arbitrary shell/Python/suppression deletion.

## P9/P10 — Resource control + local AI

Guard worker/browser concurrency, RAM/disk/USB/queue pressure. Route:
`deterministic -> small local -> larger local -> verified $0 hosted -> retry`.
No paid fallback.

## P11/P12 — Demo + quote engine

Produce before evidence, local improved demo, after evidence and scope. Pricing remains deterministic/versioned; until approved label:
`DRAFT ESTIMATE — NOT A CUSTOMER QUOTE`.

## P13 — Exact-message approval

Approval envelope includes message/business IDs, recipient, subject/body/attachment hashes, approval timestamp, approver and expiry. Any mutation invalidates approval.

## P14 — Observability

Track discovery, audits, screenshots, verified/no-email states, queue/retries, rate limits, worker restarts, disk, USB and cost=$0. Alert on stale heartbeat, missing USB, low disk, DB failure, stuck queue, crash loops, paid endpoint detection, or send endpoint exposure.

## P15 — Controlled transport, last

External transport remains isolated and disabled until all previous gates are satisfied. Global `LIVE_SEND_ENABLED=1` remains prohibited.

## Immediate execution order

1. P0 Sonar/coverage/security repair.
2. P1 security workflows.
3. P2 Playwright evidence engine.
4. P3 Lighthouse + axe unified audit.
5. Re-run CI/Sonar.
6. Merge PR #5 only after acceptable required gates.
7. Tag safe baseline.
8. Continue P4-P14.
9. P15 only after explicit approval.

## Status

- [x] Consolidation branch.
- [x] Continuous-readiness base fixes.
- [x] Fail-closed n8n bridge.
- [x] Main CI green before upgrade pass.
- [ ] P0 quality/coverage repair.
- [ ] P1 security automation.
- [ ] P2 browser evidence.
- [ ] P3 unified technical audit.
- [ ] P4-P14.
- [ ] P15 transport.

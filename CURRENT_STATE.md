# WEBSITE-AUDITOR — Current State

_Last updated: 2026-09-21 · branch `upgrade/v32-canonical-execution` · master plan v32.0_

## Canonical direction

- **Repository:** `/Users/dd/WEBSITE-AUDITOR`
- **Audit engine:** `auditor_toolkit/` with thin `wa` CLI.
- **Operator CLI:** `./mm` → `money-machine/mm`.
- **Runtime state:** SQLite + state files.
- **Queue:** SQLite leased work queue.
- **Supervisor:** launchd + `./mm supervisor`.
- **Agent orchestrator:** Hermes.
- **Human workspace:** Obsidian.
- **n8n:** not part of the default runtime.
- **Cost policy:** `paid_allowed=false`, `max_cost_usd=0`.
- **Outreach:** disabled by default.

## v32 execution status

| Phase | Status | Current evidence / next gate |
| --- | --- | --- |
| P0 Repository reconciliation | ✅ Established | Canonical repo preserved; experimental sources remain selective-port only. Current execution branch created from merged `master`. |
| P1 Reproducible baseline | ◐ Revalidate | Python target is 3.11; blocking gitleaks + strict pip-audit exist; .gitignore is hardened. Recent agency/release/browser suites passed before v32 adoption. Full regression + local `./mm doctor` still needs a fresh v32 run. |
| P2 Consolidation | ◐ Partial | Canonical audit path and operator CLI are documented. Legacy/archive sweep remains. |
| P3 Continuous control plane | ✅ Implemented | Supervisor package, PID/single-instance, daemon, metrics/log helpers and crash/recovery tests are present. Host launchd continuity still needs current-machine verification. |
| P4 Audit engine | ◐ Partial | Deterministic hygiene/fetch work exists. Lighthouse, Lychee and remaining checks still pending. |
| P5 Evidence-first findings | ✅ Implemented | Scores derive from finding/evidence records. |
| P6 NZ discovery | ⬜ Pending | Multi-source discovery/dedupe implementation remains to be integrated into canonical path. |
| P7 Identity | ◐ Partial | Canonical domain support exists; NZBN + weighted confidence still pending. |
| P8 Email Finder V2 | ◐ Partial | Provenance/verification work exists; canonical end-to-end eligibility path still needs final consolidation. |
| P9 Opportunity scoring | ✅ Implemented | Deterministic commercial scoring exists separately from audit weakness. |
| P10 Remediation | ⬜ Pending | Classification + real implementation artifacts required. |
| P11 Demo factory | ⬜ Pending | Before/after evidence pipeline required. |
| P12 Quote engine | ◐ Partial | Revenue/quote helpers exist, but canonical versioned quote rules need finalization. |
| P13 Prospect packet | ⬜ Pending | Complete reviewable packet pipeline required. |
| P14 Outreach | ◐ Draft-only | Draft/review logic exists. External sending must remain disabled by default. |
| P15 Free model router | ◐ Partial | Free/local-only policy exists; runtime routing needs final canonicalization and provider verification. |
| P16 Agent team | ◐ Partial | Hermes direction exists; role/worktree enforcement needs operational wiring. |
| P17 Observability | ◐ Partial | Supervisor logging/metrics exist; canonical health/metrics/errors/DLQ views need consolidation. |
| P18 Self-improvement | ⬜ Pending | Golden dataset + challenger/shadow promotion loop required. |
| Obsidian operator workspace | ▶ In progress | v32 makes Obsidian the human-facing read-mostly workspace; it must never become canonical runtime state. |

## Security and safety gates currently in force

- No paid fallback.
- No live outreach by default.
- No plain Markdown checkbox can authorize send/deploy/high-risk actions.
- No direct autonomous edits to `master`.
- Secrets and runtime databases are ignored from Git.
- Gitleaks and strict pip-audit are blocking CI jobs.
- Experimental n8n work is not part of the default runtime.

## Immediate execution queue

1. Adopt v32 canonical plan files.
2. Create Obsidian vault skeleton and read-mostly sync/status tooling.
3. Fresh Python 3.11 full regression + `./mm doctor`.
4. Reconcile/retire stale plan branches and archive old planning docs.
5. Finish P4/P6/P7/P8 in that order before remediation/demo/quote/packet work.
6. Keep send disabled while P14 is developed.

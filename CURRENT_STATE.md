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

| Phase | Status | Current evidence / remaining acceptance |
| --- | --- | --- |
| P0 Repository reconciliation | ✅ Implemented | Canonical repo preserved; v32 branch/PR isolates reviewed changes from master. |
| P1 Reproducible baseline | ▶ Revalidating latest head | Python 3.11, compile-all, toolkit + portable MoneyMachine CI, gitleaks and strict third-party dependency audit are wired. Latest CI is rerunning; local `./mm doctor` and clean host validation remain. |
| P2 Consolidation | ◐ Canonical path established | `auditor_toolkit` + `wa` and `./mm` are canonical. Root alias symlinks, tracked venv alias and stale DeepSeek gitlink are removed. Deprecated compatibility scripts remain until downstream callers are migrated/archived safely. |
| P3 Continuous control plane | ✅ Implemented in code | Leased queue, PID/single-instance, shutdown, heartbeats, lease recovery, retries/backoff, circuit-breakers, DLQ, log rotation and new disk/network guards are present. launchd restart/host continuity still needs current-Mac validation and 24h soak. |
| P4 Audit engine | ✅ Implemented in code | Deterministic hygiene/security/robots/sitemap/contact/schema checks plus optional local Lighthouse/Lychee. Installed-tool execution and latest real-browser run remain host gates. |
| P5 Evidence-first findings | ✅ Implemented | Scores derive from finding/evidence records and deductions link back to findings. |
| P6 NZ discovery | ✅ Implemented in code | Local import + loopback SearXNG, early dedupe, NZBN/OSM-style export adapters and source provenance. Live/source-specific acquisition remains operator-configured. |
| P7 Identity | ✅ Implemented | Weighted deterministic NZBN/name/domain/email-domain/region/address/phone evidence; conflicts lower confidence and weak single-signal matches cannot grant high confidence. |
| P8 Email Finder V2 | ✅ Implemented in code | Provenance-first verification, catch-all/pattern fail-closed behavior, canonical paths, TLS-verified/checksummed disposable-list refresh and clean-checkout tests. |
| P9 Opportunity scoring | ✅ Implemented | Deterministic commercial scoring remains separate from audit weakness. |
| P10 Remediation | ✅ Implemented | Deterministic remediation classes create reviewable preview artifacts; production changes remain zero. |
| P11 Demo factory | ✅ Implemented | Local concept demo + render path explicitly records `CONCEPT_ONLY`, `live_site_changed=false`, and never claims measured improvement. |
| P12 Quote engine | ✅ Implemented | Versioned deterministic NZD effort/rate rules; LLM cannot determine price. |
| P13 Prospect packet | ✅ Implemented | Hashed audit/remediation/demo/quote packet, exact draft, human-review state, send disabled. |
| P14 Outreach | ✅ Draft/QA boundary implemented | Legacy transports are fail-closed; old SMTP generator retired; canonical transport config/provider is `none`, daily cap 0 and network-send implementation absent. Live sending intentionally remains disabled. |
| P15 Free model router | ✅ Implemented in code | Local-first, verified-free external routes only with explicit opt-in, `:free` enforcement, zero-cost ledger, DEFER fallback, and external data collection default `deny`. Provider availability is inherently time-sensitive. |
| P16 Agent team | ✅ Policy implemented | Machine-readable roles, isolated branch/worktree rule, one writer per path, Integrator-only merge authority, no direct master writes. Host/Hermes operational enforcement remains an acceptance check. |
| P17 Observability | ✅ Implemented | `./mm health|metrics|errors|queue|dead-letter`; state snapshots include health, metrics/errors JSONL, DLQ and worker heartbeat files without DB mutation. |
| P18 Self-improvement | ✅ Evaluation loop implemented | Synthetic golden dataset + baseline/challenger comparison can recommend promotion only after measurable no-regression improvement; cannot merge or modify production. |
| Outcome tracking | ✅ Implemented | Evidence-backed append-only outcomes support measured learning; no automatic prompt/price/code changes. |
| Obsidian operator workspace | ✅ Implemented in code | Read-mostly runtime → Obsidian sync/status; Obsidian remains non-authoritative and cannot authorize send/deploy/high-risk actions. |

### Remaining acceptance gates

The implementation is not release-complete until the latest branch checks are green and host-only evidence is captured for: `./mm doctor`, actual launchd/supervisor restart recovery, real Chromium regression on the latest head, installed Lighthouse/Lychee execution when requested, local SearXNG integration when used, Obsidian sync against the actual vault, and a 24+ hour unattended run with no duplicate restart work and visible DLQ triage.

## Security and safety gates currently in force

- No paid fallback.
- No live outreach by default.
- No plain Markdown checkbox can authorize send/deploy/high-risk actions.
- No direct autonomous edits to `master`.
- Secrets and runtime databases are ignored from Git.
- Gitleaks and strict pip-audit are blocking CI jobs.
- Experimental n8n work is not part of the default runtime.

## Immediate execution queue

1. Get the latest v32 branch CI/security/Sonar checks green.
2. Run the current-head local acceptance bundle: `./mm doctor`, Chromium E2E, optional Lighthouse/Lychee, supervisor restart/crash recovery and Obsidian sync.
3. Reconcile remaining deprecated compatibility callers before archiving old auditor scripts.
4. Exercise optional local SearXNG discovery when that service is enabled.
5. Run and record the 24+ hour unattended soak with zero duplicate restart work, DLQ visibility, $0 model spend and zero external sends.
6. Keep PR #36 draft until all blocking automated gates are green; keep live outreach disabled.

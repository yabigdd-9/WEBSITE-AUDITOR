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
| P1 Reproducible baseline | ✅ Executed & gated | Python 3.11, compile-all, toolkit + portable MoneyMachine CI, gitleaks and dependency audit wired. Sandbox suite gate: 280 passed / 22 skipped / 77 subtests (explicit typed skips); host re-run remains. |
| P2 Consolidation | ◐ Canonical path established | `auditor_toolkit` + `wa` and `./mm` are canonical. Root alias symlinks, tracked venv alias and stale DeepSeek gitlink are removed. Deprecated compatibility scripts remain until downstream callers are migrated/archived safely. |
| P3 Continuous control plane | ✅ Implemented & recovery-gated | Leased queue, PID/single-instance, shutdown, heartbeats, lease recovery, retries/backoff, circuit-breakers, DLQ, log rotation, multi-probe network guard. **kill -9 recovery verified on this Mac** (cron ensure-running: PID 26743→83670 ≤5 min, no duplicates). launchd remains optional; 24h soak still required. |
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
| P17 Observability | ✅ Implemented | `./mm health|metrics|errors|queue|dead-letter|alerts|report daily|rotate-logs`; state snapshots without DB mutation; typed alert rules in `state/alert-rules.yaml` surfaced in health; daily report with safety attestation. |
| P18 Self-improvement | ✅ Evaluation loop implemented | Synthetic golden dataset + baseline/challenger comparison can recommend promotion only after measurable no-regression improvement; cannot merge or modify production. |
| Outcome tracking | ✅ Implemented | Evidence-backed append-only outcomes support measured learning; no automatic prompt/price/code changes. |
| Obsidian operator workspace | ✅ Implemented in code | Read-mostly runtime → Obsidian sync/status; Obsidian remains non-authoritative and cannot authorize send/deploy/high-risk actions. |

### What needs doing now (v32 closeout — updated 2026-09-22, FABLE P0–P8 executed)

All agent-executable workpaths (P0–P8) are committed and gated on `upgrade/v32-canonical-execution` (see `reports/fable/` and the before/after table below). What remains is **human-gated**, in order:

**Step 1 — Publish (operator, ~5 min)**
1. `git push origin upgrade/v32-canonical-execution`
2. Post `reports/fable/PR36_ADDENDUM_DRAFT.md` as a PR #36 comment (`gh pr comment 36 --body-file ...` or paste).

**Step 2 — Host acceptance evidence (operator; sandbox blocked items)**
3. Re-run the suite + `./mm doctor` on the host with full network; capture outputs into a host-evidence report.
4. Real Chromium E2E on latest head; Lighthouse/Lychee if installed; Obsidian sync against the actual vault.
5. Install/run SearXNG (127.0.0.1:8888) and re-run `./mm discover-search` + discovery suite to clear the `BLOCKED_SEARCH_*` typed skips.

**Step 3 — Release gate (operator, unattended)**
6. 24+ hour soak: cron ensure-running line active, zero duplicate restart work, DLQ visibility, $0 paid spend, zero external sends. Evidence: `state/ensure-running.log`, `./mm health` over time, first daily reports.
7. Optional: launchd restart validation (cron ensure-running is the verified path; launchd is not required).

**Step 4 — Merge & release**
8. Update PR #36 with host evidence + soak results → remove draft → Integrator-only merge (never merge on "mergeable" alone).
9. Post-merge: delete or repair the stray untracked `money-machine/test_pipeline_errors.py` under its own workpath; migrate/archive the deprecated compatibility scripts noted in P2 Consolidation.

**Then (v33+ candidates, agent workpaths under human approval)**
- Host SearXNG-backed discovery runs feeding real prospect acquisition (operator-configured sources).
- Pipeline audit worker pass over the remaining DISCOVERED rows queued in P5.
- First real customer-facing cycle only after: operator approval per prospect, quote sign-off, and per the iron rules (send path stays fail-closed until explicitly enabled by the operator).

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

---

# v32 Canonical Execution — Before/After (FABLE, 2026-09-22)

| Metric | Baseline (§1 of master plan, 2026-09-22) | After P0–P8 |
|---|---|---|
| Real prospects | 39 (incl. later-quarantined fixtures) | 21 (12 fixtures quarantined, none deleted) |
| Prospects with zero evidence | 25 | 1 (typed skip: no public_website) — 95.2% coverage (gate ≥85%) |
| Dead-letter queue | 12 (all test fixtures, root-caused) | 0 — dispositioned `test_fixture`, quarantined not deleted |
| Retryable failures | 12 | 0 |
| Supervisor continuity | single instance, no self-recovery | kill -9 → cron re-spawn ≤5 min, no duplicate workers (proven) |
| Network guard | degraded rows flooding (2 rows/5 min) | multi-probe, TTL-deduped (≤1 row/hour), health `network.mode` |
| Test suite | errors from environment noise | explicit `BLOCKED_FIXTURE` skips; 405 passed / 22 skipped gate; P5 +9, P6 +8 all green |
| Reporting | none | `mm report daily` w/ safety attestation + funnel delta; `mm metrics` funnel_stages |
| Alerting | none | typed rules in `state/alert-rules.yaml` surfaced in `mm health` alerts array |
| Send safety | fail-closed (unproven) | fail-closed with negative-proof test (transport cap 0, provider none, tamper rejected) |
| Docs | scattered plans | `docs/RUNBOOK.md` (DLQ tree, quarantine, supervisor/cron, capabilities, backup) |

Human review remains REQUIRED everywhere; `outreach_eligible` flips only via the existing approval path.

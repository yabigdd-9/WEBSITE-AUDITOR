---
title: "WEBSITE-AUDITOR — Implementation Plan"
date: "2026-09-21"
derived_from: "UPGRADE_RESEARCH_2026.md (v2.0.0) + UPGRADE_RESEARCH_2026.yaml"
goal: "Take the pipeline from BLOCKED_RUNTIME to supervised, unattended, $0/day operation"
---

# IMPLEMENTATION PLAN

## Guiding rule
Nothing else matters until **Phase 0 makes the engine runnable**. Every later
phase assumes the previous phase's acceptance check passes.

## Phase 0 — Make it run (Week 1) — unblocks everything
| # | Task | Detail | Check |
|---|------|--------|-------|
| 0.1 | Install Colima + Docker | `brew install colima docker docker-compose && colima start` | `docker run hello-world` works |
| 0.2 | Root `compose.yaml` | `app` (python:3.12-slim + repo), `worker` (same image, scale=N), `scheduler`; `restart: unless-stopped`; healthchecks; localhost-bound ports | `docker compose up -d && docker compose ps` all healthy |
| 0.3 | Fix the broken venv path | Remove `money-machine/.venv-email` symlink; email deps into the container image | `./mm doctor` → no BLOCKED_RUNTIME |
| 0.4 | Delete hazardous symlinks | `config`, `control-plane`, `migrations`, `scripts`, `tests` aliases | `pytest` discovers the real tests |
| 0.5 | Secrets hygiene | Rotate the two leaked keys; `gitleaks` in CI; mount `.env` only into app | `gitleaks detect` clean; keys not in git history |
| 0.6 | Config safety | `data_collection: deny` in `config/routing.yaml`; add `FREE_TIER_ALLOWLIST` | Router refuses non-allowlisted remote routes |

## Phase 1 — AI runtime + failover (Week 2)
| # | Task | Detail | Check |
|---|------|--------|-------|
| 1.1 | Ollama service | Add to compose, named model volume; pull `qwen3:8b`, `qwen2.5-coder:7b`, `qwen3-vl:8b`, `qwen3-embedding:0.6b` | `ollama list` shows 4 models; healthcheck green |
| 1.2 | Replace Llama-2 pin | `auditor_toolkit/ai.py` → role-routed model IDs from routing.yaml | AI smoke test returns JSON from qwen3:8b |
| 1.3 | Remote failover routes | Add Groq + Gemini + CF Workers AI to `PURPOSE_ROUTES`; provider-health-scored router; quota ledger in `rate_buckets` | Kill Ollama → fails over to Groq; restore → returns local |
| 1.4 | No-silent-paid guard | Extend `PaidRouteRefused`/`BlockedCost` across new providers | Forcing a paid route raises, never silently spends |


## Phase 2 — Audit engine upgrade (Weeks 3–4)
| # | Task | Detail | Check |
|---|------|--------|-------|
| 2.1 | Unlighthouse | Node 22.18+ container; full-site per audit; store CWV in findings | Audit JSON has performance/LCP/CLS with evidence |
| 2.2 | axe-core | `@axe-core/cli` in audit fan-out; map violations to findings registry | WCAG violations appear with check_version |
| 2.3 | lychee | Broken-link verification replaces regex scan | Findings list only verified-broken URLs |
| 2.4 | testssl.sh (passive) | TLS grade as a finding; passive only | TLS grade stored; no active exploitation |
| 2.5 | Concurrency fix | Audit workers ×4; engines in-process (drop per-site `subprocess.run`); lease ≥ p99 of audit | 4 sites audit in parallel; no lease-expiry double-runs |
| 2.6 | Vision critique | qwen3-vl:8b on full-page screenshots; prompt-injection isolation | Design-critique finding with screenshot artifact |

## Phase 3 — Identity, contact, verification (Weeks 5–6)
| # | Task | Detail | Check |
|---|------|--------|-------|
| 3.1 | NZBN backbone | Bulk extract → SQLite; watchlist change-events | Businesses table keyed by NZBN |
| 3.2 | Real identity_handler | Redirect chain → registrable domain (PSL) → NZBN cross-check | Canonical domain, not bare host |
| 3.3 | Splink dedup | Entity resolution on SQLite/DuckDB; `canonical_entity_id` | Duplicates merge; no false merges on golden set |
| 3.4 | Verify consensus | 4 independent signals; check-if-email-exists isolated AGPL container; no port-25 reliance | No address verified on a single weak signal |
| 3.5 | Disposable list refresh | Versioned refreshable pipeline; catch-all first-class | List has source+version+date |

## Phase 4 — Reporting + workflow (Weeks 7–8)
| # | Task | Detail | Check |
|---|------|--------|-------|
| 4.1 | Gotenberg | PDF/proposals, URL screenshots, PDF/UA | Proposal PDF generated from audit data |
| 4.2 | Screenshot diffing | odiff/pixelmatch before/after | Quantified diff artifact in before/after report |
| 4.3 | Gatus | Health checks + status page; watchdog push heartbeats | Status page green; alert fires on killed container |
| 4.4 | Backups | SQLite WAL + continuous file replica + nightly snapshot job | `docker compose down && up` loses no data |
| 4.5 | Dead-letter triage CLI | Surface RETRYABLE/PERMANENT_FAILURE; replay command | `mm deadletter list/replay` works |

## Phase 5 — Self-improvement + compliance (Weeks 9–10)
| # | Task | Detail | Check |
|---|------|--------|-------|
| 5.1 | Golden dataset | 8–20 hand-verified cases; immutable, versioned | Dataset committed with checksum |
| 5.2 | promptfoo harness | Defect precision/recall, severity accuracy, draft quality metrics | Eval runs in CI; regression fails the build |
| 5.3 | GEPA prompt optimisation | Optimise outreach/fix prompts against local/free models | Measured win-rate before/after |
| 5.4 | Outcome feedback | Replies → per-template/per-model success rates → monthly rubric update | Success-rate table populated |
| 5.5 | NZ legal layer | UEMA 2007 permission basis, truthful sender identity, unsubscribe, suppression enforcement | Compliance checklist passes; suppression blocks send |
| 5.6 | Vector retrieval (P2) | sqlite-vec + local embeddings | Similarity search returns known leads |

## Scheduling & concurrency rules (apply from Phase 2 on)
- Cron: discover 6h · audit 1h · verify 15m · follow-up 1h · health 5m · eval daily.
- 4–8 deterministic workers, ~1 req/2 s per domain, budgets in `rate_buckets`.
- 1 local LLM lane + 2 remote free lanes; judge/proofer serialised at temp 0.
- Backpressure: if audit queue > N, pause discovery.
- Idempotency keys per (business_id, stage, input_hash).

## Dependencies
0 → 1 → 2 → 3 → 4 → 5 strictly for the gates. Within Phase 2, tasks 2.1–2.4
and 2.6 are parallelisable; 4.1–4.4 parallelisable; 5.1–5.2 can start early
(they only need fixture data).

## What is explicitly NOT in this plan
Celery/Redis/Postgres migration · CRM replacement (Twenty/Espo) · Qdrant ·
paid AI routes · active security scanning of third-party sites · autonomous
sending without the per-message human gate.

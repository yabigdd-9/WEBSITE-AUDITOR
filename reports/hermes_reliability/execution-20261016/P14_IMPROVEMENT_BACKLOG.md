# P14 bounded improvement backlog — 16 October 2026

Status: candidate fixes implemented and independently tested; autonomous production self-modification is disabled. Existing supervisor, queue, router, scheduler and Obsidian integration are extended rather than replaced. No n8n or new paid service was introduced.

| Priority | Concrete work | Acceptance evidence / gate |
| --- | --- | --- |
| P0 | Shared atomic financial admission covering global Hermes, direct FCC bridge and every fallback | Authoritative route entitlement, reset/quota telemetry, concurrent reservation and release, unknown-cost refusal before dispatch; current response-cost latch is insufficient |
| P0 | Reconcile FCC startup/catalog/primary routing and remove invalid model aliases | Repeated bounded metadata probes plus supported free end-to-end request only after verified entitlement; retain fallback and authentication |
| P0 | Triage redacted historical secret-scan candidates and finish coverage | Confirm actual exposure without printing values; current last-100-commit scan is clean, full-history scan is incomplete |
| P0 | Reconcile exact-revision staging soak execution and release duration criteria | Tracked consumer for YAML configs, loaded-code attestation, monotonic duration, heartbeat/resource/DB/queue summaries; 24h/72h separately authorised and historical 168h criterion reconciled |
| P0 | Production worker approvals and exact source promotion | Candidate hosted checks, mandatory acceptance, independent sign-off, backup/restore and rollback; resume affected jobs individually only after gates |
| P1 | Standalone canonical-worker entrypoint ownership | Runner lock protects scheduled paths; direct worker invocations must share the same ownership protocol |
| P1 | Preserve staging progress across fresh snapshots and bound backup operations | Durable job cursor, explicit staging generation, restart/concurrency tests and deadline-aware SQLite backup |
| P1 | Complete distinct global, DB, send, AI and scheduler kill switches | Independent fault injection proving each control and safe restart without duplicate work |
| P1, candidate implemented | Promote tested daily pytest case counts and local reporting date | JUnit-derived passed/failed/skipped per run, explicit unknown legacy records and Pacific/Auckland day boundary regressions now pass; deployment remains gated |
| P1, candidate implemented | Promote tested exhausted-retry alert and funnel mapping | Both queries use actual RETRYABLE_FAILURE/PERMANENT_FAILURE states; growth/funnel regressions pass; deployment remains gated |
| P1 | Outreach release package | Exact sender/recipients/messages, eligibility evidence, unsubscribe/suppression controls, OAuth release proof, canary and per-day cap; no batch approved now |
| P2 | Confirm Obsidian reporting destination | Existing registered vault differs from default repository brain; source-backed report export with collision/retention and secret checks |
| P2 | Refresh opportunity evidence and independently judge commercial claims | Use existing 400-business inventory before more discovery; retain 1000-to-100-to-10-to-3 prioritisation without inventing validated demand |
| P2 | Optional local-model fallback | Installed supported runtime/model, resource/capability test and independent quality checks before critical use |

Improvement lifecycle: detect from retained failures/queue evidence; propose a bounded isolated patch; run focused regression, security and financial checks; obtain independent review; publish a reviewable candidate; promote only when its release gates pass. Measure defect recurrence, duplicate jobs, verified evidence coverage, successful worker completion and incident-free recovery. No agent may approve its own production rollout or rewrite previous evidence.

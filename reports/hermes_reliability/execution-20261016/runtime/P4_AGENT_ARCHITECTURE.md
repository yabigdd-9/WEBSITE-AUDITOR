# P4 Agent architecture — 16 October 2026

Status: **BLOCKED** for complete production acceptance; existing deterministic coordination is useful and retained.

Evidence: `runtime_inventory.json`, `scoped_runtime_tests.json`, `database_recovery_receipt.json`; current source `money-machine/mm_pipeline.py`, `money-machine/mm_workers.py`, `money-machine/mm_brain.py`, `ops/hermes_zero_token/runner.py`. This is local source and fixture evidence, not a new production deployment.

| Logical role | Existing implementation | Verified limit |
| --- | --- | --- |
| Master orchestrator | supervisor CLI, pipeline queue, mm_brain recommendations | Live PID 66896 has a heartbeat; loaded source revision remains unproved. |
| Executor A | identity/audit/contact handlers; screenshot worker | Pipeline data writes and public requests require the relevant release workflow. |
| Executor B | understanding/preparation workers; demo_blueprint | Templates are review-only; absent demo artifacts route to NEEDS_REVIEW. |
| Researcher | discovery quality/intelligence adapters | Standalone competitor_research still returns exit 3; no independent research completion claimed. |
| Independent judge | qualification, approval and evidence checks | Deterministic checks exist; presence of a scoring function does not prove independent review of every result. |
| Proofreader / QA | demo QA, outreach copy auditing, approval gates | Source contains checks; client-facing quality acceptance remains gated. |
| Safety/cost/recovery supervisor | runtime guards, safe mode, leases/retries/circuit breakers, transport policy | Zero-token worker policy is separate from a verified shared allowance ledger for hosted models. |

PASS: pipeline jobs have durable state and append-only events, conditional lease updates, owner-qualified release, bounded retry counters, backoff and failure isolation. Fresh synthetic suites passed: pipeline recovery 5, discovery recovery 17, reporting 8, brain 6; total 36, no failures or skips in these runs. These include sequential ownership exclusion and expiry recovery; they do not establish arbitrary multi-process or reboot correctness.

The live 09ab41ab runner has no shared artifact lock or total deadline for in-process canonical workers. The parent's focused repair exists only under `/Users/dd/Documents/Codex/2026-10-16/hi-2/work/release-candidate`: bounded process groups, shared artifact lock and fail-closed output validation. The authoritative tracked source was restored to its original revision so a scheduled worker cannot silently load an unaccepted patch. Acceptance of the isolated candidate belongs to the parent test and independent verification receipts; no candidate runtime promotion is implied.

BLOCKED: seven roles are not seven independently accepted workers; research remains incomplete, current loaded runtime revision is unknown, hosted allowance enforcement needs P3 evidence, and 24/72-hour staging acceptance has not been completed. No additional orchestration framework or permanently billed agents were introduced.

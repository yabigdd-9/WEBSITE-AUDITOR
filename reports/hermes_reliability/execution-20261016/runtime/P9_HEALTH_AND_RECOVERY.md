# P9 Health and recovery — 16 October 2026

Status: **PASS** for scoped safety containment; **BLOCKED** for unattended production acceptance.

Evidence: `runtime_inventory.json`, `scoped_runtime_tests.json`, `scheduler_pause_receipt.json`, `scheduler_artifact_pause_receipt.json`, `staging_db_schedule_candidate.yaml`, source `money-machine/supervisor/*`, `money-machine/mm_pipeline.py`, `money-machine/mm_reporting.py`, `ops/hermes_zero_token/runner.py`.

Existing operation: supervisor PID 66896 runs under UID 501 with a fresh running heartbeat. Its launchd definition uses KeepAlive, RunAtLoad and ThrottleInterval=10, a 5-second supervisor loop and MM_EXTERNAL_SEND_DISABLED=1. The only inspected runtime-startup receipt is for PID 89903 at revision 7a6a4d50..., dated 14 October. It cannot establish what current PID 66896 loaded or attest current candidate HEAD. No supervisor/FCC service start, restart or crash injection was performed.

Scheduler baseline: 17 enabled no-agent ZA jobs in the existing Hermes scheduler; no six-hour staging_db job. Existing database_guard/testing jobs already run every 360 minutes and are distinct from staging_db validation. Four unsupported mutating jobs repeatedly returned errors (dispatcher streak 49, identity 12, site auditor 8, discovery 12); competitor research was also unimplemented (streak 4) and weekly review was an enabled placeholder.

The authorised recovery action used the supported `hermes cron pause` API for six unsupported jobs and three affected artifact jobs, with a private 0600 jobs.json snapshot before each group. Both pause receipts PASS: all 17 identities were preserved, exactly the requested jobs changed only enabled/state/paused_at fields, and other configurations were unchanged. Nine are paused and eight remain enabled. Final comparison also observed ordinary runtime progress of the unaffected system-supervisor job: its successful-run count advanced 196 to197 with dispatch timestamps/next-run updates, while configuration stayed unchanged (`final_runtime_validation.json`). The extra artifact jobs retain the original live09ab runner's missing ownership guard and the outreach metadata-loss defect; their isolated candidate repair is not deployed. No job was deleted or activated. Resume uses the exact ID only after resolving its worker gate; never restore the entire live jobs.json from an old snapshot. A recurring resume can catch up a missed occurrence, so resumption must include a due-job review.

| Paused target | Exact job ID |
| --- | --- |
| queue_dispatcher | 11980f4aabec |
| identity_resolution | 3e757e476ace |
| site_auditor | 4a2b4017c296 |
| discover_nz_businesses | cd28c5527987 |
| competitor_research | 9cc96a795bc6 |
| weekly_review | b7962fff0f6a |
| screenshot_worker | 50c7e7837ab2 |
| demo_blueprint | 22bf57b29534 |
| outreach_draft | 762f1b3a355e |

PASS: five synthetic pipeline tests cover ownership exclusion, lease expiry/drain/reclaim, retry bounds/backoff, failure isolation and stale holder recovery. Seventeen discovery recovery tests preserve history and hold ambiguous identities. Eight reporting tests cover heartbeat/disk rules and retention. These are fixture-level results, not a host reboot or 24-hour operational proof.

The parent owns an isolated runner process-group deadline/shared-lock repair and its independent test receipt. Live tracked source remains unchanged; the candidate was not silently loaded by active schedules. Safe mode, no-send policy and the zero-token kill switch exist, but the zero-token kill switch covers this runner rather than every Hermes command. Separate independently accepted global-Hermes, DB-mutation, outreach, AI and scheduler emergency controls remain incomplete. Missing or malformed safe-mode reads must also be reviewed for fail-open behavior.

PASS: post-containment `hermes cron doctor` returned exit0 and no issues for the eight active jobs (`scheduler_doctor_after.txt`). The installed Hermes parser resolves `every 6h` to interval360minutes, matching the inactive candidate; the candidate is disabled/no_agent and no staging job exists (`staging_schedule_validation.json`). Parsing/configuration validation does not execute a worker or install a schedule.

NOT TESTED: live crash/reboot recovery, sleep/power interruption, sustained resource behavior, shared provider quota under concurrency and provider-backed billing. A source observability limitation remains: mm_reporting queries pipeline state DEAD_LETTER while the queue uses RETRYABLE_FAILURE/PERMANENT_FAILURE; exhausted-retry counts need correction before treating the alert as complete. The inactive six-hour candidate is prepared, not installed. Long staging soaks remain separate gates.

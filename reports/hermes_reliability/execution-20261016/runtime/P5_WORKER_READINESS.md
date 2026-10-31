# P5 Worker readiness — 16 October 2026

Status: **BLOCKED** for production release of all candidates.

| Canonical worker | Registration and contract | Persisted outputs / remaining release boundary |
| --- | --- | --- |
| staging_db | Registered; integer exit + JSON report; SQLite online snapshot; schema/integrity/FK validation; bounded audit subprocess | Recreates a dedicated staging DB. Snapshot replacement needs shared ownership. Its bounded batch can make public website requests. No production promotion performed. |
| screenshot_worker | Registered; read-only primary DB selection; browser subprocess timeout 90 seconds; hashed PNG manifest | Live capture reuse only checks PNG existence. The isolated candidate now separates URL data from Python code, validates cached URL/hash identity, requires successful child rc/report and returns failure for failed captures. Freshness and direct-entry ownership still require release policy. |
| demo_blueprint | Registered; read-only audit selection; JSON report and review-only Markdown | Produces a proposal template, not a deployed demonstration. Repeated time-tagged files are not a business-level idempotency proof. |
| outreach_draft | Registered; read-only evidence selection; integer exit + JSON; no send implementation | Live source duplicates approval items and drops owner metadata. Parent prepared an isolated queue-preservation/deduplication/lock repair; that candidate is not deployed. |

The isolated parent candidate changes canonical dispatch from an in-process `main()` to a bounded subprocess group and adds shared artifact ownership. Malformed JSON, nonzero status, reported production writes and timeout remain failures. It lives under `/Users/dd/Documents/Codex/2026-10-16/hi-2/work/release-candidate`; live authoritative source remains 09ab41ab. Review the final parent test receipt for acceptance of the candidate runner. Existing screenshot, demo and outreach schedules were paused pending accepted deployment because live artifact ownership and queue-preservation protections remain defective.

FAIL (live source): `outreach_idempotency_live_probe.json` records two synthetic runs, both exit 0 despite duplicate IDs and lost owner metadata. PASS (isolated candidate): `outreach_idempotency_candidate_probe.json` repeats the same probe and retains the owner's item/metadata with one new unique item and no send. Each records exact source path/SHA. No production approval queue was altered by these probes. PASS: `scoped_runtime_tests.json` contains 36 isolated pipeline/recovery/reporting/brain tests.

PASS (source): deprecated *_real aliases fail closed with exit 3. `handle_worker` blocks discovery-cycle, discover-batch, daily, queue_dispatcher, identity_resolution, site_auditor and discover_nz_businesses before dispatch. These protections were retained. Direct low-level helper functions are not an equivalent approved scheduling API.

BLOCKED: full canonical live contract suite reads the actual primary DB and may capture websites or modify local approval artifacts; it was not invoked indiscriminately as a fixture test. New production dispatch, source-to-staging promotion, process-crash injection against active services, reboot recovery and long-duration acceptance remain NOT TESTED here. Per-business freshness and repeated demo generation still need explicit policy.

Pipeline source supports expiring claims, owner checks, backoff and bounded retries. Synthetic coverage proves fixture behavior, not current production throughput. The primary snapshot contains 370 pipeline entries (327 REJECTED, 31 NEEDS_REVIEW, 12 SUPPRESSED), no outstanding leases, and no active pending discovery queue.

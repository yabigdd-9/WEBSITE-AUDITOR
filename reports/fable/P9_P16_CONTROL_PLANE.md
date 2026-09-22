# P9–P16 Control Plane — 2026-09-23

## Implemented

`money-machine/mm_brain.py` adds a local, deterministic read-only intelligence layer:

- funnel counts for the canonical review path, excluding quarantined fixtures;
- bottleneck ranking and a safe priority recommendation;
- explicit `NONE` recommendations when no useful safe work is pending;
- append-only decision ledger with policy version/hash, evidence references, confidence, and idempotency key;
- idempotency records returning `SKIP_ALREADY_COMPLETE` on replay;
- read-only decision replay and current/challenger shadow comparison with no promotion path;
- database integrity, foreign-key, duplicate-canonical, and contact-provenance checks;
- human-controlled safe-mode flag.

`mm_pipeline.Worker.run_once()` checks safe mode before claiming work, so enabling
safe mode prevents new leases while health/diagnostics remain available.

New CLI surfaces:

```text
./mm bottlenecks
./mm schedule --limit 10
./mm brain
./mm decisions [--business ID]
./mm decision DECISION_ID
./mm brain-replay DECISION_ID
./mm brain-shadow --current CURRENT.json --challenger CHALLENGER.json
./mm db-check
./mm safe-mode on|off|status
```

## Verification

- New control-plane tests: **4 passed**.
- Wave A regression subset: **32 passed**.
- Compile gate: `money-machine`, `auditor_toolkit`, and `website_auditor` compiled successfully.
- Existing required gates measured before this work: discovery **12 passed**; pipeline **49 passed**; supervisor **4 passed**; acceptance **56 passed, 2 skipped**.
- Full repository suite after this work: **145 passed, 2 skipped**, with 2 dependency deprecation warnings.
- Safety CLI remained fail-closed: transport provider `none`, enabled `false`, external send cap `0`, paid calls `0`, model cost `$0.00`.

## Current blockers / human gates

- `./mm db-check` reports existing active rows with missing canonical dedupe metadata; this is a data-quality finding, not silently auto-repaired.
- A 24-hour soak, host-only Chromium/SearXNG checks, and any PR publication/merge remain human-controlled.
- The two full-suite skips are explicit opt-in Chromium browser tests (`WA_BROWSER_E2E=1` / real Chromium).
- Runtime `state/`, reports, and databases are not release artifacts and must not be staged.

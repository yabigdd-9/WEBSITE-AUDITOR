# Guarded Hermes reliability candidate

Base: `09ab41ab61656ae4b63110d4ee7d418f3fbf07b8`. This source candidate does not enable production AI, outreach or new schedules.

The worker runner previously parsed nested JSON as a complete report, allowing a production-write declaration to be bypassed. It now consumes whole report objects and requires an explicit boolean false. Canonical workers execute in bounded process groups; shared staging ownership prevents cooperating scheduled workers from overlapping. Timeout and SIGTERM tests prove descendant cleanup and lock release.

Outreach draft generation preserves unrelated approval data and owner decisions, uses content-based identities, serializes cooperating writers and atomically replaces YAML. It never sends a message. Screenshot capture now passes untrusted URLs as subprocess arguments, requires successful child status and valid evidence, checks cached URL/hash identity and fails when captures fail.

The guarded model router validates response model and explicit zero-cost telemetry. Unknown or nonzero reported cost creates a private persistent stop incident instead of being hidden by a fallback. This response-side stop is not a substitute for shared provider admission or official entitlement, and does not prevent already in-flight charges. Direct/global routes remain a separate release gate.

Reporting separates individual JUnit pass/fail/skip counts from cumulative worker runs, preserves unknown legacy case counts, uses Pacific/Auckland report dates and avoids inferring NZD invoices from a zero-only workflow ledger. Both dead-letter queries use the actual pipeline failure states. Historical smoke wording is corrected to 63.7 seconds; raw historical evidence is preserved.

Independent focused verification: **90 passed and 12 subtests passed**, with unchanged source hashes. Actual execution of 52 modules matches fresh structural code compilation. The six modified production modules, regression tests, transport guards, report semantics and process/queue recovery are included. The subsequent test-only repair replaces invalid empty image paths with valid disposable image fixtures and strengthens the artifact assertion; five independent proof tests pass.

Final local suites: canonical **1127 passed**, including opt-in real local Chromium/PDF and ABI-compatible offline Pillow coverage; MoneyMachine plus synthetic Hermes **751 passed, 2 skipped, 95 subtests passed**; zero-token acceptance **18 passed**. Each run has unchanged source and zero structural loaded-code mismatches. The two skips remain release gates for global workflow accounting and independent live provider receipts. Scoped canonical/Hermes Ruff, compileall and dependency checks pass. Legacy MoneyMachine style diagnostics remain unchanged or reduced; no unrelated formatting was applied.

Release gates remain mandatory: official route allowance and common admission, complete secret-history triage, exact-candidate hosted checks, loaded runtime revision, applicable separately authorised staging soaks, worker-specific production acceptance and approved outreach recipients/messages. This candidate must not be merged as proof of full activation. Private operational reports, account telemetry, database backups and local environment links are excluded from publication.

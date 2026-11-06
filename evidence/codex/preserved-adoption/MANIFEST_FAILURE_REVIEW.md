# Manifest failure follow-up

Base: f8d68fad06c21e9f3283142dc1cff785b987b019 on agents/codex-r00.
Read-only independent reviewer found no actionable issue in the duplicate-field patch against a69d3c6f. It preserves digest checking before parsing and rejects duplicate fields throughout nested JSON objects.

Next demonstrated failure: a correctly hash-pinned, synthetically nested 2000-level JSON document raised uncaught RecursionError. Regression before fix: 1 failed, 26 deselected; child exit 1 instead of 3, receipt remained VERIFYING. This denies dispatch but fails the bounded failure receipt contract.

Correction: include RecursionError in existing manifest parse error handling. Return the existing redacted manifest_unreadable_or_invalid failure code, exit 3, FAILED status/identity_status and no target execution. No new public status or activation behavior.

Fresh verification: 27 bootstrap tests passed in 13.13 seconds; scoped ruff passed; git diff --check passed. Tests use disposable synthetic Git repositories and owned children. Full canonical/money suites were not rerun or claimed for this patch. Independent reviewer additionally inspected the working source/test diff and found no actionable issue; reviewer did not rerun tests.

Changed source files remain exclusively assigned to Codex: money-machine/runtime_bootstrap.py and money-machine/test_runtime_bootstrap.py. Evidence stays in evidence/codex. Shared branch still e68873c5 and Opus still dfc5dc39 when checked. No shared edits, service control, provider routing, production DB operations, push, deployment or soak performed.

Remaining A10 scope: live scheduler/process identity, continuous drift observation and release acceptance need separate design/ownership/activation evidence. Startup-only receipts remain limited and do not grant financial, sending or soak permission. Do not fabricate additional local upgrades as substitutes for those gates.

# A10 pinned startup reader contract

Scope: offline additive reader on agents/codex-r00. Human assigned money-machine/mm_soak.py and money-machine/test_runtime_attestation_contract.py exclusively to Codex. No activation, monitor start, scheduler modification or shared integration included.

Canonical source: MASTER_PLAN_v3.2.1.yaml A10 in the user-provided corrected archive. It requires executable/revision/config/DB/scheduler/worker/stop identity, marks ambiguous identity UNKNOWN, and explicitly rejects Git HEAD alone as live-runtime proof. This increment closes only the pinned startup receipt reader subset.

## API and trust inputs

startup_attestation() preserves the prior verified result: receipt status plus required current module-byte checks. New keyword-only manifest_path and manifest_sha256 must both come independently from the caller. The reader never selects an approval hash from the receipt itself. A pinned manifest is local operator approval evidence, not a cryptographic signature or independent provider evidence.

With both supplied, startup_identity_verified requires exact manifest digest/schema, canonical repository/interpreter/DB targets, valid revision/release identity, matching receipt PID and PID file, PINNED_STARTUP status, isolation, matching scheduler and configuration identity, current approved configuration hashes, and each receipt module hash bound to the approved committed Git tree. The DB target is resolved without opening it. Duplicate keys, ambiguous paths and malformed nesting deny identity. Bounded identity_failure_code excludes file/credential contents.

Runtime identity remains UNKNOWN even after a matching startup check. No live PID existence/start-time/lock ownership, kernel executable, active DB handle, launchd ownership or child-process attestation is inferred. No time-to-live value or undocumented process-age threshold is invented. A matching historical receipt is startup evidence only.

## Compatibility and consumers

Legacy verified meaning and status IMPORTS_VERIFIED remain unchanged. No-argument calls add startup_identity_verified=false and runtime_identity_status=UNKNOWN. Existing collect_sample and detect_violations are not rewired to use new approval inputs or to grant full A10 acceptance. Explicit integration of independently selected approval inputs and real process-start evidence is the next package; no acceptance upgrade is implicit.

## Acceptance matrix

Positive: disposable committed repository, independently pinned manifest, matching synthetic receipt/PIDfile/config/module bytes gives startup_identity_verified=true with runtime UNKNOWN.
Negative: missing approval, changed approval bytes, duplicate keys, excessive nesting, wrong PID/type/SHA/scheduler/DB/repository/interpreter/status/isolation/configuration, invalid schema, config aliases/escapes/duplicates/changes and disk+receipt hashes inconsistent with approved commit all deny startup identity. Source-only compatibility checked through bootstrap/readiness suites.

All fixtures synthetic; sockets/DNS blocked in new tests. No production DB, launchd, provider or sender invoked. Existing readiness tests retain their own isolated fixtures. Before shared adoption: independent review, immutable source SHA with focused receipts, then integrator approval. No restart or soak authorized by this contract.

## Remaining full-runtime blockers

Need a reviewed process-start identity (protect PID reuse), independent scheduler ownership observation, actual executable/DB-handle correspondence, approved configuration coverage, observation interval/max gap and stop-state contract. Any source files beyond current ownership must be assigned before edits. Cross-process live acceptance requires separate authorization; global financial admission, release review and soak duration remain independent gates.

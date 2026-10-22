# A10 specification — extend existing runtime attestation

Status: LOCAL_STARTUP_EXTENSION_IMPLEMENTED at c50fc975; independent review and
full runtime acceptance remain outstanding. See safety-followup/REPORT.md.
Integrator: human operator. No service changes or activation are included.

## Existing implementation and permitted scope

Reuse `money-machine/runtime_bootstrap.py`, its checked import loader, and
`money-machine/test_runtime_bootstrap.py`. The existing bootstrap verifies
committed Python sources during an explicitly selected startup; it is not proof
that an already-running production process loaded those sources. Its receipt
currently records PID, interpreter, expected SHA and observed module hashes.

Proposed exclusive source files for Codex are those two paths only. Before
implementation, record the integrator's assignment in the shared ownership
register and check dirty state in all affected worktrees. Opus's supervisor
files and candidate a365d6b1's seventeen paths are excluded.

## Proposed manifest and receipt contract

This contract is for integrator review, not an implemented CLI/API:

```json
{
  "schema_version": 1,
  "release_id": "operator-selected-identifier",
  "source_sha": "40-lowercase-hex-characters",
  "repository_realpath": "/explicit/approved/checkout",
  "python_realpath": "/explicit/approved/python",
  "database_realpath": "/explicit/approved/database.db",
  "configuration": [
    {"realpath": "/explicit/approved/config", "sha256": "64-lowercase-hex-characters"}
  ],
  "scheduler_identity": "explicit-approved-label-or-fixture"
}
```

Require an operator-selected manifest and its expected SHA256 for strict
acceptance. A path or a self-generated manifest alone does not prove approval.
The invoker supplies the approval evidence; this package does not invent a
cryptographic signature service or a new approval database. Schema validation
rejects unknown versions, missing fields, invalid hashes and ambiguous paths.

The receipt records manifest hash, release ID, expected and observed source,
interpreter realpath/version, process PID/start identity, resolved DB target,
configuration hashes, scheduler identity, observed module hashes and bounded
failure codes. It records no credential contents or unfiltered environment.
Write receipts using the existing private atomic output mechanism.

## Acceptance semantics

- Verify actual loaded module execution against fresh committed compilation;
  source-file hashes and function names alone are insufficient.
- Match the resolved database target before dispatch without migrating,
  restoring, checkpointing or otherwise opening the database for mutation.
- Hash only explicitly approved configuration files; reject missing files,
  path escapes and unexpected aliases. Do not search for credentials or include
  their values in receipts. Configuration changes invalidate the attestation.
- Record the source/interpreter/configuration identities frozen for the run.
  Any relevant source or configuration change during verification invalidates
  the receipt, even when tests happen to pass.
- Strict acceptance denies missing or mismatched evidence. Existing source-only
  receipts remain explicitly limited to source verification and cannot satisfy
  full runtime release acceptance.
- Existing production PIDs without startup evidence remain UNKNOWN. Never turn
  an on-disk Git SHA, listener, heartbeat or self-written report into a claim
  that those processes are verified running the release.
- Reuse the existing CLI ownership mechanism. A PID existence check is not
  atomic ownership. Duplicate/stale/ambiguous process observations deny
  acceptance; the probe does not automatically stop or restart processes.
- Financial admission, external-send policy, independent review and soak
  acceptance remain separate gates. A10 grants none of those permissions.

## Isolated regression matrix

Use disposable repositories, synthetic configs and DB paths, temporary ports
when a listener is required, and only owned subprocesses. No live launchd,
global configuration, production DB, external provider or outbound transport.

| Case | Required result |
| --- | --- |
| Matching committed source and approved manifest | Bounded verified receipt for the observed startup only |
| Wrong SHA or application source outside checkout | Denied before worker dispatch |
| Stale bytecode despite matching disk source | Denied based on executed code |
| Missing/wrong config hash or config change during run | Denied; no secret values emitted |
| Wrong resolved DB target or unexpected path alias | Denied without DB mutation |
| Wrong interpreter or repository identity | Denied |
| Duplicate/stale PID or missing scheduler identity | Denied or UNKNOWN; no process control |
| Invalid/revoked/missing manifest approval evidence | Denied strict acceptance |
| Interrupted receipt write | No partial receipt accepted |
| Existing runtime with no approved startup evidence | UNKNOWN, not verified_running |

Discover exact test selectors from the existing suite before implementation.
Run focused regressions first, then the impacted source/runtime suites. Record
command, exit code, actual duration, source SHA and loaded-code comparison.

## Integration and activation gates

1. Integrator assigns the two files and approves the manifest contract.
2. Codex submits a small source/test commit plus exact verification evidence.
3. Independent reviewer verifies the candidate and its failure cases.
4. Integrator applies accepted changes sequentially and reruns impacted tests.
5. A separately approved activation selects an exact release and approved
   manifest. No restart, production deployment or live attestation is implied
   by this specification or by the current evidence commits.

Rollback preserves safety controls and existing durable state. Revert only the
new application behavior when appropriate; do not relabel old unknown runtime
evidence as accepted, erase receipts or disable existing guards.

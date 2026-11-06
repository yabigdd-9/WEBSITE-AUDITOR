# Queue ownership repair and committed-source batching

Source: 191d85854cbbfc32e26bad3f189e45370026d191.
Approved baseline afa51457 remains in history; these changes need separate review.
Status: LOCAL_IMPLEMENTED_AND_VERIFIED. Exact commits/files: commits.json.

## Queue repair

- SQL excludes active leases before ORDER BY/LIMIT, with deterministic item-ID
  ordering for tied timestamps. The update rechecks state and retry eligibility
  after selection, including a tested competing-connection state change.
  Empty state sets/nonpositive limits return no work.
- Completion/failure acquire the SQLite writer lock before inspecting ownership.
  A savepoint encloses owner/expiry checks and all mutation/audit/metric changes.
- Workers pass the exact lease_until value returned by claim as a lease token.
  Changed, released, expired or reassigned leases deny the write. This protects
  same-worker-ID reassignment when the lease value differs. No new DDL/index.
- Rejected transitions roll back all mutations inside the savepoint. Successful
  completion returns the final row with its cleared lease. Existing outer
  transactions remain controlled by their caller. Ordinary transactional
  connections start BEGIN before the savepoint when necessary, so a later
  exception in `with d:` can roll back completion. Explicit autocommit
  connections retain their autocommit semantics.
- Lease loss does not become a normal retry/failure for somebody else's item.
  Breaker results are recorded only after authorized completion/failure.
- BLOCKED_COST remains a typed error and keeps its diagnostic prefix and
  blocked_cost classification. Provider/lane metadata is preserved.

Legacy unleased direct calls remain supported for compatibility. Worker paths
are strict because they supply expected_lease. This is not a capability system
for arbitrary callers with direct SQL access. The fence covers completion and
failure writes, not arbitrary external effects or SQL performed by a handler.
Lease renewal, durable claim UUIDs and every handler's side effects require
separate design if stronger fencing is needed. SQLite contention can still
produce a bounded database-lock error; no live database settings were changed.

## Source batching

Use NUL-delimited ls-tree metadata and cat-file --batch requests by blob ID.
This avoids delimiter ambiguity for space, non-ASCII and newline filenames.
Require regular blob entries, bounded declared per-file/aggregate sizes, exact
object/type/size response framing, successful subprocess exit and no trailing
data. Both Git subprocesses have bounded timeouts. Parsing/read errors fail
closed. Existing exact revision, bytecode, import, configuration and receipt
checks remain in place; no unchecked cache was introduced.

Current benchmark covers 334 Python files: 335 Git processes become 2.
benchmark.json records all three original/new trials, including tree enumeration.
All byte dictionaries match. This is a local warm-cache source-reading
microbenchmark, not a guarantee of total startup speed or cold-cache behavior.
Concurrent validation may affect timings.

## Verification scope

Initial implementation focused run: 141 passed; corrective queue run: 19 passed.
Final frozen full-suite receipts below are authoritative for the corrected source.
Canonical lint and new-file lint passed.
The full suites use the existing Q10 source probe, reviewed synthetic DB fixture,
credential-scrubbed environment, separate scratch roots and no-send/no-paid
flags. Exact source and loaded-code receipts are retained after completion.
No installed dependency, production DB, provider configuration, shared branch,
Opus file, service, launchd job, deployment, send or soak activation was changed.
Existing five skips and independent/global admission/release gates remain open.

## Review and integration

Review the three new source commits independently from afa51457's approval.
Shared integration remains pinned to dfc5dc39 with dirty work preserved.
Do not repeat earlier Claude cherry-picks. Any authorized fast-forward still
requires preservation/ownership of dirty work and an isolated replay of the
exact accepted candidate. Source implementation does not authorize activation.

## Corrective self-review

The first full run at 8b95f433 was intentionally interrupted after discovering
that releasing an outermost SAVEPOINT could commit before a caller's connection
context exited. interrupted-8b95f433 retains exit-2 receipt/XML and a note; it
is not a completed verification gate. Commit 191d8585 fixes this transaction
edge and rechecks claim state/retry eligibility at the update. The expanded
queue regressions are 19 passed. Final full suites replay the corrected source.

The runtime loader is byte-identical between benchmark source 8b95f433 and
final source 191d8585. Benchmark numbers retain their exact measured revision;
no end-to-end startup timing is claimed.

## Final frozen verification

- canonical: 1139 passed, 3 skipped, 2 warnings in 120.83s (0:02:00); receipt duration 121.727 seconds.
- money: 742 passed, 2 skipped, 83 subtests passed in 108.30s (0:01:48); receipt duration 109.185 seconds.

Both final suites exit 0 with changed_during_run=[] and loaded_mismatches=[].
The interrupted older run is excluded. Current candidate source is unchanged
from the tested revision; subsequent evidence-only commit is not a new app build.

# P1 Plan - Repository Hygiene + V32 Canonicalization
**Date**: 2026-09-22
**Branch**: upgrade/v32-canonical-execution

## Objective
Complete Phase 1 of the v32 execution plan: Repository Hygiene + V32 Canonicalization.

## Steps

### 1. Verify ignore protection
Confirm that runtime files cannot be accidentally staged by Git.

Run:
```bash
git check-ignore -v --no-index \
 state/errors.jsonl \
 state/health.json \
 state/metrics.jsonl \
 state/deployments.jsonl \
 state/HERMES_EXECUTION_STATE.yaml \
 reports/acceptance-results.json
```

Expected output: each file should show as ignored due to a rule in .gitignore.
If any file is not ignored, we must update .gitignore to ignore it.

### 2. Resolve already-tracked state files
Two state files are currently tracked in Git:
- state/HERMES_EXECUTION_STATE.yaml
- state/deployments.jsonl

We must decide whether to keep them tracked or remove them from the index (while keeping them locally).

**Option A**: Keep the two tracked state files and explicitly document why.
**Option B**: Remove them from the index (git rm --cached) so they remain locally but are not tracked.

We cannot choose automatically; this requires a human decision.
We will document the decision and reasoning in this plan.

### 3. Build the v32 canonicalization ledger
For every file that differs between the current repo state and any backup/restore candidate, record:
- path
- in_repo (whether the file exists in the current repository)
- current_sha256 (SHA-256 of the file in the current repo, if it exists)
- backup_sha256 (SHA-256 of the file in the backup/restore candidate, if it exists)
- decision (one of: KEEP_CURRENT, RESTORE_BACKUP, MANUAL_MERGE, OUT_OF_SCOPE)
- reason (explanation for the decision)
- covering_test (a test that verifies the decision is correct, if applicable)

Paths outside `/Users/dd/WEBSITE-AUDITOR` are automatically OUT_OF_SCOPE.

Output the ledger as a TSV file:
```
reports/fable/V32_CANONICALIZATION.tsv
```

We must examine all files in the repository and compare with known backup locations (e.g., under `backups/`, or Git branches like `backup/v32-before-local-consolidation-2026-09-22`).

### 4. Gate P1 Criteria
To complete P1, we must satisfy:
- Every candidate file has an explicit decision in the ledger.
- No mystery files are copied into the v32 branch (i.e., we have accounted for all files that differ).

## Notes
- We are currently on branch `upgrade/v32-canonical-execution`.
- The supervisor is running (PID 26743).
- External sends, paid calls, and model cost are zero (as verified in P0).
- We will need to make a decision on the two tracked state files (HERMES_EXECUTION_STATE.yaml and deployments.jsonl) and document it.

## Next Steps
After completing P1, we will move to P2: Quarantine test data + clean DLQ.


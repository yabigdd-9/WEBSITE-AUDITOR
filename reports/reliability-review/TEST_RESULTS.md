# Test results

Results are separate invocations with overlapping coverage; counts must not be added as unique tests. Command, exit code, elapsed time and frozen runtime source hashes are saved beside each transcript.

| Invocation | Actual summary |
|---|---|
| acceptance-synthetic-portable | 1 failed, 2 passed in 49.87s |
| acceptance-synthetic | 2 failed, 58 passed, 2 skipped in 188.34s (0:03:08) |
| approval-safety | 38 passed in 1.94s |
| baseline-status-cli | 1 failed in 41.18s |
| browser | 15 passed in 82.12s (0:01:22) |
| crash-recovery | 1 passed in 13.88s |
| database-queue | 62 passed, 2 skipped in 8.11s |
| discovery-qualification | 80 passed in 2.70s |
| full-final | 975 passed, 3 skipped, 1 deselected, 3 warnings in 402.32s (0:06:42) |
| full-non-slow | 973 passed, 3 skipped, 1 deselected, 3 warnings in 188.38s (0:03:08) |
| money-machine-non-slow | 94 failed, 568 passed, 10 skipped, 73 subtests passed in 62.15s (0:01:02) |
| money-machine-synthetic-final | 2 failed, 658 passed, 12 skipped, 77 subtests passed in 404.15s (0:06:44) |
| money-machine-synthetic | 3 failed, 657 passed, 12 skipped, 77 subtests passed in 248.85s (0:04:08) |
| queue-after | 76 passed in 12.69s |
| regressions-before | 4 failed in 1.87s |
| regressions-final | 9 passed in 3.92s |
| retention-after | 2 passed in 20.62s |
| retention-before | 2 failed in 2.04s |
| worker-supervisor | 83 passed, 1 deselected in 59.28s |
| money-machine-synthetic-verified | 660 passed, 12 skipped, 77 subtests passed in 209.56s (0:03:29) |

**Final acceptance:** `975 passed, 3 skipped, 1 deselected, 3 warnings in 402.32s (0:06:42)`; MoneyMachine `660 passed, 12 skipped, 77 subtests passed in 209.56s (0:03:29)`. Nine new queue/retention regressions passed. All final runtime source receipts have changed_during_run=false.

Canonical full-final passed 975 tests, with three skips (two browser opt-ins and missing Pillow) and one slow crash test deselected. Real Chromium was explicitly exercised in browser (15 passed), and crash-recovery was separately exercised (1 passed). The nine new queue/retention regressions passed. Two retention tests failed before the repair; four queue cases failed before the repair.

Initial MoneyMachine directory run: 94 failures were chiefly source fixture and interpreter setup problems. Synthetic source reruns exposed hardcoded three-history-claim and archived-score assumptions, plus a 10-second status CLI timeout under host load about 335. The fixture is generated from committed SQL; no production snapshot is used. The score replacement security test now archives its own synthetic score before attacking it. Timeouts were not increased. Preserve failed transcripts rather than presenting them as passes.

Host-only corpus, rollback SQL and Hermes source DB skips are explicit coverage gaps. Recorded model/send gate operations in acceptance tests are fake SQLite receipts; no provider or transport ran.

Scoped Ruff passed; compileall passed; pip check reported no broken requirements; git diff --check passed. Legacy mm_pipeline/daemon/test_email_hardening files retain existing whole-file style debt, so no whole-repository lint claim is made.

The baseline status CLI case was reproduced from committed HEAD in an exported code tree, using the synthetic DB (`baseline-status-cli.*`). It hit the same 10-second subprocess limit. The final candidate suite passed that case after the fixture/cache setup corrections and a change in host load. No timeout or assertion was relaxed. The earlier archived-score failure is fixed by constructing and archiving the test's own synthetic score; its replacement-attack assertions remain intact.

Stage acceptance: 100/100 valid synthetic jobs, 0 duplicate successful executions, 5 abandoned leases reclaimed, 0 stranded eligible jobs, 2/2 injected failures exhausted a two-attempt budget. Final elapsed 4.956 seconds plus a separate 25.041-second observation of the earlier staging acceptance. This is bounded staging smoke/recovery evidence, not a production soak.

# Current baseline and repaired candidate validation

Base `ec86481ccd6c674c6dfee8d7856d71d97581d08f`; uncommitted repaired source is bound by
[the source manifest](completion-20261020/source-manifest.json).

| Run | Canonical | MoneyMachine |
| --- | --- | --- |
| Unchanged baseline | 1141 passed / 3 skipped | 747 passed / 2 skipped / 83 subtests |
| Repaired candidate | 1141 passed / 3 skipped | 764 passed / 2 skipped / 83 subtests |

Commands, start timestamps, duration, exit codes and loaded-code comparison limitations
are retained in the final receipt JSONs. JUnit retains individual skip reasons.
Baseline harness failures are preserved in the chat workspace and were corrected
by supplying MM_TEST_SOURCE and MM_PYTHON, without changing application source.
Additional results: 85 overlapping focused cases, six real Chromium/PDF journeys,
17 isolated wheel imports and axe asset, Ruff, compileall, pip check, offline wheel build.

## Second batch

Current source manifest and receipts: `completion-20261020-batch2/`.
Canonical: 1,141 passed / 3 skipped. MoneyMachine: 764 passed / 2 skipped /
83 passing subtests. Full Hermes: 116 passed. These scopes overlap; do not add
counts into a unique total. All three receipts exit zero with no observed
source drift or parent-process loaded-code mismatch. Canonical and changed-file
Ruff plus compileall pass. Broader legacy website_auditor lint reports 168 issues,
verified identical to the base revision and retained as separate open work.
Browser/wheel/restore results above remain earlier isolated evidence, not fresh
second-batch runs. No production or external-route acceptance is inferred.

## Third batch

Current source/receipts: completion-20261020-batch3. Canonical 1150/3 skips; MoneyMachine 806/2 skips/83 subtests; Hermes 116. Focused 96 overlaps. All three final receipts have no observed parent-process mismatches or source drift. Full legacy pipeline import remains blocked by missing tenacity; its actual image function is tested separately.

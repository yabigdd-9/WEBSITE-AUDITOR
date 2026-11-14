# Startup receipt consumer compatibility

Application source commit: 48d3fb5a5f10701affe0a21f6ed9d905f9800508.
Changed files: money-machine/runtime_bootstrap.py and
money-machine/test_runtime_bootstrap.py only.

The existing mm_soak.startup_attestation() reader recognizes IMPORTS_VERIFIED,
not the new strict-mode status introduced in c50fc975. Preserve the historical
status for source-import verification; keep the additional manifest result in
identity_status=STARTUP_IDENTITY_VERIFIED. All observed verification failures
set both status and identity_status to FAILED. No soak reader, acceptance
criteria, provider route, launchd configuration or live service was changed.

A new isolated contract test generates an actual strict-mode child receipt and
feeds it to the unchanged soak reader with a synthetic root. Its existing
source-verification result passes; a failed receipt is rejected. This does not
turn startup evidence into a live-runtime or release attestation.

The first targeted run exposed a fixture helper that read next(glob(...)),
selecting the previous child's receipt on a repeated startup. The helper now
uses the actual Popen PID, and handles subprocess timeout cleanup. The initial
run was 54 passed/1 failed; after correction the targeted run was 55 passed.

Frozen replay uses the existing Q10 probe and sanitized integration environment
with only the targets overridden to test_runtime_bootstrap.py and
test_runtime_readiness.py. q10-money-receipt.json records the exact selectors;
the filename does not imply the entire MoneyMachine suite was replayed.
Full-suite evidence remains historical at c50fc975: canonical 1139 passed/3
skipped; MoneyMachine 715 passed/2 skipped plus 83 subtests.

The canonical full-suite source/test surface outside these two files is
unchanged. This compatibility correction requires independent review along
with the preceding safety batch; Claude's review of older candidates does not
automatically cover it. No shared integration or activation was performed.

Frozen replay: exit 0; 55 passed; 22.329 seconds;
changed_during_run=[]; loaded_mismatches=[]. Scoped lint and diff checks passed.

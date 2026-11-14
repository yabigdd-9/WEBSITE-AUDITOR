# P12 Stability Evidence

Verified 2026-10-16 Pacific/Auckland against base `09ab41ab61656ae4b63110d4ee7d418f3fbf07b8`.

## Correct historical duration

**PASS — evidence interpretation.** Historical source JSON `reports/hermes_reliability/smoke_report_hermes-zero-token-smoke-test-1792056128.json` records start `2026-10-15T09:22:08+0000`, end `2026-10-15T09:23:12+0000`, elapsed **63.70585823059082 seconds**. In Pacific/Auckland these are 22:22:08–22:23:12 on 15 October. Its actual embedded configuration sets `duration_minutes: 1`; the tracked template sets 15. This was a roughly one-minute smoke, not completed 15-minute stability evidence.

The report records production mutation false, production integrity ok and no FK issues. This is historical local evidence, not an independently instrumented current-revision production attestation. Earlier missing-shell-`timeout` exit 127 was a harness failure and is not counted as worker smoke failure. Historical JSON/outcome/heartbeat artifacts are preserved.

## Configuration review

**PASS — configuration boundaries only.** All three `ops/hermes_zero_token/soak_{smoke,24h,72h}.yaml` templates declare staging DB under `state/hermes_zero_token/staging/`, production source snapshot, production writes false, external sending false, daily cap 0, paid models false, kill switch, disk threshold and rollback without production restore. The 24/72-hour templates additionally declare duplicate ownership, lease recovery and resource criteria. 72-hour disk minimum is 2 GB versus 1 GB for shorter templates.

**BLOCKED — executable enforcement.** At base the tracked runner accepts only `--worker` and `--dry-run`; no tracked consumer of these YAML duration/monitor/stop/pass settings was found in the inspected ops/scripts/test/MoneyMachine paths. Templates alone do not implement a sustained monitored soak. `money-machine/mm_soak.py` is an existing distinct supervisor monitor, documented in `money-machine/RUNTIME_SOAK.md`; it must not be misrepresented as a completed Hermes staging soak.

## Historical supervisor evidence

Read all 12 `state/soak-evidence-*/soak-summary.json` files found at inspection. One records `soak_passed=true`: `state/soak-evidence-20261003T114403133502Z/soak-summary.json`, elapsed **86405.524033 seconds**, frozen start/finish SHA `e83121b23a404924d7df66e50b0a1f576280c873`. This accepted result is historical and revision-specific. The other 11 do not pass; several are interrupted/incomplete.

No accepted summary at base SHA `09ab41ab61656ae4b63110d4ee7d418f3fbf07b8` was found. Example latest inspected summary at `b349cd9fb23b6cf9c5a2e8a8c74691158e9cda8f` is incomplete after 8517.877019 seconds with explicit public-network probe failure and SIGTERM. None can substitute for current-candidate stability.

## Stage classification

| Stage | Result | Remaining condition |
| --- | --- | --- |
| Historical approximately 64-second bounded smoke | PASS | Correct duration interpretation only; report contains historical safety measurements. |
| Fresh corrected smoke of final candidate | NOT TESTED | Requires isolated fixture/staging harness with bounded portable timeout, measured elapsed time, heartbeat and source/revision attestation. |
| 24-hour Hermes staging soak | BLOCKED | Not started by this verifier. Separate explicit authorization, runnable enforcement, one owner, final frozen candidate and full-duration evidence required. |
| 72-hour Hermes staging soak | BLOCKED | Not started by this verifier. Separate explicit authorization and applicable release criteria required. |
| Current-revision supervisor soak | BLOCKED | No accepted exact-revision summary found. Must use existing monitor with frozen revision/config, loaded-module identity, one owner, sample continuity, accounting, DB/FK, lease/DLQ and final summary. |

`auditor_toolkit/runtime/report.py` independently requires **168 hours** for its READY status. The applicable release criteria must be reconciled explicitly; 24/72-hour templates do not silently override this threshold. No threshold was weakened during this review.

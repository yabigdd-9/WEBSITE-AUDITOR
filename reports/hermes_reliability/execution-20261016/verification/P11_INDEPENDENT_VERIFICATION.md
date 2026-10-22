# P11 Independent Security and Acceptance Verification

Verification date: 2026-10-16 Pacific/Auckland. Initial base: `09ab41ab61656ae4b63110d4ee7d418f3fbf07b8`.

Reviewer: separate independent verifier agent. Scope: release/security workflows, zero-token worker boundaries, FCC transport, release reporting, staging evidence and proposed changes. This is not full production sign-off. No services, provider calls, outreach, migrations or production records were changed by this verifier.

## Direct evidence

| Requirement | Result | Evidence and limitation |
| --- | --- | --- |
| Hosted exact-head checks | PASS | `gh pr view 52 --json ...` returned OPEN/DRAFT/CLEAN at base SHA. All 13 rollup entries were successful, including full regression, both SonarCloud checks, gitleaks, pip-audit, toolkit fixtures and CLI smoke. These checks do not cover subsequent uncommitted changes. |
| Independent isolated acceptance | PASS | `.venv/bin/python -m pytest -q -p no:cacheprovider ops/hermes_zero_token/test_integration_safety.py tests/test_fcc_bridge_transport.py tests/test_runtime_release_report.py`: **25 passed in 1.63s**, Python 3.11.16. Fixture-only tests cover staging aliases, fail-closed worker dispatch, kill switch, exception reporting, accounting unknowns, FCC loopback/proxy/redirect boundaries and release report behavior. |
| Nested worker-report safety | PASS in isolated candidate | Base defect independently reproduced: nested JSON bypassed production-write rejection. Final candidate parser consumes complete JSON objects, rejects truncation and requires explicit boolean false. Independent new regression tests pass. Fix is **not deployed** to canonical checkout. |
| Approval queue preservation | PASS in isolated candidate | Base defect independently reproduced with temporary YAML only. Candidate preserves unrelated mapping fields/items, keeps owner decisions on repeat runs, content-hash deduplicates, atomically replaces files and serializes cooperating queue writers. Concurrent subprocess regression passes. Fix is **not deployed**. |
| History secret scan | BLOCKED | Local `gitleaks git --redact=100 --no-banner --no-color --log-level warn --timeout 45 --log-opts HEAD .` exited 1: context deadline exceeded; partial 28.22 MB scan, 45.2 seconds, **15 candidate leaks**. No values were emitted. Candidates are not independently confirmed active credentials. Full scan and redacted triage remain required. |
| Recent history secret scan | PASS | Separate bounded redacted scan of `HEAD --max-count=100`, repository configuration, completed exit 0 with **zero candidates**. This narrows recent-change risk and does not clear older/full-history candidates. |
| Hosted secret/dependency scanning | PASS | Exact-head hosted gitleaks and pip-audit were successful. Security workflow uses full-depth checkout and audits project plus `money-machine/requirements-email.txt`. Gitleaks configuration excludes `test_*.py` and generated email observation evidence, so this is scoped evidence. Hosted results do not resolve the local partial history findings. |
| Dependency vulnerabilities on live installations | NOT TESTED | Hosted declared-dependency audit does not prove vulnerability status of Hermes/FCC/global tools or every installed local environment. No dependency installation was performed by this verifier. |
| Database access permissions | PASS | Base finding: production database was 0644 dd:staff beneath traversable group paths. After runtime agent repair, this verifier independently re-ran `stat`: canonical production DB and Hermes staging DB are both **0600**. `.hermes/` is 0700. This closes the inspected DB file-mode finding, not a comprehensive ACL/config/report review. |
| Production/staging isolation | PASS | Isolated tests reject same-path, outside path, symlink and hardlink aliases and preserve fixture production bytes across repeated snapshots. This does not prove every production worker is isolated. |
| Backup restoration/integrity | PASS | Independently reopened all **eight backups and eight restored databases** from `runtime/database_recovery_receipt.json` read-only: every SHA256 matches receipt, every integrity_check is ok, every FK count zero, every file mode 0600; containing recovery directory 0700. These are separate restored files, not an in-place production rollback. Runtime investigator's receipt additionally records source/backup/restore schema and count comparisons and rollback probes. |
| Live FCC health/failover/cost | NOT TESTED | Only offline transport acceptance was run here. Health, routing eligibility and official quotas require separate evidence. |
| Worker ownership/cancellation | PASS in isolated candidate | Independently reviewed final runner diff and passed shared staging lock, exceptional release, owner-process death, timeout descendant kill, SIGTERM descendant kill, cancellation audit and successful process contract tests. These prove synthetic process behavior, not host scheduler/reboot operation. |
| Installed scheduling/reboot recovery | NOT TESTED | No service/schedule changes were made by this verifier. Runtime agent's pause/ownership receipts require separate interpretation; fixture tests do not prove actual installed scheduler operation. |
| Screenshot execution/cache safety | PASS in isolated candidate | Reviewed URL separation into subprocess argv, child return-code/report-status checks, verified URL/hash cache and nonzero failure propagation. Six synthetic cases pass, including hostile quoted URL, old-PNG failure, verified cache reuse and tampered artifact recapture. No live website capture performed by verifier. |
| Test counters/reporting/alert state | PASS in isolated candidate | JUnit individual passed/failed/skipped counts recorded separately from cumulative worker runs; aliases share one lock; Auckland report day verified; legacy/missing accounting remains unknown. Both alert and funnel DLQ queries count actual RETRYABLE_FAILURE/PERMANENT_FAILURE states; focused regressions pass. |
| Prompt-injection/privacy/retention coverage | NOT TESTED | Limited source inspection found website text treated as untrusted in AI worker instructions. No exhaustive attack simulation, privacy export or log-retention audit was performed. |

## Test-isolation limitation

`ops/hermes_zero_token/test_worker_contract.py` at base hardcodes canonical database/report paths, executes real workers and edits the approval queue. It cannot be used as isolated acceptance evidence without fixture refactoring. The independent 25-test run used `test_integration_safety.py` and temporary paths instead.

## Final isolated candidate review

Candidate: `/Users/dd/Documents/Codex/2026-10-16/hi-2/work/release-candidate`; base SHA above. Interpreter: `/Users/dd/Documents/Codex/2026-10-16/hi-2/work/candidate-venv/bin/python`, Python 3.11.16, newly isolated environment with explicit shared dependency path. `auditor_toolkit` and `mm_model_router` imports were independently confirmed to resolve within the candidate.

**PASS — scoped local code remediation.** Independently inspected final diff for all six changed production modules: runner, outreach queue, screenshot worker, daily report, router and MoneyMachine reporting; related tests and smoke wording corrections were also reviewed. The earlier 68-test result is superseded for final source sign-off by this expanded frozen run:

```text
python -m pytest -q -p no:cacheprovider \
  ops/hermes_zero_token/test_runner_ownership.py \
  ops/hermes_zero_token/test_outreach_queue_safety.py \
  ops/hermes_zero_token/test_integration_safety.py \
  ops/hermes_zero_token/test_reporting_cases.py \
  ops/hermes_zero_token/test_screenshot_safety.py \
  tests/test_fcc_bridge_transport.py \
  tests/test_runtime_release_report.py \
  money-machine/test_pipeline.py::ModelRouter \
  money-machine/test_reporting.py
```

Result: **90 passed, 12 subtests passed in 32.70 seconds** (37.537-second complete harness runtime). Evidence: `validation/independent-final-scoped.log`, `validation/independent-final-scoped-receipt.json`, `validation/independent-final-scoped-loaded.json`. Receipt records **zero source changes**, **52 actual executed modules captured**, **zero structural fingerprint mismatches**, and production database not used. All six changed production modules are explicitly present in the matching loaded-module receipt. No live `test_worker_contract.py`, production worker, inference request or external send was run. `git diff --check HEAD` passed. Gitleaks stdin scan of all six changed production modules' diff completed exit 0 with no candidates; this is patch scope only.

The router tests independently demonstrate exact response-model checking, malformed-response fallback, explicit zero-cost response validation, durable owner-private stop incident, persistence failure remaining fail-closed and no fallback after unknown/nonzero cost. These are mocks, not official provider allowance or actual billing proof. A post-response incident latch cannot retroactively prevent a request already billed or stop requests already in flight.

Final source/test SHA256s below supersede the earlier six-file snapshot; all matched before/after this expanded run:

| Path | SHA256 |
| --- | --- |
| `ops/hermes_zero_token/runner.py` | `a1ef345ae26ce11cf3fbe715d8fd84a40d323b11dea5e25c037f24aa715c92ef` |
| `ops/hermes_zero_token/daily_report.py` | `5cda1f899b6a05ff4057d61a997cd145c01767aae7400d826bc130c307b96e9f` |
| `ops/hermes_zero_token/outreach_draft.py` | `24e669d95c0214dea2eccb86e860eee57b208bca99e7b93abf325578a760c010` |
| `ops/hermes_zero_token/screenshot_worker.py` | `d6ff2db774352e30ecf4c5f4fb7706d87971f9b0d61c6e12d9cf3bcfebeb6392` |
| `money-machine/mm_model_router.py` | `20128f264a0340f164ae85e7f23aa02d3c98cf33ce3d7c8f4305294e5c80b70f` |
| `money-machine/mm_reporting.py` | `4604d1401cf355647a221cba510166743e834d84e20f237641923bdaa925111b` |
| `ops/hermes_zero_token/test_runner_ownership.py` | `bcfb353d5d27bdbd55bc825f71f631275d239a2ef6f3498b5f6e2802e0f8e6a3` |
| `ops/hermes_zero_token/test_outreach_queue_safety.py` | `9a62b2101775535236d6d138c7621b86f2ba23ca9a742687b1895a079813fee3` |
| `ops/hermes_zero_token/test_reporting_cases.py` | `489a9f674c0694b7f6643912b1bc834ed67c2c10e5cb53b17a23590a5d0628ef` |
| `ops/hermes_zero_token/test_screenshot_safety.py` | `4ede33685033cac104ab950fe380c13156f8d08d886f9998370aac5660659aec` |
| `ops/hermes_zero_token/test_integration_safety.py` | `ddcdbd4a01e5233ab18c8981ce1eca42ceacc0f31157cfc4b20a79663fd57d32` |
| `money-machine/test_pipeline.py` | `568b77b1d3de3a595fd13a7af2e3f0c06da26307eec85a8b2912426c01949d69` |
| `money-machine/test_reporting.py` | `0a7408f92d5003039b6bdf8607031d15a216386379ffd44301314c97f0e54850` |
| `tests/test_proof_diff.py` | `5392fdf43fb49d3614305cce2bd277e283dc7088819b132529daa580831f7744` |

### Final test-only fixture delta

After the 90-test sign-off, the only Python source change was `tests/test_proof_diff.py`: its prior empty-path smoke fixture passed only when Pillow was missing. The reviewed repair creates two valid identical 1-pixel PPM files under `tmp_path`, asserts zero pixel difference and verifies the generated artifact exists when Pillow is available. It strengthens validation and changes no production module. Independent receipt comparison confirms exactly this one-file delta; its hash is included above, giving **14 final Python source/test files**.

Independently reran `tests/test_proof_diff.py tests/test_proof_rendering.py` with installed local ABI-compatible Pillow: **5 passed in 3.94 seconds**, complete harness 8.872 seconds, **30 actual modules captured**, **zero structural mismatches**, **zero source changes** and no production database. Evidence: `validation/independent-proof-fixture.log`, `validation/independent-proof-fixture-receipt.json`, `validation/independent-proof-fixture-loaded.json`. The earlier 90-test production-code sign-off remains valid because its six production modules are unchanged.

Fresh-process profiling began before module imports and captured actual top-level execution. The final harness structurally fingerprints every non-callable `co_*` attribute recursively, including nested code objects and typed constants; actual versus freshly compiled code matches for all 52 captured modules. Initial raw `marshal.dumps` comparisons were invalid provenance comparisons because serialization identity/interning differs; they are preserved as superseded diagnostics. Direct code-object/attribute comparison and tested structural hashes resolve that issue. Negative controls distinguish changed constants, filenames, boolean versus integer and positive versus negative zero. Source hashes remained frozen. This proves candidate execution, not the loaded production service revision.

**BLOCKED — full production acceptance.** No new blocking source defect was found within this reviewed diff. Full-history secret triage, final-candidate hosted/post-integration evidence, current-revision stability, official allowance verification and live operational/outreach gates remain unresolved. Canonical tracked source was independently confirmed restored to base with no tracked diff; candidate fixes are **NOT DEPLOYED**. A green base hosted rollup does not cover this candidate.

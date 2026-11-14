# Q10 — completed supported local baseline

Application source baseline: `09ab41ab61656ae4b63110d4ee7d418f3fbf07b8`.
Working directory: `/Users/dd/WEBSITE-AUDITOR-codex`.
Interpreter: `/Users/dd/WEBSITE-AUDITOR/.venv-email/bin/python` (Python 3.11.16).
No application source, live database, service, configuration or Opus file changed.

| Final run | Result | Receipt duration |
| --- | --- | --- |
| Canonical `toolkit_tests tests` | 1124 passed, 3 skipped | 94.441 seconds |
| MoneyMachine `money-machine -m "not slow"` | 692 passed, 2 skipped; 83 passing subtests | 117.863 seconds |
| Synthetic Hermes integration | 12 passed | 0.964 seconds |
| Offline outcomes/rejection/FCC transport | 19 passed | 1.127 seconds |

The nineteen offline cases overlap canonical coverage; do not add them again
when reporting unique cases. JUnit includes MoneyMachine subtest cases, whereas
pytest reports the 83 subtests separately. Do not treat JUnit's 777 total as
777 outer tests. Raw logs, XML and JSON receipts are retained side by side.
Raw traceback logs and JUnit failure payloads retain pytest's original trailing
whitespace; they are not reformatted. Git whitespace checks cover the authored
Markdown, Python and JSON files, with raw log/XML payloads excluded.

## Reproduction

Build a new customer-free fixture with `python -B evidence/codex/q10_fixture_source.py`.
The builder refuses to overwrite its completed fixture. It uses the versioned
schema and real core/email/pipeline/approval migrations, not a production data
copy. It models three legacy claims before installing all base guards; after
migration it verifies that a new unapproved claim is rejected. The archived
score and dummy business are explicitly synthetic, never commercial evidence.

Run `python -B evidence/codex/q10_baseline_probe.py --suite money` with:

- `MM_TEST_SOURCE` pointing to the builder's disposable fixture;
- `MM_PYTHON` selecting the verified interpreter above;
- `MM_ROOT` and `TMPDIR` pointing to owned scratch locations;
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` and `PYTHONDONTWRITEBYTECODE=1`;
- inherited credential/token/secret variables removed;
- no-send, no-hosted-LLM and no-paid-fallback environment controls retained.

Use `--suite canonical` for the canonical targets. Exact pytest arguments,
timestamps, durations and exit codes are in each final receipt. Environment and
dependency/lint observations are in `q10-environment.json`. External metadata
probes, real messages and model requests are not part of these test runs.

## Source execution evidence

Both final runs exited zero, with `changed_during_run=[]` and
`loaded_mismatches=[]`. The probe observes tracked parent-process module
execution and compares structural code with fresh compilation. Pytest's
assertion-rewritten test modules are compared with freshly rewritten code,
including conftest imports before pytest_configure. Child-process execution and
the already-running production supervisor are not attested by these receipts.

## Retained failed/inconclusive attempts

- Canonical initial receipt: tests passed, but the first probe compared rewritten
  test code with plain compilation. The corrected full run resolves that probe
  error; the original remains in `q10-canonical-initial-*`.
- MoneyMachine initial receipt: 95 failures; schema-only fixture lacked migration
  records and the worktree lacked a local interpreter. No application fix was
  inferred. Evidence remains in `q10-money-initial-*`.
- Migrated fixture receipt: 690 passed, 2 failed, 2 skipped plus 83 subtests.
  Two legacy tests assumed historical rows. Evidence remains in
  `q10-money-migrated-*`; the two corrected-fixture cases also passed separately.
- An erroneously started run was stopped after its fixture builder hit a send
  guard. `q10-money-precompletion-note.json` explicitly marks its log and stale
  preceding XML/receipt as incoherent, excluded from acceptance.
- Final full MoneyMachine run used the fully built synthetic historical fixture
  and passed. No production guards or application tests were weakened.

## Open checks and release limitations

Canonical skips: two opt-in real Chromium/PDF tests and one missing Pillow image
test. MoneyMachine skips: global/legacy Hermes accounting reconciliation and
independent live provider receipt verification. These remain open capabilities,
not successful acceptance cases.

Canonical toolkit lint and dependency checks passed; Hermes ops lint retains
nine baseline errors. Scoped evidence-script lint passes. Whole-programme
release still needs ownership, candidate integration, entitlement/security
evidence, live loaded-revision attestation, independent review and separately
approved soak/deployment/send gates. This Q10 baseline is not a release approval.

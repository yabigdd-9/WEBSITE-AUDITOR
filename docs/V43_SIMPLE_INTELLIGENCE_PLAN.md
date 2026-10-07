# v43 Simple Intelligence Execution Plan

```yaml
release:
  branch: upgrade/v43-simple-intelligence
  base: master
  objective: simplify overlapping decision logic and add small evidence-backed intelligence
  invariants:
    paid_calls: 0
    external_sends: 0
    autonomous_master_writes: 0
    human_review_required: true

workstreams:
  repository_polish:
    - refresh CURRENT_STATE.md to current master
    - remove obsolete v32 closeout instructions
    - document canonical current paths

  canonical_decision:
    module: auditor_toolkit/decision.py
    output:
      - priority_score
      - confidence
      - reason_codes
      - blockers
      - next_action
    rule: deterministic only; no LLM controls the score

  conversion_flow:
    source: PR-39 concept
    policy:
      - GET_HEAD_OPTIONS_only
      - no_form_submission
      - no_payment
      - no_checkout
      - evidence_screenshots
    output: conversion_path_health

  nightly_watchdog:
    - use auditor_toolkit.run_audit directly
    - stop invoking legacy website_auditor.py/remediation-engine.py
    - bounded snapshots instead of endless timestamped files
    - classify meaningful regressions

  learning:
    - capture human review outcomes
    - report calibration and false-positive patterns
    - never auto-change production weights

quality_gates:
  - compileall
  - pytest toolkit_tests tests
  - portable MoneyMachine regression
  - flow probe tests
  - deterministic decision tests
  - browser E2E where Chromium is available
```

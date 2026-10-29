# Website Auditor — independent readiness report

**Prepared:** 2026-10-29 01:00 NZDT (12:00 UTC)
**Source under test:** `40b2a6233ac079160d8ffcdcba755d9335524a02`
**Branch:** `integration/v44-local-machine-convergence` · **PR #52** open, draft, 13 checks green
**Working tree:** clean except untracked `.worktrees/` (pre-existing)

This is a status report, not a release recommendation. Nothing here authorizes sending,
paid activation, merge, deployment, or a restart.

---

## 1. Baseline — re-verified this session

| Check | Result |
| --- | --- |
| `git status` / HEAD | clean at `40b2a623` |
| Canonical supervisor | PID `79854`, launchd-owned, argv pins `--expected-sha 40b2a623`, `MM_EXTERNAL_SEND_DISABLED=1` |
| Heartbeat | fresh (35 s at probe time) |
| DB `database/money_machine.db` | integrity `ok`, 0 FK errors, 0 leases, 0 dead letters; 44 NEEDS_REVIEW / 338 REJECTED / 12 SUPPRESSED, unchanged since 2026-10-27 |
| Committed soak validator re-run | `collect_sample` + `detect_violations` → **0 violations**, all 6 gates pass |
| Completed soak | 289 samples / 86,405.53 s / max gap 304.56 s, raw stream SHA `3f6d1a8d…`, independently recomputed. Proves that window only. |
| Separate opus runtime | PID `48436` in `WEBSITE-AUDITOR-opus`, own DB (integrity ok, empty pipeline), untouched. No restarts, no signals sent. |
| Owner app `127.0.0.1:8766` | HTTP 200; all 14 tracked code hashes match the recorded manifest; 3 audit records preserved; 0 approval changes; 0 sends |
| Local SearXNG | running on **8888** (docs/plan say 8080 — a stale port reference), returns real results |
| Fresh real audit | `www.clyne-bennie.co.nz/`: 14/14 required static checks, 8 findings, score 68, deterministic, no model calls |

## 2. Defect found and fixed — transport test

`toolkit_tests/test_outcomes_transport.py::test_transport_is_schema_locked_disabled_and_network_free`
failed: `mm_transport.status()` reads a **private owner override** at
`state/transport-policy.json` (currently: enabled Gmail, unlimited cap), so the bare call
returned `MANUAL_EXACT_APPROVAL` instead of the committed `DRAFT_ONLY` default.

Root cause was a test that asserted a schema default against live runtime state — not a
safety regression. Fixed by pinning the default path explicitly and adding coverage for the
override path, the `MM_EXTERNAL_SEND_DISABLED` kill switch, and the private-file refusals
(directory / symlink / world-readable). **8/8 pass.** Full toolkit suite **330 passed,
2 skipped** (both opt-in Chromium). Money Machine acceptance **56 passed, 2 skipped**.

Committed as `1f30ad14`. The live `state/transport-policy.json` is preserved unchanged.

## 3. Accuracy gate — frozen, awaiting a human reviewer

`outputs/holdout-accuracy-20261029/`

| Item | Value |
| --- | --- |
| Cases | 30, exactly 10 per required stratum |
| Predicted observation units | 339 |
| Fixture bytes | SHA-256 frozen, all 30 distinct, none collides with the 120 development hashes |
| Raw auditor reports | 30 preserved |
| Deterministic replay | 30/30 cases reproduce the live auditor's defect-key set exactly |
| Scorer | 22/22 synthetic contract tests pass; blank template still correctly fails |

**Known weaknesses, recorded not hidden:**
1. Universe is 44 URLs drawn from the operator's own contact-review queue — NZ trades, mostly
   single-page brochure sites. Not a representative sample.
2. `javascript-application` stratum is assigned by script-count heuristic, not an independent
   page-type label.
3. No negative-only cases — every case has ≥1 predicted finding, which biases the observable
   false-positive rate upward.
4. `holdout-004` (`www.excelsior.net.nz`) failed to fetch; predictions are empty.
5. Three cases show viewport / meta-description divergence between the frozen capture and
   the live run. Frozen capture is authoritative.

**Blocked on:** an independent human reviewer labelling all 339 units
(`present` / `absent` / `uncertain` + rationale) and hunting for missed findings.
Guide: `REVIEWER-GUIDE.md`. Then `python3 accuracy_score.py holdout.json` prints TP/FP/FN,
precision, recall and Wilson 95% intervals. A pass does **not** authorize release —
`release_authorized` is always `false`.

## 4. Gates still open

| Gate | State |
| --- | --- |
| Audit accuracy | predictions frozen; **labels pending a human** |
| Security — 16 historical holds | all `decision: null` in the owner template. Needs owner/provider evidence per item; any rotation needs explicit authorization |
| Owner workflow / email | synthetic transport contracts pass (87); live reply/bounce/complaint evidence absent; owner acceptance pending |
| Stale-heartbeat incident | root cause unproven; recovery proposal exists, restart not authorized |
| Paid routes | unproven, activation not authorized |
| Release | held pending the above + explicit human acceptance |

## 5. What I need from you

1. **A reviewer** for the 339 accuracy units — the only thing blocking the accuracy
   measurement, and not something I can do for you.
2. **Go / no-go** on starting the security disposition template for the 16 holds.
3. Nothing was sent, paid for, merged, deployed, restarted, or deleted.
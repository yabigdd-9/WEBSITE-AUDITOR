# OPUS ARCHITECTURE AUDIT — P15

**Project:** WEBSITE-AUDITOR / MoneyMachine / Hermes  
**Branch:** `integration/v44-local-machine-convergence`  
**HEAD:** `09ab41ab` (verified `git log --oneline -1`)  
**Workspace:** `/Users/dd/WEBSITE-AUDITOR`  
**Policy:** `paid_allowed=false`, `max_cost_usd=0`, `external_send_allowed=false`, `daily_cap=0`  
**Basis:** Direct source inspection of `auditor_toolkit/`, `money-machine/`, `toolkit_tests/`, plus `CLAUDE.md`, `MASTER_PLAN.md`, `MASTER_PLAN.yaml`, `CURRENT_STATE.md`.

---

## Summary

The system is a deliberately deterministic, zero-paid-token, local-first Website Auditor with a hardened Money Machine control plane. Release readiness is **HELD** (per `CURRENT_STATE.md`, 2026-10-15) pending secondary Sonar triage, independent model/provider/contact/receipt acceptance, missing fixture coverage, historical privacy/secret review (T20, 16 inputs needs_review), and an authorized exact-revision runtime/soak acceptance.

Baseline re-verified 2026-10-16:
- Toolkit suite: **297 passed, 2 skipped** (opt-in Chromium E2E)
- Money Machine acceptance: **58 passed, 2 skipped**
- Python 3.11.16 (`.venv` and `.venv-email`)

No paid calls, no external sends, no model generation were exercised.

---

## Canonical architecture (from source)

| Layer | Canonical implementation | Evidence |
|---|---|---|
| Audit engine | `auditor_toolkit/` + thin `wa`/`mm` CLI layer | CLAUDE.md; `auditor_toolkit/cli.py`, `pipeline.py`, `checks.py`, `models.py` |
| Operator CLI | `./mm` → `money-machine/mm_operator.py` | `mm` shell wrapper; `mm_operator.py:main` |
| Runtime state | SQLite + state files | `mm_core.py:connect` → `database/money_machine.db`; `state/` |
| Queue | SQLite leased work queue | `mm_pipeline.py` (state machine, leases, retries, DLQ) |
| Supervisor | `launchd` + `./mm supervisor` | `money-machine/supervisor/cli.py`, `daemon.py`, `launchd.py` |
| Orchestrator | Hermes | CLAUDE.md; `auditor_toolkit/agency_cli.py` |
| Human workspace | Obsidian (`WEBSITE-AUDITOR-BRAIN`) | CLAUDE.md; never runtime authority |
| Model routing | `mm_model_router.py` — FCC first, Hermes free-role second, DEFER otherwise | fail-closed; `probe_fcc`, `probe_hermes`, `local_complete` |
| Transport gate | Fail-closed; `HUMAN_APPROVAL_REQUIRED` | `outreach/execution_gate.py`, `catalyx_send.py`, `send.py`; `test_p14_transport_gate.py` |

---

## Findings register

Each finding: source file/location, evidence, root cause, proposed solution, expected benefit, risk, tests required, dependencies, overlap with P0–P14.

### F-01 (MEDIUM) Fragile top-level module import — `email_baseline_capture`

**Location:** `money-machine/mm_email_network.py:13`; also `mm_contact_review_network.py:16`, `mm_recurring_contact_review.py:30`, `email_fresh_validation.py:13`.

**Evidence:** `from email_baseline_capture import clean_url, get_public, CONTACT_PATHS` imports a sibling script as a top-level module. It works only when `money-machine/` is on `sys.path` or cwd is `money-machine/`. `mm_operator.py` inserts `money-machine` into `sys.path` for supervisor, but the import is not package-relative and breaks under other entry points (e.g. direct `python module.py` execution, pytest rootdir variations).

**Root cause:** Sibling scripts imported by bare module name instead of package-relative import or explicit path insertion.

**Proposed solution:** Convert `email_baseline_capture.py` into a proper module importable via the package context already established (`sys.path.insert(0, money-machine)` is done by `mm_operator.py` for operator paths; ensure all CLI entry points do the same), or make the import defensive with a fallback `sys.path` insertion guarded by `ModuleNotFoundError`.

**Expected benefit:** Reliable imports across all entry points; no silent `ModuleNotFoundError` in workers/cron.

**Risk:** Low — import relocation is behaviour-preserving.

**Tests required:** Import each affected module from a clean interpreter with cwd outside `money-machine/`; run `money-machine/test_email_integration.py`.

**Dependencies:** None.

**Overlaps P0–P14:** No. P2 (consolidation) touches module boundaries but not this import style.

---

### F-02 (HIGH) Unimplemented analyzer stages not tracked as unimplemented

**Location:** `auditor_toolkit/models.py:10-11` and `:160-161`; `CURRENT_STATE.md` §Implementation and acceptance row "Audit coverage safety and maintenance".

**Evidence:** `UNIMPLEMENTED_STATIC_CHECKS = frozenset()` and `UNIMPLEMENTED_RENDERED_CHECKS = frozenset()` are empty, yet `STATIC_REQUIRED_CHECKS` and `RENDERED_REQUIRED_CHECKS` list checks (e.g. `third_party`, `browser_console`, `cookie_consent`, `axe`, `pdf`, `lighthouse`) whose analyzer bodies CURRENT_STATE records as unimplemented ("The seven analyzer bodies remain unimplemented; the candidate prevents their no-op results from appearing complete"). `coverage_summary`/`current_coverage_gaps` treat any required check with `status != "ok"` as a gap, but nothing records *which* required checks are unimplemented vs. executed-and-passed.

**Root cause:** The "unimplemented" marker sets are empty, so there is no explicit, machine-readable record separating "check exists and passes" from "check stage is unimplemented and intentionally skipped."

**Proposed solution:** Populate `UNIMPLEMENTED_STATIC_CHECKS` / `UNIMPLEMENTED_RENDERED_CHECKS` with the genuinely unimplemented analyzer stage IDs, and gate `current_coverage_gaps` so an unimplemented-but-required check is reported as a coverage gap with an explicit "unimplemented" reason rather than silently failing coverage.

**Expected benefit:** Accurate coverage reporting; no unimplemented stage can be mistaken for a passing check; aligns code with the documented "explicit required/optional skipped coverage" contract.

**Risk:** Low — additive markers; coverage checks already treat missing `ok` as gaps.

**Tests required:** `toolkit_tests/test_audit_coverage.py` should assert unimplemented checks appear in `current_coverage_gaps` with reason; verify `has_current_complete_coverage` returns False when unimplemented required checks exist.

**Dependencies:** `auditor_toolkit/models.py`, `storage.py`, `pipeline.py`.

**Overlaps P0–P14:** Yes — P4 (audit engine) and the Master Plan's "seven audit stages" future implementation. This is a marker fix, not analyzer implementation.

---

### F-03 (MEDIUM) Duplicate audit check definitions in registry

**Location:** `auditor_toolkit/models.py:118-126`.

**Evidence:** `REGISTRY` contains duplicate `CheckDefinition` entries: `"hygiene"` appears twice (lines 117, 125) and `"links"` appears twice (lines 118, 126). `REGISTRY = {d.id: d for d in (...)}` silently deduplicates by `id`, so the later definition wins and the earlier is unreachable/dead.

**Root cause:** Copy-paste in registry construction; dict comprehension hides duplicates.

**Proposed solution:** Remove the duplicate `"hygiene"` and `"links"` entries; add a unit test asserting `len(REGISTRY) == len([d.id for d in ...])` (no silent drops).

**Expected benefit:** Clean registry; no silent definition loss; clearer audit coverage contract.

**Risk:** Very low — duplicates are identical in intent.

**Tests required:** Test registry uniqueness and count.

**Dependencies:** `auditor_toolkit/models.py`.

**Overlaps P0–P14:** No.

---

### F-04 (CRITICAL) Transport/approval safety is fail-closed and well-tested — NO CHANGE NEEDED

**Location:** `outreach/execution_gate.py`, `catalyx_send.py`, `send.py`; `money-machine/mm_core.py` triggers (`mm_message_queue_guard`, `mm_proposal_send`, `mm_stage_guard`, `mm_ready_stage_guard`); `toolkit_tests/test_p14_transport_gate.py`.

**Evidence:** `test_external_release_gate_is_fail_closed` asserts `PermissionError` on `require_external_release()`; SMTP sender never reaches network (`BlockedCost`/`AssertionError`); legacy Gmail sender raises `HUMAN_APPROVAL_REQUIRED`; legacy monthly generator retired (`main() == 2`, writes nothing). SQL triggers block sends without exact approval, verified receipt, and suppression checks. `mm_model_router.py` refuses non-`:free` models, non-loopback FCC endpoints, redirects, and never falls back to paid.

**Root cause:** None — this is a strength.

**Proposed solution:** Preserve. Do not weaken. Add regression test asserting `mm_model_router.local_complete` raises `BlockedCost` when both FCC and Hermes routes are unavailable (DEFER path).

**Expected benefit:** Continued zero-cost guarantee and send safety.

**Risk:** None.

**Tests required:** Extend `test_p15_local_routing.py` with a DEFER test; `test_p14_transport_gate.py` already covers transport.

**Dependencies:** None.

**Overlaps P0–P14:** Preserves P14 (outreach) and P15 (free model router) non-negotiables.

---

### F-05 (MEDIUM) Discovery search lane degrades gracefully but has no local fallback ranking

**Location:** `money-machine/mm_discovery.py` (`searxng_candidates`, `SearchBlocked`); `mm_search_backend.py`.

**Evidence:** `discover-search` catches `mm_discovery.SearchBlocked` and returns empty candidates with a `blocked` note ("Search lane is blocked in this environment; run on a host with a local SearXNG for ranked candidates."). `mm_search_backend.probe` targets `http://127.0.0.1:8888` only. No ranked fallback when SearXNG is unavailable — discovery relies on imports only in this environment.

**Root cause:** SearXNG is optional and not configured on this host (per CLAUDE.md: "Validate optional local SearXNG only when it is configured, and record a clear blocked/deferred state if unavailable").

**Proposed solution:** Record the blocked/deferred state explicitly in `OPUS_EXECUTION_STATE.yaml` and `CURRENT_STATE.md`; no code change required unless SearXNG is configured. The current graceful degradation is correct.

**Expected benefit:** Transparent blocked state; no fabricated discovery results.

**Risk:** None.

**Tests required:** `test_search_backend.py` / `test_discovery.py` already cover probe/ingest behavior.

**Dependencies:** None.

**Overlaps P0–P14:** P6 (NZ discovery) — SearXNG optional lane.

---

### F-06 (LOW) Dead-letter resolution is scoped to test fixtures only

**Location:** `money-machine/mm_operator.py:153-251` (`cmd_dead_letter_resolve`).

**Evidence:** `cmd_dead_letter_resolve` resolves only `b.source='test_import' AND b.is_dummy=1` rows — explicitly "Do not retry them"; real production dead letters in `state/dead-letter/` are handled by `mm_observability.dead_letter()` (read-only listing) but there is no operator command to triage/resolve non-test dead letters.

**Root cause:** Deliberate safety scoping — production DLQ triage remains human/Obsidian-driven.

**Proposed solution:** No code change. Document that DLQ resolution for production items is a manual, gated operator action via Obsidian review queue (P26 dashboard). This matches the "visible dead-letter triage" acceptance criterion.

**Expected benefit:** Clarity that DLQ is human-triaged, not auto-resolved.

**Risk:** None.

**Tests required:** `test_p3_runtime_guards.py` / `test_supervisor.py` cover DLQ listing.

**Dependencies:** None.

**Overlaps P0–P14:** P3 (continuous control plane — DLQ exists).

---

## Ranked priority queue (see OPUS_PRIORITY_UPGRADE_QUEUE.yaml)

| Rank | ID | Severity | Finding |
|---|---|---|---|
| 1 | F-02 | HIGH | Unimplemented analyzer stages not tracked as unimplemented |
| 2 | F-01 | MEDIUM | Fragile `email_baseline_capture` top-level import |
| 3 | F-03 | MEDIUM | Duplicate `hygiene`/`links` registry entries |
| 4 | F-05 | MEDIUM | Discovery SearXNG lane blocked/deferred (documented state) |
| 5 | F-04 | CRITICAL (strength) | Transport/approval fail-closed — preserve, add DEFER regression test |
| 6 | F-06 | LOW | Dead-letter production triage is manual (documented) |

---

## Immediate safe repairs (P15.4)

The following are well-understood, isolated, safe to implement now:

1. **F-03:** Remove duplicate `hygiene`/`links` entries in `auditor_toolkit/models.py:REGISTRY`; add registry-uniqueness test. (Behaviour-preserving.)
2. **F-02:** Populate `UNIMPLEMENTED_STATIC_CHECKS`/`UNIMPLEMENTED_RENDERED_CHECKS` with the seven unimplemented analyzer stage IDs and gate coverage reporting. (Additive markers.)
3. **F-01:** Make `email_baseline_capture` import robust across entry points. (Import relocation.)
4. **F-04:** Add `test_p15_local_routing.py` DEFER regression test (both routes unavailable → `BlockedCost`).

F-04 (transport) and F-06 (DLQ) require no code change — they are documented strengths/constraints.

---

## Evidence commands (re-run to confirm)

```bash
cd /Users/dd/WEBSITE-AUDITOR
.venv/bin/python -m pytest toolkit_tests -q                      # 297 passed, 2 skipped
.venv-email/bin/python money-machine/test_acceptance.py          # 58 passed, 2 skipped
.venv-email/bin/python -c "import sys; sys.path.insert(0,'money-machine'); import mm_email_network"  # import check
./mm doctor --profile research-only                              # db integrity OK; models disabled
```

---

**Next:** Implement F-01/F-02/F-03 repairs, verify with tests, then proceed to P16–P27 deliverables. Each change gets a focused commit with test evidence; nothing is pushed to `master`.

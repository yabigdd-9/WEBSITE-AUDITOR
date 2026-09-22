---
doc_role: "ADDENDUM — corrections and gap-fill. Does NOT replace the canonical plan."
canonical_plan: "/Users/dd/WEBSITE-AUDITOR/docs/SEARXNG_SERVICE_PLAN.md"
canonical_plan_owns: "P0–P4, tasks T0.*–T4.*, Layer A/B design, host setup, rollback, risk register, DoD"
this_doc_owns: "corrections C1–C6 and gaps A1–A11 only"
executor: "FABLE"
date: "2026-09-22"
repo: "/Users/dd/WEBSITE-AUDITOR"
branch: "upgrade/v32-canonical-execution"
constraints: "$0 · no new dependencies · no new system software · loopback only · no sends · fail-closed"
status: "COMPLETE (this file is finished; see §1)"
---

# FABLE — SearXNG lane: addendum, corrections and gap-fill

## 0. Read this first — which plan to execute

Two SearXNG plans exist in this repo. **Execute exactly one.** This file is not a second plan.

| | Canonical plan | This file |
|---|---|---|
| Path | `docs/SEARXNG_SERVICE_PLAN.md` | `docs/FABLE_SEARXNG_SERVICE_PLAN.md` |
| Role | **the plan to execute** | addendum: corrections + gaps it does not cover |
| Size | 639 lines, P0–P4, T0.1–T4.5 | short, A1–A11 |
| Host service | optional P2, human-gated | says nothing; defer to canonical §5 |

Reasoning, already recorded by the canonical plan's own §13:

1. `FABLE_EXECUTION_PLAN.md` v2 **PHASE 3** says: *"SearXNG (P6) — FOLLOW docs/SEARXNG_SERVICE_PLAN.md (it supersedes this section)."*
2. That plan's §13 lists both SearXNG plans, notes ~80% overlap, and states: *"do not execute both… merge the loser's unique content in rather than running both."*
3. It already adopted the five ideas worth keeping from my earlier draft (endpoint resolution order, `state/search_service.json` projection, zero-dependency guard test, degraded-path chaos test, additive-only provenance).

**Result:** canonical plan is binding for the work; this file binds only where it says so below
(`C*` corrections are mandatory, `A*` gaps are additive). The user's stated preference — *free, and
without pulling extra software* — is satisfied by canonical **P0 + P1 + P3 + P4** with **P2 gated to a
human**. Nothing in either document requires a new dependency, a container, or a system package.

If a conflict is ever found between the two documents, **canonical wins** unless the conflicting
statement is one of the `C*` corrections below.

---

## 1. Status note resolving the canonical plan's §632 observation

Canonical §632 records: *"`docs/FABLE_SEARXNG_SERVICE_PLAN.md` ends mid-file at a `<!-- PART-4 -->`
marker, i.e. it was still being written. Verify it is complete and its task IDs do not collide with
`T0.*`–`T4.*` here before starting work."*

Both concerns are now resolved:

| Concern | Status |
|---|---|
| File ends mid-write | **Resolved.** The earlier draft was replaced by this addendum deliberately, not accidentally. It contains no `PART-*` markers. Verify: `grep -c 'PART-' docs/FABLE_SEARXNG_SERVICE_PLAN.md` → `0`. |
| Task-ID collision with `T0.*`–`T4.*` | **Resolved by namespace split.** Canonical keeps `T0.*`–`T4.*` and `P0`–`P4`. This file uses `C1`–`C6` (corrections) and `A1`–`A11` (gaps). No ID is reused. |
| Two plans executed at once | **Forbidden.** Canonical §13.1 and §0 above. |

---

## 2. Corrections (C1–C6) — mandatory, they prevent rework and collisions

These correct my earlier draft, which FABLE may still find quoted in other notes. Where a correction
contradicts my draft, the correction wins.

### C1 — `money-machine/test_discovery.py` is frozen: do not add tests to it

My earlier draft said "extend `test_discovery.py`". **Wrong.** Canonical G1 and §9 freeze that file
and its 12 tests; its rule is *"`searxng_candidates` and its `urlopen` usage are explicitly out of
scope."* Every new assertion goes into `money-machine/test_search_backend.py` (canonical T0.5).

```bash
# frozen-contract check, run before and after every commit
cd /Users/dd/WEBSITE-AUDITOR && .venv-email/bin/python -m pytest money-machine/test_discovery.py -q   # expect: 12 passed
```

### C2 — the module is `mm_search_backend.py`, not `mm_search_service.py`

Canonical T0.2/T0.2b define the module, its constants and its API (`probe`, `cache_*`, `search`).
Do not create a second module with a different name; one layer, one vocabulary.

### C3 — adopt the canonical state vocabulary, not mine

Mine used `DISABLED / CONTRACT_OK / NOT_JSON / UNAVAILABLE / HTTP_ERROR / REJECTED_ENDPOINT`.
Canonical T0.2 already defines the vocabulary that all other code, CLI and docs will use:

```
OK · BLOCKED_ENDPOINT_INVALID · BLOCKED_NOT_LOOPBACK · BLOCKED_NOT_LISTENING · BLOCKED_TIMEOUT
BLOCKED_HTTP_STATUS · BLOCKED_NOT_JSON · BLOCKED_TOO_LARGE · BLOCKED_INVALID_JSON · BLOCKED_CIRCUIT_OPEN
```

Use those exact strings. My names appear nowhere in the shipped code.

### C4 — endpoint/config resolution: canonical order, no second config file

Resolution order is `--endpoint` > `MM_SEARXNG_ENDPOINT` > `http://127.0.0.1:8888` (canonical §13.3).
My earlier `money-machine/config/search_service.json` (with an `enabled` flag) is **withdrawn** —
canonical has no enable-flag concept and adds only `config/search-queries.json` for query templates.
Introducing a second config file would create two sources of truth for the same lane.

### C5 — do not register a new worker in `mm_workers.WORKERS`

My earlier draft proposed a `discovery_search` worker declaring `services=(...)`. Withdrawn, because:

- `WORKERS` values are `(states, handler)` 2-tuples unpacked as `Worker(id, *entry)` in three places —
  `mm_operator.py:332`, `supervisor/cli.py:94`, `mm_pipeline.py:610`. Changing arity risks all three.
- Canonical T3.1 achieves the same safety by wrapping `search()` in `mm_pipeline.RetryableError` at the
  call site, with no registry change.
- Canonical §8 explicitly lists `mm_pipeline.py` DDL/transitions as **do not touch**.

### C6 — the canonical "frozen suite" command is broken (verified)

Canonical §9 tells FABLE to run:

```bash
cd ~/WEBSITE-AUDITOR/money-machine
python3 -m pytest test_discovery.py test_supervisor.py test_pipeline.py -q
```

`money-machine/test_supervisor.py` **does not exist.** Measured on this host 2026-09-22:

```
$ cd money-machine && ../.venv-email/bin/python -m pytest test_discovery.py test_supervisor.py test_pipeline.py -q
ERROR: file or directory not found: test_supervisor.py
no tests ran in 0.00s          real pytest exit = 4
```

The supervisor suite actually lives at `toolkit_tests/test_supervisor.py` (P3 control-plane tests:
start/stop/status/leases/crash recovery, isolated `MM_ROOT` temp workspaces). Verified:

```
$ .venv-email/bin/python -m pytest toolkit_tests/test_supervisor.py -q
4 passed in 13.48s             exit = 0
```

**Use this instead, from the repo root:**

```bash
cd /Users/dd/WEBSITE-AUDITOR
.venv-email/bin/python -m pytest money-machine/test_discovery.py money-machine/test_pipeline.py -q   # 61 passed, exit 0
.venv-email/bin/python -m pytest toolkit_tests/test_supervisor.py -q                                # 4 passed,  exit 0
```

**Why this matters more than a typo:** the broken invocation prints `no tests ran` and, when the output
is piped (e.g. `| tail`), the pipeline's exit status becomes the pager's `0`. A FABLE run could therefore
record "suite green" while **zero** tests ran. Never pipe pytest when you are checking the exit code:

```bash
$P -m pytest <paths> -q >/tmp/pytest.txt 2>&1; echo "exit=$?"; tail -3 /tmp/pytest.txt
```

Counters to expect on this host today: `test_discovery.py` = 12, `test_pipeline.py` = 49 (61 combined),
`toolkit_tests/test_supervisor.py` = 4. If a run reports fewer, it did not run what you think it ran.


---

## 3. Gaps (A1–A11) — additive work the canonical plan does not yet cover

Each gap lists: **what · why it matters · where it lands · test · evidence · done-when.**
Do these *after* the canonical phase they extend is green. No gap may weaken a canonical rule.

### A1 — Zero-dependency guard, sharper than a diff

- **Why:** canonical T4.1/T4.5 *state* "no new dependency"; nothing *enforces* it on every run, so a
  future edit can add `requests` silently.
- **Where:** `money-machine/test_zero_new_dependencies.py` (new, stdlib + `ast`).
- **What:** parse `mm_search_backend.py` and `mm_operator.py`; assert every top-level import is stdlib
  (allow-list) or repo-local; assert no `shell=True`, no `subprocess` in the backend, no
  `ssl._create_unverified_context`, and that the only URL literals in the backend are loopback.
  Add a **planted violator self-test**: a temp module containing `import requests` must fail the audit
  (proves the audit is not vacuous). Compare SHA256 of `requirements.txt`,
  `money-machine/requirements-email.txt`, `pyproject.toml`, `package.json` against the P0 baseline.
- **Evidence:** `reports/search-service/a1-import-audit.txt` showing both the pass and the planted failure.
- **Done-when:** audit green on real modules, red on the planted violator; manifest hash diff empty.

### A2 — Make CI prove *absence handling*, not just "tests pass"

- **Why:** canonical T4.1 wires the new suite into CI, but a green CI with no service running does not
  by itself demonstrate the degraded path that the operator will actually experience. This is the exact
  failure the whole plan exists to fix: green tests, unusable capability.
- **Where:** `.github/workflows/ci.yml` (`full-regression`), one informational step, appended to T4.1.
- **What:**
  ```yaml
  - name: Search lane absence handling (expected: BLOCKED_NOT_LISTENING offline)
    run: |
      python money-machine/mm_operator.py searxng status --json || true
      python money-machine/mm_operator.py searxng verify; echo "verify exit=$? (2 expected offline)"
  ```
  The step must never fail the job — it exists so the job log *contains* the typed state and remedy.
- **Evidence:** the CI log excerpt `a2-ci-absence.txt` (state + exit code visible).
- **Done-when:** job log shows a `BLOCKED_*` state and `exit=2`, with the job still green.

### A3 — Host-acceptance test that skips *truthfully*

- **Why:** canonical §9 requires any live-service test to carry the `slow` marker and stay out of the
  default run, but does not name an opt-in host test or a skip protocol.
- **Where:** `money-machine/test_search_service_host.py` (new); marker already registered —
  `pyproject.toml:65` ("slow: marks tests that spawn background processes and take >10s").
- **What:** gate on `MM_SEARXNG_HOST_TESTS=1`; `pytest.mark.slow`; when the gate is unset **skip** with
  reason `host search service not enabled`; when set and absent, skip with reason
  `service not listening: <state>` — never pass silently, never fake green.
- **Commands:**
  ```bash
  MM_SEARXNG_HOST_TESTS=1 .venv-email/bin/python -m pytest money-machine/test_search_service_host.py -q -rs -m slow
  ```
- **Evidence:** `reports/search-service/a3-host-skip.txt` (skip reasons verbatim).
- **Done-when:** default suite unaffected; opt-in run either exercises the real service or reports a
  named skip reason.

### A4 — Evidence bundle with a hash manifest and a "what was NOT done" section

- **Why:** canonical T4.4 appends raw output to `docs/TOOLKIT_VALIDATION.md`; a reviewer then has to
  hunt across files to confirm the claim. One bundle makes the release gate checkable in one pass.
- **Where:** `reports/search-service/` (new, non-authoritative; **check `.gitignore` first** — canonical
  T0.1 already adds discovery runtime state to it, so match existing conventions rather than adding a new one).
- **What:** `README.md` (scope, commit SHAs, before/after table from A6, every command + exit code,
  the canonical §0 ground-truth table re-run, `DEFERRED/BLOCKED` items with reasons) plus `MANIFEST.sha256`.
- **Commands:** `cd reports/search-service && shasum -a 256 ./* > MANIFEST.sha256 && shasum -a 256 -c MANIFEST.sha256`
- **Done-when:** manifest verifies; every claim in `README.md` links to a file in the bundle.

### A5 — Baseline-mismatch gate (stop, do not "fix")

- **Why:** canonical §0 is a snapshot. If the host has moved (supervisor stopped, service now running on
  8888, tests red), every later measurement is invalid — and the temptation is to "adjust" code instead.
- **Where:** canonical P0 step 1, extended.
- **What:** before any edit, assert: `test_discovery.py` = 12 passed; `./mm health` shows
  `external_sends == 0` and `paid_calls == 0`; `./mm metrics` model cost = 0; `lsof -nP -iTCP:8888 -sTCP:LISTEN`
  still empty. Any mismatch → record `BASELINE_MISMATCH` (§7.2) and stop.
- **Done-when:** the four checks pasted with exit codes into the bundle before the first commit.

### A6 — Put measured numbers in the workpath matrix

- **Why:** canonical §2 lists "Today → After" qualitatively. "Better in every workpath" should be
  falsifiable, not asserted.
- **Where:** canonical §2 matrix (add a `measured` column) or the A4 bundle.
- **What:** for each lane touched (discovery-search, discovery-import, identity, qualification,
  contact, audit, observability, reliability, CI/docs) record a number before and after, e.g.:
  opaque `URLError` count at the CLI boundary `1 → 0`; typed states available `0 → 10`;
  provenance keys on a candidate `2 → 8`; `test_discovery.py` `12 → 12` (unchanged, by design);
  new tests `0 → 12+`; new dependencies `0 → 0`; new system packages `0 → 0`; cost `$0 → $0`;
  sends `0 → 0`.
- **Evidence:** `reports/search-service/a6-delta-table.md`.
- **Done-when:** every row has both numbers and the command that produced them. A row that did not
  improve must say so.

### A7 — Measure the P1 quality claim instead of asserting it

- **Why:** canonical T1.2 (cross-query ranking by `hit_count`) is presented as "repeated hits = stronger
  lead signal". That is a hypothesis. The repo already has a challenger harness
  (`./mm challenger-eval --golden/--baseline/--challenger --min-improvement`).
- **Where:** `money-machine/fixtures/search_service/` (synthetic JSONL), run via `challenger-eval`.
- **What:** compare import-only vs multi-query-ranked candidates on
  unique-canonical-hosts-per-query-budget and precision (share of hosts matching an NZ `.co.nz`/region
  shape). Promote nothing in code; record the verdict **including a "no improvement" verdict**, which is
  a valid result and must be reported as such.
- **Evidence:** `reports/search-service/a7-challenger.json`.
- **Done-when:** a reproducible verdict exists with fixtures committed (synthetic only, no real PII).

### A8 — Prove "no schema drift" mechanically

- **Why:** canonical §8 forbids touching `mm_pipeline.py` DDL and requires additive-only provenance.
  Prose is not proof that a later edit stayed inside the rules.
- **Where:** the existing pipeline tests plus a DDL hash capture.
- **What:** capture `PRAGMA user_version` and a hash of `SELECT name,sql FROM sqlite_master ORDER BY name`
  on a temp copy **before** the work and **after**, and assert equality. Also assert `ingest()` stays
  idempotent: re-running the same candidates yields `duplicates`, never double inserts.
- **Commands:**
  ```bash
  .venv-email/bin/python -m pytest money-machine/test_pipeline.py money-machine/test_discovery.py -q
  ```
- **Evidence:** `reports/search-service/a8-schema-hash.txt` (before/after hashes identical).
- **Done-when:** hashes identical and idempotence proven by test, not by inspection.

### A9 — Keep the error stream clean (the search lane must not flood it)

- **Why:** the v3 addendum already flags error-log flooding (`network_guard` wrote a full row per
  failure cycle). A retrying search lane against an absent service is the next flood source, and a noisy
  `state/errors.jsonl` trains operators to ignore errors.
- **Where:** the typed-state path in `mm_search_backend.py` + wherever errors are appended.
- **What:** one deduplicated error row per (state, endpoint) per cooldown window, with a repeat counter;
  never one row per retry. `BLOCKED_NOT_LISTENING` while the breaker is open must not write at all.
- **Tests:** `test_absent_service_writes_one_error_row_per_window`,
  `test_breaker_open_writes_no_error_rows`.
- **Evidence:** `reports/search-service/a9-errors.jsonl` (row count over N attempts).
- **Done-when:** N attempts against an absent service produce ≤1 row per window, and the row carries
  state, endpoint host, repeat count — no bodies, no secrets.

### A10 — Keep the search lane out of the DLQ's way

- **Why:** the v3 addendum establishes that the 12 dead-lettered items are **test fixtures**
  (`source='test_import'`), not real prospects. Canonical T3.2 sends exhausted search failures to the
  same DLQ. Mixing provider-outage items with fixture noise will re-create exactly the confusion Phase A
  is cleaning up.
- **Where:** canonical T3.2 handling.
- **What:** when a dead-letter is caused by a provider state, tag it (`provider_state: BLOCKED_*`,
  `lane: search`) so `./mm dead-letter` can separate *infrastructure* deferrals from *prospect-quality*
  failures. Do not change the DLQ schema; tag inside the existing detail/payload JSON.
- **Tests:** `test_dead_letter_distinguishes_provider_outage_from_prospect_failure`.
- **Evidence:** `reports/search-service/a10-dlq-tag.txt`.
- **Done-when:** the two categories are separable by a single query with no schema change.

### A11 — Prove rollback, do not promise it

- **Why:** canonical §5.6 defines rollback for the service. Reverting *code* also needs proof, because a
  half-reverted lane (backend present, CLI arg removed) is worse than either end state.
- **Where:** A4 bundle.
- **What:** after each workpath commit, revert it in a scratch copy and re-run the frozen contract plus
  the absence-handling check; paste both outputs. Canonical §5.6 already covers host rollback
  (`stop`/`uninstall` → `BLOCKED_NOT_LISTENING`, all other lanes unchanged).
- **Done-when:** every workpath has a verified revert with pasted evidence, or an explicit
  `REVERT_NOT_VERIFIED` note.

---

## 4. Gates to run before every commit (canonical vocabulary)

| Gate | Command | Must be |
|---|---|---|
| G1 Frozen contract | `.venv-email/bin/python -m pytest money-machine/test_discovery.py -q` | `12 passed`, file unmodified |
| G2 New backend suite | `.venv-email/bin/python -m pytest money-machine/test_search_backend.py -q` | all green, no network |
| G3 Adjacent lanes | `.venv-email/bin/python -m pytest money-machine/test_pipeline.py -q` **and** `.venv-email/bin/python -m pytest toolkit_tests/test_supervisor.py -q` (see C6 — never the canonical `money-machine/test_supervisor.py`, which does not exist) | 49 passed / 4 passed, exit 0 |
| G4 Zero new software | `git diff --stat -- requirements.txt money-machine/requirements-email.txt pyproject.toml package.json` | empty |
| G5 Zero cost / zero sends | `./mm health` → `guards.external_sends == 0`, `paid_calls == 0`; `./mm metrics` cost 0 | holds |
| G6 No schema drift | DDL hash + `PRAGMA user_version` unchanged (A8) | identical |
| G7 Compile | `.venv-email/bin/python -m compileall -q money-machine` | exit 0 |
| G8 Branch discipline | `git --no-pager log --oneline origin/master..HEAD`; `git status --short` has no `state/*`, `*.db`, secrets | clean |

G4, G5 and G8 are absolute. A violation stops the workpath; it is never "fixed later".

---

## 5. Where the A-gaps attach to the canonical phases

| Canonical phase | Attach |
|---|---|
| P0 (T0.1–T0.7) | A5 before starting; A1 after T0.2 lands; A3, A9 with T0.4/T0.7 |
| P1 (T1.1–T1.8) | A6, A7, A8 |
| P2 (host service) | nothing — human-gated; FABLE may print `./mm searxng install-plan` only |
| P3 (T3.1–T3.8) | A10 |
| P4 (T4.1–T4.5) | A2, A4, A11 |

Recommended order (canonical first, gaps interleaved):

```
A5 baseline → P0 → A1 → A3 → A9 → GATE(canonical P0 acceptance)
P1 → A6 → A7 → A8 → GATE(canonical P1 acceptance)
P3 → A10 → GATE
P4 → A2 → A4 → A11 → GATE(canonical §11 DoD)
```

---

## 6. Forbidden claims

If FABLE writes any of these, the workpath fails regardless of test results:

- "SearXNG is installed / running / enabled" — no service is installed by default; check with
  `lsof -nP -iTCP:8888 -sTCP:LISTEN`.
- "The lane works end to end" when only mocked `urlopen` ran. Say: "typed states verified with mocked
  transport; live service not enabled."
- "Host-level configuration is complete" — P2 is human-gated; until a human runs it, the honest state
  is `BLOCKED_NOT_LISTENING`.
- "CI proves the search service works" — CI proves **absence handling** only.
- "Quality improved" without the A7 challenger verdict (including a "no improvement" verdict, which
  must be reported as-is).
- "All tests pass" while omitting skip counts or a `slow`-marked suite that never ran.
- A quoted pytest exit code taken through a pipe (`pytest … | tail`) — that reports the pager's status,
  not the suite's. See C6.

---

## 7. Handoff templates

### 7.1 Workpath record (one per canonical task or A-gap)

```markdown
## <T0.x | A#> — <title>   STATUS: DONE | BLOCKED | DEFERRED | SKIPPED
- Commit: <sha>        Revert: git revert <sha>        Revert verified: yes/no
- Commands: <cmd> → exit <code>          Tests: <file>: n passed / n skipped (reason)
- Measured delta: <before> → <after>     Evidence: <bundle path>
- Not done / still open: <explicit list>
```

### 7.2 `BASELINE_MISMATCH` (A5) — stop, do not edit

```markdown
BASELINE_MISMATCH
Expected: test_discovery.py 12 passed · external_sends 0 · paid_calls 0 · model cost 0 · nothing on 8888
Observed: <paste>
Action: stop. Report the delta. A moved baseline invalidates every number in A6.
```

### 7.3 `HUMAN_EXECUTION_REQUIRED` (canonical P2 only)

```markdown
HUMAN_EXECUTION_REQUIRED
Reason: host service install (P2) is human-gated by the canonical plan.
Prepared for you (in-repo, already committed): scripts/searxng.sh, supervisor/searxng_launchd.py
Commands to review first:  ./mm searxng install-plan
Then, if you approve:      ./mm searxng verify   → expect state OK, loopback bound, JSON enabled
Paste back: the full `./mm searxng verify` output and `lsof -nP -iTCP:8888 -sTCP:LISTEN`
Until then: the lane is BLOCKED_NOT_LISTENING, which is a supported, tested state.
```

---

## 8. Writer serialization and ID namespace

**Namespace map (no collisions):**

| Owner | IDs |
|---|---|
| `docs/SEARXNG_SERVICE_PLAN.md` | `P0`–`P4`, `T0.*`–`T4.*`, its own `G1`–`G12` ground-truth rows |
| `FABLE_EXECUTION_PLAN.md` (+ v3 addendum) | `PHASE 0`–`PHASE 6`, `PHASE A`–`PHASE E` |
| this file | `C1`–`C6`, `A1`–`A11`, and the local gates `G1`–`G8` in §4 |

Because two documents both use the label "G1", always write **"canonical G1"** (ground-truth row) or
**"addendum G1"** (gate in §4). Never a bare "G1" in a report.

**Files multiple plans want to edit — serialize, never parallel-edit:**

| File | Wanted by | Rule |
|---|---|---|
| `money-machine/mm_operator.py` | canonical P0, notes in `FABLE_EXECUTION_PLAN.md` | one writer at a time; commit the search-lane change before another agent edits it |
| `money-machine/mm_discovery.py` | canonical P1, notes in `FABLE_EXECUTION_PLAN.md` | same |
| `docs/TOOLKIT_VALIDATION.md` | canonical T4.4, addendum A4 | append-only, one writer per commit |
| `.gitignore` | canonical T0.1 | exactly as canonical specifies; no new patterns here |
| `docs/FABLE_SEARXNG_SERVICE_PLAN.md` | this file | do not rewrite again; propose edits to the operator |

Standing prohibitions: no push to `master`; no merge of PR #36; no enabling of sends, models, pricing,
approvals or launchd host installs without explicit human approval.

---

## 9. Command index for the A-gaps

```bash
cd /Users/dd/WEBSITE-AUDITOR
P=.venv-email/bin/python

# A5 baseline gate (run BEFORE any edit)
$P -m pytest money-machine/test_discovery.py -q
./mm health; ./mm metrics; lsof -nP -iTCP:8888 -sTCP:LISTEN

# A1 dependency audit
$P -m pytest money-machine/test_zero_new_dependencies.py -q
git diff --stat -- requirements.txt money-machine/requirements-email.txt pyproject.toml package.json

# A3 host acceptance (opt-in, truthful skips)
MM_SEARXNG_HOST_TESTS=1 $P -m pytest money-machine/test_search_service_host.py -q -rs -m slow

# A8 no schema drift + idempotent ingest
$P -m pytest money-machine/test_pipeline.py money-machine/test_discovery.py -q

# A7 quality challenger (verdict may be "no improvement")
./mm challenger-eval --golden money-machine/fixtures/search_service/golden.jsonl \
  --baseline money-machine/fixtures/search_service/baseline.jsonl \
  --challenger money-machine/fixtures/search_service/challenger.jsonl --min-improvement 0.1

# A9 / A10 error-stream and DLQ hygiene
./mm errors | tail -20 ; ./mm dead-letter

# A4 evidence bundle
cd reports/search-service && shasum -a 256 ./* > MANIFEST.sha256 && shasum -a 256 -c MANIFEST.sha256
```

---

## 10. One-line summary for the operator

The canonical plan already makes the SearXNG lane typed, ranked, cached and **useful with zero
installs**, keeping the real service optional and human-gated. This addendum exists only to stop FABLE
from stepping on that work (`C1`–`C6` — frozen tests, one module name, one state vocabulary, one config
source, no new worker, and the verified broken frozen-suite command) and to close eleven proof gaps (`A1`–`A11` — machine-checked zero-dependency,
CI-proven absence handling, truthful skips, hash-manifested evidence, measured deltas, a quality verdict,
schema-hash proof, error-stream and DLQ hygiene, verified rollbacks). Everything stays at $0 with no new
dependency, no container, and no path to a send.

— End of addendum.





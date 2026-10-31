# Authorized local safety upgrade batch

Source revision: c50fc9757d156fdce20a975f3ff0f04e98065af8.
Status: LOCAL_BATCH_IMPLEMENTED_AND_VERIFIED; no release or shared integration.

## Implemented scope

1. PID guard uses a stable file inode, acquires flock before inspecting/writing
   ownership, denies uncertain process inspection, and clears only its owned
   descriptor before close. It deliberately leaves an empty PID file after
   release. Failed contenders cannot unlink ownership, including the empty-file
   creation window. Legacy live PIDs remain respected.
2. SearchBlocked retains structured search-lane metadata and is retryable in
   worker handling. Retry/dead-letter payloads retain it. Source-level collection
   failures retain metadata without creating fake prospect records.
3. Adapted only the reviewed mm_model_router.py cost-stop changes from
   a365d6b1, with explicit user assignment. Missing/invalid/nonzero cost persists
   a stop and prevents fallback or subsequent route probes. Added conservative
   stops for uncertain dispatched requests, billing HTTP errors and exhausted
   quota responses. The stop is never automatically cleared.
4. Watchdog webhook configuration no longer authorizes transmission. Alerts
   remain blocked previews; no live adapter was added. Existing missing-webhook
   skip behavior remains.
5. Opt-in startup manifest checks pin approval input by its expected SHA256,
   source, interpreter, repository, default DB target, config hashes and caller
   scheduler label. It rechecks configs during imports and before dispatch, and
   invalidates receipts when source/config drift is observed on target return.
   Existing source-only CLI behavior remains explicitly SOURCE_ONLY.

## Limits and remaining gates

This is A10-1 startup verification, not complete canonical A10 runtime acceptance.
The scheduler label is caller-provided and matched to the pinned manifest, not
independently verified launchd evidence. The DB identity is the existing default
CLI target; this does not attest every arbitrary SQLite connection. Already
running processes remain UNKNOWN. No continuous watchdog, approved release
activation, live configuration lock, soak or independent acceptance is claimed.

The financial patch is a MoneyMachine router safety latch, not global atomic
financial admission. Standalone FCC bridge/Claude CLI and global Hermes paths
still require assigned ownership, entitlement/quota evidence and shared
admission design. The remaining sixteen a365d6b1 paths are not integrated.
No production/provider configuration or bridge activation was changed.

The five pre-existing skips remain release limitations: two opt-in browser/PDF
cases, one missing Pillow case, global Hermes accounting reconciliation and
independent provider receipt verification. No dependencies were installed.

## Safety and review

All modifications are confined to /Users/dd/WEBSITE-AUDITOR-codex, branch
agents/codex-r00. Exact commits/files are in commits.json. Shared integration
and Opus remain at dfc5dc39; their dirty work is preserved. No push, merge into
shared integration, deployment, service restart, live DB change, production
configuration change or outreach send was performed.

One initial fixture accidentally reached the real fallback child. Its log
records a missing-credential block and no model attempts; catalog access was
attempted. This is not included in a claim of zero provider HTTP requests.
The fixture and subprocess isolation were corrected; see
test-isolation-incident.json. No model dispatch is recorded for the child.

Claude's supplied review predates this source batch. It does not approve these
new changes. CLAUDE_REVIEW_RECONCILIATION.md explains the exact test targets and
why older counts and toolkit-only counts differ from the pinned full suites.

## Final frozen verification

- canonical: 1139 passed, 3 skipped, 2 warnings in 124.25s (0:02:04); receipt duration 125.134 seconds.
- money: 715 passed, 2 skipped, 83 subtests passed in 101.26s (0:01:41); receipt duration 101.903 seconds.

Both suites ran sequentially at the exact source revision above with synthetic
DBs, isolated temporary directories, inherited credential variables removed,
no-send/no-paid flags, and zero source/loaded-code mismatches. The parent probe
does not certify child process execution or production runtime. Canonical lint,
new-file lint, scoped router lint and installed dependency check passed. See
checks.json for the retained pre-existing router lint limitation.

## Controlled integration

Do not repeat Claude cherry-picks: shared dfc5dc39 is already an ancestor.
Review the complete current Codex candidate and its six source/test commits.
Preserve and assign the shared checkout's seven modified and 241 untracked
files before any authorized update. Under unchanged ancestry, integrate the
accepted candidate by fast-forward after a clean isolated replay. Do not mix
the preserved dirty changes into that acceptance; review them independently.
No branch promotion or live activation is authorized by this report.

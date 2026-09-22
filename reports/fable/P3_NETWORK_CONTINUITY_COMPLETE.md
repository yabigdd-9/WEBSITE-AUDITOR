# P3 — NETWORK GUARD & SELF-HEALING CONTINUITY — COMPLETE
**Date:** 2026-09-22 · **Branch:** upgrade/v32-canonical-execution · **Cost:** $0 · **New deps:** ZERO

## Changes
1. **Multi-probe guard** (`money-machine/mm_runtime_guards.py`): `MM_NETWORK_PROBE_HOSTS`
   (comma-separated `host:port`, default `example.com:443`) tried in order with
   per-attempt timeout; success if ANY responds. Legacy `MM_NETWORK_PROBE_HOST` and
   `host=` callers still work. Injected `resolver`/`connector` for tests bypass cache.
2. **60s result cache** (`state/network_guard.json`): repeated callers within the TTL
   share one probe outcome (`"cached": true`). Degraded log rows deduped: at most one
   per TTL window AND at most one per `MM_NETWORK_LOG_DEDUP` (default 3600s) while
   continuously degraded; `network_recovered` logged once on flip back to ok.
   Fixes the observed flood (was 1 `network_guard` row / 5 min / forever: 41 stale rows
   in `mm errors` history; new code emits ≤1/hour while degraded).
3. **Degraded mode surfaced**: `mm health` gains
   `"network": {"mode": "ok|degraded|unknown", "since": ..., "checked_at": ...}`
   (read-only, never opens a socket).
4. **Deferred workers still heartbeat**: proven by
   `test_deferred_worker_still_heartbeats` — `heartbeat()` runs after every item
   outcome (incl. RetryableError deferral) at `mm_pipeline.py:685`; supervisor reaps
   only on `2 * lease_seconds` staleness.
5. **`./mm supervisor ensure-running`**: idempotent start-if-dead, no-op-if-alive
   (`supervisor/cli.py cmd_ensure_running`); single-instance guaranteed by PID lock +
   flock in `_run-foreground`.
6. **Cron continuity** (installed, user crontab):
   ```
   */5 * * * * cd /Users/dd/WEBSITE-AUDITOR && ./mm supervisor ensure-running >> state/ensure-running.log 2>&1
   @reboot cd /Users/dd/WEBSITE-AUDITOR && ./mm supervisor ensure-running >> state/ensure-running.log 2>&1
   ```
   Removal: `crontab -e`, delete both lines (documented in RUNBOOK, P7).

## Tests (11, all passing)
`test_network_guard.py`: multi-probe fallback, all-fail action, env host order,
dedupe within TTL, dedupe while continuously degraded, recovery logged once,
status modes, deferred-worker heartbeat, ensure-running no-op-when-alive,
ensure-running no-duplicate-starts, health reports network mode.

## GATE evidence
- **kill -9 self-recovery:** killed supervisor PID 26743 at ~23:45 local;
  status immediately `running: false, pid: null`; cron `ensure-running`
  recovered it with **NEW pid 83670** at 23:50:01 local (≤5 min) — poller log
  showed continuous `running: true, pid: 83670` from first recovery poll onward.
- **No duplicate workers:** post-recovery `ps` revealed 3 stale Python 3.14
  `_run-foreground` processes from 2026-09-21 (pre-flock era, wrong runtime —
  global 3.14 is forbidden by iron constraint 2). Killed (50133/49924/49976).
  Exactly one supervisor remains: 83670 (.venv-email 3.11). Queue unaffected.
- **Network rows:** 0 `network_degraded` rows since new code; historical flood
  rows predate the fix.
- **Safety:** `./mm health` → `external_sends: 0`, `paid_calls: 0` (asserted).
- Suites: test_network_guard 11/11; test_pipeline 49; test_quarantine 4;
  test_dedupe 7; test_error_tracking 5; test_discovery 12; toolkit supervisor 4;
  acceptance 56 passed / 2 skipped (documented BLOCKED). compileall clean.

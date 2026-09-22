# RUNBOOK — WEBSITE-AUDITOR / Money-Machine (v32 canonical execution)

Human decisions only. Nothing in this runbook sends, publishes, or prices to a customer.
Runtime: Python 3.11 in `.venv-email` (never "fix" with global 3.14). All commands run from `/Users/dd/WEBSITE-AUDITOR`.

## 1. DLQ disposition decision tree

`./mm dead-letter` to list. For each item, in order:

1. **Is it a test fixture?** (`source='test_import'`, names like `Acme Corporation`, `not-a-url`, ids formerly 29–40)
   → `./mm dead-letter resolve --all --reason test_fixture` (never raw SQL). Fixtures are quarantined (`is_dummy=1`), never deleted.
2. **Is the failure a bare-domain / malformed URL?** Intake-time normalizer (P2) now fixes this class.
   If one appears anyway: record reason, fix at intake, resolve as `intake_url_defect`.
3. **Is it `site unreachable` / network?** Check `./mm health` network mode. If degraded, wait for recovery
   (guard self-heals; max 1 `network_degraded` row per 60s TTL). Resolve as `transient_network` only after the site
   is reachable or the prospect is suppressed.
4. **Real prospect, real failure** → fix root cause in code, then `./mm dead-letter resolve --id <id> --reason <root-cause-id>`.
5. **Never** delete DLQ rows, never bulk-UPDATE outside the CLI, never resolve without a recorded reason (every transition stores reason + timestamp).

## 2. Test-data quarantine

- `./mm data-quarantine --source test_import` → sets `is_dummy=1` + suppression reason `test_fixture`; quarantined rows
  are excluded from leased queue, funnel metrics, and reports. Idempotent; always run `./mm backup` first.
- A quarantined prospect can never re-enter the queue; re-import of the same fixture adds 0 dupes (dedupe, P2).

## 3. Supervisor: restart / stale lease / PID lock

- Status: `./mm health` (shows pid, heartbeat age, network mode, alerts) or `ps aux | grep '[s]upervisor'`.
- **Expected: exactly one supervisor process** running under `.venv-email` (Python 3.11).
- Dead: `./mm supervisor start` (or `./mm supervisor ensure-running` — idempotent start-if-dead, no-op-if-alive).
- **kill -9 recovery:** cron re-spawns within 5 min via the ensure-running line (below). No duplicate workers; no queue dupes.
- **Stale lease:** leases expire (`lease_until`); a worker that died mid-lease releases after expiry. If a lease looks
  stuck past expiry, check the worker heartbeat file under `state/worker-heartbeats/` before touching anything.
- **PID lock removal:** only when `state/supervisor.pid` names a process that no longer exists
  (`kill -0 $(cat state/supervisor.pid)` fails). Then `rm state/supervisor.pid` and `./mm supervisor ensure-running`.
  Never remove the pidfile while a live process holds it.
- Stale-process hygiene: `ps aux | grep '[s]upervisor'` may match multiple; confirm cwd with
  `lsof -p <PID> | awk '$4=="cwd"'` before killing strays (e.g. pre-flock Python 3.14 leftovers).

## 4. Continuity cron (ensure-running) — install & removal

Installed (one line, built into macOS, plus @reboot):
```
*/5 * * * * cd /Users/dd/WEBSITE-AUDITOR && ./mm supervisor ensure-running >> state/ensure-running.log 2>&1
@reboot cd /Users/dd/WEBSITE-AUDITOR && ./mm supervisor ensure-running >> state/ensure-running.log 2>&1
```
- Install: `crontab -e`, add both lines. Verify: `kill -9 <supervisor_pid>` → new PID within 5 min, no duplicates.
- **Removal:** `crontab -e`, delete both lines, save. Then `./mm supervisor stop` if you want it fully down.
- Log: `state/ensure-running.log` (tail it to see no-op vs start events).

## 5. Sandbox vs host capability table

| Capability | Sandbox (this Mac, no route) | Host (full network) |
|---|---|---|
| Loopback sockets (127.0.0.1) | ✅ works | ✅ works |
| DNS / external sockets | ❌ `network_degraded` guard rows expected | ✅ |
| SearXNG (127.0.0.1:8888) | ❌ absent → typed `BLOCKED_SEARCH_SERVICE_ABSENT` | ✅ if service running |
| Own-site contact crawl | ❌ typed `BLOCKED_SITE_*` attempts recorded | ✅ |
| Playwright / browser e2e | ❌ (skipped) | ✅ |
| Discovery tests (frozen 12) | ✅ pass | ✅ pass |
| Email send transport | ❌ none (fail-closed, cap 0) | ❌ must stay none |
| launchd install | ❌ blocked | optional; cron is the supported path |

`./mm doctor` prints live capabilities so "why skipped" is one command away. Test skips are explicit
(`BLOCKED_FIXTURE: <path> not present in this environment`) — never silently green.

## 6. Backup / restore

- Backup: `./mm backup` → checksummed copy under `database/backups/`. **Always run before any migration or bulk change.**
- Restore: stop the supervisor, replace `database/money_machine.db` with the chosen backup, run `./mm doctor` and
  `./mm health`, then `./mm supervisor ensure-running`. Verify `PRAGMA integrity_check` = ok before restarting workers.
- Log/jsonl retention: `./mm rotate-logs` gzips `state/errors.jsonl` + `state/metrics.jsonl` older than 30 days
  into `state/archive/` (also automatic during `mm report daily`).

## 7. Reporting & alerting

- `./mm report daily` → `reports/YYYY-MM-DD.md` with the safety attestation (`external_sends: 0 · model_calls: 0 · model_cost_usd: 0.0`).
- Alert rules live in `state/alert-rules.yaml` (flat `key: threshold`):
  `dead_lettered_growth_per_hour_max`, `disk_free_mb_min`, `heartbeat_age_seconds_max`.
  Evaluated in `./mm health` (`"alerts": [...]`), `./mm alerts`, and the daily report.
- Non-zero alert in health = investigate before any queue work.

## 8. Iron rules (from the master plan — restated for operators)

$0 spend (`paid_allowed=false`, never set `MM_ALLOW_EXTERNAL_FREE_MODELS=1`) · zero new software/deps ·
fail-closed transport (`external_send_allowed=false`, `daily_cap=0`) · loopback-only probes ·
one writer per file · never commit `state/*`, `*.db`, `.env`, reports outputs, caches, secrets ·
human-only: external sends, model enablement, pricing to customers, approvals, launchd, SearXNG host service, master merges, remote pushes.

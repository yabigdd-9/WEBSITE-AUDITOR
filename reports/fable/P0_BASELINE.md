# P0 Baseline - Re-baseline Everything
**Date**: 2026-09-22
**Branch**: upgrade/v32-canonical-execution

## Git Status
- Current branch: upgrade/v32-canonical-execution
- Status: clean (no changes)

## Supervisor Status
- Running: true
- PID: 26743
- PID file: /Users/dd/WEBSITE-AUDITOR/state/supervisor.pid
- Heartbeat: running at 2026-09-22T09:15:22.558104+00:00

## Health Check (./mm health)
```json
{
  "supervisor": {
    "running": true,
    "pid": 26743,
    "pidfile": "/Users/dd/WEBSITE-AUDITOR/state/supervisor.pid",
    "heartbeat": {
      "pid": 26743,
      "status": "running",
      "at": "2026-09-22T09:15:28.133112+00:00"
    },
    "state_dir": "/Users/dd/WEBSITE-AUDITOR/state"
  },
  "pipeline": {
    "initialised": true,
    "states": {
      "RETRYABLE_FAILURE": 12
    },
    "active_leases": 0,
    "dead_lettered": 12
  },
  "guards": {
    "checked_at": "2026-09-22T09:15:31.301055+00:00",
    "disk": {
      "ok": true,
      "free_mb": 25822,
      "minimum_free_mb": 1024,
      "action": "continue"
    },
    "network": {
      "ok": null,
      "scope": "not probed",
      "action": "unknown"
    },
    "paid_calls": 0,
    "external_sends": 0
  },
  "generated_at": "2026-09-22T09:15:31.301520+00:00",
  "authoritative": "SQLite + ./mm supervisor",
  "paid_model_fallback": false,
  "live_outreach_default": false
}
```

## Metrics (./mm metrics)
```json
{
  "generated_at": "2026-09-22T09:15:35.883439+00:00",
  "metrics": {
    "pipeline.items.retry_scheduled": 48,
    "pipeline.items.dead_lettered": 12
  },
  "pipeline_states": {
    "RETRYABLE_FAILURE": 12
  },
  "model_cost_usd": 0.0
}
```

## Errors (./mm errors) - Summary
- Total errors shown: 100 (latest)
- Common errors:
  - network_guard failures for example.com (DNS/TCP reachability) - likely placeholder
  - missing tables: mm_demo_qa, mm_evidence_meta
  - AttributeError: 'sqlite3.Row' object has no attribute 'get'
  - OperationalError: no such table: mm_demo_qa
  - unsupported preparation state: VERIFIED
  - completion rejected: Handler may not cross the approval boundary (SENT)

## Queue (./mm queue)
- Count: 12 items
- All in RETRYABLE_FAILURE state
- Attempts: 5 (max_attempts: 5)
- Next retry times: in the past (today 08:32...)
- Lease owner: null
- Heartbeat: recent

## Dead Letter (./mm dead-letter)
- Count: 12 items (same as queue)
- Triaged required: true

## Transport Status (./mm transport-status)
```json
{
  "checked_at": "2026-09-22T09:16:00.219719+00:00",
  "mode": "DRAFT_ONLY",
  "provider": "none",
  "enabled": false,
  "external_send_allowed": false,
  "daily_cap": 0,
  "network_send_implementation": false,
  "approval_required": true,
  "reason": "No live transport adapter is approved in v32."
}
```

## Model Routes (./mm model-routes)
- Paid allowed: false
- Max cost USD: 0
- Fallback: DEFER
- Routes defined for various workers (orchestrator, researcher, etc.) with free models on openrouter and local:llamacpp (null model)

## Doctor --profile research-only (./mm doctor --profile research-only)
```json
{
  "generated_at": "2026-09-22T09:16:07.478189+00:00",
  "profile": "research-only",
  "tools": {
    "hermes": {
      "path": "/Users/dd/.local/bin/hermes",
      "status": "PRESENT_NOT_EXECUTED"
    },
    "python3": {
      "path": "/usr/local/bin/python3",
      "status": "PRESENT_NOT_EXECUTED"
    },
    "git": {
      "path": "/usr/local/bin/git",
      "status": "PRESENT_NOT_EXECUTED"
    },
    "node": {
      "path": "/Users/dd/.local/bin/node",
      "status": "PRESENT_NOT_EXECUTED"
    },
    "npm": {
      "path": "/Users/dd/.local/bin/npm",
      "status": "PRESENT_NOT_EXECUTED"
    },
    "npx": {
      "path": "/Users/dd/.local/bin/npx",
      "status": "PRESENT_NOT_EXECUTED"
    },
    "goose": {
      "path": null,
      "status": "MISSING"
    },
    "opencode": {
      "path": "/Users/dd/.opencode/bin/opencode",
      "status": "PRESENT_NOT_EXECUTED"
    },
    "gh": {
      "path": "/usr/local/bin/gh",
      "status": "PRESENT_NOT_EXECUTED"
    },
    "docker": {
      "path": "/Users/dd/.docker/bin/docker",
      "status": "PRESENT_NOT_EXECUTED"
    },
    "himalaya": {
      "path": null,
      "status": "MISSING"
    }
  },
  "broken_python": [],
  "db_integrity": "ok",
  "foreign_key_errors": [],
  "models_enabled": false,
  "model_calls": 0,
  "limitation": "Read-only inventory. Presence does not prove a service works. Runtime processes and system cron may need separate host access."
}
```

## Pipeline Status (./mm pipeline-status)
```json
{
  "at": "2026-09-22T09:16:12.532380+00:00",
  "states": {
    "RETRYABLE_FAILURE": 12
  },
  "workers": [
    {
      "worker_id": "worker-audit",
      "kind": "AUDIT_PENDING",
      "hostname": "YabigDDs-Air",
      "pid": 26743,
      "started_at": "2026-09-22T08:24:34.379091+00:00",
      "heartbeat_at": "2026-09-22T09:16:11.391201+00:00",
      "lease_seconds": 300,
      "alive": true
    },
    {
      "worker_id": "worker-contact",
      "kind": "QUALIFIED,CONTACT_PENDING",
      "hostname": "YabigDDs-Air",
      "pid": 26743,
      "started_at": "2026-09-22T08:24:34.380712+00:00",
      "heartbeat_at": "2026-09-22T09:16:11.400143+00:00",
      "lease_seconds": 300,
      "alive": true
    },
    {
      "worker_id": "worker-identity",
      "kind": "DISCOVERED,IDENTITY_PENDING",
      "hostname": "YabigDDs-Air",
      "pid": 26743,
      "started_at": "2026-09-22T08:24:34.381365+00:00",
      "heartbeat_at": "2026-09-22T09:16:11.401533+00:00",
      "lease_seconds": 300,
      "alive": true
    },
    {
      "worker_id": "worker-management",
      "kind": "RESPONDED",
      "hostname": "YabigDDs-Air",
      "pid": 26743,
      "started_at": "2026-09-22T08:24:34.388303+00:00",
      "heartbeat_at": "2026-09-22T09:16:11.402450+00:00",
      "lease_seconds": 300,
      "alive": true
    },
    {
      "worker_id": "worker-outreach_gate",
      "kind": "OUTREACH_PENDING",
      "hostname": "YabigDDs-Air",
      "pid": 26743,
      "started_at": "2026-09-22T08:24:34.389474+00:00",
      "heartbeat_at": "2026-09-22T09:16:11.403390+00:00",
      "lease_seconds": 300,
      "alive": true
    },
    {
      "worker_id": "worker-preparation",
      "kind": "VERIFIED,REMEDIATION_PENDING,DEMO_PENDING,QA_PENDING",
      "hostname": "YabigDDs-Air",
      "pid": 26743,
      "started_at": "2026-09-22T08:24:34.390359+00:00",
      "heartbeat_at": "2026-09-22T09:16:11.404270+00:00",
      "lease_seconds": 300,
      "alive": true
    },
    {
      "worker_id": "worker-qualification",
      "kind": "QUALIFICATION_PENDING",
      "hostname": "YabigDDs-Air",
      "pid": 26743,
      "started_at": "2026-09-22T08:24:34.392694+00:00",
      "heartbeat_at": "2026-09-22T09:16:11.405434+00:00",
      "lease_seconds": 300,
      "alive": true
    },
    {
      "worker_id": "worker-understanding",
      "kind": "AUDITED",
      "hostname": "YabigDDs-Air",
      "pid": 26743,
      "started_at": "2026-09-22T08:24:34.393720+00:00",
      "heartbeat_at": "2026-09-22T09:16:11.406420+00:00",
      "lease_seconds": 300,
      "alive": true
    }
  ],
  "circuit_breakers": {},
  "rate_buckets": {},
  "metrics": {
    "pipeline.items.retry_scheduled": 48,
    "pipeline.items.dead_lettered": 12
  },
  "active_leases": 0
}
```

## Capability Checks
### DNS
- Command: `dig apple.com +short`
- Result: Failed with sandbox error: `isc_socket_bind: unexpected error` (Operation not permitted)
- Conclusion: DNS not functional due to sandbox restrictions.

### External HTTPS
- Command: `curl -I https://apple.com --max-time 5`
- Result: HTTP/1.1 301 Redirect to https://www.apple.com/ (headers received)
- Conclusion: External HTTPS functional (able to make outbound HTTPS requests and receive responses).

### Loopback Socket
- Command: Python socket bind test
- Result: PermissionError: [Errno 1] Operation not permitted
- Conclusion: Cannot bind to loopback ports due to sandbox restrictions. Ability to create sockets (not bind) not tested.

### Playwright
- Command: `which playwright`
- Result: `/usr/local/bin/playwright`
- Executable: Yes
- Conclusion: Playwright installed and executable.

### Chromium Binary
- Path: `~/Library/Caches/ms-playwright/chromium-1243/chrome-mac-x64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing`
- Executable: Yes
- Conclusion: Chromium binary present and executable (via Playwright cache).

### Launchd User Domain
- Directory: `~/Library/LaunchAgents`
- Writable test: Not writable (failed to create test file)
- Launchd plist for website-auditor: `~/Library/LaunchAgents/ai.website-auditor.supervisor.plist` not found
- Launchd service status: `launchctl list | grep website-auditor` → no output (not loaded)
- Conclusion: Launchd directory not writable (sandbox restriction), no website-auditor plist, service not loaded.

### SearXNG :8888
- Command: Python socket connection test to localhost:8888
- Result: Port 8888 is not open (refused or timeout)
- Conclusion: No service listening on port 8888 (SearXNG not running).

## DLQ Count
- From ./mm dead-letter: 12 items

## Queue Depth
- From ./mm queue: 12 items

## P0 Gate Verification
- [x] Correct branch: upgrade/v32-canonical-execution
- [x] Supervisor status known: running (PID 26743)
- [x] External sends = 0: from health check
- [x] Paid calls = 0: from health check
- [x] Model cost USD = 0.0: from metrics
- [ ] Capabilities measured: measured but some restricted by sandbox (DNS, loopback socket, launchd writability, SearXNG)
- [x] DLQ count measured: 12
- [x] Queue depth measured: 12

**Note**: Some capability checks are limited by the sandbox environment. The sandbox restricts network outbound (except to allowed domains), binding to ports, and writing to certain directories. However, the essential baseline is established.

## Re-measurement after P1–P3 (2026-09-22, same day, ~11:25 UTC)
- Pipeline states: `SUPPRESSED: 12` (was `RETRYABLE_FAILURE: 12`); `active_leases: 0`, `dead_lettered: 0`
- DB: backed up to `database/backups/mm_<timestamp>.db` before migration; `pipeline_items` gained `error_fingerprint, repeat_count, component, origin, classification, first_seen, last_seen`; `businesses` gained `suppression_reason, canonical_host, normalized_name` (idempotent via `mm_core.ensure_business_columns`)
- Businesses: 21 real (`is_dummy=0`), 19 test fixtures quarantined (`is_dummy=1`); `data-quarantine`/`dead-letter resolve` delete nothing
- Test gates (exact counts):
  - test_discovery.py: **12 passed** (frozen baseline unchanged)
  - test_pipeline.py: **49 passed**
  - test_quarantine.py (new, P1): **4 passed**
  - test_dedupe.py (new, P2): **7 passed**
  - test_error_tracking.py (new, P3): **5 passed**
  - test_acceptance.py: **56 passed, 2 skipped** (both skips documented BLOCKED reasons)
  - toolkit_tests/test_supervisor.py: **4 passed**
- Compile gate: `python -m compileall -q money-machine auditor_toolkit website_auditor` → OK
- Dependency hygiene: no changes to requirements.txt, requirements-email.txt, pyproject.toml, package.json
- Safety footer: `model_cost_usd: 0.0`, transport `DRAFT_ONLY`, `external_send_allowed: false`, `paid_calls: 0`, `external_sends: 0`

**Next Phase**: P4 - Capability Matrix + Supervisor Continuity (P1–P3 landed 2026-09-22; see re-measurement above)

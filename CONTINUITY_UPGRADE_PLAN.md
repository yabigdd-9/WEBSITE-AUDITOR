# CONTINUITY UPGRADE PLAN
## WEBSITE-AUDITOR / MONEY-MACHINE Repository
## Version: 1.0 | Date: 2026-09-20

---

## EXECUTIVE SUMMARY

This plan outlines the upgrades needed to make the Money-Machine pipeline truly continuous, self-healing, and production-ready. Based on a deep scan of the repository, the system already has strong foundations (deterministic pipeline, leased workers, circuit breakers, rate limiting, evidence-gated approvals) but lacks the operational scaffolding for true continuous operation.

**Current State**: Core pipeline is green (52 tests pass), schema drift is handled, drift-first start-up works, basic CLI exists.
**Target State**: Fully supervised, self-healing, zero-babysitting pipeline with observable health, graceful degradation, and documented runbooks.

---

## 1. ARCHITECTURE GAPS IDENTIFIED

| Area | Current State | Gap | Priority |
|------|---------------|-----|----------|
| Process Supervision | run_pipelineloop exists but no daemon mode, PID management, log rotation | No unattended operation possible | P0 |
| Inference Resilience | Single-shot probe; brief llama.cpp outage blocks queue | No retry/backoff + fallback cache | P0 |
| Health Observability | health() returns dict; no CLI, no periodic snapshots, no alerting | No passive monitoring | P1 |
| Log Management | JSONL to state/worker-logs/; no rotation, no retention, no structured query | Disk growth, hard to debug | P1 |
| Configuration Drift | routing.yaml exists but no hot-reload or validation on change | Manual restart required | P1 |
| Secret Management | Gmail OAuth token read from disk; no rotation, no vault | Credential exposure risk | P1 |
| Database Migrations | migrate() is idempotent but no version tracking table | Hard to track applied migrations | P2 |
| Dead Letter Visibility | RETRYABLE_FAILURE/PERMANENT_FAILURE states exist but no triage UI/CLI | Manual SQL required to triage | P2 |
| Worker Hot Reload | Workers defined in mm_workers.py; change requires restart | No hot-reload | P2 |
| Documentation | Excellent technical docs but no operator runbook | New operators blocked | P2 |

---

## 2. UPGRADE PLAN - PHASE P0

### P0.1 - Implement Supervisor Daemon Class
Files: money-machine/supervisor/__init__.py, money-machine/supervisor/daemon.py, money-machine/supervisor/pid.py, money-machine/supervisor/logrotate.py
Description: Create a SupervisorDaemon class that manages PID file with atomic write + lock, registers SIGTERM/SIGINT handlers for graceful shutdown, rotates JSONL logs by size (50MB default) and time (daily), maintains worker registry with heartbeat monitoring, exposes start/stop/status/restart CLI.
Tests: test_daemon_start_stop, test_pid_lock_prevents_dual_start, test_log_rotation_by_size, test_graceful_shutdown_on_sigterm

### P0.2 - Wire mm run-pipeline --daemon CLI
Files: money-machine/mm_operator.py
Description: Extend pipeline-run subcommand with --daemon flag, --pid-file, --log-dir, --max-cycles, --sleep, --report-every flags.
Tests: test_daemon_flag_parsing, test_pid_file_created_on_start, test_graceful_shutdown_on_sigterm

### P0.3 - Log Rotation & Retention
Files: money-machine/supervisor/logrotate.py
Description: Implement size-based (50MB default) + daily rotation with compressed archives (.jsonl.gz), configurable retention (default 30 days, max 100 files), atomic rotate, manifest index.
Tests: test_rotation_by_size, test_rotation_by_time, test_retention_enforcement, test_manifest_index

### P0.4 - Supervisor Status CLI
Files: money-machine/mm_operator.py
Description: Add mm supervisor-status command that prints PID, uptime, worker count, alive/dead, pipeline state distribution, recent loop cycles, errors, throughput, lease expiration warnings, last log rotation time.

### P0.5 - Bounded Retry with Exponential Backoff
Files: money-machine/mm_model_router.py
Description: Add probe_local_with_retry(kind, max_attempts=3, base_delay=2.0, max_delay=60.0) that retries on connection refused, timeout, HTTP 5xx with exponential backoff: base * 2^attempt + jitter (+/-25%), respects max_delay cap, on exhaustion returns None.

### P0.6 - Last-Known-Good Model Cache
Files: money-machine/mm_model_router.py
Description: Add in-process cache for last successful local model: Key local:{kind} -> model_id, updated on successful probe, used as fallback when probe fails but cache hit, TTL 10 minutes, does NOT persist to disk.

---

## 3. UPGRADE PLAN - PHASE P1

### P1.1 - Passive Health Endpoint
Files: money-machine/mm_pipeline.py, money-machine/mm_operator.py
Description: Add mm pipeline-health --json outputting pipeline state counts, worker registry, lease statistics, circuit breaker states, rate bucket usage, recent errors, loop throughput.

### P1.2 - Structured Log Query CLI
Files: money-machine/supervisor/logquery.py, money-machine/mm_operator.py
Description: Add mm supervisor-logs with filters: --kind, --worker, --since, --level, --json.

### P1.3 - Metrics Export (Prometheus Format)
Files: money-machine/supervisor/metrics.py, money-machine/mm_operator.py
Description: Add mm metrics --prometheus exposing pipeline_items_total{state}, worker_alive{worker_id}, lease_active_total, circuit_breaker_state{service,state}, rate_bucket_usage{bucket,used,cap}, loop_cycles_total, loop_cycle_duration_seconds_bucket.

### P1.4 - Config Hot Reload
Files: money-machine/supervisor/configwatch.py, money-machine/mm_model_router.py
Description: Watch routing.yaml for changes using inotify/kqueue, validate schema, test probes, hot-reload routes, emit event to supervisor log, rollback on validation failure.

### P1.5 - Config Schema Validation
Files: money-machine/config/routing.schema.yaml
Description: Create JSON Schema for routing.yaml: PURPOSE_ROUTES structure validation, provider allowlist enforcement, model format validation (:free suffix for external), local endpoint URL format.

### P1.6 - Secret Rotation Framework
Files: money-machine/secrets/rotate.py, money-machine/outreach/catalyx_send.py
Description: Create rotation CLI for Gmail OAuth token: mm secret rotate gmail, mm secret status gmail, mm secret rotate --dry-run, stores in macOS Keychain with fallback to encrypted file, audit log entry on rotation.

---

## 4. UPGRADE PLAN - PHASE P2

---

## 5. IMPLEMENTATION SEQUENCE

1. Create supervisor package skeleton (money-machine/supervisor/)
2. Implement daemon.py + pid.py (PID lock, signal handlers)
3. Wire mm run-pipeline --daemon in mm_operator.py
4. Add retry/backoff to mm_model_router.py
5. Run full suite - ensure no regressions
6. Push to trial/hermes for validation

---

## 6. RISK REGISTER

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Daemon PID lock contention | Medium | High | Atomic PID write, lock file cleanup on startup |
| Log rotation race condition | Low | Medium | Atomic rename, verify before compress |
| Config hot-reload breaks workers | Medium | High | Validation before reload, graceful drain |
| Secret rotation breaks Gmail | Low | High | Dry-run mode, immediate rollback token |
| Circuit breaker false positive | Low | Medium | Tunable threshold, half-open probe |
| Log rotation loses events | Very Low | High | Atomic write, fsync, verify before delete |

---

## 6. SUCCESS CRITERIA

| Metric | Target | Measurement |
|--------|--------|-------------|
| Daemon uptime | > 99.9% over 7 days | mm supervisor-status uptime |
| Loop cycle latency | < 100ms p99 | Prometheus histogram |
| Inference recovery time | < 30s after outage | mm_model_router probe logs |
| Config reload latency | < 5s | Supervisor log timestamp |
| Dead letter triage time | < 2 min | mm dead-letter show |
| Secret rotation time | < 60s | mm secret rotate gmail |
| Doc coverage | 100% commands | grep -r "mm " CONTINUITY_RUNBOOK.md |

---

## 7. FILE CREATION CHECKLIST

### New Files to Create
- money-machine/supervisor/__init__.py
- money-machine/supervisor/daemon.py
- money-machine/supervisor/pid.py
- money-machine/supervisor/logrotate.py
- money-machine/supervisor/logquery.py
- money-machine/supervisor/configwatch.py
- money-machine/supervisor/metrics.py
- money-machine/supervisor/secret_scan.py
- money-machine/supervisor/hotreload.py
- money-machine/supervisor/__init__.py
- money-machine/config/routing.schema.yaml
- money-machine/secrets/rotate.py
- reports/CONTINUITY_RUNBOOK.md
- reports/INCIDENT_RESPONSE.md

### Existing Files to Modify
- money-machine/mm_pipeline.py - add daemon helpers, worker config
- money-machine/mm_operator.py - add CLI commands
- money-machine/mm_model_router.py - retry logic, cache, circuit breaker
- money-machine/mm_pipeline.py - health endpoint, metrics
- money-machine/mm_operator.py - new CLI subcommands
- money-machine/mm_model_router.py - retry logic, cache, circuit breaker
- money-machine/outreach/catalyx_send.py - secret rotation hook
- money-machine/mm_core.py - migration version table

---

## 8. IMMEDIATE NEXT STEPS

1. Create supervisor package skeleton (money-machine/supervisor/)
2. Implement daemon.py + pid.py (PID lock, signal handlers)
3. Wire mm run-pipeline --daemon in mm_operator.py
4. Add retry/backoff to mm_model_router.py
5. Run full suite - ensure no regressions
6. Push to trial/hermes for validation

---

*End of Continuity Upgrade Plan*
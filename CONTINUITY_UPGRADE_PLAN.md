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

### P0.7 - Circuit Breaker for Local Inference
Files: money-machine/mm_model_router.py, money-machine/mm_pipeline.py
Description: Wrap local probe with existing circuit breaker: service name local:llamacpp/local:ollama, failure threshold 5, cooldown 5 minutes, half-open probe after cooldown.
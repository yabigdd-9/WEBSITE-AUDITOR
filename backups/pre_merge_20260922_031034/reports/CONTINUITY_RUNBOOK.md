# CONTINUITY RUNBOOK
## Money Machine Pipeline Operations

---

## QUICK START

```bash
# Start continuous pipeline (daemon mode)
mm run-pipeline --daemon --cycles 0 --sleep 60

# Run bounded cycles (for testing)
mm run-pipeline --cycles 10 --sleep 30

# Check pipeline health
mm pipeline-health --json

# View supervisor status
mm supervisor-status

# Query logs
mm supervisor-logs --since 1h --kind loop_cycle
```

---

## HEALTH CHECKS

### Pipeline Health
```bash
mm pipeline-health --json
```
Returns: state counts, worker registry, lease stats, circuit breakers, rate buckets, recent errors, loop throughput.

### Supervisor Status
```bash
mm supervisor-status
```
Shows: PID, uptime, worker count, alive/dead, state distribution, recent cycles, errors, throughput, lease warnings, last rotation.

### Pipeline State Distribution
```bash
mm pipeline-health --json | jq '.states'
```

### Worker Health
```bash
mm pipeline-health --json | jq '.workers'
```

---

## LOG ANALYSIS

### Recent Loop Cycles
```bash
mm supervisor-logs --kind loop_cycle --limit 20
```

### Filter by Worker
```bash
mm supervisor-logs --worker w-identity --limit 50
```

### Error Search
```bash
mm supervisor-logs --kind loop_error --since 24h
```

### Export for Analysis
```bash
mm supervisor-logs --json --since 24h > logs_24h.json
```

---

## DRIFT RECOVERY

### Schema Drift Repair
Automatic on startup. Manual trigger:
```bash
mm pipeline-migrate  # runs driftfirst_apply()
```

### Check Drift Status
```bash
mm pipeline-health --json | jq '.drift_repair'
```

---

## DEAD LETTER TRIAGE

### List Dead Letters
```bash
mm dead-letter list --state RETRYABLE_FAILURE
mm dead-letter list --state PERMANENT_FAILURE
```

### Inspect Business
```bash
mm dead-letter show <business_id>
```

### Retry
```bash
mm dead-letter retry <business_id> --reset-attempts
```

### Suppress
```bash
mm dead-letter suppress <business_id> --reason "No verified email"
```

---

## SECRET ROTATION

### Check Status
```bash
mm secret status gmail
```

### Dry Run Rotation
```bash
mm secret rotate gmail --dry-run
```

### Execute Rotation
```bash
mm secret rotate gmail
```

---

## EMERGENCY STOP

### Graceful Stop
```bash
mm supervisor-stop
```

### Force Stop (if stuck)
```bash
kill -TERM $(cat state/supervisor.pid)
```

---

## COMMON ISSUES

| Issue | Diagnosis | Resolution |
|-------|-----------|------------|
| Pipeline stalled | No cycles for 10+ min | Check `mm supervisor-status`, check worker heartbeats |
| Worker heartbeats lost | `alive: false` in status | Check worker logs, restart with `mm run-pipeline --daemon` |
| Circuit breaker open | `circuit_breaker_state=open` | Check inference logs, wait for half-open probe |
| Database locked | `sqlite3.OperationalError` | Check for concurrent access, run `mm migrate` |
| Inference down | `BLOCKED_COST` in logs | Check llama.cpp process, restart if needed |
| Config validation failed | `config_reload_failed` in logs | Fix routing.yaml, run `mm config-validate` |

---

## METRICS

### Prometheus Export
```bash
mm metrics --prometheus
```

### Key Metrics
- `pipeline_items_total{state}` - items per state
- `worker_alive{worker_id}` - worker health
- `lease_active_total` - active leases
- `circuit_breaker_state{service,state}` - breaker status
- `rate_bucket_usage{bucket,used,cap}` - rate limit usage
- `loop_cycles_total` - total cycles completed
- `loop_cycle_duration_seconds_bucket` - cycle latency histogram

---

## ESCALATION

If issue persists after runbook steps:
1. Check `mm supervisor-logs --kind loop_error --since 1h`
2. Review `state/worker-logs/` for detailed traces
3. Check `mm pipeline-health --json` for system state
4. Escalate to orchestrator with logs and state snapshot

---
*Generated: 2026-09-20 | Version: 1.0*

# INCIDENT RESPONSE RUNBOOK
## Money Machine Pipeline - Incident Response Procedures

---

## INCIDENT CLASSIFICATION

| Severity | Criteria | Response Time |
|----------|----------|---------------|
| SEV-1 | Pipeline completely stopped, data loss risk | Immediate |
| SEV-2 | Degraded performance, partial outage | 15 minutes |
| SEV-3 | Minor issue, workaround exists | 1 hour |
| SEV-4 | Low impact, monitoring only | Next business day |

---

## SCENARIO 1: PIPELINE STALLED

**Symptoms**: No cycles for 10+ minutes, `mm supervisor-status` shows 0 recent cycles

**Diagnosis**:
1. `mm supervisor-status` - check uptime, worker count
2. `mm supervisor-logs --kind loop_error --since 30m`
3. `mm pipeline-health --json` - check state distribution

**Resolution**:
1. If workers dead: `mm run-pipeline --daemon --cycles 0 --sleep 60`
2. If DB locked: Check for concurrent `mm` processes, `mm migrate` to repair
3. If inference down: Check llama.cpp process, restart if needed
3. If queue empty: Check `mm pipeline-health` for items in pending states

**Escalation**: SEV-1 if no recovery in 15 min

---

## SCENARIO 2: WORKER HEARTBEATS LOST

**Symptoms**: `mm supervisor-status` shows workers with `alive: false`

**Diagnosis**:
1. `mm supervisor-logs --worker <worker_id> --since 30m`
2. Check for `loop_error` entries in logs
3. Check `mm pipeline-health --json` for lease expiration

**Resolution**:
1. If worker crashed: Restart with `mm run-pipeline --daemon`
2. If lease expired: `mm pipeline-transition --to <next_state>` to unstick
3. If handler error: Check `mm dead-letter show <business_id>`

**Escalation**: SEV-2 if multiple workers down

---

## SCENARIO 3: CIRCUIT BREAKER OPEN

**Symptoms**: `circuit_breaker_state{service="local:llamacpp",state="open"}` in metrics

**Diagnosis**:
1. `mm pipeline-health --json | jq '.circuit_breakers'`
2. Check `mm_model_router` probe logs for failures
3. Check llama.cpp process: `ps aux | grep llama`

**Resolution**:
1. If llama.cpp down: Restart llama.cpp server
2. Wait for cooldown (5 min) then half-open probe
3. If persistent: Check GPU memory, restart llama.cpp with smaller model

**Escalation**: SEV-2 if no recovery in 30 min

---

## SCENARIO 4: DATABASE LOCKED / CORRUPTION

**Symptoms**: `sqlite3.OperationalError: database is locked` or integrity check fails

**Diagnosis**:
1. `sqlite3 database/money_machine.db "PRAGMA integrity_check"`
2. Check for concurrent `mm` processes: `ps aux | grep mm`
3. Check WAL files: `ls -la database/*.wal database/*.shm`

**Resolution**:
1. Kill all `mm` processes
2. Run `mm migrate` to repair from backup
3. If corruption: Restore from `backups/mm-v2-*/money_machine.db`
4. Verify: `sqlite3 database/money_machine.db "PRAGMA integrity_check"`

**Escalation**: SEV-1 - data integrity at risk

---

## SCENARIO 5: SECRET COMPROMISED

**Symptoms**: Suspicious API activity, unauthorized sends, token in logs

**Diagnosis**:
1. `mm secret status gmail` - check token status
2. Scan logs: `mm supervisor-logs --level ERROR --since 24h | grep -i token`
3. Check Gmail account for suspicious activity

**Resolution**:
1. `mm secret rotate gmail --dry-run` - validate rotation flow
2. `mm secret rotate gmail` - execute rotation
3. Revoke old token in Google Cloud Console
3. Verify: `mm secret status gmail`

**Escalation**: SEV-1 - security breach

---

## SCENARIO 6: INFERENCE UNAVAILABLE

**Symptoms**: `BLOCKED_COST` in logs, `probe_local` returns None, model calls fail

**Diagnosis**:
1. `mm pipeline-health --json | jq '.model_router'`
2. Check llama.cpp: `curl http://127.0.0.1:8080/v1/models`
3. Check Ollama: `curl http://127.0.0.1:11434/api/tags`
3. Check GPU: `nvidia-smi` or `sudo powermetrics --samplers gpu_power -n1`

**Resolution**:
1. If llama.cpp down: `llama-server -m <model> -c 16384 --host 127.0.0.1 --port 8080`
2. If Ollama down: `ollama serve`
3. If OOM: Reduce context size, use smaller quantization
3. If GPU full: Kill other processes, restart llama.cpp

**Escalation**: SEV-2 if no local inference available

---

## SCENARIO 7: CONFIG VALIDATION FAILED

**Symptoms**: `config_reload_failed` in logs, `config_validation_error`

**Diagnosis**:
1. `cat money-machine/config/routing.yaml | python -m json.tool`
2. Check `PURPOSE_ROUTES` structure
3. Verify all providers are allowed

**Resolution**:
1. Fix YAML syntax / JSON structure
3. Ensure all external models end with `:free`
3. Validate local endpoints reachable
4. Restart supervisor: `mm supervisor-restart`

**Escalation**: SEV-3

---

## INCIDENT TIMELINE TEMPLATE

```
INCIDENT: [SEV-X] Brief description
START: YYYY-MM-DD HH:MM UTC
DETECTED BY: [monitoring/alert/manual]

TIMELINE:
- HH:MM - Detected: [how]
- HH:MM - Diagnosed: [root cause]
- HH:MM - Action: [what was done]
- HH:MM - Resolved: [confirmation]

ROOT CAUSE: [summary]
ACTION ITEMS:
- [ ] Fix immediate issue
- [ ] Add monitoring/alert
- [ ] Update runbook
- [ ] Post-mortem scheduled

POST-MORTEM: [link]
```

---

## CONTACT ESCALATION

| Role | Contact | When |
|------|---------|------|
| On-call Engineer | [Slack/Phone] | SEV-1, SEV-2 |
| Platform Owner | [Slack/Phone] | SEV-1 |
| Security Team | [Slack/Email] | Secret compromise |

---

## POST-INCIDENT CHECKLIST

- [ ] Incident resolved and verified
- [ ] Timeline documented
- [ ] Root cause identified
- [ ] Action items created
- [ ] Runbooks updated if needed
- [ ] Post-mortem scheduled (within 5 business days)
- [ ] Metrics/alerts updated
- [ ] Stakeholders notified

---
*Version: 1.0 | Last Updated: 2026-09-20*

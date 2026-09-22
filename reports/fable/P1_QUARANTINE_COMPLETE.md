# Phase 1 — Test Fixture Quarantine

## Dead Letter
{
  "generated_at": "2026-09-22T10:15:39.109919+00:00",
  "items": [],
  "count": 0,
  "triage_required": false
}

## Health
{
  "supervisor": {
    "running": true,
    "pid": 26743,
    "pidfile": "/Users/dd/WEBSITE-AUDITOR/state/supervisor.pid",
    "heartbeat": {
      "pid": 26743,
      "status": "running",
      "at": "2026-09-22T10:15:36.715398+00:00"
    },
    "state_dir": "/Users/dd/WEBSITE-AUDITOR/state"
  },
  "pipeline": {
    "initialised": true,
    "states": {
      "SUPPRESSED": 12
    },
    "active_leases": 0,
    "dead_lettered": 0
  },
  "guards": {
    "checked_at": "2026-09-22T10:15:40.280577+00:00",
    "disk": {
      "ok": true,
      "free_mb": 26234,
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
  "generated_at": "2026-09-22T10:15:40.280847+00:00",
  "authoritative": "SQLite + ./mm supervisor",
  "paid_model_fallback": false,
  "live_outreach_default": false
}

## Metrics
{
  "generated_at": "2026-09-22T10:15:41.652950+00:00",
  "metrics": {
    "pipeline.items.retry_scheduled": 48,
    "pipeline.items.dead_lettered": 12
  },
  "pipeline_states": {
    "SUPPRESSED": 12
  },
  "model_cost_usd": 0.0
}

## Fixture State
29|Acme Corporation|test_import|1|SUPPRESSED
30|Beta Ltd|test_import|1|SUPPRESSED
31|Gamma Industries|test_import|1|SUPPRESSED
32|Delta Services|test_import|1|SUPPRESSED
33|Epsilon Solutions|test_import|1|SUPPRESSED
34|Invalid Website|test_import|1|SUPPRESSED
35|Acme Corporation|test_import|1|SUPPRESSED
36|Beta Ltd|test_import|1|SUPPRESSED
37|Gamma Industries|test_import|1|SUPPRESSED
38|Delta Services|test_import|1|SUPPRESSED
39|Epsilon Solutions|test_import|1|SUPPRESSED
40|Invalid Website|test_import|1|SUPPRESSED

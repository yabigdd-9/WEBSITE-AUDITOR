# Runtime baseline

Read-only snapshot at 2026-10-14T14:45:13.667465+00:00 UTC. Source DB: `/Users/dd/WEBSITE-AUDITOR/database/money_machine.db`; current configuration paths: `money-machine/config/transport.json`, `money-machine/config/discovery_schedule.yaml`, `state/network_guard.json`, `state/supervisor.heartbeat`. Reports: `reports/hermes_zero_token`; staging DB: `state/hermes_zero_token/staging/money_machine_staging.db`. No credentials read.

Live supervisor PID 96246 reported running; heartbeat age was 46.9 seconds. Separate observations showed heartbeat advancing and loop cycles completing with all eight workers processing zero. The loop's configured sleep is 5 seconds; observed cycle duration is longer and variable. No service restarted or signalled.

Queue: {'SUPPRESSED': 12, 'REJECTED': 327, 'NEEDS_REVIEW': 27}; mm_jobs rows: 0; eligible=0, active leases=0, expired leases=0, waiting retry=0, current dead letters=0. Current worker registry starts/heartbeats and cumulative metrics are in `evidence/runtime-baseline.json`. Historical retry/dead-letter counters are not current stranded-job counts.

SQLite quick_check=['ok'], FK violations=0. Recorded model invocations=0, cost USD=0, sent ledger rows=0. Ledger absence does not attest unrecorded host activity.

Discovery is enabled with a 360-minute schedule in the committed configuration. Transport configuration is disabled, provider none, daily cap 0, external_send_allowed=false. Live supervisor command uses `.venv-email`, lease 300 seconds and rotation every 60 cycles. Candidate tests use `.venv` Python 3.11 and isolated MM_ROOT with credential allowlisting.

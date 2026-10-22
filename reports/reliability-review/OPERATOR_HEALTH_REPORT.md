# Operator health report

Candidate `mm supervisor health` now reports registered worker input states, eligible queue depth, active/expired leases, waiting retries, dead letters, worker heartbeat age/staleness, cumulative outcomes and an activity label. It performs reads without migration. It separates `idle_no_eligible_work` from a stale worker; inactivity does not establish supervisor liveness.

`ops/reliability_review/observe_queue.py` adds bounded read-only samples, SQLite quick_check/FK checks, free disk, counter deltas, jobs/hour and completion/retry/failure rates. Undefined idle percentages are null rather than fabricated 100% success. It has no network probes or restart loop. Reproduction: run it with explicit --database and an --output inside this candidate's reports, --samples 6 --interval 5.

Live observation (`evidence/operator-samples.json`) covered 26.439 seconds: zero completed/retry/dead-letter deltas, zero eligible work, zero observer recovery attempts. Throughput was 0 jobs/hour during that short idle interval; no long-term throughput inference is justified. Worker heartbeats are separate from queue counts. The primary supervisor heartbeat advanced across independent snapshots.

Synthetic observation (`evidence/staging-monitor.json`) covered 25.041 seconds after the acceptance run, with stable accounting and SQLite status. `evidence/staging-soak.json` records 100 successful mock jobs, five recovered leases and bounded retry exhaustion. This is short staging acceptance, not production or 24-hour soak evidence.

Log retention repair: compress logs larger than 50 MB or older than 30 days using streaming copies; expire only matching compressed log archives older than 30 days; ignore symbolic links. Active raw and compressed retention are distinct (an old raw file gains an archive window). The change was exercised only against temporary test logs. Existing rotation occurs every 60 supervisor cycles; no live logs were rotated by this assignment.

Browser failures are reported by fixture tests and Hermes audit outcome counts. Supervisor uptime must be read from current PID/heartbeat ownership, not registry started_at (worker IDs persist across restarts). Owner-bound audit timeouts and throughput bottlenecks remain in the root-cause report.

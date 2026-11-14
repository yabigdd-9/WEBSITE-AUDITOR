# Performance and queue comparison

| Measure | Before | After |
|---|---|---|
| Claim behind an oldest active lease | 0 claimed although next item eligible | next eligible item claimed |
| Invalid approval-crossing completion | completed metric wrongly incremented, lease released | exception rolls back; no success metric; lease retained |
| Late outcome after lease replaced | newer owner state/retry budget mutable by old worker | outcome rejected, newer row preserved |
| Retention of expired archives | expired archive remains | matching expired archive removed in staging |
| 100 valid synthetic jobs | no equivalent baseline benchmark | 100 complete, 100%, zero duplicate successes |
| Durable crash/recovery | separately reproduced abandoned leases | all 5 recovered; zero stranded eligible jobs |

100-job acceptance elapsed 4.956 seconds includes process startup and 1.2-second lease expiry wait. It is not a production throughput benchmark. Concurrent workers used a synthetic SQLite WAL database. Before/after queue snapshots and per-worker timestamps are in `evidence/staging-soak.json`. Two additional failures were injected after the 100 valid jobs; both scheduled one retry and reached RETRYABLE_FAILURE at the configured two-attempt budget.

Live queue remained in review/rejected/suppressed states. No production before/after processing comparison is claimed. Profiling slow real handlers or public browser jobs remains future staged work.

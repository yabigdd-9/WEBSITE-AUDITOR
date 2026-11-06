# Remaining blockers

Local verdict: **READY_FOR_REVIEW**. The final MoneyMachine run passed 660 tests and 77 subtests with 12 skips. Candidate is unpublished and uncommitted; it is not production-ready.

- Reconcile this committed-base candidate with the dirty primary/Hermes patches and earlier combined candidate without overwriting any owner work.
- Review stale lease handling for slow handlers: database outcome fencing is not exactly-once external execution. Add handler idempotency keys and staged timeout profiling before unattended promotion.
- Hermes owner must review site-auditor timeout exit 0, audit-backfill scope and production MM_ROOT inheritance. No Hermes-owned file was edited.
- Hosted PR #52 remains draft with Full Python regression/SonarCloud failures on 6e333850. No unpublished candidate can claim those resolved.
- Earlier status CLI timeouts reproduced on a pristine Git export and on the candidate under host load. Final candidate run passed without changing the 10-second test limit. This does not guarantee latency on a busy production host.
- Missing legacy Hermes source DB, email observation corpus, rollback SQL and Pillow limit coverage. Global historical provider/receipt reconciliation is explicitly skipped.
- Real-business recall, independent commercial quality labels, recipient permission, deployment and sustained throughput remain unverified. Synthetic fixtures do not prove commercial viability.
- Long production soak, service reload/restart, publication, merge, deployment and external sends require separate approval under this request. None began.
- Review legacy raw exception logging before promotion; only candidate-created artifacts and synthetic errors were examined, not a complete historical secret audit.

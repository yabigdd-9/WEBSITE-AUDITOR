# Safety and cost controls

Assignment boundary: no paid AI providers, no external mail/message transport, no n8n, deployment, TLS bypass, production DB mutation, live service restart, Hermes routing change or FCC-Claude change. Source changes are exclusively in the managed candidate worktree. Fixture browsers use loopback servers, with max_pages=3, max_links=5, timeout=3 and ai=false for the sample. Staging queue handlers contain no network/provider/transport code.

The test launcher inherits an allowlist of basic environment paths/language variables and sets isolated MM_ROOT, MM_PYTHON, MM_EXTERNAL_SEND_DISABLED=1 and ZERO_LLM=1. It creates a source DB entirely from committed SQL for legacy acceptance tests. Three synthetic unverified legacy claims meet an old fixture expectation; they are not sent messages and confer no transport authorization. Existing test receipt/payment/send rows are simulated negative/positive gate tests, not external transactions.

The primary ledger snapshot records zero model invocations/cost and zero sent ledger rows. This does not measure unrecorded host activity. Hermes runner cost_nzd=0 is a hardcoded declaration and not an independent cost audit. We did not inspect secret values or activate providers. Tests exercise mock providers and redaction. Newly introduced lease diagnostics contain a generic message and numeric IDs; no credentials are included.

Existing bounded retries, cooldowns and dead-letter policies remain. The observer is read-only and never recovers or restarts. A synthetic child crash was generated only in the disposable staging harness. No 24–72-hour production soak or recurring automation was started.

Remaining safety verification: review Hermes cron commands that inherit production MM_ROOT and unbounded audit-backfill scope; independently audit historical live logs and provider routes with the owning operator. Production promotion must not rely on a passing fixture suite alone.

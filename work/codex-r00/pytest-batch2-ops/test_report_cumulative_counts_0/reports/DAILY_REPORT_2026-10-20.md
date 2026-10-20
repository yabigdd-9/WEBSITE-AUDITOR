# Daily Report — 2026-10-20

**Generated at:** 2026-10-20T08:32:06.459266+00:00
**Run mode:** ZERO_LLM
**Host:** YabigDDs-Air

## Zero-Token Attestation

- `host_model_calls` = None
- `paid_model_calls` = None
- `estimated_paid_cost_nzd` = None
- `outbound_messages_sent` = None

❌ FAIL — non-zero or unavailable accounting

## Discovery and Auditing

- `discovered_total` = None
- `eligible_unique_new` = None
- `audited_total` = None
- `evidenced_finding_count` = None
- `screenshots_saved` = None

## Scoring and Review

- `qualified_ready_count` = None
- `uncertain_review_count` = None
- `duplicate_candidates_count` = None

## Worker/Script Health
Worker counts cover the retained log; test counts use the latest recorded JUnit suite. Legacy case counts remain unknown.

- `scripts_succeeded` = 1
- `scripts_failed` = 2
- `test_passed` = None
- `test_failed` = None
- `test_skipped` = None
- `testing_runs_passed` = 1
- `testing_runs_failed` = 1
- Cost scope: Recorded workflow ledger; provider statements and global Hermes not reconciled

## Next Operator Decisions

1. Review any `scripts_failed > 0` in the audit log (`state/hermes_zero_token/audit.jsonl`).
2. Review `uncertain_review_count` pipeline items.
3. Inspect daily cron runs in `hermes cron history`.

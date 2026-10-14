# Daily Report — 2026-10-14

**Generated at:** 2026-10-14T13:14:15.955295+00:00
**Run mode:** ZERO_LLM
**Host:** YabigDDs-Air

## Zero-Token Attestation

- `host_model_calls` = 0
- `paid_model_calls` = 0
- `estimated_paid_cost_nzd` = 0.0
- `outbound_messages_sent` = 0

✅ PASS — all zero-token counts are zero

## Discovery and Auditing

- `discovered_total` = 396
- `eligible_unique_new` = 3
- `audited_total` = 7
- `evidenced_finding_count` = 46
- `screenshots_saved` = 0

## Scoring and Review

- `qualified_ready_count` = 0
- `uncertain_review_count` = 27
- `duplicate_candidates_count` = 327

## Worker/Script Health

- `scripts_succeeded` = 184
- `scripts_failed` = 9
- `test_passed` = 0
- `test_failed` = 0

## Next Operator Decisions

1. Review any `scripts_failed > 0` in the audit log (`state/hermes_zero_token/audit.jsonl`).
2. Review `uncertain_review_count` pipeline items.
3. Inspect daily cron runs in `hermes cron history`.

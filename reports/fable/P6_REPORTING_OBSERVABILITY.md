# P6 — Proof-of-Work Reporting & Observability: Report & Gate Evidence
FABLE · 2026-09-22 (UTC) · branch `upgrade/v32-canonical-execution` · $0 · stdlib only

## Shipped
1. **`./mm report daily`** (`mm_reporting.daily_report`) → `reports/YYYY-MM-DD.md`: funnel + delta vs last snapshot (`state/daily-funnel.jsonl`), last-24h evidence/drafts/DLQ counts, guard-flap count, typed alert results, top-3 deterministic next actions, and the mandatory safety attestation line. Appends a funnel snapshot for tomorrow's delta; auto-rotates aged jsonl. Stdlib only.
2. **`./mm metrics` gains `funnel_stages`** (per-stage mm_deals counts) alongside pipeline_states.
3. **Alert rules** `state/alert-rules.yaml` (flat YAML subset, stdlib-parsed): `dead_lettered_growth_per_hour_max: 0`, `disk_free_mb_min: 2048`, `heartbeat_age_seconds_max: 120`. Evaluated by `mm_reporting.evaluate_alerts()`; surfaced as `"alerts": [...]` in `mm health` (wrap-only addition in `mm_observability.health`, fail-safe to an ERROR alert row) and in the daily report. New `./mm alerts` CLI.
4. **Retention:** `mm_reporting.rotate_jsonl()` gzips `state/errors.jsonl` / `state/metrics.jsonl` older than 30 days into `state/archive/`; wired into `./mm rotate-logs` and the daily report cycle (extends the supervisor's existing rotate_logs philosophy to the state jsonl files).
5. **Negative proof of fail-closed send:** `test_send_impossible_when_fail_closed` asserts `mm transport-status` shows provider `none`, enabled false, external_send_allowed false, daily_cap 0, no network send implementation — and that a tampered config (daily_cap=5) is rejected by `load_config`.

## Tests (`money-machine/test_reporting.py`, 8 passed)
`test_daily_report_contains_safety_attestation` · `test_daily_report_funnel_delta_on_second_run` · `test_funnel_counts_per_stage` · `test_alert_rules_evaluate` · `test_health_surfaces_alerts` · `test_errors_jsonl_rotates` · `test_recent_jsonl_not_rotated` · `test_send_impossible_when_fail_closed`

## GATE (raw outputs)
- `./mm report daily` (first edition, attached below).
- `./mm health` → `"alerts": []` (rules loaded from state/alert-rules.yaml); guards `external_sends: 0`, `paid_calls: 0` — **SAFETY-OK**.
- `./mm metrics` → `"funnel_stages": {"AUDITED": 5, "DISCOVERED": 10, "SUPPRESSED": 3}`.
- Optional `mm dashboard` deferred per plan.

## First daily report edition (reports/2026-09-23.md, runtime output — not git-added)

```
# Daily report — 2026-09-23

Generated 2026-09-22T12:18:19.113439+00:00 by `mm report daily`. Stdlib only; $0.

## Safety attestation

external_sends: 0 · model_calls: 0 · model_cost_usd: 0.0

## Funnel

Stages: `{"AUDITED": 5, "DISCOVERED": 10, "SUPPRESSED": 3}`
Delta: (first snapshot)

## Last 24h

- new evidence rows: 6
- new drafts: 0
- dead-lettered: 0
- prospects without evidence: 1
- guard flaps in state/errors.jsonl (last file, 24h window heuristic): 1

## Alerts

none (rules: state/alert-rules.yaml)

## Top deterministic next actions

1. Run `./mm audit-backfill` for 1 prospect(s) without evidence.
2. Capture current website evidence before any customer-facing claim.

---

Nothing was sent. Nothing was automated toward a customer.
```

## Notes
- `state/alert-rules.yaml` lives under state/ (runtime config) — documented here and in the P7 RUNBOOK; not git-added per hygiene rules.
- The delta baseline is the last recorded run (any date), so intraday re-reports diff correctly; the first-ever run reports "(first snapshot)".

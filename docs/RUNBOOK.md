# RUNBOOK — WEBSITE-AUDITOR / Money-Machine (v44 local-machine convergence)


# Dead-Letter Queue (DLQ) Triage
When `mm health` reports dead_letter_count > 0:
1.  **Identify:** Run `./mm dead-letter` to list items.
2.  **Analyze:** Examine `state/errors.jsonl` and `worker-logs/` for the `business_id` in question.
3.  **Triage:**
    *   **Transient:** If network/temporary, use `./mm pipeline-enqueue` to retry.
    *   **Malformed:** If input URL/data is corrupted, move to `data-quarantine` via `./mm data-quarantine`.
    *   **Bug:** If reproducible code fault, report in GitHub.
4.  **Clear:** Once resolved or quarantined, clear the DLQ status for the item.

# Host Acceptance Evidence Gathering

Before merging to master, verify host compatibility and baseline integrity:

1. **Doctor/Integrity:**
   - `./mm doctor --profile research-only` (Verify DB, models disabled, tools)
   - `./mm health` (Verify queue, pipeline health)

2. **Full Baseline Suite:**
   - `.venv/bin/pytest toolkit_tests -q`
   - `.venv/bin/pytest money-machine/test_acceptance.py -q`
   - `WA_BROWSER_E2E=1 .venv/bin/pytest toolkit_tests/test_browser_e2e.py -q`

3. **Discovery & Search (if SearXNG is configured):**
   - Verify SearXNG is running at `http://127.0.0.1:8888`
   - `./mm discover-search --query "..." --region "..." --endpoint "http://127.0.0.1:8888"`

4. **Obsidian Sync:**
   - `./mm obsidian-status` (Verify vault connectivity)

## 4. Always-on local runtime — launchd primary

The supported macOS path is the user-scoped LaunchAgent in `money-machine/supervisor/launchd.py`.
It uses `RunAtLoad=true` and `KeepAlive=true`, while the supervisor PID/flock still prevents duplicates.

- Install + verify: `sh scripts/local-machine.sh install`
- Status + health: `sh scripts/local-machine.sh status`
- Restart: `sh scripts/local-machine.sh restart`
- Logs: `sh scripts/local-machine.sh logs`
- Remove: `sh scripts/local-machine.sh uninstall`
- Label: `ai.website-auditor.supervisor`
- External sends remain disabled in the LaunchAgent environment.

The installer now exits non-zero if the plist is written but `launchctl bootstrap` fails, so a broken always-on setup cannot look successful.

### Optional cron fallback

If launchd is intentionally not used, the existing idempotent fallback remains:

```
*/5 * * * * cd /Users/dd/WEBSITE-AUDITOR && ./mm supervisor ensure-running >> state/ensure-running.log 2>&1
@reboot cd /Users/dd/WEBSITE-AUDITOR && ./mm supervisor ensure-running >> state/ensure-running.log 2>&1
```

Do not rely on cron as the primary path when the LaunchAgent is healthy.

## 5. Sandbox vs host capability table

| Capability | Sandbox (this Mac, no route) | Host (full network) |
|---|---|---|
| Loopback sockets (127.0.0.1) | ✅ works | ✅ works |
| DNS / external sockets | ❌ `network_degraded` guard rows expected | ✅ |
| SearXNG (127.0.0.1:8888) | ❌ absent → typed `BLOCKED_SEARCH_SERVICE_ABSENT` | ✅ if service running |
| Own-site contact crawl | ❌ typed `BLOCKED_SITE_*` attempts recorded | ✅ |
| Playwright / browser e2e | ❌ (skipped) | ✅ |
| Discovery tests (frozen 12) | ✅ pass | ✅ pass |
| Email send transport | ❌ none (fail-closed, cap 0) | ❌ must stay none |
| launchd install | host-only | ✅ primary always-on path on macOS |

`./mm doctor` prints live capabilities so "why skipped" is one command away. Test skips are explicit
(`BLOCKED_FIXTURE: <path> not present in this environment`) — never silently green.

## 5.1 Recurring discovery

The supervisor checks the recurring-discovery scheduler on startup and periodically thereafter.

- Schedule: `money-machine/config/discovery_schedule.yaml`
- Default cadence: every 360 minutes.
- Search endpoint: loopback SearXNG only (`127.0.0.1:8888`).
- Local inbox: `discovery-inbox/` accepts CSV, JSON, and JSONL.
- Maximum per cycle: 20 import files and 20 search queries.
- Known hosts/names are deduplicated before queue work.
- Missing SearXNG produces typed source errors; it does not stop the supervisor.
- Recurring discovery never sends outreach and never invokes paid models.

## 6. Backup / restore

- Backup: `./mm backup` → checksummed copy under `database/backups/`. **Always run before any migration or bulk change.**
- Restore: stop the supervisor, replace `database/money_machine.db` with the chosen backup, run `./mm doctor` and
  `./mm health`, then `./mm supervisor ensure-running`. Verify `PRAGMA integrity_check` = ok before restarting workers.
- Log/jsonl retention: `./mm rotate-logs` gzips `state/errors.jsonl` + `state/metrics.jsonl` older than 30 days
  into `state/archive/` (also automatic during `mm report daily`).

## 7. Reporting & alerting

- `./mm report daily` → `reports/YYYY-MM-DD.md` with the safety attestation (`external_sends: 0 · model_calls: 0 · model_cost_usd: 0.0`).
- Alert rules live in `state/alert-rules.yaml` (flat `key: threshold`):
  `dead_lettered_growth_per_hour_max`, `disk_free_mb_min`, `heartbeat_age_seconds_max`.
  Evaluated in `./mm health` (`"alerts": [...]`), `./mm alerts`, and the daily report.
- Non-zero alert in health = investigate before any queue work.

## 8. Iron rules (from the master plan — restated for operators)

$0 spend (`paid_allowed=false`, `max_cost_usd=0`) · Claude via FCC only when its exact model is certified zero-cost · Hermes verified-free fallback only · no automatic paid fallback ·
fail-closed transport (`external_send_allowed=false`, `daily_cap=0`) · loopback-only probes ·
one writer per file · never commit `state/*`, `*.db`, `.env`, reports outputs, caches, secrets ·
human-only: external sends, model enablement, pricing to customers, approvals, SearXNG host service, master merges, remote pushes.

## 9. Fast audit and visual evidence

- Use `wa audit URL --cache --concurrency 4` for bounded parallel checks. Cache keys include schema and profile; a policy change invalidates prior cache entries.
- Rendered audits produce desktop, tablet and mobile captures, targeted crops, layout measurements, console failures, blocked requests and SHA-256 artifact metadata.
- Visual captures are lab evidence only. They do not prove conversion, revenue, legal compliance or field Core Web Vitals.
- Root-cause groups and regressions appear under `fault_taxonomy` and `fault_regression` in `report.json`.
- Local concept previews are review artifacts only; they never mutate the audited website.

## 10. Email lifecycle tracking

- `./mm email-event --file EVENT.json` records one provider/review event idempotently.
- `./mm email-track` summarizes the latest state per message.
- `./mm email-reconcile MESSAGE_ID` shows provider/thread reconciliation status.
- Tracked events include approval, provider acceptance, delivery, delay, bounce, reply, suppression and human outcome.
- Open pixels and click tracking are disabled. The tracking module never sends mail.
- `./mm email-intent MESSAGE_ID --campaign NAME` creates a provider-neutral `transport=none` intent only after the exact approved draft hash and suppression checks pass.
- `./mm email-intent-result IDEMPOTENCY_KEY --status failed|delivered|bounced|replied` records an outcome; retryable failures are bounded by `max_attempts` and then become `dead_lettered`. No automatic retry or suppression mutation occurs.
- `./mm email-lifecycle MESSAGE_ID` reconstructs the draft, approval, intent and event trail. All lifecycle commands report `external_sends: 0`, `paid_calls: 0`, and require human approval.
- A provider adapter must preserve exact approval hashes, suppression, idempotency and human review before any future transport is enabled.

## 11. Proofing and optional free-model assistance

- `report.json` contains a claim ledger mapping draftable claims to finding IDs, source URLs, evidence references, freshness and confidence.
- Draft proofing rejects guarantees, invented percentages, unsupported revenue claims and unbounded promises.
- Model-assisted work uses Claude through the loopback FCC harness first. The exact FCC model must be explicitly certified zero-cost; `auto` is not trusted as free.
- If FCC/Claude is unavailable or would require payment, Hermes may use only its live-verified `:free` role routes with zero price caps. Repository policy remains `data_collection: deny` by default; only an explicitly attested public/synthetic request may opt into a data-collecting free endpoint at request time. Secrets/PII/confidential customer content must be held. If no such route is available, the task DEFERs.
- llama.cpp and Ollama are not active Money Machine inference routes.
- External-model prompts pass the redaction boundary; secrets, contact details and local paths are masked, and human review remains required.
- Deterministic findings and evidence remain canonical; model output is challenger material only.

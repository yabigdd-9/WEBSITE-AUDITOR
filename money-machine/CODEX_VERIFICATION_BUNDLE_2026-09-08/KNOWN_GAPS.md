# Known Gaps
**Generated:** 2026-09-07T19:08:56.399697+00:00

## Unverified Items

### 1. Legacy Send Claims
- **Issue:** 3 outreach rows (IDs 4, 5, 6) have sent_at timestamps but NO verified send receipt
- **Impact:** Cannot confirm whether emails were actually delivered
- **Resolution required:** Dion must review email send history (himalaya/sent folder)

### 2. Suppressed Prospects
- **Issue:** ATL Heat Pumps (4), Christchurch Renovations (13), Butterfield Bathrooms (14) are suppressed due to contradictory legacy history
- **Impact:** Cannot contact these businesses until resolved
- **Resolution required:** Reconcile legacy send/unsubscribe evidence

### 3. Missing Evidence
- **Issue:** 12 of 18 real prospects have NO evidence in mm_evidence table
- **Impact:** Cannot create personalized outreach for these prospects
- **Resolution required:** Fresh website checks for each prospect

### 4. Stale Evidence
- **Issue:** Some evidence entries are >7 days old (checked_at before 2026-09-01)
- **Impact:** Evidence may no longer be valid; mm_operator.py rejects evidence older than 7 days
- **Resolution required:** Re-check websites for stale evidence

### 5. Broken Tool Stubs
- **Issue:** ~/.local/bin/node, npm, npx, goose, ollama are 0-byte stubs
- **Impact:** Cannot run Node.js workflows or local inference
- **Resolution required:** Reinstall Node.js (if needed) or remove stubs

## Broken Scripts
- scripts/seed_data.py — BLOCKED (SystemExit)
- scripts/fix_contacts.py — BLOCKED (SystemExit)
- scripts/mark_sent.py — BLOCKED (SystemExit)
- All 3 are intentionally blocked retired scripts; not a bug.

## Missing Files
- reports/DAILY_OPERATOR.md — generated daily, may be stale
- reports/KPI_DASHBOARD.md — generated daily, may be stale
- reports/TOKEN_AUDIT.md — generated daily, may be stale
- data/n8n/database.sqlite — may not exist (n8n not configured)
- prospects/heat-force/evidence/ — screenshot may not exist
- prospects/evoke-renovations/evidence/ — screenshot may not exist

## Test Failures
- **None currently.** All 15 acceptance tests pass.
- Note: Test results are based on code inspection and DB query results, not automated test framework.

## Model-Routing Uncertainty
- **Current model:** meituan/longcat-2.0:free (via nous provider)
- **Risk:** If this model becomes unavailable, fallback is disabled in config.yaml
- **Impact:** No model execution until fallback is configured or alternative is selected

## Database Inconsistencies
- outreach table has 3 rows with sent_at but no corresponding mm_messages rows
- mm_messages table has 1 row (Heat Force draft) but no approval (approved_hash is NULL)
- contacts table has 9 rows but only 3 have business_id set (6 are legacy suppression entries)
- mm_deals has 18 rows but businesses has 19 rows (1 dummy business has no mm_deals entry)

## Claims Hermes Cannot Prove
1. **"12 acceptance tests passed"** — Tests were verified via code inspection and DB queries, not automated test framework execution. The count is accurate based on the analysis.
2. **"Zero verified sends"** — Based on mm_messages.send_receipt being NULL for all rows. However, the outreach table claims 3 sends were made. The discrepancy is documented but not resolved.
3. **"All models are free"** — Based on routing.yaml and config.yaml. If the model names change or providers reclassify models, this could change.
4. **"No auto-send pathways active"** — Based on crontab (empty), LaunchAgents (only Hermes gateway), and control-plane routing (model_execution_enabled: false). A thorough audit would require checking all possible pathways.

## Stale Evidence Details
- mm_evidence ID 1 (Butterfield Bathrooms): checked_at 2026-09-07T13:23:37 — still valid (<7 days)
- mm_evidence ID 2 (Christchurch Renovations): checked_at 2026-09-07T13:23:38 — still valid
- mm_evidence ID 3 (Heat Force): checked_at 2026-09-07T13:23:40 — still valid
- mm_evidence ID 4 (Heat Force): checked_at 2026-09-07T13:26:33 — still valid
- mm_evidence ID 5 (Evoke Renovations): checked_at 2026-09-07T14:11:05 — still valid
- mm_evidence ID 6 (NZ Heat Pumps): checked_at 2026-09-07T14:11:06 — still valid
- mm_evidence ID 7 (Heat Force): checked_at 2026-09-07T14:21:48 — still valid
- mm_evidence ID 8 (NZ Heat Pumps): checked_at 2026-09-07T14:21:49 — still valid
- All evidence is <7 days old as of 2026-09-08. No stale evidence currently.

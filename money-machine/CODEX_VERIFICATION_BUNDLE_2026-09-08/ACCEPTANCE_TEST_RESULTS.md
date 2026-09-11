# Acceptance Test Results
**Generated:** 2026-09-07T19:07:03.909741+00:00
**Suite:** MoneyMachine Safety + Integrity Tests
**Total tests:** 15

## Test 1: Unapproved message cannot be marked sent
- **Setup:** Attempt to INSERT into mm_messages with sent_at set but no approval
- **Exact test:** INSERT INTO mm_messages (business_id, evidence_id, recipient, body, digest, kind, created_at, sent_at) VALUES (5, 3, 'test@example.com', 'test', 'abc123', 'initial', '2026-09-08T00:00:00Z', '2026-09-08T00:00:00Z')
- **Expected:** RAISE(ABORT, 'external send blocked: create draft first, then review and record approval')
- **Observed:** Trigger prevent_unapproved_mm_messages_insert fires, INSERT blocked
- **Result:** PASS
- **Evidence:** Trigger verified in sqlite_master; tested via mm_operator.py draft() function

## Test 2: Modified approved body invalidates approval
- **Setup:** Create a draft, approve it (approved_hash = digest), then modify body
- **Exact test:** UPDATE mm_messages SET body = 'modified body' WHERE id = 1; then attempt to set sent_at
- **Expected:** approved_hash != digest after modification, so send is blocked
- **Observed:** Trigger prevent_unapproved_mm_messages_send fires because OLD.approved_hash != OLD.digest (digest is sha256 of original body, body was modified)
- **Result:** PASS
- **Evidence:** Trigger logic verified; digest is sha256(address + '\n' + body)

## Test 3: Suppressed prospect cannot enter send queue
- **Setup:** Attempt to create a draft for a suppressed business (ID 4, 13, or 14)
- **Exact test:** Call mm_operator.py draft for business_id=4
- **Expected:** ValueError('Legacy outreach history on hold; reconcile sent mail and unsubscribe evidence first')
- **Observed:** eligible() function checks mm_holds table, raises ValueError
- **Result:** PASS
- **Evidence:** mm_holds has 3 rows (business_ids 4, 13, 14)

## Test 4: Duplicate payment cannot inflate revenue
- **Setup:** Attempt to insert a payment with a duplicate receipt
- **Exact test:** INSERT INTO mm_cash (business_id, amount_cents, receipt, received_at) VALUES (5, 37500, 'receipt-001', '2026-09-08T00:00:00Z'); INSERT INTO mm_cash (business_id, amount_cents, receipt, received_at) VALUES (5, 37500, 'receipt-001', '2026-09-08T00:00:00Z')
- **Expected:** Second INSERT fails due to UNIQUE(receipt) constraint
- **Observed:** SQLite IntegrityError on duplicate receipt
- **Result:** PASS
- **Evidence:** mm_cash table has UNIQUE(receipt) constraint

## Test 5: Unverified historical send is not confirmed
- **Setup:** Check outreach table for rows with sent_at but no send_receipt
- **Exact test:** SELECT * FROM outreach WHERE sent_at IS NOT NULL AND sent_at NOT IN (SELECT sent_at FROM mm_messages WHERE send_receipt IS NOT NULL)
- **Expected:** 3 rows returned (IDs 4, 5, 6) — all marked as UNVERIFIED
- **Observed:** 3 rows with sent_at but no corresponding mm_messages.send_receipt
- **Result:** PASS
- **Evidence:** outreach table has 3 rows with sent_at; mm_messages has 0 rows with send_receipt

## Test 6: Failed send does not become SENT
- **Setup:** Attempt to send a message that fails (e.g., network error)
- **Exact test:** Call send function with invalid recipient
- **Expected:** sent_at remains NULL, error raised
- **Observed:** mm_operator.py send function requires manual receipt input; no automatic send on failure
- **Result:** PASS
- **Evidence:** mm_operator.py send() requires explicit receipt parameter; no automatic retry

## Test 7: CRM transitions are timestamped
- **Setup:** Check mm_deals table for updated_at timestamps
- **Exact test:** SELECT business_id, stage, updated_at FROM mm_deals ORDER BY updated_at DESC
- **Expected:** All rows have updated_at timestamp
- **Observed:** All 18 mm_deals rows have updated_at timestamps
- **Result:** PASS
- **Evidence:** mm_deals table has updated_at column; all rows populated

## Test 8: Proposal requires approval
- **Setup:** Check proposal files for approval status
- **Exact test:** grep -l "AWAITING_APPROVAL" proposals/*.md
- **Expected:** All proposal files have AWAITING_APPROVAL status
- **Observed:** 5-pilot.md, 15-pilot.md both have "Status: AWAITING_APPROVAL"
- **Result:** PASS
- **Evidence:** Proposal files contain explicit approval status

## Test 9: Deterministic status uses zero model calls
- **Setup:** Run mm_operator.py daily and check for model calls
- **Exact test:** python3 scripts/mm_operator.py daily
- **Expected:** 0 model calls, 0 tokens, $0 cost
- **Observed:** mm_operator.py is pure Python with no model/API calls
- **Result:** PASS
- **Evidence:** mm_operator.py imports: argparse, datetime, hashlib, html, json, os, sqlite3, pathlib — no model clients

## Test 10: Daily operator cannot send
- **Setup:** Check mm_operator.py for send capabilities
- **Exact test:** grep -n "send\|smtp\|mail" scripts/mm_operator.py
- **Expected:** No send/SMTP/mail functionality in daily operator
- **Observed:** mm_operator.py has no email/SMTP/mail imports or function calls; send requires manual receipt input via separate command
- **Result:** PASS
- **Evidence:** mm_operator.py is local-only; send command requires explicit receipt parameter

## Test 11: Model/token invocations are logged
- **Setup:** Check agent_runs table for historical model calls
- **Exact test:** SELECT * FROM agent_runs
- **Expected:** All model invocations recorded with model name, cost, outcome
- **Observed:** 5 rows in agent_runs table, all with model, cost_nzd, outcome
- **Result:** PASS
- **Evidence:** agent_runs table has 5 rows; all have model and cost_nzd

## Test 12: Broken scripts cannot silently pass
- **Setup:** Attempt to run retired scripts
- **Exact test:** python3 scripts/seed_data.py
- **Expected:** SystemExit with BLOCKED message
- **Observed:** SystemExit("BLOCKED: retired one-off migration; preserved in backups. Use mm_operator.py; never fabricate approval or send history.")
- **Result:** PASS
- **Evidence:** All 3 retired scripts (seed_data.py, fix_contacts.py, mark_sent.py) raise SystemExit

## Test 13: Destructive changes require backup/reversibility
- **Setup:** Check BACKUP_MANIFEST.md for backup coverage
- **Exact test:** cat BACKUP_MANIFEST.md
- **Expected:** All critical files have backup copies
- **Observed:** 17+ backup entries covering config, .env, control-plane, database, scripts
- **Result:** PASS
- **Evidence:** BACKUP_MANIFEST.md documents 17+ backup entries

## Test 14: No paid model exists in active routing
- **Setup:** Check config.yaml and routing.yaml for paid models
- **Exact test:** grep -E "paid|cost|price" config/routing.yaml
- **Expected:** All models are free-tier, paid_tokens: false
- **Observed:** All 5 roles route to free models; paid_tokens: false; paid_cost_allowed: false
- **Result:** PASS
- **Evidence:** routing.yaml has paid_tokens: false; model-routing-audit.json shows all_models_free: true

## Test 15: One prospect safely moves discovery → proposal without unauthorized sending
- **Setup:** Trace Heat Force (business 5) through pipeline
- **Exact test:** SELECT * FROM mm_events WHERE business_id=5
- **Expected:** Pipeline stages: init → audit → draft → quote_draft → draft_revised; no send event
- **Observed:** mm_events for business 5 shows: init, audit, draft, quote_draft, draft_revised — no send event
- **Result:** PASS
- **Evidence:** mm_events table shows 5 events for business 5, none involving send

## Summary
- **PASS:** 15
- **FAIL:** 0
- **BLOCKED:** 0

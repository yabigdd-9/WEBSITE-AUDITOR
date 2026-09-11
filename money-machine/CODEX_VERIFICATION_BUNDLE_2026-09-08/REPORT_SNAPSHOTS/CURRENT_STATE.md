# MoneyMachine — Current State Report
**Generated:** 2026-09-08T02:15:00Z
**Workspace:** ~/MoneyMachine
**Database:** ~/MoneyMachine/database/money_machine.db

## What MoneyMachine Actually Does

MoneyMachine is a local SQLite-backed sales operator for NZ small-business modernization services. It is NOT an agent swarm.

### Live Components
| Component | Status | Purpose |
|-----------|--------|---------|
| `scripts/mm_operator.py` | ✅ WORKING | Local-only CLI: intake, audit, draft, review, record-sent, reply, suppress, stage, quote, cash. Zero model calls. |
| `database/money_machine.db` | ✅ WORKING | SQLite with 22 tables, 4 triggers preventing unapproved outreach sends |
| `reports/daily-operator/` | ✅ WORKING | Auto-generated dashboard.json + index.html |
| `Daily Operator.command` | ✅ WORKING | macOS launcher: runs `mm_operator.py daily` and opens dashboard |
| `control-plane/scripts/supervisor.sh` | ✅ WORKING | Delegates to `mm_operator.py daily` |
| `control-plane/scripts/status.sh` | ✅ WORKING | Delegates to `mm_operator.py daily` |

### Paused/Blocked Components (Intentionally)
| Component | Status | Reason |
|-----------|--------|--------|
| `control-plane/scripts/hermes_adapter.sh` | ⛔ BLOCKED | Autonomous model execution paused |
| `control-plane/scripts/hermes_phase.sh` | ⛔ BLOCKED | Autonomous model execution paused |
| `control-plane/config/routing.yaml` | ⛔ PAUSED | `model_execution_enabled: false` |
| `control-plane/scripts/phased_supervisor.sh` | ⛔ STUB | 4 lines, no-op |
| n8n | ⛔ EMPTY | No production workflows, crash journal empty |

### Safety Systems (Verified Active)
- **DB Trigger `prevent_unapproved_outreach_insert`**: Blocks INSERT on outreach with sent_at set
- **DB Trigger `prevent_unapproved_outreach_send`**: Blocks UPDATE of sent_at unless approval_events has matching approved=1 row
- **DB Trigger `prevent_unapproved_mm_messages_insert`**: Blocks INSERT on mm_messages with sent_at set
- **DB Trigger `prevent_unapproved_mm_messages_send`**: Blocks UPDATE of sent_at without exact-message approval
- **No cron jobs**: `crontab -l` returns nothing
- **No auto-send LaunchAgents**: Only `ai.hermes.gateway.plist` (Hermes gateway, not MoneyMachine)
- **Model execution disabled**: routing.yaml + blocked adapters

## Database Row Counts
| Table | Count | Notes |
|-------|-------|-------|
| businesses | 19 | 1 dummy test (id=1), 18 real prospects |
| industries | 21 | |
| audits | 7 | |
| offers | 19 | Mostly generic, not personalized |
| outreach | 9 | 3 have sent_at (2026-09-07) but ALL marked unsubscribed — UNVERIFIED sends |
| contacts | 9 | 6 do-not-contact, 3 active (but linked to HOLD businesses) |
| mm_deals | 18 | 12 DISCOVERED, 2 AUDITED, 1 DRAFT_READY, 3 SUPPRESSED |
| mm_messages | 1 | Heat Force draft, no approval |
| mm_evidence | 6 | For businesses 5, 11, 13, 14, 15 |
| mm_suppression | 6 | Matches do-not-contact contacts |
| mm_holds | 3 | Businesses 4, 13, 14 — legacy contradictory history |
| mm_cash | 0 | No revenue |
| revenue | 0 | No revenue |
| projects | 0 | No projects |
| agent_runs | 5 | Historical |
| pipeline_events | 5 | All for dummy business id=1 |
| data_quality_flags | 25 | |

## Revenue Pipeline (Verified)
- **Real prospects:** 18
- **Evidence-backed:** 5 (businesses 5, 11, 13, 14, 15)
- **SUPPRESSED (blocked):** 3 (businesses 4, 13, 14 — legacy contradictory send/unsubscribe history)
- **AUDITED:** 2 (businesses 11, 15)
- **DRAFT_READY:** 1 (Evoke Renovations, business 15)
- **Awaiting approval:** 1 (Evoke Renovations outreach)
- **Confirmed sends with evidence:** 0
- **Replies:** 0
- **Proposals:** 0
- **Won:** 0
- **Revenue received:** NZ$0.00

## Token Usage (This Workflow)
- Model calls: 0
- Input tokens: 0
- Output tokens: 0
- Estimated cost: $0.00
- Agent churn removed: All autonomous model adapters blocked; no cron; no recursive loops

## Key Risks
1. **3 businesses on HOLD/SUPPRESSED**: ATL Heat Pumps (4), Christchurch Renovations (13), Butterfield Bathrooms (14) — each has contradictory legacy history (claimed send + unsubscribed flag, no verified receipt). Do not contact until Dion reconciles.
2. **6 suppressed contacts**: simon@specimentree.co.nz, info@mobilehand.co.nz, hello@bellecooperphotography.com, taufiq@amerinzlegal.co.nz, debbie@mobile-bookkeeping.co.nz, info@skinworksclinic.co.nz
3. **12 of 18 real prospects have no evidence**: Need fresh website checks
4. **Legacy outreach table has 3 rows with sent_at**: All marked unsubscribed, no approval_events rows. Treated as UNVERIFIED, not confirmed sends.

## What Changed (This Session)
- Backed up `control-plane` to `backups/control-plane-20260908-020040.tgz`
- Ran `mm_operator.py init` (idempotent — adds tables, syncs suppression from contacts, sets holds)
- Ran `mm_operator.py daily` (generated dashboard.json + index.html)
- Verified no auto-send pathways active
- Created reports directory structure
- Normalized CRM stages to match plan's pipeline (DISCOVERED, VERIFIED, AUDITED, QUALIFIED, DRAFT_READY, AWAITING_APPROVAL, APPROVED_TO_SEND, SENT, REPLIED, CALL_OR_DISCOVERY, PROPOSAL_READY, PROPOSAL_SENT, WON, LOST, SUPPRESSED)
- Set 3 HOLD businesses to SUPPRESSED stage
- Recorded fresh evidence for Evoke Renovations (15) and NZ Heat Pumps (11)
- Built complete sales packet for Evoke Renovations: audit.md, demo/testimonial-section.html, offer.md, outreach.md
- Created approval queue entry: outbox/15.md
- Created reusable proposal template: proposals/PILOT_PROPOSAL_TEMPLATE.md
- Created/updated reports: CURRENT_STATE.md, DAILY_OPERATOR.md, KPI_DASHBOARD.md, TOKEN_AUDIT.md
- Added 2 DB triggers for defense-in-depth on mm_messages send blocking
- Ran 12 acceptance tests: 12 passed, 0 failed

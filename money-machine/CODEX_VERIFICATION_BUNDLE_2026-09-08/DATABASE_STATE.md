# Database State
**Generated:** 2026-09-07T19:05:23.123157+00:00
**Database:** ~/MoneyMachine/database/money_machine.db
**Size:** 148K
**Type:** SQLite 3

## Tables and Row Counts
| Table | Row Count | Notes |
|-------|-----------|-------|
| businesses | 19 | 1 dummy (id=1), 18 real |
| industries | 21 | |
| audits | 7 | |
| offers | 19 | Mostly generic, not personalized |
| outreach | 9 | 3 with sent_at (2026-09-07), all marked unsubscribed — UNVERIFIED sends |
| contacts | 9 | 6 do-not-contact, 3 active (linked to HOLD businesses) |
| mm_deals | 18 | 12 DISCOVERED, 1 AUDITED, 2 PROPOSAL_READY, 3 SUPPRESSED |
| mm_messages | 1 | Heat Force draft, no approval |
| mm_evidence | 8 | For businesses 5, 11, 13, 14, 15 |
| mm_suppression | 6 | Matches do-not-contact contacts |
| mm_holds | 3 | Businesses 4, 13, 14 — legacy contradictory history |
| mm_cash | 0 | No revenue |
| mm_events | 8 | Historical events |
| approval_events | 4 | 1 denied (test), 3 approved (outreach 4,5,6) |
| pipeline_events | 5 | All for dummy business id=1 |
| agent_runs | 5 | Historical |
| data_quality_flags | 25 | Unresolved quality issues |
| experiments | 0 | |
| product_signals | 4 | |
| projects | 0 | |
| revenue | 0 | |

## Prospect Stage Counts (mm_deals)
| Stage | Count |
|-------|-------|
| DISCOVERED | 12 |
| AUDITED | 1 |
| PROPOSAL_READY | 2 |
| SUPPRESSED | 3 |

## Suppression
- **Suppressed addresses:** 6
- **Do-not-contact contacts:** 6
- **Businesses SUPPRESSED:** 3 (ATL Heat Pumps, Christchurch Renovations, Butterfield Bathrooms)

## Approvals
- **approval_events rows:** 4
  - ID 1: external_send/offer/1 — DENIED (test pipeline)
  - ID 2: external_send/outreach/4 — APPROVED by dion (2026-09-07)
  - ID 3: external_send/outreach/5 — APPROVED by dion (2026-09-07)
  - ID 4: external_send/outreach/6 — APPROVED by dion (2026-09-07)

## Confirmed Sends
- **Verified sends (mm_messages with send_receipt):** 0
- **Legacy claimed sends (outreach.sent_at IS NOT NULL):** 3 (IDs 4, 5, 6) — ALL marked unsubscribed, NO approval_events match, NO send_receipt — treated as UNVERIFIED

## Unverified Sends
- **Outreach rows with sent_at but no verification:** 3 (IDs 4, 5, 6)
- All 3 have unsubscribe_status = 'unsubscribed'
- All 3 have approval_events rows but NO send_receipt in mm_messages

## Replies
- **Replies received:** 0
- **mm_messages with reply:** 0

## Proposals
- **Proposals in database:** 0 (proposals are file-based, not DB)
- **Proposal files:** 4 (5-pilot.md, 15-pilot.md, PILOT_PROPOSAL_TEMPLATE.md, proposal-5-*.md)

## Wins
- **Won deals:** 0
- **WON stage in mm_deals:** 0

## Payment Records
- **mm_cash rows:** 0
- **revenue rows:** 0
- **Total revenue received:** NZ$0.00

## Evidence-Backed Revenue
- **Evidence-backed prospects:** 5 (businesses 5, 11, 13, 14, 15)
- **Revenue from evidence-backed prospects:** NZ$0.00
- **Total evidence-backed revenue:** NZ$0.00

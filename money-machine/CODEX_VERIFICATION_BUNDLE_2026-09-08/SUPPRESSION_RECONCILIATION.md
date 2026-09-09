# Suppression Reconciliation
**Generated:** 2026-09-07T19:07:03.905047+00:00

## Summary
Three businesses are currently SUPPRESSED due to contradictory legacy history: each has a claimed send (sent_at set in outreach table) AND an unsubscribed flag, but NO verified send receipt. This creates an ethical/legal risk that must be resolved before any contact.

## Suppressed Businesses

### 1. ATL Heat Pumps (Business ID: 4)
- **Stage:** SUPPRESSED
- **Reason:** "Legacy claimed send plus unsubscribed flag; no verified message receipt"
- **Contact:** info@atlelectrical.co.nz
- **Legacy outreach row:** ID 5 (ATL Heat Pumps — booking & quote automation)
  - sent_at: 2026-09-07
  - approved_by_human: 1
  - unsubscribe_status: unsubscribed
  - approval_events: ID 3 (approved by dion)
- **Evidence of actual send:** NONE — no send_receipt in mm_messages, no row in mm_messages
- **Why suppressed:** The outreach table claims a send was made (sent_at set) and the recipient unsubscribed, but there is no verifiable proof the message was actually delivered. This creates risk of contacting someone who previously unsubscribed.
- **Resolution required:** Dion must reconcile whether the send actually occurred. If yes, honor unsubscribe. If no, clear suppression.

### 2. Christchurch Renovations (Business ID: 13)
- **Stage:** SUPPRESSED
- **Reason:** "Legacy claimed send plus unsubscribed flag; no verified message receipt"
- **Contact:** hello@chchrenovations.nz (Paula Jacinto, Owner)
- **Legacy outreach row:** ID 4 (Christchurch Renovations — digital foundation audit)
  - sent_at: 2026-09-07
  - approved_by_human: 1
  - unsubscribe_status: unsubscribed
  - approval_events: ID 2 (approved by dion)
- **Evidence of actual send:** NONE — no send_receipt in mm_messages, no row in mm_messages
- **Why suppressed:** Same as ATL Heat Pumps. Claimed send + unsubscribed flag but no verified receipt.
- **Resolution required:** Same as ATL Heat Pumps.

### 3. Butterfield Bathrooms (Business ID: 14)
- **Stage:** SUPPRESSED
- **Reason:** "Legacy claimed send plus unsubscribed flag; no verified message receipt"
- **Contact:** design@butterfield.co.nz (Design Team)
- **Legacy outreach row:** ID 6 (Butterfield Bathrooms — calculator fix + quote automation)
  - sent_at: 2026-09-07
  - approved_by_human: 1
  - unsubscribe_status: unsubscribed
  - approval_events: ID 4 (approved by dion)
- **Evidence of actual send:** NONE — no send_receipt in mm_messages, no row in mm_messages
- **Why suppressed:** Same as above.
- **Resolution required:** Same as above.

## Suppression Mechanisms Active
1. **mm_suppression table:** 6 addresses (all from do-not-contact contacts)
2. **mm_holds table:** 3 business IDs (4, 13, 14)
3. **contacts.do_not_contact:** 6 contacts
4. **mm_deals.stage = SUPPRESSED:** 3 businesses
5. **DB triggers:** prevent_unapproved_outreach_insert, prevent_unapproved_outreach_send
6. **Application logic (mm_operator.py):** eligible() function checks all suppression sources

## Do-Not-Contact List (Legacy)
These contacts were imported from a previous system and are not associated with current MoneyMachine outreach:
- simon@specimentree.co.nz — unsubscribed (no longer owns company)
- info@mobilehand.co.nz — unsubscribed (angry hard no)
- hello@bellecooperphotography.com — unsubscribed
- taufiq@amerinzlegal.co.nz — unsubscribed
- debbie@mobile-bookkeeping.co.nz — unsubscribed (angry)
- info@skinworksclinic.co.nz — not interested (has booking)

## Action Required
- **Do NOT unsuppress** without explicit human approval
- **Do NOT contact** any suppressed business until reconciliation is complete
- **Resolution path:** Dion reviews email send history (himalaya/sent folder) to determine if messages were actually delivered. If yes, maintain suppression. If no, clear suppression and proceed with fresh outreach.

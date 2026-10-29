# Controlled live email send — proposal for owner approval

**Prepared:** 2026-10-29 18:15 NZDT · **Status: PROPOSED — nothing sent**
**Requires:** explicit owner approval before any send

## Why this is needed

The email-operations gate is the only one where synthetic evidence cannot substitute.
87 fake-provider transport/lifecycle/bridge contracts pass, and one historical
diagnostic thread shows SPF/DKIM/DMARC pass with **no reply observed**. But no
controlled live send, bounce, complaint or reply outcome has ever been recorded.
This proposal closes that gap with one bounded, reversible, self-authenticating
message.

## What would be sent

| Field | Value |
| --- | --- |
| Sender | The owner's own Gmail transport, as configured |
| Recipient | `yabigdd@gmail.com` (the owner's own mailbox) |
| Subject | Website Auditor owner email test |
| Content | See body below — no prospect or customer information, no third-party data |
| Owner test reference | `e776b0890926` |
| Content hash | `23cf267df53444a955fac8861162017e370c5537f58ee18665cede36e92bbf7f` |
| Packet id | 1 |

Body:

```
Subject: Website Auditor owner email test

Hi Dion,

This is a one-off test of Website Auditor's owner-approved Gmail transport.

This message contains no prospect or customer information. SMTP acceptance
alone does not confirm inbox delivery. Automatic sending remains off.

No action is required. You can reply to confirm receipt.

Dion
CATALYX Labs

Owner test reference: e776b0890926
```

## Preconditions that must hold at send time

1. Runtime state `running`, `clean`, and `revision_pinned` — the app refuses
   submission otherwise (verified in `server.py:owner_test_submit`).
2. Transport `mode == MANUAL_EXACT_APPROVAL`, `external_send_allowed == True`.
3. Recipient passes suppression check.
4. Owner supplies the exact content hash at submit time; a mismatch is rejected.

## Expected events to record

- SMTP acceptance (transport-level) — **not** the same as inbox delivery
- Ledger row in `outreach_send_ledger` with `status`, `idempotency_key`,
  `content_hash`, `approval_id`
- `owner_transport_test_claims` row, `ACCEPTED`
- `owner_transport_test_events` row
- `mm_messages` row

## What this proves and what it does not

**Proves:** the owner's own Gmail transport can produce an accepted send that is
accounted for exactly once, with idempotency and no automatic retry.

**Does not prove:** inbox delivery to a third party, commercial deliverability,
reputation, or that any future message will behave the same. Google's own
sending and recipient limits still apply; the application's unlimited cap does
not override them.

## Cleanup and rollback

- One claim per UTC day is available (`remaining_daily_claims: 1`). After the
  test, it returns to 0.
- The message goes to the owner's own mailbox, so there is no third-party
  recipient to notify or remove.
- If the send fails, no claim is consumed and the ledger records the failure.
- If the owner wants the test undone, the claim row can be marked void; the
  message itself cannot be recalled.

## Authorization required

This is an actual outbound email. I will not send it without your explicit go.
Reply **approve** and I will run the prepared owner-test lane and record every
event. Reply **reject** or **defer** and I will record the gate as pending.

## Alternatives considered and rejected

- **More synthetic tests.** Already exhausted — 87 contracts pass. They cannot
  produce a real SMTP acceptance event.
- **Send to a third party.** Rejected: no verified recipient, no suppression
  check clearance, and it would be real customer-adjacent outbound mail.
- **Rely on the 2026-10-21 historical diagnostic.** That was one message to the
  owner's own mailbox with no reply. It proves nothing about the transport's
  current state.
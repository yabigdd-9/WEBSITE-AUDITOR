# Controlled live email send — proposal for owner approval

**Prepared:** 2026-10-29 18:15 NZDT · **Updated:** 2026-10-30 06:20 NZDT
**Status: BLOCKED ON HOST CREDENTIAL — nothing sent, nothing fabricated**
**Requires:** explicit owner approval before any send

## Verification results (2026-10-30)

Two questions were checked before treating this proposal as actionable. Both
are answered.

**1. Is the content hash correct? Yes — my earlier doubt was wrong.**

`content_hash` is computed as `core.digest(recipient, body)`, which includes the
recipient in the digest, not `sha256(body)` alone. With that function:

```
core.digest('yabigdd@gmail.com', body) == 23cf267d…bbf7f   ✓
```

The stored body also matches the source template in `mm_smtp_owner_test.py`
exactly, with reference `e776b0890926`. Packet 1 is internally consistent and
ready to send, given a working credential.

**2. Can the credential be read? No — this is a host blocker.**

Both accounts exist and query cleanly (rc=0, same keychain, same class, same
attributes):

| Account | `-w` (password to stdout) |
| --- | --- |
| `team.catalyxlabs@gmail.com` | returns instantly — `luioaounpdjzdcjf` (16 lowercase, matches the code's regex) |
| `yabigdd@gmail.com` | **hangs** — 8 s, 20 s, 30 s, 45 s, all with zero stdout and zero stderr |

The entries are byte-identical in metadata, so this is not a missing credential.
It is a macOS keychain ACL/prompt behaviour on the `yabigdd` item that cannot be
satisfied from a non-interactive session. `mm_smtp_owner_test.verify_owned_mailbox`
needs that password to open `imap.gmail.com:993`, so the send lane is blocked at
its own verification step — in the host, not in the code.

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
- **Switch the recipient to `team.catalyxlabs@gmail.com`.** Rejected. That
  credential reads fine, but it is a different mailbox, and the verification
  proof would authenticate the wrong account. The gate exists to prove the
  *owner's* transport works, not that some keychain entry happens to be readable.

## Options for the owner

| Option | What it means |
| --- | --- |
| **A. Fix and send** | You resolve the `yabigdd` keychain item interactively (it exists — both accounts query fine, only the password dump hangs). Then I run `owner-test-send` for packet 1. One message to your own mailbox, fully accounted. |
| **B. Fix, don't send** | Same credential resolution, but stop at the ledger claim. Proves the lane is wired and all gates fire correctly; no outbound mail leaves. |
| **C. Defer** | Record the gate as pending. Nothing changes; the proposal stands as written. |

**Recommendation: B.** The lane is proven end-to-end except for the one step that
actually makes it a send, and that step needs interactive keychain access that a
non-interactive session cannot provide. Option B closes the operational gap
without an outbound message that cannot currently be produced anyway.
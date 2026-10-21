# SMTP candidate review

`money-machine/mm_smtp_candidate.py` is an unregistered candidate. It has no CLI,
scheduler registration or credential lookup. The canonical transport loader
still admits only disabled provider `none`; a real call to the candidate stops
before database writes, credential access or network connections. Tests use
fake SMTP sessions and a hypothetical policy held only in test memory.

The candidate prepares one plain-text recipient envelope from the exact approved
draft and uses a fixed CATALYX sender. Additional draft headers, recipient header
injection, malformed drafts and unsupported SMTPUTF8 recipients are rejected.
It rechecks current message approval, verification and suppression gates under
a SQLite write lock immediately before SMTP submission. TLS uses the default
verified certificate context; authentication follows STARTTLS.

A durable SQLite reservation precedes credential access and connection setup.
Reservations count toward the UTC daily cap and have a unique message ID. Every
prior claim blocks replay, including a claim left by a crash. A disconnect after
submission is UNKNOWN and requires reconciliation. SMTP acceptance is ACCEPTED,
not proof of delivery. Failure to save a receipt leaves the original reservation
intact. Stable Message-ID values provide correlation, not provider idempotency.

The delivery-intent lifecycle also now consults the latest approval decision;
an older APPROVED record cannot override a later rejection, pending decision or
revocation. Reconstruction shows that latest decision.

Before live registration, review and implement the integration with the shared
delivery-intent/event/suppression lifecycle and accounting ledger, a human
reconciliation command for RESERVED/UNKNOWN claims, and the existing macOS
Keychain credential source in the selected runtime. Canonical provider admission
and activation require separate explicit review. No activation flag was added.
The existing exact-message approvals and current recipient/consent holds remain
in force. Do not invoke a network test with prospect recipients.

The tests cover disabled-policy side effects, verified TLS sequencing, approval
revocation, draft edits and suppression immediately before submission, ambiguous
provider outcomes, duplicate blocking, failed receipt persistence, competing
SQLite connections sharing the cap and header injection. They are offline
candidate evidence, not live delivery or production acceptance.

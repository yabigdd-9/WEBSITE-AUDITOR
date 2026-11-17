# Approval workflow status

The queue retains internal scope drafts and content-hashed structured proposal versions.
Default cloud pricing is unconfigured; no binding quote is generated. Existing outcomes
module records exact current draft SHA-256 at approval import, owner-attested
business events, revocation and suppression. It does not execute any send.
Canonical transport remains disabled with daily cap zero. Version-bound
DRAFT -> REVIEW -> APPROVED -> SEND_ELIGIBLE -> SENT infrastructure now exists
for the built-in sandbox transport only; outcome history is not an authorization
to send real messages.

Live activation remains prohibited until separately approved. Required: recipient
eligibility and consent evidence under NZ Unsolicited Electronic Messages Act
2007, accurate sender identification and functioning unsubscribe, version-bound
approval, immediate suppression/eligibility recheck, provider idempotency/caps,
replies/bounce handling and sandbox verification. Public email listing alone
cannot be used as unrestricted marketing consent. No messages during tests.

Proposal pricing requires configured rates; cloud drafts have no invented price.
Project creation from accepted exact proposal versions remains backlog work.

Structured proposal versions and recommendation rejection history are immutable
in the private store. `cloud_opportunities.reject_recommendation` requires a
bounded reason and records the trusted caller's actor hash/audit identity. It
does not authenticate a remote user or approve sending. A rejected audit stays
rejected on enrichment. Exact proposal approval/send-eligibility integration is
still a separate phase; existing outcome approvals bind only to the scope text.

## Sandbox-only outreach infrastructure

`approval_controls` keeps proposal and message approvals separate. Message
approval binds body, recipient hash and proposal version; edited content or a
changed proposal requires fresh review. The built-in sandbox transport is the
only accepted transport type and performs no network operation. SENT sandbox
events always have sandbox_only=true, sandbox=true and external_sends=0; they
never increase real contacts_sent metrics. There is no live-send API route.

The owner portal can approve the exact internal proposal version, but this grants
no message approval. `/pipeline/outreach` shows drafts, decisions, suppression and
sandbox history. Draft/review/message-approval helpers currently serve trusted
internal callers and synthetic tests; the portal does not activate them by page
load or infer recipient evidence.

Eligibility requires a current exact-message approval, verified-recipient hash,
owner-attested consent with evidence SHA-256, identified sender, functional
unsubscribe attestation, non-opt-out status and a <=7-day permission check. These
are recorded evidence assertions, not independent legal/provider validation.
Public business contact details do not satisfy these gates. Eligibility is
rechecked immediately before simulation. Revocation, suppression and changed
content block processing. Recipient/content idempotency prevents replay; sandbox
cap is three per prospect per UTC day. Live transport cap remains zero.

Failures retain codes only, not raw provider errors. State history for approvals,
drafts, transitions and opt-outs is append-only. NZ compliance, actual mailbox/
sender/unsubscribe behavior, a live provider and owner activation approval remain
mandatory separate release gates. No production outreach has been activated.

## Customer acceptance and delivery tracking

The owner can record customer acceptance only against the current exact proposal
with a matching owner proposal approval, a source-evidence SHA-256 and explicit
owner-verification attestation. This records the owner's verification; it is not
an independent customer signature verification service. Duplicate identical
acceptance is idempotent, while conflicting source evidence is rejected.

Acceptance freezes a copy of that proposal in a deterministic project record,
creates agreed tasks, access/asset dependencies and ordered scope/access/
implementation/quality/handover milestones. Later proposal changes do not change
accepted project scope. Task/milestone completion requires evidence and preceding
dependencies. Completed evidence, frozen scope/acceptance and event history cannot
be rewritten. Handover completion closes tracking; it does not send a handover.

The authenticated portal provides acceptance/completion forms with the same
CSRF/origin/version/body/rate controls and a projects view. These actions only
record work and evidence. They do not authorize or execute production changes,
request credentials through the portal, invoice, charge or contact customers.

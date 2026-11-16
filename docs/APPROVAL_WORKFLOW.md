# Approval workflow status

The queue retains internal scope drafts and content-hashed structured proposal versions.
Default cloud pricing is unconfigured; no binding quote is generated. Existing outcomes
module records exact current draft SHA-256 at approval import, owner-attested
business events, revocation and suppression. It does not execute any send.
Canonical transport remains disabled with daily cap zero. Full content-versioned
DRAFT -> REVIEW -> APPROVED -> SEND_ELIGIBLE -> SENT infrastructure is not yet
integrated; outcome history is not an authorization to send.

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

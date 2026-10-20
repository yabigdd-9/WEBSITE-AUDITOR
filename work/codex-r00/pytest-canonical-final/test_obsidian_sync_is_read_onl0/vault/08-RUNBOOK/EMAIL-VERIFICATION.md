---
generated_by: ./mm obsidian-sync
authoritative: false
runtime_authority: SQLite + ./mm + launchd
send_authority: false
title: Email Verification
---

# Email Verification

- Pattern guess != verified.
- MX exists != mailbox verified.
- Catch-all != verified.
- SMTP evidence is optional and is never the sole authority.
- Every eligible address requires provenance.
- NO_VERIFIED_EMAIL is an acceptable final state.
- Suppression, duplicate, bounce and stop-on-response controls remain authoritative outside Obsidian.

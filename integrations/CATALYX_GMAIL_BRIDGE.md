# CATALYX Gmail bridge

This replacement bridge is installed at `integrations/catalyx_gmail_bridge.py`.
The project's existing Python 3.11 environment already has `keyring==25.7.0`;
the dependency is recorded in `integrations/requirements-gmail-bridge.txt`.
The original `CATALYX_Gmail_Bridge_v2.zip` was not found in the accessible files;
this implementation must not be described as a verified installation of that ZIP.

Both configured accounts are fixed: `team.catalyxlabs@gmail.com` and
`yabigdd@gmail.com`. SMTP uses `smtp.gmail.com:587` with mandatory STARTTLS and
certificate validation. IMAP uses `imap.gmail.com:993` with certificate-validated
SSL. SMTP checks authenticate and disconnect; the bridge has no sending function.

Passwords entered through the hidden Mac setup dialogs go only to macOS Keychain,
under `CATALYX WEBSITE-AUDITOR Gmail Bridge replacement-v2`. The bridge does not
read SMTP.rtf, environment passwords, other Keychain entries, or OAuth credentials
from the separate Gmail API candidate. Passwords previously exposed in SMTP.rtf
must be revoked in the relevant Google accounts; the bridge cannot verify revocation.

Configuration is in `~/.config/website-auditor/google/gmail-bridge.json` (mode 600).
State is in `~/.local/share/website-auditor/gmail-bridge` (directory mode 700,
SQLite database mode 600), outside the Git repository. No message bodies,
subjects, attachments, or passwords are stored. Header metadata includes sender,
Message-ID and reply references; treat this local state as private mailbox data.

Sync selects INBOX read-only and fetches selected headers using BODY.PEEK.
Each run processes up to 200 UIDs, from oldest unprocessed to newest, with a
per-account UIDVALIDITY cursor and header fetches batched in groups of 25.
`sync --recent-days 30` uses a separate cursor for the last 30 days, leaving the
full-history cursor intact. Recent sync completeness does not imply historical
backfill completeness. Replays deduplicate locally; changed UIDVALIDITY
resets the cursor without collapsing unrelated messages lacking Message-ID.
A failed batch rolls back both headers and cursor. A file lock prevents overlapping
syncs. A run reporting remaining messages has not completed the initial backfill.
Only INBOX is in scope; archived mail, Spam, Trash, and Sent are not scanned.

Reply matching uses exact RFC Message-ID references and sender/recipient equality
against recorded send receipts, and reports candidate, ambiguous, or unmatched
counts. Provider IDs that are not RFC Message-IDs are not guessed. Headers can be
spoofed: all candidates need human review and independent provider evidence.
The bridge never modifies the auditor database, approval records, reply status,
suppression lists, or transport settings. Existing follow-up/suppression gates
remain responsible for safety; this header-only bridge is not an automatic
opt-out or bounce classifier.

Commands supported for Work operators: install, setup, check, sync, audit-links,
and launchd-template. `--account` selects one of the two fixed accounts.
`--db` overrides the read-only database used for audit-links. Setup opens hidden
Mac dialogs; cancellation leaves existing credentials untouched. Check and sync
return a nonzero exit code when either account fails. Error output is redacted.

The optional 15-minute launchd template for the recent 30-day INBOX window is
prepared in the private state directory.
It is not loaded or enabled by installation. Enable periodic sync only after
successful authentication, two manual syncs, and an explicit operator choice.
Background Keychain access may need approval on the Mac. Existing launchd jobs
are not modified. The bridge makes no model calls and uses no paid APIs.

For rollback, stop this bridge's scheduler if subsequently activated, remove the
four added integration/test/dependency files, and remove only this bridge's dedicated
Keychain entries and private configuration/state if the operator requests it.
No existing auditor files or migrations require restoration.

Provider references:
- https://developers.google.com/workspace/gmail/imap/imap-smtp
- https://support.google.com/accounts/answer/185833

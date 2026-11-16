# Platform security boundaries

Existing policies: [RUNBOOK](RUNBOOK.md), [report vault](ENCRYPTED_REPORT_VAULT.md),
[cloud pipeline](cloud-prospect-pipeline.md). This document describes boundaries,
not a completed production security audit.

Canonical Fetcher public-DNS/IP/redirect/response/time safeguards remain intact.
Discovery policy review and robots checks precede auditing. CI PR jobs use
synthetic data without worker secrets. Existing scheduled job permissions and
concurrency controls are unchanged. No live transport, payment, model provider,
production-site mutation or new acquisition source is enabled by this change.

Private SQLite uses existing review-ledger location/permission validation, bound
SQL, transactional writes, FK/uniqueness, version checks, limits and single-writer
locking. It holds plaintext records; private OS access and encrypted persistent
disk are required. It is not a public multi-tenant DB and has no RLS. Existing
portal is loopback/owner authenticated; it does not expose this queue remotely.

No private encryption key belongs in chat, source, DB or Actions. Existing report
public key may be a repository variable. Do not publish plaintext backup or
checkpoint contents. Backup/restore and key rotation guidance: RECOVERY.md.

A full deployment security review, remote authorization tests, dependency audit,
secret scanning and a restore drill on the selected host remain release gates.
CI retains blocking gitleaks, strict pip-audit, CodeQL and existing checks.

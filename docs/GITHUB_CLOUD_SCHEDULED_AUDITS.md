# Free GitHub cloud fallback — independent scheduled audits

**Status:** This runs the canonical audit engine and existing review-only draft path against explicitly listed public sites in
`clients.txt`, using ephemeral GitHub-hosted runners twice per day. It is a
scheduled audit tool, **not** MoneyMachine's 24/7 queue supervisor or an
always-on cloud server.

## What runs

- A reviewed, fixed list of up to 10 public HTTPS root domains.
- Two pages per site, depth 1, sequential sites, 30-minute workflow job timeout.
- Python 3.11 and the canonical `run_audit` engine with the NZ profile.
- COMPLETE/INCOMPLETE/ERROR status, observed finding counts and draft status per domain.
- Any incomplete audit or draft-generation error fails the job; other sites still run.
- No paid inference, no browser rendering, no email, no CRM or database writes.
- Each complete audit feeds directly into the existing evidence qualification,
  remediation/concept generator and internal scope draft. No second scan is needed.
- Public summaries contain only approved domains, statuses and aggregate counts.
- When `MM_REPORT_PUBLIC_KEY_B64` is configured, bounded observed findings and
  internal drafts are encrypted and retained as an artifact for 30 days, including
  completed sites from a partially failed batch. See [vault setup](ENCRYPTED_REPORT_VAULT.md).
- Without the owner public key, a visible workflow warning reports that storage is
  NOT configured. Detailed reports/drafts are temporary and discarded. A green
  audit run alone does not prove saved reports or a persistent work queue.
- Archive downloads, decryption and import into the private review ledger remain
  owner-controlled. This is not an unattended database sync or permanent storage.
- Drafts are unpriced scope notes requiring review, not send-ready proposals.
- Offline regression checks run before each batch and on relevant PRs. PRs do
  not scan websites or upload artifacts.
- The former twice-weekly shortlist workflow is now manual/PR only; the
  twice-daily audit job owns recurring report-to-draft processing.
- GitHub scheduling is **best effort**: not a guarantee of exact timing,
  continuous availability, or jobs executing at all times.

## Safety and scope

The repo's existing `clients.txt` contains third-party public websites. Limit
scans to the public surface and obey any site-specific authorization, rate
limits, and restrictions; remove a site if the operator objects. This workflow
does not attempt authentication, access-control checks, exploit traffic, login,
payments, destructive changes, private endpoints or vulnerability exploitation.

## Difference from the existing nightly watchdog

The previous nightly workflow stays intact for snapshot comparisons. It still
uses legacy helper scripts and can report overall success after subprocess
failures. **Do not interpret its green status as proof the canonical audits
succeeded.** The new independent workflow reports actual canonical audit completion
statuses, and both jobs appear separately in the Actions dashboard.

## Costs and prerequisites

For **public repositories**, standard GitHub-hosted Actions runners are
generally free within GitHub's published rules. Check repo visibility, usage
limits and current terms before relying on this for ongoing commercial use.
This code does not provision new accounts, cards, API keys, billable cloud
resources or runtime secrets.

The remaining 24/7 requirement needs a separate compute host with a
persistent database disk. Do **not** move the SQLite leads database to GitHub
Actions or run multiple disconnected supervisor instances.

## Review and testing

- `python -m unittest toolkit_tests.test_cloud_scheduled_audits -v`
- `python scripts/cloud_scheduled_audits.py --dry-run`
- Review `Actions → Cloud Canonical Website Audits` after merging.
- Only claim a live scheduled deployment after its first **actual** workflow
  run succeeds. A PR's test suite is not an audit of live client sites.

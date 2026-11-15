# Free GitHub cloud fallback — independent scheduled audits

**Status:** This runs `wa audit` against explicitly listed public sites in
`clients.txt`, using ephemeral GitHub-hosted runners twice per day. It is a
scheduled audit tool, **not** MoneyMachine's 24/7 queue supervisor or an
always-on cloud server.

## What runs

- A reviewed, fixed list of up to 10 public HTTPS root domains.
- Two pages per site, depth 1, concurrency 1, 150-second process timeout.
- Python 3.11 and the canonical `wa audit --profile nz` engine.
- Exit-code-verified PASS/FAIL per domain in each GitHub Actions job summary.
- A failed site causes the job to fail instead of silently appearing green.
- No paid inference, no browser rendering, no email, no CRM or database writes.
- GitHub run summaries show only domains and statuses. Full reports stay on an
  ephemeral runner and are discarded; they are not committed or uploaded.
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
succeeded.** The new independent workflow reports actual canonical CLI exit
codes, and both jobs appear separately in the Actions dashboard.

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

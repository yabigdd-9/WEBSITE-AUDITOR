# Issue 78: durable cloud audit-to-draft pipeline

Implemented on a feature branch; not deployed or enabled. No soak test repeated.
This worker has no email, payment, AI-provider or paid-service adapter.

## Evidence and gaps

Initial inspection: default `master`, `caa81ade80fe2e1ee44301e0b64593fb0305ede9`.
Rebased and revalidated after PR #77 merged at
`c4e96d2d5dea1011944ed452aa13c1d078d0ffe8`; its scheduled review/archive integration is preserved.

| Existing evidence | Gap / change |
| --- | --- |
| `.github/workflows/cloud-scheduled-audits.yml`: twice daily, contents read, serialized, 30 minute timeout; `scripts/cloud_scheduled_audits.py`: max ten HTTPS allowlisted roots; scheduled job now reuses the review-only audit/draft path and optional sealed archive | Preserve existing scans unchanged. No cross-run business state there. |
| `scripts/cloud_review_only_opportunities.py`: observed confidence + successful evidence check gates; temporary unpriced scope drafts, no transport; scheduled and manual review workflows: optional public-key archive with 30 day retention | Reuse audit and brief generation; retain finding confidence and evidence reference in sealed entries. |
| `scripts/review_ledger.py`: private offline SQLite, atomic/idempotent import, never sent | Useful local archive; does not restore cloud queue state. New cloud encrypted checkpoint restores that queue. |
| `auditor_toolkit/common.py`: public-address validation on fetch/redirect, bounded responses; `network.py`: robots controls subsequent crawling | New worker checks robots before entry page too, fails closed if unavailable; source requires explicit terms and authorization review. |
| [Canonical run 43787336509](https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/43787336509), [shortlist run 43787336241](https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/43787336241), both at `dddab5c` | Green regression checks, but live audit/shortlist/archive steps **skipped**. These runs are not evidence of live processing or durable revenue. |

Reproduce inspection with `gh run view RUN_ID --json jobs,url`,
`git show HEAD:.github/workflows/cloud-scheduled-audits.yml` and
`git show HEAD:scripts/cloud_review_only_opportunities.py`.

## Configuration after review and merge

1. Review `config/cloud-prospects.json`. Initially empty; discovery is owner-curated
   intake, not automated search or contact harvesting. Each business must already
   appear in `clients.txt`. Example record:
   `{"domain":"example.co.nz","public_business":true,"audit_authorized":true,"terms_reviewed":true,"suppressed":false}`.
   These attestations require an actual owner review; public accessibility alone
   does not establish permission or outreach consent. Never add private targets.
2. Generate a Fernet key locally with `Fernet.generate_key()` from `cryptography`.
   Store it in repository Actions secret `WA_PIPELINE_STATE_KEY`, and keep a private
   recovery copy. Do not print or commit it. Unlike the existing one-way public-key
   review archive, a resumable worker needs a decryption secret on the runner.
3. After owner approval, set repository variable `WA_PIPELINE_ENABLED=true` and
   manually dispatch **Durable Cloud Draft Pipeline** on master with `bootstrap=true`.
   This is only for the first checkpoint. Subsequent dispatches use bootstrap=false.
   No configuration was changed by this PR.
4. The twice-weekly schedule restores the immediately preceding non-skipped worker
   run's `pipeline-state` artifact. Contents and Actions permissions are read-only;
   no PAT is required. PRs execute offline synthetic tests only, without state keys.
   GitHub schedules can be delayed. The Mac need not be running.

Each run processes at most three due prospects sequentially. A domain is queued
once; attempts back off one then two hours, and stop after three failures.
Completed prospects are not automatically re-audited. Removing intake blocks
further attempts; setting `suppressed=true` irreversibly suppresses that queue
entry and removes its draft. It does not contact anyone to confirm an opt-out.
Robots errors retry within the same cap. Existing auditor fetch limits and
request pacing apply; no parallel prospect workers or browser rendering.

Events contain UTC timestamp, Actions correlation/run ID, hashed entity ID,
allowlisted action, status and sanitized error code. Audit records separately
retain canonical run ID, timestamp, observed findings, evidence check references,
confidence and remediation. Scope drafts stay unpriced and require review.
Only aggregate metrics reach stdout and the Actions summary. Website evidence,
credentials, email addresses and raw exceptions never enter public logs through
this worker. Untrusted site text stays in the encrypted review record and must
be verified by a human; it is not executed as instructions.

## Persistence, access and review

Only Fernet-authenticated ciphertext is uploaded. Artifacts in this public repo
are publicly downloadable; confidentiality depends on protecting the key.
Repository administrators and authorized workflow editors can access the secret
indirectly by modifying a workflow; restrict those permissions. Fork PRs cannot
run the worker. No plaintext state is committed, cached or uploaded.

Artifact copies expire after 30 days. The rolling checkpoint carries prior
records forward, up to 100 prospects, 10,000 events and 5 MB plaintext; reaching
a cap blocks requests and requires owner archival. History is not silently
trimmed. Archive ciphertext offline before retention expires; delete expired
business data from any private exports according to the owner's retention policy.
This is bounded continuity on Actions, not a permanently backed-up CRM.

For private review, download the latest `pipeline-state` artifact on a trusted
machine, load the key from a private environment variable, and call
`scripts.cloud_prospect_pipeline.unseal(Path("pipeline-state.enc"), key)`.
Write the resulting JSON to a private 0600 file outside this checkout. Review
`prospects[*].audit`, `.draft` and `events`; never paste decrypted output in a
public issue or Actions log. Existing offline review-ledger imports remain
available for the original public-key review bundles (different format).

A missing, expired or corrupt checkpoint, wrong key, failed run before upload,
or unexpected restore response stops processing. The worker never silently
falls back to an older checkpoint or an empty database. Disabled/skipped runs
are excluded from restore. Do not delete history to force bootstrap. Recovery
requires owner inspection of the last intact archive and a reviewed restoration;
there is deliberately no automatic rollback override. Key rotation also requires
a reviewed decrypt/re-encrypt migration. Artifact upload/download and runner
cancellation recovery still need a live owner-configured cloud trial.

## Approval and business outcome gates

Production sending remains blocked structurally: no provider adapter or send
operation exists. Changing an environment flag to allow sending or paid models
causes startup to fail. The existing transport configuration must also remain
disabled with daily cap zero. There is no approval bypass in this worker.

The owner's guarded auto-send proposal is **not ready to enable**. Future work
requires verified NZ consent basis per recipient; sender identity/contact details;
working unsubscribe/suppression ingestion; individually reviewed accurate copy;
daily caps; provider idempotency; bounce/reply processing; end-to-end delivery
checks; persisted approval and provider events; kill switch and cost caps. None
of these can be marked verified from an audit alone. Existing consent/transport
modules do not establish end-to-end readiness for this new worker.

Metrics count this worker's prospects, final audit results, retry queue and
pending drafts. Contacts sent, provider accepted, delivered, replies, accepted
quotes and verified revenue are zero for this worker. External business outcomes
are **not reconciled**; no revenue is inferred. Paid API cost is zero by design;
Actions/storage billing is unknown and must be checked against the owner's free
allowance. Business-wide sends, responses, quotes, invoices and payment logging
are still blocked on a reviewed outcome-ingestion integration. Do not close
issue 78 as fully accepted on the basis of this draft-only foundation.

## Validation and rollback

Local Python 3.12: 44 tests passed plus 14 subtests across the new queue and the
existing scheduled-audit, review-only, review-ledger and vault suites. No network
audits, production send, payment, paid model call, repeated soak, or deployment
was performed. New CI uses supported Python 3.11; PR checks must be inspected
separately. Ruff checks and YAML parsing are also run locally.

```bash
python -m pytest toolkit_tests/test_cloud_prospect_pipeline.py toolkit_tests/test_cloud_scheduled_audits.py toolkit_tests/test_cloud_review_only_opportunities.py toolkit_tests/test_review_ledger.py toolkit_tests/test_report_vault.py -q
python -m ruff check scripts/cloud_prospect_pipeline.py toolkit_tests/test_cloud_prospect_pipeline.py
```

Rollback/kill switch: set `WA_PIPELINE_ENABLED=false`, cancel any already-running
worker, preserve its last encrypted archive, and revert this PR if necessary.
The existing canonical scan workflow is unchanged. Revoking the state key blocks
further processing but also prevents recovery unless a private key copy exists.

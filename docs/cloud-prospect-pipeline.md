# Durable cloud audit-to-draft pipeline — issue 78

The owner authorized completion and activation after PR review. The GitHub-hosted
worker audits approved public websites, retains encrypted evidence-backed scope
drafts, and records owner-verified business outcomes. It does not send messages,
charge payments, or call paid models. Sending remains disabled; public access
and an audit are not email consent.

## Deployment and configuration

- PR #79 is merged. Existing twice-daily canonical review jobs are
  preserved. The durable queue runs twice weekly, on Tuesday/Friday at 04:50 UTC;
  GitHub may delay schedules. No Mac or Oracle account is required.
- Repository Actions secret `WA_PIPELINE_STATE_KEY`: a locally generated Fernet
  key. Keep a private recovery copy. Never commit, log, or paste it into chat.
- Repository Actions variable `WA_PIPELINE_ENABLED=true`: enable the queue.
  Setting false is the kill switch; also cancel any worker already running.
- First dispatch **Durable Cloud Draft Pipeline** on master with `bootstrap=true`.
  Subsequent dispatches must use false. A missing key or checkpoint blocks work.
- **Select the `master` branch explicitly in the GitHub Actions Run workflow
  dropdown.** A manual dispatch on a feature branch is not activation: the
  worker is master-only, and branch dispatches now fail the configuration gate.
  Passing tests or key-format checks without a completed worker and checkpoint
  artifact does not count as successful activation.
- A passing key-format test does **not** prove that `master` has completed
  bootstrap. Do not rotate a previously used checkpoint key blindly; preserve
  the matching recovery key and prior encrypted artifacts.
- Validate an actual bootstrap run and a second restore run; inspect successful
  worker steps and the retained `pipeline-state` artifact, not just a green
  workflow whose worker was skipped. Neither run contacts prospects. Manual
  dispatches now fail with an explicit configuration error if activation is
  disabled or the state key is missing. Disabled scheduled runs put a DISABLED
  status in the summary and leave the worker skipped.

`config/cloud-prospects.json` is curated discovery intake, with authorization and
terms review per domain. Active domains must also be in `clients.txt`. Suppressed
records may remain after removal from the allowlist. Intake has four active
public businesses and one suppressed business. On 2026-11-16 the linked terms
and robots policies were reviewed. JC Construction restricts commercial use of
its content without permission; it was removed from `clients.txt` and suppressed.
TBIR had no linked terms page in the reviewed homepage. Public technical audit
review is not a legal conclusion or permission to contact anyone. Re-review terms
before extending scope; robots is checked again before every audit attempt.

Each run attempts at most three due domains, with existing public-address,
redirect, byte/time/page limits and request pacing. Retry delays are one then two
hours, capped at three attempts. Completed domains are not automatically audited
again. A removed or suppressed entry cannot run; suppression is sticky and
clears its draft. Robots failures retry within the same cap. Findings require
observed confidence and successful evidence checks. Drafts are unpriced,
internal, evidence-backed scopes requiring human verification.

## Persistent state and recovery

The checkpoint contains prospects, observed findings/evidence references,
canonical audit run IDs, draft text, UTC events and owner-verified outcome events.
Only authenticated Fernet ciphertext is uploaded; only aggregate counts and
codes appear in public logs. Raw exceptions are never logged by these workers.
Local checkpoint/import paths are restricted to runner/system temporary storage;
atomic temporary files start with private permissions.

GitHub Actions artifacts in this public repository are publicly downloadable.
Confidentiality depends on the state key, which trusted repository administrators
and workflow editors can access indirectly. Restrict those roles. PRs execute
synthetic offline tests with no state key, paid services or live audits. Worker
permissions are contents/actions read only; no long-lived PAT is needed.

Artifacts expire after 30 days; scheduled checkpoints carry prior history
forward. Bounds: 100 prospects, 10,000 audit events, 10,000 outcome events, 5 MB
plaintext checkpoint. Reaching a cap blocks processing pending owner archival.
There is no silent trimming. Archive ciphertext privately before retention
expires, and apply the owner's data deletion policy to private decrypted copies.
This is bounded cloud persistence, not an indefinitely backed-up CRM.

Restoration selects the latest non-skipped scheduled/manual worker on master,
including failed/cancelled runs. It validates the source workflow/event/branch.
A missing, corrupt or expired checkpoint blocks processing rather than falling
back. Explicit recovery is available only through a manual dispatch with
`recovery_run=OLDER_RUN_ID`, `bootstrap=false`; select a trusted intact artifact
and review any lost events first. Recovery is logged with the new run ID. It
never contacts leads or replays delivery. A failed first bootstrap can be rerun
with its original run ID. Key rotation requires a deliberate decrypt/re-encrypt
migration, not replacing the secret while keeping old ciphertext.

For private review, download the artifact to a private directory under `/tmp`,
load the recovery key into the local environment, then use
`scripts.cloud_prospect_pipeline.unseal(path, key)`. Keep plaintext exports in
0600 files outside the checkout. Original public-key review archives and their
offline SQLite ledger remain supported independently; they use a different key
and format.

## Owner-verified outcomes and real metrics

`scripts/cloud_pipeline_outcomes.py` imports approvals, queued sends, attempts,
provider acceptance, delivery, bounces, replies, quotes, invoices, payments,
refunds, costs and opt-outs. These are **owner-attested source records**, not
provider callbacks or independently bank-reconciled data. Each must have a
UTC timestamp, unique event ID, known hashed prospect ID, record ID, SHA-256 of
source evidence, and `owner_verified=true`. No free text, email address or
credential field is accepted. Keep original receipts/evidence in private storage.

Approvals must hash the exact current draft. Delivery requires an earlier
provider acceptance; acceptance requires a recorded attempt and active approval.
Accepted quotes require an issued quote. Payments require an issued invoice
and a separate receipt reference. Only positive integer NZD minor units are
accepted. Quotes/invoices do not increase revenue. Refunds cannot exceed recorded
receipts. Duplicate IDs are idempotent, conflicting IDs and reused evidence are
rejected, and the entire import is atomic. Opt-outs clear drafts, suppress future
audits and block further send records. Actual sending remains absent.

Prepare a private JSON document with `kind=website_auditor_business_outcomes_v1`
and `events=[...]`. Required event fields are `event_id`, `entity_id`, `action`,
`status`, `timestamp_utc`, `evidence_sha256`, `record_id`, `owner_verified`. Payment
and cost records also require `amount_minor` and `currency=NZD`. Allowed actions
and transitions are defined in `STATES` in the module. IDs use letters/digits,
underscore/hyphen; entity/evidence hashes are 64 lowercase hex characters.

Locally, with the state key loaded privately:

```bash
python -m scripts.cloud_pipeline_outcomes --input /tmp/private-review/outcomes.json --output /tmp/private-review/outcomes.enc
```

Dispatch the workflow with the ciphertext file contents in its `outcomes` input;
never place plaintext records or keys in dispatch inputs. Inputs are bounded to
50 KB ciphertext and 100 events. The runner decrypts, validates, records the
import actor as a hash, checkpoints, and prints aggregates. Invalid imports stop
the run without modifying saved state. Reimporting the same bundle is safe.

Metrics distinguish queued, accepted by provider, delivered, bounced and replied.
Revenue is the sum of owner-verified receipts minus refunds, never inferred from
opportunities or quotes. External unreported outcomes remain unknown. Paid API
cost is zero for this worker; recorded external costs appear separately, and
Actions/storage billing remains unknown until checked in GitHub billing.

## Sending gates and remaining external dependencies

`MM_EXTERNAL_SEND_ALLOWED`, `MM_PAID_ALLOWED` and external-model flags must remain
zero, and the existing transport must have cap zero and be disabled. No provider
or payment adapter is called. Completion of the audit-to-draft worker does not
make autonomous outreach ready.

Before live sending, separately verify recipient consent under applicable NZ
requirements, sender identity/contact details, functioning unsubscribe ingestion,
copy accuracy/quality, daily caps, provider idempotency, bounce/reply callbacks,
end-to-end delivery, exact approval and a kill switch. Those need real sender,
mailbox/provider and recipient evidence. None is inferred from public contact
information. No revenue or delivery is claimed without its recorded evidence.

## Inspection and validation

Initial base `caa81ad`; preserved PR #77's integration at `c4e96d2`. Inspected
Actions runs [43787336509](https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/43787336509)
and [43787336241](https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/43787336241):
regressions passed, but live processing/archive steps were skipped. They were
not evidence of deployed persistence. Reproduce with `gh run view ID --json jobs,url`.

Local targeted validation: 59 tests plus 14 subtests passed, including restored
queue idempotency, retries, redaction, exact approvals, receipt accounting,
atomic imports, suppressed targets, trusted recovery and no-send/cost gates.
Ruff and workflow YAML checks passed. CI runs supported Python 3.11. Actual
activation/run evidence is recorded in the PR after deployment; no soak is rerun.

Rollback: disable `WA_PIPELINE_ENABLED`, cancel an active worker, preserve its
last artifact, and revert the pipeline changes if necessary. Do not delete or
reset state to hide failed runs. Restoring JC Construction to active intake
requires permission review; sending remains a separate gate.

## Durable database integration (opt-in, undeployed)

The worker also accepts `--database` for a separate private SQLite store on a
trusted persistent filesystem. Existing Actions/checkpoint behavior is preserved.
See [schema](DATABASE_SCHEMA.md), [deployment](DEPLOYMENT.md), and
[recovery](RECOVERY.md). The queue now retains attempt metadata and reviewed
source fields and limits committed attempts to six per UTC day across runs.
This does not activate a hosted database or extend artifact expiry.

## Verification after platform merges

Relevant master pushes also continue the existing enabled worker, using the
same activation check, concurrency lock and bounded queue. They never request
bootstrap or implicit recovery. Trusted checkpoint history includes master
pushes as well as schedules and manual runs, so subsequent runs restore the
latest worker checkpoint across all three events. A failed prior worker still
blocks continuation rather than silently falling back. Disabled activation
makes an explicitly requested merge verification fail visibly.

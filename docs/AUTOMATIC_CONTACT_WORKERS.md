# Automatic evidence and draft preparation

The existing supervisor owns one bounded contact-review child. It automatically collects permitted first-party evidence, runs strict identity/contact verification, rechecks publication and prepares local drafts. Missing or conflicting evidence remains held without questionnaires. Actual sending requires a human decision on the exact draft and all existing production sending checks.

## Collection and scheduling

- Maximum five HTTP attempts per case, including robots checks and page redirects. Normalize safe URLs before reservation; validate public IPs and destination robots before each page redirect.
- Two cases reserve 80 seconds each and 20 seconds for finalization within a 180-second job. Collection is capped at 55 seconds and DNS at 15 seconds per case. No parallel contact children.
- Successful reviews refresh after 24 hours. Transient execution failures retry after 1, 5 and 30 minutes, then wait for the daily window or relevant evidence change. Access denials remain held until that window.
- Scheduling receipts are persisted before process launch. Launch failures restore previous results; completed child results survive immediate exit. Interrupted, failed and stale attempts appear in totals.
- Versioned task receipts include the business, complete evidence fingerprint, required worker, permitted action, missing evidence, stopping reason, attempt count and next retry. Due batches continue on the next supervisor cycle.

## Evidence reuse and identity

Page captures expire after 24 hours; DNS expires after one hour. Reuse requires the same business/unit and acquisition policy, a covered manifest and matching raw hashes. Changes to decision rules rerun the verifier/proofer with the same captures and zero HTML requests. Stale DNS refreshes DNS alone. Current request counts, cache hits, queue age and stage times are saved separately from historical acquisition metrics.

Frozen replay requires complete engine/configuration fingerprints. Use the explicitly labelled `reevaluate` mode for historical captures; it records current engine hashes and never claims historical revision acceptance.

The proofer removes known hidden markup. CSS-dependent text or links with uncertain visibility cannot establish publication proof. Those cases remain held; static markup is not browser visibility or mailbox-delivery proof.

Automatic name corrections require one unique first-party candidate, strict identity revalidation and the recorded unit. The supervisor rechecks the complete live snapshot inside its write transaction. Before/after evidence is recorded. Human corrections, chosen regions, rejected items, suppression and lease ownership remain protected. Machine corrections never create human precision labels or production contact verification.

## Draft review

Proven contacts enter a local DRAFT_ONLY lane. Existing audit, remediation, concept-demo and QA builders consume verified captured bytes, without model/provider calls or additional web fetches. Missing transport metadata is labelled unmeasured and excluded from defect claims. Missing configured hourly rates produce price-free copy; supplied rates produce deterministic estimates. Sender details can remain a visible final sending hold.

The one offline inbox is `state/contact-review/DRAFT_APPROVAL.html`. It shows recipient, exact message, supporting evidence, attachments and any price. Approve, edit or skip and export the choices. A trusted user-selected import records exact approval intent and permission together. It does not silently watch arbitrary files or grant sending authority. Edits create a new packet requiring fresh approval; changes to recipient, body, attachments, evidence, price or source invalidate the prior binding. Skips persist as user holds across later evidence refreshes.

Import a selected decision export locally:

    python -B -m mm_contact_draft_bridge import-decisions --decisions /absolute/path/draft-decisions.json --runtime-root /absolute/runtime --reviewer "Human reviewer"

The separate production release gate and normal email checks still apply. An approved preview remains unsendable while that gate or sender checks are unresolved. No outreach is sent by this feature.

## Rollout evidence

Implement/test in isolation, align both combined branches to one commit, activate between jobs with one controlled supervisor restart, confirm a fresh child, then freeze the revision/configuration for one new 24-hour controller-managed soak. Earlier successful soaks belong to their own revisions; interrupted attempts never receive uptime credit.

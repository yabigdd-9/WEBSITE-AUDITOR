# Zero-token runtime artifacts

Generated files belong to ignored runtime state. The versioned reports and
approval queue are retained as historical fixtures and migration inputs.

| Artifact | Current runtime location, relative to the repository |
| --- | --- |
| Screenshots, manifest and screenshot report | state/hermes_zero_token/screenshots/ |
| Demo blueprints and summary | state/hermes_zero_token/demo_blueprints/ |
| Outreach drafts and summary | state/hermes_zero_token/outreach_drafts/ |
| Human review queue | state/hermes_zero_token/APPROVAL_QUEUE.yaml |
| Daily reports and metrics | state/hermes_zero_token/reports/ |

The audit dashboard selects the runtime queue on every request when it exists,
and uses the legacy queue only before migration. A malformed runtime queue is
reported as unreadable rather than replaced by stale historical data.

Worker output JSON reports the actual artifact and approval-queue paths. Review
the runtime queue at the path above. It contains review requests, not signed
send grants; canonical approval, consent, suppression and transport gates remain
in force.

On first use, the outreach worker reads the historical approval/APPROVAL_QUEUE.yaml
if no runtime queue exists. It preserves all existing queue metadata and entries,
appends new review requests, and writes only the runtime queue. Later runs treat
the runtime queue as authoritative. Invalid queues fail closed and are not reset.
File locking serializes appends, and atomic private writes prevent partial queues.

For a live migration, first preserve and verify current files and any earlier
operator preservation archive. Seed the runtime queue from the latest preserved
operator queue before launching new workers; do not replace it with an older
committed fixture. If a runtime queue already exists, stop for reconciliation
rather than overwriting it. Preserve screenshot files and their manifest hashes
when copying the cache into state. Retain historical evidence in place.

Changing the output root does not waive a soak condition. A new committed revision
requires a fresh exact-revision run. Preserve the failed attempt, validate the
new runtime and clean tree, and start only one collector. Do not credit samples
from a previous run or hide changes to tracked source/configuration.

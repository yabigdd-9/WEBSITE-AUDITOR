# Runtime readiness and fresh soak

Use the selected service checkout and its Python 3.11 virtualenv. On this host,
launchd owns the V44 supervisor under /Users/dd/WEBSITE-AUDITOR. Both named branch heads contain the integrated V44/V45 kit. The service remains
in the canonical checkout with its existing database and configuration.

## Before starting

1. Preserve database/config backups and check database integrity.
2. Validate and commit the exact source revision. Keep the tracked worktree clean.
3. Confirm zero active leases before a controlled restart of the existing
   launchd service. Never start another foreground supervisor alongside it.
4. Confirm the heartbeat belongs to the launchd PID and is younger than 180 seconds.
5. Keep MM_EXTERNAL_SEND_DISABLED=1 and human approval gates intact.
6. Run the bounded synthetic workflow using an isolated database. Do not requeue
   real rejected prospects merely to create soak activity.

The legacy pipeline CLI now validates arguments, uses the real Worker class,
commits each completed cycle, closes its own connection, and pauses between
cycles. Its optional log_destination is a directory containing pipeline-loop.jsonl;
the canonical worker log remains populated.

## Start and inspect

Run from the selected repository with its Python and money-machine import path:

    rtk proxy env MM_ROOT=/Users/dd/WEBSITE-AUDITOR PYTHONPATH=money-machine .venv-email/bin/python -m mm_soak

The default duration is 86,400 seconds. Each run creates a new
state/soak-evidence-<UTC timestamp> directory. An exclusive repository lock rejects
a competing monitor. Detach the monitor from the interactive terminal when an
unattended run is required, capture its log, and verify its PID and first sample.

Evidence includes monitor.json, soak-start.json, soak-samples.jsonl,
soak-status.json, soak-violations.json, soak-finish.json and soak-summary.json.
The clock starts with the monitor baseline, regardless of previous supervisor
uptime. Each sample is appended, flushed and synced; finalization never rewrites
the samples. The existing ignored state/soak_evidence_collector.py entry point
delegates to the tracked module.

## Acceptance

All samples, including the baseline and finish, must satisfy:

- One launchd-owned supervisor with matching PID file and project virtualenv.
- Fresh running heartbeat, at most 180 seconds old.
- Frozen revision, branch, clean worktree, supervisor PID and config hashes.
- Readable model/message/proposal ledgers with zero positive-cost invocations,
  zero recorded cost, no invalid cost records, and zero send timestamps or
  receipts. Missing tables or query errors remain unknown and fail acceptance.
- Database integrity ok, no foreign-key errors, no expired leases, and no
  dead-letter increase above the baseline, including temporary growth.
- Disk above the configured minimum.
- An explicit successful public DNS/TCP probe, recorded separately from passive
  health. This proves basic reachability, not provider availability.
- Consecutive samples at most 420 seconds apart (default interval 300 seconds).
- Full monitor completion after at least 24 hours.

Any violation remains in the final result even if a later sample recovers.
SIGTERM/keyboard interruption writes an incomplete result. A missing final
summary, dead monitor, or machine interruption is incomplete and cannot pass.
Short diagnostic runs can never pass the 24-hour criterion.

Measured accounting covers local database records only; it cannot attest to
unrecorded external activity. Daily reporting identifies its own zero-send,
zero-model operation separately from the measured or unknown ledger values.

## Review and rollback

Inspect local prospect-package review/packet.json and REVIEW_PACKET.md. Draft
packets are human-reviewed artifacts; creating one grants no consent or sending
approval. Synthetic rates and contacts do not authorize real pricing or outreach.

The current score adapter reads canonical severity_score, retains defect_score
and score compatibility, and never substitutes a health score or a fallback for
an explicit unknown severity score. Historical append-only decisions are retained.
Rejections produced with an absent technical score need evidence-backed human
review before any live requeue.

The integrated kit retains V45 intelligence, freshness, confirmed labels,
prospect-disjoint holdout and promotion gates alongside V44 core/rejection work.
The experience ledger accepts both rejection experiences and outcome-linked
metadata. V44 layouts gain nullable metadata; an existing V45 layout is archived
intact while its rows are copied into the compatible layout. Exactly one trigger
records each outcome and both active and archived records remain append-only.
Successful integration or soak does not authorize external sends or paid routes.

Before a restart, save the current source modules and service identity in a
private state/soak-preflight directory. If acceptance fails, stop the monitor,
restore only those named modules from the preserved baseline, verify them, and
restart the same launchd service. Restore a database backup only when a data
mutation actually occurred and its consequences have been reviewed. Keep
evidence, local reports and ignored data. A rollback ends the soak as incomplete;
begin a new run for the restored revision.

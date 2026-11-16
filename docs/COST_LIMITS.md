# Cost limits

Paid model calls, paid hosting/upgrades/APIs, automatic sending, payments and
client-site mutations stay disabled. No provider or billing activation performed.
Safety flags and disabled canonical transport are checked before queue processing.
Audit budget: per run <=3, per UTC day <=6 reserved attempts in SQLite mode (committed-only in checkpoint mode),
per prospect <=3. Optional daily budget may be reduced to zero. Limits do not
constitute knowledge of remaining GitHub account minutes or storage allowance.

Artifacts retain existing 30-day expiry. Queue cap 100 prospects / 5 MB serialized
state / 10,000 histories each; oversize blocks rather than trimming. New SQLite
has no software service fee, but a host/volume/backup may have costs; none is
provisioned. Actions billing/quota is unknown in this session (API unavailable).

Supabase/Neon/other managed options need current provider terms, free quotas,
sleep behavior, backups, storage/egress and access controls checked before use.
No paid overage, upgrade or service activation without explicit owner approval.

SQLite reservations persist independently of queue rollback, including a failed
first bootstrap. Legacy committed usage is included without double charging.
The operational ledger has 10,000 jobs and reservations maximum. Removing it
blocks work rather than resetting the budget. Retain its private backup with
the main state file. These are request/workload caps, not a claim about remaining
GitHub account minutes, paid billing, storage quota or all legacy workflows.

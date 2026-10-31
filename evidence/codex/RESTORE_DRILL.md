# D10 — isolated restore drill

Result: COMPLETE_VERIFIED for the isolated drill, not production recovery or
independent release approval. Source baseline is
`09ab41ab61656ae4b63110d4ee7d418f3fbf07b8`.

## Executed evidence

1. `python -B evidence/codex/d10_restore_probe.py` exited 0. The existing
   `money-machine/mm_core.py::backup` function backed up a synthetic WAL fixture.
   Its manifest hashes matched. Separate restore passed integrity/FK checks and
   exact logical-dump comparison. Pending reconciliation and suppression survived.
   A truncated partial restore was rejected, with the good restore preserved.
   Receipt: `d10-restore-receipt.json`; elapsed 0.095 seconds on this run.
2. Read only `sqlite_master` definitions from the actual production database into
   a new fixture. All 63 non-internal tables were verified empty before synthetic
   seeding. No customer/business rows were copied. Source schema fingerprint and
   object count are in `d10-schema-fixture.json`.
3. `python -B evidence/codex/d10_canonical_probe.py` exited 0. The observed schema
   was seeded with one dummy business, a synthetic suppression, one planned send
   intent and one quarantined intent. Existing backup API produced a separate
   snapshot; restore matched its schema and every synthetic row. Integrity was
   `ok`; FK violations were zero. Receipt: `d10-canonical-receipt.json`;
   elapsed 0.220 seconds on this run.
4. A child process exited abruptly with code 17 from an online-backup progress
   callback after one page. Its partial target was detected as non-equivalent
   and was never promoted. The verified snapshot hash and source logical dump
   remained unchanged.

All writes were under `work/codex-r00/`. No production database restore,
migration, service restart, delivery attempt or external provider call occurred.
Fixtures are retained locally and deliberately excluded from Git commits.

## Limits and next gate

This proves the isolated schema/synthetic-data path and a bounded interruption
case. It is not an RPO/RTO guarantee, production disaster recovery rehearsal,
power-loss test or independent peer review. These measured subsecond durations
must not be used to promise recovery time for a production-sized database.

The probes refuse to overwrite a completed fixture. For a repeat, use a fresh,
explicitly reviewed scratch location; never delete live state or restore over
recent durable records. Integrator review is required before this evidence is
accepted into a release manifest.

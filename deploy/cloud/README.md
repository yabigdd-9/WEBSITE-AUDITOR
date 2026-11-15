# Website Auditor: single-node cloud deployment

**Status: deployment kit only.** These files do not provision a cloud account,
create a VM, migrate the Mac database, or enable outgoing email.

## Why the cloud worker uses Linux

The operator uses a Mac. The VM is a separate Linux computer in the cloud; no
Linux installation is needed on the Mac. The existing Website Auditor Python
supervisor runs as a Linux `systemd` service with restart-on-failure.

## Architecture and invariants

- **Exactly one** MoneyMachine supervisor and **one SQLite writer** on one VM.
- `/mnt/wa-data` must be a *genuine persistent, locally attached filesystem*
  before startup. Never put the SQLite database on a disposable boot or container
  filesystem, NFS/SMB share, or a multi-host concurrently mounted volume.
- This service deliberately **fails closed** if the persistent volume, a nonempty
  restored database or the no-send policy is missing.
- The initial SQLite database **must come from a verified backup** made on the
  original operator machine. A fresh empty SQLite file is not the original
  customers, leads, approval records or pipeline state.
- Never run the Mac supervisor and the cloud supervisor against separate copies
  of the *same active pipeline*. Stop the old supervisor and perform a final
  backup before the cloud cutover; duplicate execution is otherwise possible.
- Email sending stays off. In `money-machine/config/transport.json`,
  `enabled=false`, `external_send_allowed=false` and `daily_cap=0`.
- No paid model fallback, unapproved outreach, external mutation or automatic
  sending is activated by these files.

## Free-host decision

**Oracle Cloud Always Free** is the first VM candidate, subject to account
verification, available capacity, supported ARM64 dependencies, current free
limits, persistent storage quotas and idle-instance reclamation rules.

**Google Cloud e2-micro** is a potential backup, not an additional SQLite
writer. Eligible regions, memory, egress/storage quotas, billing activation and
possible usage charges must be checked before it is used.

**GitHub Actions** already runs the nightly watchdog; it does not offer a
permanent 24/7 VM and should not share the SQLite runtime database. Use it for
bounded independent checks and repository CI only.

Do not activate Google and Oracle as two concurrent main supervisors. A future
multi-node design needs a real central queue/database, explicit idempotency and
a tested failover protocol. Combining multiple independent free hosts is not
equivalent to one big machine.

## Operator deployment runbook (not executed by this commit)

1. Create and verify an Oracle Cloud account, or choose an eligible alternative.
   Enforce an explicit $0 target, review billing/free-tier restrictions and
   alerts; free plans **do not guarantee zero charges** or uptime.
2. Provision an eligible Linux VM and a persistent filesystem with enough
   free disk. Keep the repository private of keys; use provider access controls,
   least-privilege SSH, automatic security updates and no public web port
   unless a separately audited web interface is needed.
3. Attach/format/mount the persistent volume at `/mnt/wa-data`. Configure
   `/etc/fstab` by stable UUID and verify `findmnt /mnt/wa-data` succeeds.
   Do not use an unmounted directory of the same name as fallback storage.
4. Create a non-root `websiteauditor` system user, and place a verified clone
   of the repository at `/mnt/wa-data/WEBSITE-AUDITOR`, owned by that user.
   On the host use Python 3.11+, a new `.venv-email`, and the dependency set
   documented in the main README and `money-machine/requirements-email.txt`.
   Validate ARM64 support for *every native dependency* if using Oracle A1.
5. **On the Mac**, stop the local supervisor, run the existing verified backup
   workflow, and securely transfer the complete relevant database and state/
   artifacts (including file-backed evidence paths) to the persistent disk.
   Do not upload confidential leads or database backups to public GitHub.
   Restore and run `PRAGMA integrity_check`; compare counts and hash manifests.
6. Check `money-machine/config/transport.json` is still fail-closed, then run
   `MM_ROOT=/mnt/wa-data/WEBSITE-AUDITOR WA_DATA_MOUNT=/mnt/wa-data
   .venv-email/bin/python deploy/cloud/preflight.py` from the repository root.
   Fix any error **without creating an empty replacement database**.
7. As root on the VM, copy `deploy/cloud/website-auditor.service` to
   `/etc/systemd/system/website-auditor.service`, then run
   `systemctl daemon-reload`, `systemctl enable --now website-auditor`.
   Verify `systemctl status website-auditor` and
   `journalctl -u website-auditor --since today`.
8. Compare `./mm supervisor health`, the database item counts and audit
   snapshots against the original Mac. Perform bounded public-site checks.
   Test a controlled service restart and VM reboot, verify persistent state,
   queue leases, non-duplicate jobs, and no external emails. Observe at least
   one complete cycle and restore test before treating it as production ready.
9. Schedule and test encrypted, *off-host*, access-controlled backups. Monitor
   uptime, disk, network, cost alerts, worker heartbeats and dead-letter growth.
   Restart is not a substitute for backups or alerts.

## Cutover and rollback

Keep the original Mac state untouched as an offline recovery copy. On failure,
stop the cloud supervisor, reconcile any cloud-only work and create a fresh
backup before considering a restore. **Never** switch an old Mac database back
on while the cloud worker is still writing. Preserve human approval/consent
gates throughout the cutover.

## What this branch does *not* prove

This repository change alone does **not** prove a live Oracle/Google connection,
24/7 uptime, cloud production acceptance, successful browser audits, customer
replies, or any income. Host sign-up, credentials, provider billing consent,
data migration and runtime validation must be completed separately.

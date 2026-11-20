# P2/P3 release evidence and remaining gates — 21 Nov 2026

Repository: `yabigdd-9/WEBSITE-AUDITOR`. Reviewed production branch: `master` at `b5bbeffdefaadbaa8c12cdeff1e41dd6e10ebeca`. Target: Supabase project `srymerkhraklwuttzexi`, Sydney.

This is a dated evidence snapshot, **not** commercial production approval or an automatically maintained status page. Recheck current GitHub Actions and Supabase before taking any subsequent action.

## Verified on the actual hosted environment

| Gate | Evidence | Decision |
| --- | --- | --- |
| Restricted PostgreSQL runtime | [Two-runner verification 44771789006](https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/44771789006) passed preflight and both independent pause-event writes; no request reservations added | PASS |
| One-time checkpoint import | [Import 44774181724](https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/44774181724) succeeded with source worker `44746146509`; the SQL store records `checkpoint_import` and `storage_authority=postgres` | PASS |
| First Postgres-backed worker | [Run 44777372523](https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/44777372523) succeeded. TLS, worker step and both encrypted artifact uploads passed | PASS |
| Observed database continuation | Read-only Supabase inspection after the run: 5 prospects, 43 events, 7 succeeded jobs and 0 reservations | PASS |
| Artifact presence | `pipeline-state` and `pipeline-postgres-backup` present in 44777372523; expire 20 Dec 2026 | PASS for upload **only** |
| Public-role isolation | Private schema RLS/role inspection completed; Supabase security adviser had no findings | PASS for inspected configuration |

An earlier manual attempt, [44775992580](https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/44775992580), failed in both attempts because `BOOTSTRAP=true` was supplied with `WA_PIPELINE_STORAGE=postgres`. This is an intentional fail-closed guard, not evidence that the DSN or `moneymachine_runner` login is missing. Never bootstrap Postgres over the imported state; leave the recovery-run input blank.

## Gates **not yet** satisfied

1. **Independent, production-derived recovery validation.** The encrypted paired export exists, but neither its authenticated decryption nor an end-to-end restore of that exact artifact into an empty, isolated migrated PostgreSQL database has been independently attested. Do not restore into live `moneymachine`, reimport the older checkpoint or reset reservations. Test source/run identity, recovered state, operational jobs and budgets, checksum/tamper rejection, denied wrong key, and replay protection.
2. **Durable off-site recovery copy.** GitHub Actions artifacts expire after 30 days. Set an approved encrypted off-site backup mechanism and separately preserve any ciphertext files; free-tier managed database backups alone are not sufficient.
3. **Next scheduled worker.** Verify the Tuesday **24 Nov 2026 04:50 UTC** (17:50 NZDT) `schedule` event and the real `draft-pipeline` job on Postgres, both uploaded artifacts, schedule health and any alerts. Do not treat a `workflow_dispatch` or push as scheduled evidence.
4. **Hosted owner dashboard.** `hosted_portal` code and container tests are present, but there is no verified remote production deployment. Select a commercially permitted host, configure secrets only in its manager, enable trusted-proxy HTTPS, and test session/CSRF/Origin limits, private records, restart persistence, exact-version review, mobile behavior and logout. Do not publish login credentials or private customer content.
5. **Repository protections and release acceptance.** `master` was observed unprotected with a disabled branch ruleset. Activate appropriate required CI/reviews, record the exact release commit and incident closure, and verify outreach consent/legal and spending gates **before** any commercial release.

## Restore regression development

The test change accompanying this note ports the independent-database restore scenario from [PR #120](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/120) onto current `master`, replacing a same-database truncate-and-restore fixture. It verifies that a failed request reservation survives an export/restore into a *second disposable PostgreSQL server*, denies another request at the exhausted daily limit, rejects tampering and leaves the source unchanged. This is synthetic CI coverage; **it does not substitute for the production-derived encrypted artifact recovery gate above.**

## Operational safeguards

Keep `MM_PAID_ALLOWED=0`, `MM_ALLOW_EXTERNAL_FREE_MODELS=0` and `MM_EXTERNAL_SEND_ALLOWED=0` until separately authorized and verified. Do not run `BOOTSTRAP=true` with PostgreSQL, do not import another checkpoint into occupied state, and do not silently fall back to the checkpoint backend. Maintain a single storage authority and check the paired recovery path before declaring a release.

Current status: **P2 worker continuation proven; P2 disaster recovery and scheduled continuity outstanding; P3 commercial dashboard NO-GO.**

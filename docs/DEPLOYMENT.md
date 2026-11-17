# Deployment status

No new service has been provisioned or deployed. Existing Actions workflows are
preserved. See [cloud pipeline runbook](cloud-prospect-pipeline.md) and
[scheduled audit runbook](GITHUB_CLOUD_SCHEDULED_AUDITS.md) for existing configuration.
GitHub schedules run independently of the Mac, but do not provide an always-on
supervisor or a permanent database.

The optional SQLite queue requires a trusted persistent filesystem; an Actions
runner's ephemeral disk does not qualify. For local synthetic or approved trusted
host operation, create a private directory outside the repository and run:

```sh
python -m scripts.cloud_prospect_pipeline --database /tmp/private-owner/pipeline.sqlite3 --bootstrap
python -m scripts.cloud_prospect_pipeline --database /tmp/private-owner/pipeline.sqlite3
```

The directory must already exist and be private. `/tmp` is an example for tests;
it is not durable production storage. These commands execute approved allowlist
audits; use synthetic tests when no live requests are intended. First run needs
bootstrap, subsequent bootstrap attempts fail. SQLite mode needs no report key;
encrypted outcome imports still require WA_PIPELINE_STATE_KEY. Checkpoint mode
continues using `--state`, its secret, and existing workflow restoration.

Before hosted activation: select and verify a free-tier destination, account and
quotas; review access controls/backups; obtain owner activation approval; deploy
one exact reviewed commit; record run IDs and state changes. A remote dashboard
also requires reviewed HTTPS/session/auth configuration. No service has been
chosen based on assumed availability or pricing.

## Offline discovery intake

Import a privately held, permitted export (curated, NZBN or OSM) using the existing
MoneyMachine adapters:

```sh
python -m scripts.cloud_discovery --database /tmp/private-owner/pipeline.sqlite3 --input /tmp/private-owner/export.json --source curated --source-url https://source.example.com/export --terms-reviewed
```

Use `--bootstrap` only for a new queue. This command makes no network requests
and prints counts only. `--terms-reviewed` is an explicit operator attestation,
not a legal finding by the tool. Check source rights/terms before export use;
retain required source attribution/licensing (including OSM ODbL requirements).
The importer does not bypass restricted directories or fetch NZBN/API records.
Discovered records remain unverified/pending policy review. To audit one, review
business identity, terms and eligibility independently and use the existing
tracked manifest plus clients.txt approval path. A pending discovery is never
automatically placed on either list. No new source acquisition schedule exists.

## Owner pipeline dashboard (local, opt-in)

Use the existing portal password setup on a trusted host, then supply the
existing private pipeline DB explicitly:

```sh
wa dashboard --output-root /private/owner/audit-history --set-password
wa dashboard --output-root /private/owner/audit-history --pipeline-db /private/owner/pipeline.sqlite3
```

The server binds 127.0.0.1 as before. Visit `/pipeline` after login. New pages
provide overview, searched/paginated prospects, provenance/evidence/proposal
details, pending discovery and system health. An authenticated owner can reject
the current exact proposal version with a reason. No action is triggered by a
page view. Reports are not decrypted in the browser. The integration adapters
are included in the wheel so this optional mode works outside a source checkout.
Cloud worker configuration/manifest files still belong to the reviewed repo.

This is not a remotely deployed mobile dashboard. Responsive markup is present,
but remote HTTPS, secure-cookie deployment settings, external identity and
real-device browser acceptance still require a reviewed deployment. Do not
change the loopback bind or trusted hosts to expose it without that work.

## Operational persistence and controls

Schema v3 stores state in a private pair: pipeline.sqlite3 and
pipeline.operations.sqlite3. Mount and back up both on the trusted persistent
filesystem. The second file preserves job history and quota reservations across
queue rollback/crashes; missing history blocks processing. The backup API creates
a corresponding pair automatically. No ephemeral Actions disk or temporary test
directory constitutes a durable host.

`--max-audits` accepts 1-3, `--daily-limit` accepts 0-6, and `--paused` records a
control event without processing pipeline stages or outcome imports. The SQLite
CLI always wires the durable reservation check before robots/audit requests.
Request reservations use actual UTC time even when a batch crosses midnight.
Checkpoint-only Actions behavior and existing schedules remain intact.

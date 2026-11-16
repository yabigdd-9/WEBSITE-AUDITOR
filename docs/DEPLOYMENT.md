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

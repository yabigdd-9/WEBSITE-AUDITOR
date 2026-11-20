# Deployment status

The owner-approved `moneymachine` Supabase project has been provisioned on
the Free plan; application workloads and the remote dashboard are not deployed.
Existing Actions workflows are preserved. See [cloud pipeline runbook](cloud-prospect-pipeline.md) and
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

## Optional report custody deployment boundary

The report archive feature is tested local software. Enable the optional portal
archive flag only on an owner-controlled device with an existing private archive
directory; see ENCRYPTED_REPORT_VAULT.md. No cloud archive or remote dashboard
deployment has been activated or verified. Persistent hosted storage/project
mapping, authorization controls and recovery verification remain release gates.

## Supabase free-tier proposal — 2026-11-16

Historical proposal: subsequently approved and created; see the verified
provisioning record below. Application integration remains pending.
The owner selected `yabigdd-9's Org` (`luvtvzzhzutxizpfdsgb`) for the proposal.
The organization API reports `plan=free`, `tier=tier_free`. The project-cost
quote for that organization returned `amount=0`, `recurrence=monthly`.

| Setting | Proposed value |
| --- | --- |
| Project | `moneymachine` |
| Organization | `yabigdd-9's Org` |
| Region | Sydney, `ap-southeast-2` |
| Plan / quoted project cost | Free / $0 per month |
| Existing project changes | None; do not repurpose or resume another project |
| Paid add-ons / upgrades | Disabled; require separate explicit owner authorization |
| Proposal-stage approval | Organization selection and proposal preparation; later creation approved below |

Account inventory shows one `ACTIVE_HEALTHY` project (Catalyx Labs) and two
`INACTIVE` projects. Official documentation allows two free projects across
organizations where the account is an Owner/Administrator; paused projects do
not count. Thus a slot appears available, but this is not a successful creation
or reservation. If creation is denied, stop and report the reason; do not delete,
pause, resume, transfer or upgrade an existing project to make room.

### Cost and reliability limits

Current official documentation lists 500 MB database capacity per free project,
1 GB Storage and 5 GB egress allowances, with usage quotas shared at organization
level except where specified per project. Existing organization consumption was
not measured, so these are included limits, not remaining capacity. The existing
application limits (100 prospects, 5 MB state, three audits/run, six/day, 50 MB
ciphertext archive) remain in place; a Postgres adapter must preserve their
transactional and durable quota semantics. Quota exhaustion must block work,
never trigger a paid upgrade.

Free projects can pause after low activity over seven days; this does not promise
continuous availability. Do not add artificial keep-alive activity. Provider
managed daily backups are not a Free-plan guarantee: encrypted off-site exports
and restore testing are required before production collection. Database backups
do not include Storage object bytes; ciphertext needs a separate backup.

### Proposed access model and staged activation

1. After explicit project-creation approval, create only this free project and
   verify its returned reference, organization, Sydney region and healthy state.
   No existing project or production workflow is changed by that approval.
2. Prepare and test a Postgres adapter/migrations against the existing pipeline
   contract. The current SQLite store cannot be pointed at a Supabase URL.
   Preserve immutable evidence/history, exact-version approvals, deduplication,
   durable quota reservations and atomic state changes rather than adding a
   disconnected second pipeline.
3. Use a private application schema and least-privilege server-side roles.
   Revoke public/anon access. Enable RLS with explicit owner/worker policies;
   authenticated status alone never grants all prospect data. Do not expose
   private records through Data API defaults, public functions or views.
4. If separately activated, use a private ciphertext-only Storage bucket with
   the existing 50 MB application cap and envelope/checksum validation. Preserve
   the existing vault cryptography and trusted-device decryption. Never store
   the owner's private encryption key in Supabase, CI or the dashboard.
5. Keep privileged credentials server-side in approved secret storage. No
   service secret goes into browser bundles, source, chat or public logs. Owner
   authentication and authorization must be reviewed before remote dashboard
   exposure; project creation alone does not deploy it.
6. Before cloud activation, test denied anonymous/non-owner access, missing
   credentials, duplicate runs, quota/crash recovery, exact-version approvals,
   paired data/ciphertext export and restore, and two independent bounded runs
   using the same durable store. Record exact commits/run IDs and sanitized
   persistence evidence. Live sends, payments and client changes remain disabled.

Official sources checked via the connected documentation search:
- https://supabase.com/docs/guides/platform/billing-on-supabase
- https://supabase.com/docs/guides/platform/free-project-pausing
- https://supabase.com/docs/guides/platform/backups
- https://supabase.com/docs/guides/api/securing-your-api
- https://supabase.com/docs/guides/storage/serving/downloads

The skill-requested changelog URL returned HTTP 403 from this environment.
Current billing/storage/security documentation was available through the plugin;
recheck relevant breaking changes before implementing the adapter. No Supabase
schema, Storage object, credential, deployment or billing setting was modified.

## Owner-approved Supabase provisioning — verified 2026-11-16

The owner approved the exact $0/month creation proposal with “Do it”. The
cost was rechecked immediately before creation and remained `amount=0`,
`recurrence=monthly`. Existing project inventory contained no `moneymachine`,
avoiding duplicate provisioning. Creation returned the following verified target:

| Setting | Verified value |
| --- | --- |
| Name | `moneymachine` |
| Project reference | `srymerkhraklwuttzexi` |
| Organization | `yabigdd-9's Org` / `luvtvzzhzutxizpfdsgb` |
| Region | Sydney / `ap-southeast-2` |
| State | `ACTIVE_HEALTHY` (separate post-create lookup) |
| Organization plan | `free` / `tier_free` (post-create lookup) |
| Database | PostgreSQL 17.11 (read-only query) |
| Public application tables / Storage buckets | 0 / 0 |
| Supabase security advisor | `lints: []` on the empty project |

[Project dashboard](https://supabase.com/dashboard/project/srymerkhraklwuttzexi).
The reference is an identifier, not a credential. No API secret, password or owner
private key was requested, printed or committed. No existing project was changed,
and no paid plan, add-on, schema, bucket or production workflow was activated.
An empty-project advisor result is not a security review of future application
schemas or a deployed dashboard.

Next implementation work: prepare/test the Postgres adapter and migrations with
the existing pipeline contracts, establish least-privilege server credentials
through secure configuration, then complete the documented access/backup/recovery
and independent-run checks before authorized production activation. Existing
SQLite code is not yet connected to this database. Project creation does not
complete cloud persistence, remote dashboard deployment or durable report custody.

## Postgres adapter and selected project connection

The approved private schema is deployed to `srymerkhraklwuttzexi` (migration
history version `20261116105816`, name `private_pipeline_store`). Its exact SQL
was recovered into the original CLI-generated migration file after workspace
replacement; do not reapply it to this project. All 12 tables force RLS. Public,
anonymous, generic authenticated and generic service roles lack schema access.
The worker group has append-only history privileges and cannot delete quotas.

Install the optional pinned driver with `pip install -e '.[postgres,portal]'`.
The existing CLI supports `python -m scripts.cloud_prospect_pipeline --postgres
--paused`; the existing loopback dashboard supports `wa dashboard --output-root
/private/history --pipeline-postgres`. Preserve its trusted-device password
setup. The Postgres flag changes persistence, not audit/approval business rules.
It never migrates automatically or opens the dashboard to remote traffic.

A later read-only inspection confirmed the dedicated `moneymachine_runner`
LOGIN role exists, has no superuser/database/role creation/BYPASSRLS privileges,
uses NOINHERIT and belongs to `moneymachine_worker`. Its password and actual
runtime connectivity have not been verified here. No credential is available
in this workspace, and repository secret access remains Forbidden. Do not
recreate or rotate this role merely to repeat setup. Do not use `postgres`,
`service_role`, or an application API key as the runtime identity. The adapter
explicitly switches into the restricted worker group.

Store its direct or session-pooler connection string as the private server
variable / GitHub Actions secret `WA_POSTGRES_DSN`. Use the project's Connect
panel for the session endpoint; do not guess the pooler hostname. Requirements:
- Database `postgres`, port `5432`; transaction-pooler port `6543` is rejected.
- Direct host `db.srymerkhraklwuttzexi.supabase.co`, user `moneymachine_runner`;
  session pooler host ending `.pooler.supabase.com`, user
  `moneymachine_runner.srymerkhraklwuttzexi`.
- `sslmode=verify-full`, `sslrootcert=system`; host/IP overrides are rejected.
- Pass the secret through secure server configuration, never command arguments,
  source, client bundles, chat, screenshots, public logs or public artifacts.

The cloud database is initialized with an empty prospect collection and one
explicit synthetic storage-verification event; use **no `--bootstrap`** against
this project. A second management connection verified the committed state.
No real audits or sends were performed. Existing checkpoint schedules remain
unchanged; no workflow has been switched to Postgres or dispatched.

A manual-only `postgres-persistence-verification.yml` is provided for an
owner-authorized future master release. Its two independent runners persist and
read pause events, verify unchanged request reservations, and perform no audits
or sends. It requires `WA_POSTGRES_DSN`. Do not claim the worker integration is
production-verified until that workflow completes on the reviewed commit.

## Trusted-device runtime credential setup

From a reviewed checkout containing `scripts.configure_postgres`, use an
owner-controlled interactive terminal and GitHub CLI authenticated to github.com
with permission to manage this repository's Actions secrets:

```sh
python -m pip install -e '.[postgres]'
gh auth login --hostname github.com
python -m scripts.configure_postgres --install-github-secret
```

Enter the dedicated runner connection string **only at the hidden prompt**.
Use the selected project's direct or session endpoint and verified TLS settings
above. Do not paste the password or connection string into chat, a command
argument, shell history, .env file, screenshot or repository. The private report
encryption key is unrelated and must never be entered into this command.

The helper first verifies GitHub authentication, then validates the selected
project/TLS/runner identity and reads initialized state plus operational history.
Only after those checks does it create/replace `WA_POSTGRES_DSN` in the fixed
`github.com/yabigdd-9/WEBSITE-AUDITOR` repository. The value travels over standard
input to `gh secret set`, which encrypts repository secrets before upload; the
helper never writes or prints the value. It refuses non-interactive execution
and getpass's echoing fallback. Errors and invalid command arguments are redacted.
It stores no plaintext credential file and does not create/rotate database roles.

Omit `--install-github-secret` for read-only connection verification without any
GitHub write. Neither mode bootstraps state, consumes request reservations,
starts a workflow, merges code, audits websites, sends messages or activates
production. Installing a secret is not evidence that an Actions runner has used
it successfully. Run the reviewed manual persistence workflow only after the
release is authorized. Provider/permission/credential failures remain blocking;
do not send the credential in chat to troubleshoot them.

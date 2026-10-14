# Run the CatalyxLabs web staging app locally

The customer/admin app lives in `catalyx_web` and uses its own database. Local staging defaults to SQLite. The application does not read `auditor_toolkit` history. Its manual local worker can run the fixed one-page audit adapter only when explicitly enabled; the customer service itself never runs a scan.

## Install and start

From the repository root, install the selected web dependencies from the lock,
then start the server on loopback:

```sh
uv sync --frozen --no-dev --extra web --extra portal
if [ -f .env.local ]; then
  set -a
  . ./.env.local
  set +a
fi
uv run --frozen uvicorn catalyx_web.app:app --host 127.0.0.1 --port 4174
```

Keep `.env.local` owner-only and untracked. External mail is disabled by
default. Sending account verification or password-recovery messages requires
both `CATALYX_MAIL_MODE=smtp` and `CATALYX_EXTERNAL_SEND_ALLOWED=true`; only
configure these after approval and when a real message is intended.

`uv.lock` pins the project resolution. `requirements-catalyx-web.lock` is the
hash-pinned dependency export for the selected web runtime and the scope of the
2026-09-28 dependency audit. Optional `smtp`, `ai`, browser, and development
dependencies are not installed in that deployment profile.

Root `requirements.txt` installs the project entry points and includes this
locked web profile. The CI full-regression job also selects the `web` extra so
the Catalyx backend tests have their application dependencies.

The default local database is `state/catalyx-app.sqlite3`. Set `CATALYX_DB_PATH` to use another location. SQLite creates a matching `*.totp-key` sidecar with mode `0600` to encrypt administrator authenticator seeds; keep it available with the database, and do not commit or expose it. PostgreSQL requires `CATALYX_TOTP_ENCRYPTION_KEY` to be supplied from the process environment. That variable must contain base64url-encoded 32-byte key material. The production secret manager and lost-key recovery procedure are not selected or implemented.

### Administrator TOTP key rotation

The local `catalyx-totp-key-rotate` command can validate and rotate encrypted
administrator seeds. It is read-only unless `--apply` is supplied. It requires
`CATALYX_TOTP_ROTATION_OLD_KEY` and `CATALYX_TOTP_ROTATION_NEW_KEY`, each
base64url-encoded 32-byte values provided through a protected environment or
secret manager. Never pass key values as command-line arguments or print them.

For an approved maintenance rehearsal, first stop app instances that can modify
administrator MFA records and take a verified database backup. Run the command
without `--apply`; confirm the counts and successful validation. Then run it
with `--apply`, set `CATALYX_TOTP_ENCRYPTION_KEY` to the new key on every app
instance before allowing sign-in, and verify named administrator MFA access.
Retain the old key only as long as required to recover the verified backup, then
retire it under the approved key policy. The transaction rolls back if any
stored seed matches neither key or changes during rotation. A lost old key or
unavailable backup cannot be recovered by this command.

This procedure has only been exercised with synthetic local SQLite data. It
does not establish provider secret-manager behavior, live PostgreSQL locking,
backup recovery, coordinated deployment across multiple app instances, or
owner approval of key retention and recovery.

Local registration writes verification links to the mode-0600 `state/catalyx-local-mailbox.json` file; view it explicitly with `catalyx-web --show-local-mailbox`. The one-time links are kept out of server logs. This mailbox is local staging only. Hosted startup requires a PostgreSQL URL, a fixed HTTPS public origin, and an explicit TOTP encryption key; it does not run database migrations automatically. Mail defaults to disabled. To opt into transactional SMTP, set `CATALYX_MAIL_MODE=smtp` and `CATALYX_EXTERNAL_SEND_ALLOWED=true`, then provide the authenticated SMTP settings below. A PostgreSQL adapter is available through `CATALYX_DATABASE_URL`, and `catalyx-db-migrate` explicitly initializes/upgrades its schema. No live PostgreSQL integration has been completed; do not use this adapter with customer data yet.

Public registration is disabled by default on hosted preview and production.
Local development defaults to open registration for legacy synthetic tests.
For the local invitation beta, set `CATALYX_REGISTRATION_MODE=invitation_only`;
an owner/admin can issue a 72-hour, one-use link from `/admin/invitations`.
The invite address is stored only as a keyed fingerprint, the token is stored
as a hash, and no email or audit job is created. The invitee's account remains
unverified until an owner/admin records an identity review on the customer
page. The invitation flow is explicitly rejected in hosted mode; it does not
approve production identity verification, customer data, or launch.

SQLite schema upgrades first create a mode-0600 `.pre-v9-*.bak` file and verify
its integrity, schema version, and schema fingerprint before applying the
migration. If backup creation or verification fails, startup stops before
schema changes. Existing PostgreSQL databases require a verified `pg_dump`
artifact when running `catalyx-db-migrate`; live PostgreSQL restore and
concurrency behavior remain unverified. Example for a reviewed maintenance
window:

```sh
pg_dump --format=custom --file state/catalyx-pre-migration.dump "$CATALYX_DATABASE_URL"
shasum -a 256 state/catalyx-pre-migration.dump
catalyx-db-migrate --database "$CATALYX_DATABASE_URL" \
  --postgres-backup state/catalyx-pre-migration.dump \
  --postgres-backup-sha256 <reviewed-sha256>
```

Store and protect the dump outside the application checkout according to the
approved retention policy. The command checks the dump signature and the
operator-supplied digest; it does not perform a restore rehearsal.

The built-in SMTP sender supports implicit TLS on port 465 or STARTTLS on port 587. Set `CATALYX_MAIL_MODE=smtp`, `CATALYX_EXTERNAL_SEND_ALLOWED=true`, `CATALYX_SMTP_HOST`, `CATALYX_SMTP_PORT`, `CATALYX_SMTP_USERNAME`, `CATALYX_SMTP_PASSWORD`, and `CATALYX_SMTP_FROM` only after an owner-approved email provider is available. No SMTP credentials are stored in the repository. Hosted startup validates the presence and shape of these settings but does not prove provider connectivity or deliverability. Failed verification delivery can be retried from `/resend-verification`; password-reset requests can be repeated.

The server-rendered screens and the versioned customer/admin JSON API use the same tenant and role checks. The API endpoints and request examples are in [api-v1.md](api-v1.md). API mutations require the signed-in session's `X-CSRF-Token`; audit submissions also require an idempotency key.

## Bootstrap an administrator

Stop the server, then run:

```sh
catalyx-web --create-admin admin@example.invalid
```

The command prompts for a password and prints a one-time TOTP setup secret and provisioning URI. Add it to a named authenticator account. Do not paste that secret into chat or commit it. Restart the server, sign in with the email, password, and six-digit authenticator code.

## Boundaries

- Requests can be submitted and reviewed. Approving one only changes it to `queued`.
- Customers can cancel requests through `running`; cancellation clears the claim token, and the local transport checks for cancellation between response chunks. This remains cooperative cancellation with bounded socket timeouts, not an isolated-worker kill switch.
- The customer-facing service never runs a scan. A manual, local-only worker harness can process one reviewed request after an operator explicitly sets `CATALYX_ENABLE_LOCAL_WORKER=1` and runs `catalyx-web --run-worker-once`.
- Failed requests stay visible on the reviewer jobs page with their attempt count and last outcome. A reviewer can retry a failure below the local two-attempt cap, with a recorded reason; exhausted failures remain failed. This is a local recovery view, not a provider dead-letter service, and the cap is not a production limit approval.
- That harness uses a fixed one-page profile, checks `robots.txt`, pins public DNS answers to the TCP connection, limits redirects/requests/bytes/time, and stores a sanitized report for human review. It is still not an OS-isolated production worker; do not expose it to the public service.
- Only reports that pass manual administrator review are visible to the owning customer. Release and withhold decisions require a reason and are recorded.
- Billing, model calls, site edits, and deployment actions are disabled. Transactional email is disabled by default and requires explicit SMTP mode plus `CATALYX_EXTERNAL_SEND_ALLOWED=true`; no provider or credentials are selected in this repository.
- The local app is a staging implementation, not a production-ready service. Provider, data region, email, retention, backup/restore, support ownership, and legal copy remain owner decisions.

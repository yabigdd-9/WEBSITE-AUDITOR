# ADR 0001: CatalyxLabs.com application boundary

Date: 2026-09-27
Status: proposed for staging

## Context

The recorded source revision is `0348b3f9c06b62d29d51414ffdee7594cb6ecbf5` from `/Users/dd/WEBSITE-AUDITOR`. The original checkout has unrelated uncommitted and untracked work; implementation is isolated in a detached worktree. The repository has no customer web frontend. Its FastAPI portal is a single local operator interface backed by local SQLite history and one password file.

The audit engine is Python. The first implementation is a FastAPI application in a separate `catalyx_web` package, using local password/session primitives and a separate application database. SQLite remains the local default. A PostgreSQL adapter and explicit schema-migration command were added for future persistent hosting; this adapter has not yet been tested against a live PostgreSQL service and is not evidence of production readiness.

## Decision for the staging slice

- Build the public, customer, and administrator interfaces as server-rendered pages served by FastAPI.
- Use a separate application database for local staging and future hosting, with workspace IDs and server-side ownership checks. SQLite is local staging only. PostgreSQL can be selected with `CATALYX_DATABASE_URL`; apply schema changes explicitly with `catalyx-db-migrate`. Do not reuse `History` as a customer database.
- Keep the public scan worker disabled. The code includes a fixed single-page adapter and a manually invoked local staging worker that uses a connection-pinned transport, checks `robots.txt`, and writes sanitized reports for quality review. It is not OS-isolated and must not be exposed to customers as an automatic worker.
- Keep billing, model calls, email delivery, site edits, deployments, and outbound customer messages disabled.
- Add a narrow adapter boundary for a future fixed audit profile; never expose CLI arguments or internal artifact paths.

## Owner decisions still required before production

On 2026-09-27, the owner directed us to reuse the existing setup. The recorded setup is Vercel for app hosting and Cloudflare for `.com` DNS. A fresh dashboard view shows the Vercel workspace is Hobby, whose terms are incompatible with operating this commercial service. A local Cloudflare Workers Free probe served a simple FastAPI route and D1 query. Direct use of the app's Python password-hash and `cryptography` AES-GCM paths failed, while a separate WebCrypto prototype passed a local round trip and matched a CPython PBKDF2 reference. Authentication integration, D1 persistence, Cloudflare CPU fit, and restricted scan egress remain unproven. Keep both providers out of production pending an approved $0 architecture, or an owner-approved budget change. Cloudflare DNS remains unchanged; this decision does not authorize domain cutover, customer data migration, or deployment. Details are recorded in `../catalyx-platform/hosting-cost-and-terms-assessment.md`.

Email verification delivery, support and incident owner, retention/deletion policy, approved legal text, primary audience beyond the provisional NZ small-business focus, and public onboarding mode also remain owner decisions. No paid resource has been created or provisioned.

## Consequences

The local staging app can demonstrate accounts, site authorization records, request review, sanitized report review/release, and admin actions. It is not production-ready until a PostgreSQL integration run, provider configuration, verified-email delivery, independent security review, worker/container egress isolation, accessibility review, backup and restore, and owner-approved operational policies are complete.

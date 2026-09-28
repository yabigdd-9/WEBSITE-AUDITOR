# CatalyxLabs.com rebuild — phase 0 inventory

Observed 2026-09-27. Source and saved-state inventory, plus a fresh read-only public DNS lookup. Provider-console assignments and authenticated settings were not verified.

## Source preservation

- Canonical source: `/Users/dd/WEBSITE-AUDITOR`.
- Original checkout: branch `upgrade/v32-canonical-execution`, HEAD `0348b3f9c06b62d29d51414ffdee7594cb6ecbf5`, five commits ahead of its upstream at inspection.
- Original checkout had 28 modified tracked files, including audit engine and MoneyMachine modules, `state/network_guard.json`, and many untracked review artifacts. No changes were made there.
- Implementation worktree: detached at the same SHA, clean before implementation, at `work/catalyx-auditor-rebuild`.
- Root `AGENTS.md` was not present. The only discovered `AGENTS.md` is under `shorts-project/` and does not apply to `auditor_toolkit` or this new app. Shell usage follows `/Users/dd/.codex/RTK.md` (`rtk` prefix).

## Existing product and engine

- Python package `auditor_toolkit`; project requires Python 3.11+.
- Existing web dependency group is optional (`fastapi`, `uvicorn`, `argon2-cffi`, `python-multipart`). There is no frontend framework or customer app in the recorded revision.
- `auditor_toolkit/portal.py` provides a loopback-host-restricted single-operator portal. It reads a local `portal-auth.json`, keeps sessions in process memory, and displays `History` runs and artifacts. It has no customer accounts, workspace tenancy, or admin roles.
- `auditor_toolkit/storage.py` stores local reports and remediation events in `history.sqlite3`. It is not tenant-owned application storage.
- `run_audit` invokes a fixed set of first-party checks; its options also permit deeper crawl, TLS, rendered/browser, screenshot, and external local tools. The initial `static` defaults still perform a network fetch and secondary robots/sitemap requests. Browser flow checks, artifact generation, subprocesses, and optional AI/tool paths require separate review before a public worker can use them.
- Confirmed check families in the source include fetch, page metadata/content, schema, response headers, robots/sitemap, security headers, mixed content, conversion signals, optional links/crawl/DNS/TLS, optional browser and axe, and optional Lighthouse/lychee. Reports carry per-check status, evidence, limitations, findings, severity, and score metadata; skipped/error states exist.
- URL checks reject many non-global address results and each redirect is revalidated. However, URL preflight DNS validation and the later HTTP connection resolve separately, leaving a DNS rebinding/time-of-check gap. Browser and auxiliary fetch paths need their own boundary. The rebuild now includes a connection-pinned transport and a fixed single-page adapter with robots checks and bounded requests, covered by focused tests. The manual worker is still not OS-isolated, so customer-facing scanning stays disabled.
- Existing action policy defaults to dry-run and explicitly blocks production DNS/deploy/outreach categories. The customer app will not expose those internal action routes.

## Infrastructure facts carried from the previously verified plan

The attached plan records a 2026-09-27 Vercel-console observation: `catalyx-labs-grow-os` owned both `.com` and both `.shop` hostnames; `.shop` apex redirected to `www`; the Auditor project had only its Vercel hostname and `/api/health` returned 404. Those authenticated Vercel assignments have not been refreshed. A read-only DNS lookup on 2026-09-27 confirmed `.com` is delegated to Cloudflare (`candy.ns.cloudflare.com`, `fonzie.ns.cloudflare.com`); apex and `www` resolve to Cloudflare proxy IPv4/IPv6 ranges. `.shop` is delegated to GoDaddy (`ns05.domaincontrol.com`, `ns06.domaincontrol.com`); apex resolves to `216.198.79.1`, and `www` resolves through `53a89e45c57e5a61.vercel-dns-017.com` to Vercel IPv4 addresses. No DNS, Vercel assignment, or production deployment was changed. Keep `.shop` outside scope.

## Public-page refresh

On 2026-09-27, read-only browser requests confirmed that `https://catalyxlabs.com/` still serves the Grow OS public homepage. `https://catalyxlabs.shop/` redirects to `https://www.catalyxlabs.shop/`, which serves the Grow OS public homepage with product/shop navigation. The DNS lookup above refreshed public delegation and resolution, but does not prove account ownership, complete DNS record contents, TLS settings, or Vercel project assignments. No production changes were made.

## Confirmed facts, assumptions, and decisions

- Confirmed: `.com` is intended to host the complete Auditor app; `.shop` remains the garden store.
- Working assumption from the plan: start with NZ small-business site owners; agency support is undecided.
- Proposed for local staging: FastAPI server-rendered pages and an independent SQLite application database, with explicit tenant IDs and a disabled scan worker.
- Owner decision required before production: host/database/auth/email provider and region/cost, retention and legal wording, support owner, and onboarding policy. No paid service, billing, model call, or external email has been enabled.

## First release boundary

This implementation starts the public/customer/admin product and durable lifecycle. An audit submission records the site's authorization receipt and enters admin review. Approving a request only places it in a waiting state; it cannot invoke `run_audit` while the worker security gate is closed. The sample report is synthetic and explicitly labeled.

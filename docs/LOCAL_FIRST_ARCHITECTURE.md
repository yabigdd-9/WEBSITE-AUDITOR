# Local-First Architecture — WEBSITE-AUDITOR / Money Machine

## Purpose

The public/client website and the Money Machine are separate systems.

### Client website

The website is a lightweight customer-facing surface for:

- showing the work and services offered;
- letting people share the business/site;
- collecting subscription or contact interest;
- presenting approved examples, demos, and information.

It is **not** the Money Machine runtime. It must not own the worker queue, local prospect database, model routing, supervisor, approval state, or autonomous outreach.

### Local Money Machine

The Money Machine runs locally on the operator Mac and remains the source of truth for:

- NZ business discovery and deduplication;
- identity confidence;
- website auditing and evidence collection;
- opportunity scoring;
- remediation/demo generation;
- deterministic quotes;
- prospect packets;
- observability, retries, leases, DLQ, backups, and reports;
- Claude through the local FCC harness first, with Hermes verified-free role routing as fallback.

Human review remains required. Paid fallback remains disabled. If FCC/Claude would require payment or is unavailable, the machine falls back to Hermes verified-free roles; if those are unavailable it defers. External outreach remains fail-closed unless separately and explicitly enabled later.

## Always-on macOS runtime

The supported primary runtime is the existing user-scoped launchd service:

- label: `ai.website-auditor.supervisor`
- process: `.venv-email/bin/python -m supervisor.cli _run-foreground`
- working directory: `money-machine/`
- `RunAtLoad=true`
- `KeepAlive=true`
- external send disabled in the launchd environment
- PID/flock protection prevents duplicate supervisors;
- a separate user LaunchAgent keeps the loopback FCC server alive on `127.0.0.1:8082`;
- recurring discovery runs every 6 hours by default from `money-machine/config/discovery_schedule.yaml`, using only the local inbox and loopback SearXNG.

Install and verify from the repository root:

```sh
sh scripts/local-machine.sh install
```

Check it at any time:

```sh
sh scripts/local-machine.sh status
```

Restart:

```sh
sh scripts/local-machine.sh restart
```

Logs:

```sh
sh scripts/local-machine.sh logs
```

Uninstall:

```sh
sh scripts/local-machine.sh uninstall
```

The install command runs `./mm doctor`, loads the FCC LaunchAgent when available, installs/loads the Money Machine LaunchAgent, checks both statuses, runs `./mm health`, and prints the active model routes. Money Machine launch failure is fatal; FCC launch failure leaves Hermes verified-free fallback available.

## Runtime boundary

```text
CLIENT WEBSITE
  services / portfolio / subscribe / contact
             |
             | approved, narrow integration only
             v
LOCAL MONEY MACHINE
  discover -> identity -> audit -> evidence -> opportunity
           -> remediation -> demo -> quote -> prospect packet
           -> HUMAN REVIEW
```

The website must never become a hidden remote control for high-risk local actions. Any future website-to-machine integration should use a narrow authenticated API or reviewed import queue, not direct database access.

## Release gates

Before calling the local machine production-ready:

1. CI/security/toolkit checks green.
2. `./mm doctor` and `./mm health` green on the Mac.
3. Real Chromium audit path verified.
4. FCC/Claude loopback route verified with an explicitly zero-cost model.
5. Hermes verified-free fallback verified.
6. Optional local SearXNG discovery verified when enabled.
7. 24+ hour unattended soak with no duplicate workers, healthy lease recovery, visible DLQ, $0 paid spend, and zero external sends.

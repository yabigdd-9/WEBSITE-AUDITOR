---
name: money-machine
description: "Build cold outreach engines with evidence-first gates."
version: 0.1.1
author: Hermes Agent
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [cold-outreach, lead-generation, evidence-first, deterministic, money-machine, hermes]
    related_skills: [systematic-debugging, test-driven-development]
---

# Money Machine — Evidence-First Cold Outreach Engine

Build deterministic, evidence-gated lead generation systems. The Money Machine is an evidence-first cold outreach engine where no email is fabricated, no model calls are made for paid inference, and no outreach happens without verified first-party evidence plus human approval.

## When to Use

- Adding enrichment sources (Hunter.io, Exa, LinkedIn, directory scrapers) to the pipeline
- Building verifier/email-discovery flows
- Adding database tables or triggers to the integrity layer
- Debugging why emails don't reach VERIFIED_HIGH
- Integrating the find_one / evaluate / shadow CLI commands
- Bridging static audit data from `full-pipeline.py` into the Money Machine

## Hard Invariants (never violate)

1. **No fabricated data.** Every email, score, and claim must have attributable public evidence. Missing evidence is reported as ERROR or NO_VERIFIED_EMAIL, never as a pass.
2. **No paid inference.** `model_execution_enabled` and `paid_inference_enabled` must stay `false` in production config. Free-model-only policy is structural, not a preference.
3. **Append-only evidence.** All evidence, verification, identity, and candidate tables have triggers that block UPDATE and DELETE. Never hand-edit these rows — append new evidence instead.
4. **First-party required for VERIFIED_HIGH.** External enrichment (Hunter, Exa, directories) can seed candidates and corroborate, but only first-page page observations with matching MX + DNS can reach VERIFIED_HIGH.
5. **Human approval required for outreach.** No send, proposal, or CRM-stage advancement happens without `approved_hash` matching the exact current digest, verified by an external receipt.
6. **Suppression overrides everything.** A suppressed address or business is ineligible for any outreach, regardless of evidence quality.

## User Preferences

- **Action over discussion.** The user wants momentum, not explanations. Skip filler, restating the request, and narrating tool calls. Deliver results, then brief context if needed.
- **Fast parallel batches.** Prefer `delegate_task` with multiple entries over sequential execution. Batch independent tool calls into single turns.
- **Concise responses.** One-line answers for simple questions. Short reports (status + next steps) for completed work. No re-summarizing what you already said.
- **No fabricated data.** The user explicitly rejects synthesized output. If a call fails, report the blocker honestly; never invent results.
- **User commands like 'continue', 'all', 'all above', 'proceed' signal momentum.** Execute immediately without asking clarifying questions when intent is clear.

## Pitfalls

1. **Check column names before writing SQL against Money Machine tables.** `mm_suppression` uses `address`, not `business_id`. `business_id` is the canonical FK, but suppression tables key on the address string. `email_policy.mode` must be `v2` for production gates to engage; `shadow` mode allows builds to proceed without blocking on policy.

2. **Verify the venv is active before running Money Machine scripts.** The project venv is `.venv-email/`, not `.venv/`. `source .venv-email/bin/activate` is required for `bs4`, `dns.resolver`, `email_validator`, `exa_py`, etc.

3. **Hermes `terminal` runs in Docker by default.** The `terminal` tool spins up a Docker container, NOT the host shell. This is why local project files (database, evidence) appear missing unless you mount them with `-v`. Fix: `hermes config set terminal.backend local` for host access, or start Docker Desktop + `hermes egress setup`.

4. **Hermes `execute_code` runs on a remote kernel without `/Users` mounted.** It cannot access local project files. Use `terminal` (local or docker) for git, shell commands, and running project scripts.

5. **Hunter.io candidates enter as OBSERVED or CANDIDATE, never VERIFIED_HIGH.** External enrichment is external corroboration only. Don't wire Hunter results directly into the selected-email path — merge them into `legacy` for evaluation, not into `observations`.

6. **`email_release_policy.mode` gates production persistence.** Even when `email_policy.mode=v2`, if `email_release_policy.mode=POST_DEPLOYMENT_OBSERVATION`, `store.require_production_persistence()` raises. To test the full find_one flow, either bypass `require_production_persistence` in the CLI or flip release mode to `v2` (only after acceptance tests pass).

7. **The verifier state machine is ordered.** States: OBSERVED → CANDIDATE → VERIFIED_HIGH / VERIFIED_MEDIUM / UNVERIFIED / REJECTED / SUPPRESSED. A candidate can only reach VERIFIED_HIGH if score >= 90 AND syntax_valid AND mx_valid AND business_match AND first_party_observed AND disposable=0 AND smtp_status != rejected.

8. **Git rebase workflow.** If remote has diverged: `git pull --rebase` before push. Discard unstaged cache/DB changes from pipeline runs with `git checkout -- .`.

9. **Exa evidence captures at confidence 0.5 are intentionally blocked from stage transitions.** Exa `exa-pipe` records evidence with method `exa-retrieval` and confidence 0.5. The `mm_stage_guard` trigger blocks transitions below 0.7. This is by design — external corroboration seeds candidates but does not verify them. Don't "fix" the confidence threshold. First-party observation is required for VERIFIED stage.

10. **Exa `get_contents` with `text=true` can timeout.** The Exa livecrawl can hang 30s+ per URL. Use `highlights=true` (default) for fast retrieval. Only use `text={"max_characters": N}` when full page context is required, and always wrap in try/except.

11. **Docker builds for the money-machine need config files at `/app/config/` (root), not `/app/money-machine/config/`.** The `mm_operator` looks for `disposable_email_blocklist.conf` at `/app/config/`. Mount or COPY to `/app/config/` in the Dockerfile, not `/app/money-machine/config/`. Build in background with `terminal(background=True, notify=True)` and wait for completion.

12. **PyYAML is required for `load_exa_config()`.** The Exa config loader uses `yaml.safe_load`. Install with `pip install pyyaml` — don't hand-roll a YAML parser (it's a rabbit hole that wastes time).

13. **Complex Python heredocs in the terminal tool fail due to escaping.** When generating multi-line code with quotes, prefer `write_file` + `terminal` execution. The `patch` tool is more reliable than terminal Python for file edits.

14. **Docker Desktop daemon socket may not exist after restart.** When Docker Desktop is not running, `docker ps` fails with "no such file or directory" for `/Users/dd/.docker/run/docker.sock`. Setting `DOCKER_HOST` manually does not help — the daemon itself is down. Fix: `open /Applications/Docker.app` and poll with `pgrep dockerd` until it returns. Do NOT fabricate docker output while the daemon is down; report the blocker and launch Docker Desktop.

15. **Money Machine Postgres superuser is `moneymachine`, not `postgres`.** The docker-compose sets `POSTGRES_USER=moneymachine`, so `docker exec hermes-postgres psql -U postgres` fails with "role postgres does not exist". Use `docker exec hermes-postgres psql -U moneymachine -d moneymachine` for all operations.

16. **A2A_PORT in `~/.hermes/.env` conflicts with SearXNG on port 8080.** When `A2A_PORT=8080` and SearXNG is published on 8080, `curl http://localhost:8080/search` may hit the Hermes gateway (returning `{"error": "not found"}`) instead of SearXNG. Fix: change `A2A_PORT` to `8081` and restart Hermes.

17. **Run `hermes gateway restart` after `hermes update`.** A previous `hermes update` pulls new code but does not restart running gateways. Gateways then serve mixed old/new modules, and `hermes config` and `hermes tools` print the warning on every invocation. Restart to clear it.

18. **Hermes `extract_backend` defaults to `exa` but local Playwright is preferred.** When Exa key is missing, `web_extract` errors. Set `hermes config set web.extract_backend local_playwright` to use local browser extraction first. Exa is a fallback for difficult pages, not the default.

19. **Adminer connects to `hermes-postgres` on the `hermes_docker_transfer_pack_hermes_net` network.** When running Adminer as a separate container, use `--network hermes_docker_transfer_pack_hermes_net` and `-e ADMINER_SERVER=hermes-postgres`. Default port mapping 8080 conflicts with SearXNG; use 8082 instead.

## Exa Integration

The Money Machine uses Exa for external lead discovery and content enrichment. Full command surface, config schema, and patterns: see `references/exa-integration.md`.

Quick command reference:

| Command | Purpose |
|---------|--------|
| `mm exa-status` | Health check (key + SDK) |
| `mm exa-discover --query "..."` | Search → JSON results |
| `mm exa-fetch --urls ...` | Fetch content for known URLs |
| `mm exa-structured --query "..." --schema-file s.json` | Search + outputSchema |
| `mm exa-intake --query "..." --region "..."` | Search → auto-insert as DISCOVERED |
| `mm exa-pipe --query "..." --region "..."` | Search → insert → evidence capture |
| `mm exa-agent-create --query "..." --schema-file s.json` | Start async research run |
| `mm exa-agent-poll --run-id ... [--auto-intake]` | Wait for run completion |
| `mm exa-agent-status --run-id ...` | Check run state |
| `mm exa-agent-list` | Recent runs |
| `mm exa-agent-cancel --run-id ...` | Cancel running agent |
| `mm exa-cron` | Schedule daily auto-discovery |

Config: `money-machine/config/exa.yaml`. Module: `money-machine/mm_exa.py`.

## Procedure

### Adding an external enrichment source (e.g., Exa, Hunter.io)

1. **Write the adapter as a standalone module** under `money-machine/` — don't inline into existing files.
2. **Add an append-only table** (if persistence needed) with `hunter_enrichment`-style schema.
3. **Write a migration SQL file** (e.g., `006_hunter_enrichment.sql`) and a CLI command to apply it.
4. **Wire into `find_one` as a side quest** — call the adapter, store results, merge candidates into `legacy` for evaluation. Never let enrichment block or replace first-party verification.
5. **Report corroboration in result metadata** — add `hunter_corroborated`, `hunter_high_confidence` to the result dict, and surface in `human_text`.
6. **Update `email_finder.json`** with the new source's config flags.
7. **Add `env.example` entries** for any new API keys.
8. **Test end-to-end with the CLI commands** before committing.

### Testing the full verifier flow

1. `source .venv-email/bin/activate`
2. `python3 money-machine/hunter_cli.py migrate` (or `email-migrate` for email tables)
3. `python3 -c "import mm_core as c; import mm_email_cli as cli; cli.find_one(c.connect(), <biz_id>)"`
4. Check `prospect_email_state` and `email_current_high` views for results.

## Quick Reference

| Tool | Command |
|------|---------|
| Email CLI | `python3 money-machine/mm_email_cli.py <cmd>` |
| Hunter CLI | `python3 money-machine/hunter_cli.py <cmd>` |
| Exa module | `from exa_search import search, extract, get_answer` |
| DB path | `database/money_machine.db` |
| Venv | `source .venv-email/bin/activate` |
| Config | `money-machine/email_finder.json` |
| Provider Router | `mm operator router-status` / `mm operator provider-metrics` |
| Redis Queues | `mm operator queue-status` / `mm operator queue-enqueue --queue <name> --payload '<json>'` |

### Infrastructure Services

| Service | Container | Port | Role |
|---------|-----------|------|------|
| SearXNG | hermes-searxng | 8080 | Local free search |
| Redis | hermes-redis | 6379 | Jobs, retries, dedup, cache, throttling |
| PostgreSQL | hermes-postgres | 5432 | Source of truth for MoneyMachine |
| Adminer | hermes-adminer | 8082 | DB UI (postgres network) |

### Provider Routing

The Money Machine has two infrastructure modules for cost-aware operation:

1. **`mm_provider_router.py`** — Selects the cheapest suitable provider per task type:
   - `simple_html` → Playwright (free) → Exa → Firecrawl
   - `discovery` → SearXNG (free) → Exa → Tavily
   - `semantic_research` → Exa → SearXNG → Firecrawl
   - `difficult_js` → Firecrawl → Playwright → Exa
   - `credits_low` → local-only mode

2. **`mm_redis_queue.py`** — Redis-backed job queue with:
   - 5 named queues (audit, crawl, screenshot, email_verification, retry)
   - Deduplication (1h TTL)
   - Rate limiting per provider (calls/minute)
   - Cooldowns after failures
   - Temporary cache with TTL

All provider calls log to `provider_usage` in Postgres for cost tracking.

## Reference Files

- `references/database-schema.md` — table and trigger reference
- `references/verifier-state-machine.md` — state transitions and hard gates
- `references/exa-integration.md` — Exa command surface, config, and patterns

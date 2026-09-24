# Local integration layer

The integration layer is a free/local handoff point for WEBSITE-AUDITOR. It does not send outreach or make paid model calls. Jobs live in `outputs/integration-events.db`; local webhooks and an MCP JSON-RPC stdio server can publish them.

Commands:

```bash
./integration-status                         # one status command/dashboard
python -m integrations status
python -m integrations serve                 # 127.0.0.1:8091
python -m integrations serve --port 8092
python -m integrations mcp
```

The local MCP server is configured in Hermes user config, `.cline/mcp.json`, and `opencode.json` for this repository. The Cline and OpenCode entries are project-scoped. Hermes marks the server untrusted so its event-publishing tool uses approval. `integration_status` is the read-only health tool; `publish_event` queues a shared job.

Endpoints are `GET /health`, `POST /webhooks/event` (or `/events`), `POST /webhooks/github`, `GET /events/claim`, and `PATCH /events/{id}` to acknowledge completion or report an error. A payload may include `kind`; remaining fields become the job payload. `X-WA-Source` identifies the producer; `Idempotency-Key` makes generic event delivery deduplicated. GitHub deliveries require `GITHUB_WEBHOOK_SECRET`, validate `X-Hub-Signature-256`, and deduplicate `X-GitHub-Delivery`. Failed jobs retry with exponential backoff (up to five claims) before `dead_letter`; stale claims are recovered, or dead-lettered when attempts are exhausted.

`serve` starts the local HTTP receiver and a supervised-in-process worker thread. The worker accepts only GitHub `push` and pull-request actions `opened`, `synchronize`, `reopened`, or `ready_for_review` for the configured `GITHUB_AUDIT_SITE_URL`; delete/force pushes and unsupported pull-request actions are skipped. It runs a bounded static audit (`ai=false`, no browser/external tools; 3 pages max) and writes a report under `outputs/github-audits`. The target must resolve only to public IP addresses. Set the target explicitly before processing GitHub events; failed handler work is retried and dead-lettered. This does not initiate an agent conversation or perform outreach, publishing, deployment, or paid inference. The service is loopback-only; `--host` rejects non-loopback binds.

For OmniRoute, `python -m integrations omniroute-mcp` (launcher: `integration-omniroute-mcp`) is a fail-closed stdio proxy. Hermes, Cline, and OpenCode configs expose only six health/combo/quota/usage/model-catalog reads and reject completion, provider-search, and mutation tools regardless of caller metadata. The upstream environment scopes are defense in depth, not the authorization boundary. Verified live: six tools listed, health read succeeds, completion call is rejected before forwarding. OmniRoute emitted SQLite initialization warnings, but the read-only health call responded.

The host LaunchAgent `~/Library/LaunchAgents/ai.website-auditor.integrations.plist` starts `integrations/service_runner.py` at login, keeps it alive, and reads `GITHUB_WEBHOOK_SECRET` and `WA_WEBHOOK_TOKEN` from macOS Keychain into process environment only. It binds only to `127.0.0.1:8091`. It survived an explicit `launchctl kickstart -k` test with local and public Quick Tunnel health checks passing. It is tied to the current isolated worktree path, so move/recreate it if this worktree is removed. The receiver is persistent; the current Quick Tunnel is not.

Set `WA_WEBHOOK_TOKEN` to require `X-WA-Token` or `Authorization: Bearer ...` for generic webhooks and queue-consumer endpoints. It is mandatory for those routes. GitHub's HMAC signature is required independently through `GITHUB_WEBHOOK_SECRET`; both secrets are injected as environment variables at process start and are not stored in the repo. The public health response is redacted; the local health response includes component details.

Hermes, Cline, OpenCode, OmniRoute and Ollama commands are detected separately from their API health. FCC health requests its documented admin status route at the existing `127.0.0.1:8082`; OmniRoute health checks its local `/api/health` route at `127.0.0.1:20128`; Ollama health requests `/api/tags`. Obsidian uses `OBSIDIAN_VAULT_PATH` when set; otherwise it discovers the app-registered vault containing `40 Projects/WEBSITE-AUDITOR`. Notion's local API adapter requires `NOTION_API_KEY` or `NOTION_API_TOKEN`. Secrets are read only from environment variables and never printed. Unsupported or unconfigured clients are reported as `blocked` with the next action.

## Current host findings (2026-09-24)

- GitHub projects reviewed: [OmniRoute](https://github.com/diegosouzapw/OmniRoute) and [Free Claude Code](https://github.com/Alishahryar1/free-claude-code). OmniRoute documents local port 20128 and MCP stdio via `omniroute --mcp`; FCC documents the local 8082 proxy and agent launchers including `fcc-cline`, `fcc-hermes`, and `fcc-opencode`.
- Host discovery found OmniRoute running and local binaries for OmniRoute, FCC, Hermes, Cline, OpenCode, and Ollama.
- FCC uses the user-selected NVIDIA NIM default `nvidia_nim/nvidia/nemotron-3-super-120b-a12b` (verified earlier in the setup session); do not send a completion as part of integration checks. NVIDIA NIM is a hosted provider and can incur cost if invoked.
- Existing Hermes primary model remains on its prior Nous endpoint; this task changed FCC's default only.
- The project MCP server is registered in Hermes user config and project-scoped Cline/OpenCode configs. OmniRoute's read-only proxy has also been registered in those configs; reload each client to establish the new connection. A2A remains disabled. The only allowed OmniRoute tools are `omniroute_get_health`, `omniroute_list_combos`, `omniroute_get_combo_metrics`, `omniroute_check_quota`, `omniroute_cost_report`, and `omniroute_list_models_catalog`.
- Obsidian resolved `/Users/dd/Downloads/CatalyxLabs_Master_Brain_V7` from the installed app registry; its `40 Projects/WEBSITE-AUDITOR` folder exists. Set `OBSIDIAN_VAULT_PATH` explicitly only if the vault moves.
- Notion's Codex connector updated the existing workspace page `Catalyx AI Agent System`. The Hermes OAuth consent screen is open and requires user approval. Until then, local Notion MCP/API remains blocked; Codex OAuth is not exported as a local token.
- FCC's model prefix, local base URL and fallback settings follow [Free Claude Code's upstream guidance](https://github.com/Alishahryar1/free-claude-code).
- The loopback receiver and worker run under the per-user LaunchAgent. GitHub hook `684596041` is active for `push` and `pull_request`; HMAC-signed delivery and idempotency were verified. Existing GitKraken hook `684430534` was preserved. The active callback is still a Quick Tunnel and is not durable. Cloudflare login/origin certificate and account-owned domain are missing, so a named tunnel cannot yet be created.
- GitHub payloads are reduced to repository/branch/change metadata before durable storage; comment bodies, commit text, and user identities are omitted. The worker routes only allowlisted push and pull-request actions to a deterministic static audit, but requires both `GITHUB_REPOSITORY_ALLOWLIST` and an explicit public `GITHUB_AUDIT_SITE_URL`; without them the job safely retries and dead-letters. No AI, outreach, publishing, deployment, or agent conversation occurs.
- Notion local API supports `NOTION_API_KEY` or `NOTION_API_TOKEN`; neither is configured. The separate Codex Notion connector remains available and was used to update the existing status page. Local OAuth consent remains pending.

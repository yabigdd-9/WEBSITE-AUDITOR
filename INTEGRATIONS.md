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

`serve` starts the local HTTP receiver and a supervised-in-process worker thread. The worker only auto-acknowledges explicitly inert `integration.noop` jobs; other event types are retried and then dead-lettered until an agent/client registers a safe handler. This is not an AI agent or the existing auditor pipeline worker and cannot make model calls or perform outreach. It is intentionally loopback-only; `--host` rejects non-loopback binds.

Set `WA_WEBHOOK_TOKEN` to require `X-WA-Token` or `Authorization: Bearer ...` for generic webhooks and queue-consumer endpoints. It is mandatory for those routes. GitHub's HMAC signature is required independently through `GITHUB_WEBHOOK_SECRET`; both secrets are injected as environment variables at process start and are not stored in the repo. The public health response is redacted; the local health response includes component details.

Hermes, Cline, OpenCode, OmniRoute and Ollama commands are detected separately from their API health. FCC health requests its documented admin status route at the existing `127.0.0.1:8082`; OmniRoute health checks its local `/api/health` route at `127.0.0.1:20128`; Ollama health requests `/api/tags`. Obsidian uses `OBSIDIAN_VAULT_PATH` when set; otherwise it discovers the app-registered vault containing `40 Projects/WEBSITE-AUDITOR`. Notion's local API adapter requires `NOTION_API_KEY`. Secrets are read only from environment variables and never printed. Unsupported or unconfigured clients are reported as `blocked` with the next action.

## Current host findings (2026-09-24)

- GitHub projects reviewed: [OmniRoute](https://github.com/diegosouzapw/OmniRoute) and [Free Claude Code](https://github.com/Alishahryar1/free-claude-code). OmniRoute documents local port 20128 and MCP stdio via `omniroute --mcp`; FCC documents the local 8082 proxy and agent launchers including `fcc-cline`, `fcc-hermes`, and `fcc-opencode`.
- Host discovery found OmniRoute running and local binaries for OmniRoute, FCC, Hermes, Cline, OpenCode, and Ollama.
- FCC uses the user-selected NVIDIA NIM default `nvidia_nim/nvidia/nemotron-3-super-120b-a12b` (verified earlier in the setup session); do not send a completion as part of integration checks. NVIDIA NIM is a hosted provider and can incur cost if invoked.
- Existing Hermes primary model remains on its prior Nous endpoint; this task changed FCC's default only.
- The project MCP server is registered in Hermes user config and in project-scoped Cline/OpenCode configs. Hermes connection test passed with two tools discovered. OpenCode reports the server connected. Use the included `integration-mcp` launcher so stdio output and working directory stay correct. OmniRoute's own MCP server currently reports offline, with scope enforcement off; A2A reports disabled. Do not connect it until read-only scopes are enforceable and tested. Its model-completion capability is intentionally outside this local/no-paid integration route.
- Obsidian resolved `/Users/dd/Downloads/CatalyxLabs_Master_Brain_V7` from the installed app registry; its `40 Projects/WEBSITE-AUDITOR` folder exists. Set `OBSIDIAN_VAULT_PATH` explicitly only if the vault moves.
- Notion's Codex app connector is connected to the workspace, but its OAuth credential is not exposed to this local process. No `NOTION_API_KEY` was found in checked environment/config sources. Keep local Notion API access blocked until a separate local credential is supplied. Alternatively, clients supporting OAuth can use Notion's hosted MCP at `https://mcp.notion.com/mcp` without exporting the token; workspace approval may be required. See [Notion MCP setup](https://www.notion.com/help/notion-mcp) and the [official MCP server](https://github.com/makenotion/notion-mcp-server).
- FCC's model prefix, local base URL and fallback settings follow [Free Claude Code's upstream guidance](https://github.com/Alishahryar1/free-claude-code).
- Receiver and worker health were verified at `127.0.0.1:8091/health`. The worker uses a separate durable integration inbox, runs locally, and will not perform model calls, outreach, or unregistered event work. GitHub can only deliver remotely after a user-approved public HTTPS callback/tunnel is provided; the existing repository webhook was not changed.
- **Temporary GitHub callback (2026-09-24):** Cloudflare quick tunnel at `https://richards-italia-hourly-font.trycloudflare.com/webhooks/github`; GitHub hook ID `684596041`, active for `push` and `pull_request`. Existing GitKraken hook ID `684430534` was preserved. Signed delivery was verified end-to-end. The quick-tunnel URL is ephemeral and only works while both the receiver and `cloudflared` sessions remain running; stop either session to take this endpoint offline. A restart creates a different URL and requires updating this GitHub hook. Cloudflare documents quick tunnels as testing/development only with no uptime guarantee; use a named tunnel/domain for a durable production callback.
- GitHub payloads are reduced to repository/branch/change metadata before durable storage; comment bodies, commit text, and user identities are omitted. Valid GitHub events are acknowledged as received only. Events do not trigger model calls or repository actions.
- Notion's local API remains blocked until a local `NOTION_API_KEY` is explicitly provided; the connected Codex Notion connector remains a separate route.

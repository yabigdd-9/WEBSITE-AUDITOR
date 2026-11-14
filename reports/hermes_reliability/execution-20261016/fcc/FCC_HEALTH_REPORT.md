# FCC health verification — 16 October 2026

Status: **BLOCKED_REMEDIATION_REQUIRED** for production inference. Discovery and metadata succeeded; service responsiveness was intermittent and no inference was sent.

Evidence collected around 08:46–08:51 Pacific/Auckland (UTC+13), source baseline `09ab41ab` plus the separately documented working router repair. Secrets were read only for allowlisted presence checks and one existing Nous OAuth account GET; no secret values were printed or saved. No credentials were refreshed and no service/configuration was changed.

## Installation and ownership

- Installed distribution metadata: `free-claude-code 6.2.57`, Python requirement `>=3.14.0`.
- Entrypoint: `/Users/dd/.local/share/uv/tools/free-claude-code/bin/fcc-server`.
- Launch agent `ai.website-auditor.fcc` owns PID `99117`, parent PID `1`, started 15 October at 00:53:33 according to local process inventory.
- Exactly one listener observed on `127.0.0.1:8082`; no all-interface FCC listener was present in the scoped port inventory.
- Wrapper: `scripts/fcc-server-wrapper.sh`, enforces IPv4 loopback after loading repository environment files. Launch configuration enables `RunAtLoad`, `KeepAlive`, and a ten-second throttle. These are configuration observations, not crash/reboot acceptance evidence.
- Repository `.env.fcc`: `HOST=127.0.0.1`, `PORT=8082`, `PROXY_AUTH_ENABLED=false`, local auth token empty. Successful unauthenticated model catalog GET corroborates local metadata accessibility. Upstream credentials are present for multiple providers; validity/entitlement is not implied.

## Bounded non-inference probes

Requests bypassed HTTP proxy settings, used a four-second timeout, and never called a generation endpoint.

| Endpoint | Observation | Elapsed |
| --- | --- | --- |
| IPv4 `/health` at 08:46:44 | Timeout | 4.009 s |
| IPv4 `/v1/models` | HTTP 200; 2,076 IDs | 3.501 s |
| IPv6 `[::1]:8082/health` | Connection refused | 0.001 s |
| Ollama `127.0.0.1:11434/api/tags` | Connection refused | <0.001 s |
| IPv4 `/health` immediately afterward | HTTP 200, `status=healthy` | 0.039 s |
| IPv4 `/admin/api/status`, second round | Timeout | 4.056 s |
| IPv4 `/health`, second round | HTTP 200 | 1.295 s |
| IPv4 `/v1/models`, second round | HTTP 200; exact-ID membership checked | 2.874 s |

`/health` source (`free_claude_code/api/routes.py:202`) returns a fixed healthy status. It does not verify upstream generation, account balance, or model entitlement. IPv6 refusal is consistent with the intentionally IPv4-only listener; configured clients use `127.0.0.1`, so switching them to `localhost`/IPv6 would introduce a failure.

## Current model observations

Global Hermes primary: `fcc-claude`, model `anthropic/kilo/anthropic/claude-opus-5.5`, base URL `http://127.0.0.1:8082/v1`, API mode `codex_responses`. Exact model exists in the returned catalog.

Configured Hermes fallbacks, in order:

1. FCC `claude-fable-5`: present in catalog.
2. FCC `claude-opus-5.5`: absent from catalog.
3. Nous `upstage/solar-pro4:free`: not verified through Nous inference/catalog during this pass.

The master plan's earlier `anthropic/claude-opus-5.5` is absent. The repeated `anthropic/kilo/...` primary prefix is an actual catalog entry, so it must not be normalized by guesswork. The saved FCC `.env` default is `nvidia_nim/nvidia/nemotron-3-super-120b-a12b`; this differs from explicit Hermes selection and does not establish which upstream handles a generation.

No `ollama` or `llama-server` executable was found on PATH. Neither 11434 nor 8080 had a listener in the scoped inventory. Local fallback is currently unavailable, not accepted.

## Remaining checks

Upstream generation/authentication, `codex_responses` end-to-end compatibility, official per-model entitlement, TLS upstream configuration, repeated stable responsiveness, concurrency, duplicate prevention, graceful restart, reboot recovery, and a sustained provider soak remain **NOT TESTED/BLOCKED**. Existing logs were inventoried by path/size without dumping their potentially sensitive contents. No broad diagnostic archive was exported.

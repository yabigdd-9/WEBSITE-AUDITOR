# Model Routing (Redacted)
**Generated:** 2026-09-07T19:03:40.127364+00:00

## Provider Configuration
- **Provider:** nous
- **Default model:** upstage/solar-pro4:free
- **Base URL:** https://inference-api.nousresearch.com/v1
- **Auth:** OAuth via Hermes auth (key redacted)

## Role Routing
| Role | Model | Classification |
|------|-------|----------------|
| MASTER_ORCHESTRATOR | meituan/longcat-2.0:free | FREE |
| JUDGE | tencent/hy3:free | FREE |
| RESEARCHER | upstage/solar-pro4:free | FREE |
| FAST_RESEARCHER | stepfun/step-3.7-flash:free | FREE |
| CODER | poolside/laguna-s-2.1:free | FREE |

## Fallback Order
- **Primary:** nous/upstage/solar-pro4:free
- **Fallback:** DISABLED (fallback_model commented out in config.yaml)
- **Supported fallback providers (documented but not active):** openrouter, openai-codex, nous, zai, kimi-coding, kimi-coding-cn, minimax, minimax-cn, bedrock

## Local Models
- **Ollama:** INSTALLED but BROKEN (0-byte stub at /usr/local/bin/ollama)
- No local inference active.

## Cost Status
- **All models confirmed FREE:** true
- **Paid cost allowed:** false
- **Zero-cost enforcement:** PASS
- **Any route that could incur paid usage:** NONE — all roles route to free-tier models. Fallback is disabled. No paid provider keys configured.

## Secrets Redacted
- API keys, tokens, OAuth credentials: NOT EXPOSED
- auth.json path: ~/.hermes/auth.json (contents redacted)

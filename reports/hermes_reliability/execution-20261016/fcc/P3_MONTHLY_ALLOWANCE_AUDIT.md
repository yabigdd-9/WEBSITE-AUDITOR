# Monthly allowance and billing audit — 16 October 2026

**P3 gate: BLOCKED_REMEDIATION_REQUIRED.** Incremental budget remains NZ$0. No provider generation was sent by this workstream, no credits were purchased, and no billing settings were changed. This is not a provider-wide invoice attestation.

## Current account evidence

| Route | Current evidence | Allowance / remaining / reset | Admission |
| --- | --- | --- | --- |
| FCC → Kilo Opus primary | Model catalog contains exact Hermes ID; Kilo credential present | Account allowance and current price unknown; no remaining/reset telemetry verified | Block new production inference |
| FCC default NVIDIA NIM | Saved `.fcc/.env` points at Nemotron default; credential present | Current account quota, reset and terms unknown | Block until verified |
| Nous | Existing OAuth account GET HTTP 200; no refresh | Free plan; monthly credits 0; subscription remaining 0; purchased remaining 0; usable paid credits 0 | No paid allowance available; exact free model eligibility unknown |
| Repository OpenRouter free-role fallback | Explicit `:free` routes, live catalog price checks and all-zero request price caps | No credential in checked process environment, Hermes env or auth pool; remaining/reset unknown | Not currently verified usable |
| Local Ollama / llama.cpp | No checked listener or executable on PATH | No metered inference cost, but unavailable | Defer |
| Other FCC-connected providers | Credential presence only | Billing account, concurrency, allowances and remaining quotas unknown | Not eligible by mere connectivity |

Nous account response allowed fields at approximately 08:50 Pacific/Auckland: `subscription.plan=Free`, `monthly_charge=0`, `monthly_credits=0`, `credits_remaining=0`, `rollover_credits=0`, `paid_service_access.allowed=false`, `paid_access=false`, `active_subscription_is_paid=false`, `total_usable_credits=0`; account-period end `2026-11-08T14:30:17Z` = **9 November 2026 03:30:17 NZDT**. This period-end is not evidence of any credits being granted on reset. Account identity and credentials were excluded.

## Official provider findings

- Kilo Gateway supports application/API use, but free and paid routes are distinct. Free model access does not establish that this exact Opus route is included. BYOK may show zero Kilo balance charge while charging the upstream provider. [Kilo authentication](https://kilo.ai/docs/gateway/authentication).
- Kilo describes model-dependent inference pricing, free Auto Free, and separately charged paid tiers. This cannot certify the user's currently selected exact model or account credits. [Kilo costs](https://kilo.ai/docs/getting-started/rate-limits-and-costs).
- Nous documents subscription-backed model routing and warns that OpenRouter-specific provider routing extensions may be ignored. OpenRouter zero-price request fields cannot be assumed to constrain the Nous route. [Official Nous integration documentation](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/website/docs/integrations/nous-portal.md).
- OpenRouter documents authenticated `GET /api/v1/key` with credit limits, budget/reset fields and free-model daily counters. That is an appropriate read-only telemetry source once an actual connected OpenRouter credential is available. Do not purchase credits to resolve a limit under the NZ$0 instruction. [Official OpenRouter limits](https://openrouter.ai/docs/api_reference/limits).

## Existing controls and candidate repair

Repository role routing requires a live catalog proving zero prices, `:free` model IDs and provider-side zero prompt/completion/request/image caps. It stops on authentication/billing and account daily quota errors. This is a stronger constraint than a model name alone, but source/configuration is not live account entitlement evidence.

The candidate router now treats unknown/invalid reported cost as a safety stop; records a positive observed cost in a separate private first-incident file; prevents later router plans and completions after that latch; does not allow a fallback to hide the incident. Model response identity must exactly match the requested FCC catalog ID. Synthetic positive amounts are test fixtures, not actual charges.

These repairs do not create a full monthly billing supervisor. The existing ledger records requests/status/tokens but enforces stored `cost_usd=0`; it does not track every Hermes/FCC request, upstream bills, account periods, verified balance, request reservations, concurrent allowance allocation, retries by every agent, or all tool costs. Global Hermes and direct bridge calls bypass the repaired local router. A rejected cost inside the free-role subprocess also needs a structured shared incident contract.

## Required P3 completion

1. Obtain official account telemetry and allowed per-model scope for each desired route; unknown stays blocked.
2. Bind model/account entitlement and reset evidence to shared atomic request admission; reserve capacity across workers before dispatch, and reconcile outcomes including failure/retry/uncertain billing.
3. Enforce the same guard in global Hermes, FCC/direct bridge, role subprocesses and auxiliary/tool model calls; verify provider-side spend restrictions and topups are disabled where supported.
4. Preserve actual observed nonzero/unknown amounts as incidents independently of the zero-only application ledger; never overwrite an unknown with zero.
5. Derive 70/85/95% alerts only from trustworthy finite cap/remaining values. All quota percentages in this audit remain unknown, so none were invented.
6. Prove exhaustion, concurrency, crash recovery, persistent billing stop and operator-controlled reset with offline fixtures before any eligible live canary.

No route can be declared globally protected against unapproved incremental charges yet. Maintain production inference gates while completing these controls.

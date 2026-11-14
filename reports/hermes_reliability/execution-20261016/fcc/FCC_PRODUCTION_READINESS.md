# FCC production readiness — 16 October 2026

**BLOCKED_REMEDIATION_REQUIRED.** Existing FCC metadata service is live on IPv4 loopback, but reliable upstream generation and an eligible NZ$0 allowance are not verified. No new provider activation was performed.

## Verified progress

- One launchd-owned FCC listener; loopback enforcement is present.
- Two model-catalog responses succeeded; primary Hermes exact model exists.
- Invalid configured `claude-opus-5.5` fallback was identified and documented without silently substituting it.
- Narrow MoneyMachine router repair adds explicit response-model validation, defensive schema handling, unknown-cost rejection, and a private persistent billing safety stop. Positive observed amount is retained outside the zero-only SQL ledger.
- 90 relevant tests and 12 subtests passed on the working candidate; zero new lint diagnostics; whitespace check passed.
- Nous official account GET confirms zero paid usable credits. Local inference fallback is unavailable.

## Remaining release blockers

1. Global Hermes FCC requests bypass the repository router's guards. `~/.hermes/config.yaml` selects an upstream model with unverified allowance. Existing account credentials/catalog presence do not prove free execution.
2. `money-machine/scripts/fcc-bridge.py::send_to_fcc` directly submits chat completions and has no shared financial admission. It remains unchanged and must not be activated as a production zero-cost route.
3. `_fcc_model_allowed` still accepts a `:free` suffix or operator exact-ID certification; neither reserves verified provider quota. No provider-side spend caps/auto-topup settings were verified.
4. `mm_model_invocations` (`money-machine/mm_core.py:135`) constrains `cost_usd=0`. It is an application safety invariant, not a provider invoice or comprehensive billing ledger. The new separate incident preserves abnormal cost without changing this schema, but all entrypoints must participate.
5. Free-role subprocess rejects reported costs inside its own routing layer. Its current failure JSON does not expose a structured observed cost to the parent router, so a shared cross-entrypoint incident contract remains necessary.
6. Health and admin status timed out intermittently within four seconds. A fixed `/health` response and populated catalog do not establish readiness under load.
7. Nous has Free plan with zero monthly/purchased usable paid credits; exact `upstage/solar-pro4:free` eligibility is unknown. Ollama/llama fallback lacks current listener/executable evidence.
8. No live generation, supported API compatibility canary, concurrency, deduplication, circuit-backoff acceptance, restart/reboot, or sustained soak evidence exists for this candidate.

## Safe continuation and rollback

Keep inference deferred until verified cost admission covers every path. Preserve working authentication and existing service owner. Do not change global Hermes model names from catalog guesses. Use isolated mock fault injection to extend acceptance before a bounded nonbillable canary.

The candidate billing incident is `state/model-routing-cost-stop.json` below the configured MoneyMachine runtime root. Existence (including a symlink) blocks later router planning/completion. An operator must reconcile provider billing and fix the offending route before explicitly removing/archive-clearing the incident. There is no automatic clear or automatic topup. If incident persistence fails, the current call raises a safety stop; durable protection after filesystem repair still requires operator action.

No live database migration, service restart, provider configuration edit, credential refresh, inference request, paid purchase, or external send was performed in this provider workstream. Parent-agent candidate integration and final exact-revision acceptance remain separate gates.

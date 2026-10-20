# Free model response allowance candidate

Prepared source only: not executed, regression tested, installed or promoted.

## Evidence behind the change

The preserved isolated public triage run completed with max_tokens 8192,
finish_reason stop, a visible answer and reported cost USD 0. Its receipt records
7207 completion tokens. The repository dispatcher instead hardcoded 2048.
That isolated result proves one completed draft, not integrated route acceptance.

OpenRouter documents that reasoning and visible output share max_tokens on
most providers. Reasoning can consume a small allowance and produce an empty,
length-limited answer. A larger allowance permits an answer but does not
guarantee completion or override provider/context constraints.

- [Reasoning and response allowances](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens)
- [Request parameter semantics](https://github.com/OpenRouterTeam/docs/blob/main/api_reference/parameters.mdx)
- [Provider parameter support](https://openrouter.ai/docs/guides/routing/provider-selection)

## Proposed contract

- The role dispatcher uses policy.max_output_tokens, defaulting to 8192.
- A role may specify max_output_tokens; an explicit request override wins.
- Every configured role allowance and every request override must be a genuine
  integer in 1–16384. Boolean, float, string, zero and larger values are rejected.
- The CLI accepts --max-output-tokens and validates the selection before the
  catalog request. The selected limit is sent as max_tokens and reported with
  the response and finish_reason.
- Truncated or empty role answers remain failures. No automatic allowance
  escalation or paid fallback is introduced.
- The Money Machine API accepts an omitted response allowance. FCC then retains
  its previous 64-token default; Hermes uses its configured role allowance.
  An explicit caller allowance is forwarded to either route.
- FCC length-limited content is treated as incomplete, permitting only the
  already configured free fallback. Reported nonzero or unrecognised cost raises
  PaidRouteRefused and stops further requests, rather than being swallowed as
  an ordinary unavailable FCC route.

Provider selection continues to require parameter support and zero price caps.
The catalog's top-provider response ceiling describes one provider, so it is
not used as a blanket reason to discard an entire model. Context limits and
provider support can still cause a request to fail and defer.

## Public-data exception

Money Machine previously appended --public-or-synthetic on every Hermes call.
The candidate defaults allow_data_collection to false and appends that flag
only when the caller explicitly sets a boolean true with authority for that
public prompt. Redaction remains in place; it does not prove that arbitrary
source material is non-confidential.

This preparation grants no new data-sharing permission. The existing approval
and successful model run cover only the saved exact public prompt. No private
credential is copied into the candidate, and no provider request is run.

## Required regression coverage

Use mocked transports and child processes only:

- Default, per-role and explicit request limits; invalid type/boundary rejection
  before provider requests; consistent selected-limit result metadata.
- Reasoning-only, empty and length-limited answers; no allowance escalation.
- FCC/Hermes allowance forwarding, default FCC compatibility, incomplete
  FCC fallback and hard stop on unexpected reported cost.
- Default deny, explicit boolean public exception and rejection of truthy
  non-booleans; child command must not silently enable the exception.
- Free catalog pricing, zero caps, auth/billing and daily quota stop conditions,
  role fallback and model identity checks.
- Existing router, redaction and dispatcher regression suites.

P15 also requires integrated acceptance of the intended route order. This
candidate changes response handling and explicit data collection; it does not
implement or prove a large/small local model lane, install a live credential,
or complete the whole phase. The current configured order remains FCC, Hermes
role routes, then defer; its relationship to the canonical plan requires a
separate acceptance decision.

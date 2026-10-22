# FCC failover and billing tests — 16 October 2026

Evidence scope: synthetic fixtures and local HTTP metadata; no live inference or production database mutation. Source repair is limited to `money-machine/mm_model_router.py` and `money-machine/test_pipeline.py`. Candidate transfer/final revision verification is owned by the parent execution agent.

## Executed checks

Initial baseline:

`rtk proxy .venv/bin/python -m pytest -q tests/test_fcc_bridge_transport.py money-machine/test_pipeline.py::ModelRouter money-machine/scripts/test_free_role_router.py`

Result: **33 passed in 3.48 s**.

After the narrow repair, same selection: **40 passed and 12 subtests passed in 2.66 s**.

Expanded relevant regression:

`rtk proxy .venv/bin/python -m pytest -q money-machine/test_pipeline.py tests/test_fcc_bridge_transport.py money-machine/scripts/test_free_role_router.py`

Result: **90 passed and 12 subtests passed in 12.88 s**, zero failures/skips. These results bind the pre-transfer working candidate, not a final committed/deployed revision.

Scoped Ruff was run on both changed source files. Comparison to `git show HEAD:<file>` with the same Ruff invocation found **zero introduced diagnostics**. Existing diagnostics: router 2 before / 1 after; pipeline tests 12 before / 12 after. The remaining router diagnostic is pre-existing `PaidRouteRefused` naming; existing test import/semicolon diagnostics were not broadly reformatted. `git diff --check` passed for both files.

## Defects reproduced independently before repair

| Synthetic trigger | Baseline result | Candidate result |
| --- | --- | --- |
| Missing reported `usage.cost` | Returned `cost_usd=0` | Safety stop; unknown cost incident |
| Actual response model changed | Accepted unapproved model | Rejects exact-ID mismatch; safe fallback |
| Nonzero reported FCC cost | Fell back and returned zero, obscuring incident | Records first observed amount; stops without fallback |
| Invalid JSON | Uncaught `JSONDecodeError`; no fallback | Controlled `BlockedCost`; safe fallback |
| Malformed `choices` | Uncaught `AttributeError`; no fallback | Controlled `BlockedCost`; safe fallback |

New tests also verify zero numeric-string cost, boolean/invalid/nonfinite/negative cost rejection, model absence, private incident permissions, persistent stop before later transport/planning, first-incident preservation, and fail-closed behavior on incident-write failure. No prompt or credential is stored in the billing incident.

## Coverage classification

| Requirement | Evidence/status |
| --- | --- |
| FCC primary and fallback ordering | PASS, existing mocked router tests |
| Unavailable/nonfree model; missing credential; no safe route | PASS for existing mocked validation/role-router rejection |
| OpenRouter endpoint 429 | PASS, mocked fallback retains zero caps |
| Daily quota exhausted | PASS, mocked stop rather than model loop |
| Changed catalog price; paid/unknown route | PASS, mocked pre-request rejection |
| Reported nonzero/unknown FCC cost | PASS, new synthetic incident and latch tests |
| Malformed FCC response | PASS, new JSON/schema tests |
| Loopback-only, IPv4/IPv6 URL validation, redirects/proxy boundary | PASS, transport fixture tests |
| Actual IPv6 listener | NOT AVAILABLE; connection refused, IPv4 configured |
| FCC HTTP 500/502/503, DNS failure, timeout permutations | Source handles HTTP/URL/OS timeout exceptions; full requested fault matrix NOT TESTED |
| Cancellation, parallel inference, duplicate provider requests | NOT TESTED |
| Process restart/reboot and graceful shutdown | NOT TESTED; no service disruption attempted |
| Live generation/authentication and free allowance | BLOCKED pending official entitlement and shared admission |

The cost latch prevents subsequent router requests after an observed anomaly. It cannot undo a request already sent or recall concurrent requests in flight; it is not a central quota reservation system. The direct FCC bridge, global Hermes, and free-role subprocess's own rejected-cost accounting still need a common admission/incident contract before production AI activation.

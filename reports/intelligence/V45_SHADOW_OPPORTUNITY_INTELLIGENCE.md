# V45 Shadow Opportunity Intelligence — Identity, Evidence, Planning, Source Yield

## Scope

This increment adds four deterministic, shadow-only intelligence capabilities:

1. **Identity confidence** — quantifies how much deterministic identity evidence is present.
2. **Evidence completeness** — distinguishes missing/unknown evidence from negative evidence.
3. **Next-best-evidence planning** — recommends the cheapest high-information next observation without executing it.
4. **Source/query intelligence** — measures discovery-source yield, rejection rate, engagement, and won outcomes.

The implementation is deliberately advisory. It does **not** change qualification thresholds, pipeline states, approvals, outreach, model routing, or send behavior.

## Implementation

### Core module

`money-machine/mm_opportunity_intelligence.py`

Public surfaces:

- `identity_confidence(business, evidence=None)`
- `evidence_completeness(stage, observed)`
- `next_best_evidence(identity, completeness)`
- `shadow_assessment(business, stage, observed=(), evidence=None)`
- `prospect_snapshot(d, business_id)`
- `source_query_summary(d)`

Rule version: `v45-shadow-intelligence-v1`

### Identity confidence

Signals currently include canonical public host, NZ-domain signal, business name, name/domain token alignment, region, discovery-source provenance, legal/trading name evidence, NZBN evidence, and discovery-quality evidence.

Outputs are `HIGH`, `MEDIUM`, `LOW`, or `CONFLICTED`. A conflict forces review in the planner. The score is not used as an authorization gate.

### Evidence completeness

The completeness layer defines a minimum evidence set per pipeline stage. Identity stages require business name + canonical host + source provenance; audit requires deterministic audit evidence; qualification requires audit + substantive commercial evidence; contact stages require contact evidence.

**Missing evidence is explicitly UNKNOWN, not negative evidence.** The legacy qualification score produced from name + region does not, by itself, satisfy the new shadow `commercial_evidence` requirement.

### Next-best-evidence planner

The planner recommends one action only; it never executes the action.

Current actions:

- `VERIFY_PUBLIC_WEBSITE`
- `VERIFY_BUSINESS_IDENTITY`
- `RECOVER_SOURCE_PROVENANCE`
- `RUN_STATIC_AUDIT`
- `INSPECT_FIRST_PARTY_COMMERCIAL_PAGES`
- `DISCOVER_OWN_SITE_CONTACT_EVIDENCE`
- `HUMAN_IDENTITY_REVIEW`
- `NO_ADDITIONAL_EVIDENCE_REQUIRED`

Every result contains estimated information gain, bounded cost class, trigger, and `execute: false`.

### Source/query intelligence

`source_query_summary()` is read-only and groups non-dummy prospects by `businesses.source`.

It reports candidate count, pipeline state distribution, qualified-or-later count, negative terminal count, qualification yield, negative terminal rate, engaged-business count, won-business count, engagement rate, won rate, and SearXNG query fingerprint when present.

It does not claim profitability unless verified outcome evidence exists.

Each source also receives a conservative diagnostic:
- `INSUFFICIENT_SAMPLE` below 10 non-dummy prospects,
- `PROMISING` only when downstream engagement or won evidence exists,
- `POOR_YIELD` only with a sufficiently large cohort plus high negative-terminal rate and low qualification yield,
- `MIXED` otherwise.

All diagnostics carry `automatic_action: false`; no source or query is auto-promoted, suppressed, or removed.

## Worker integration

### Identity worker

The worker still returns the existing target `AUDIT_PENDING`. Its evidence now also includes `shadow_intelligence` containing identity confidence, completeness, and next-best-evidence guidance.

### Qualification worker

The worker's existing qualification thresholds and verdict logic are unchanged. Its evidence now includes a shadow assessment. If substantive commercial evidence is absent, the shadow layer records that absence and recommends gathering first-party commercial evidence. It does not change `REJECTED` to `QUALIFIED` or `NEEDS_REVIEW`.

## Read-only CLI

New commands:

```bash
./mm intelligence-prospect BUSINESS_ID
./mm intelligence-sources
./mm intelligence-review --limit 50
./mm intelligence-summary --limit 500
```

Both use read-only database connections.

`intelligence-prospect` returns current pipeline state, the originating/assessment stage used for evidence-completeness analysis, observed evidence classes, identity confidence, evidence completeness, next-best-evidence action, counterfactual explanation, current audit/qualification derived evidence, paid calls = 0, and external sends = 0.

For terminal/review states such as `REJECTED`, the report separates:
- `state`: the actual current pipeline state,
- `assessment_stage`: the stage whose evidence requirements are being evaluated.

The assessment stage prefers the recorded transition's `from_state` when available, with deterministic evidence-based fallback otherwise. This prevents a terminal label from erasing the context of why evidence was incomplete.

`intelligence-sources` returns source/query yield analytics.

`intelligence-review --limit N` returns a read-only shadow review queue containing only current negative/review states where identity uncertainty, missing required evidence, or a near-threshold current score justifies human inspection. The queue never changes pipeline state, never resurrects a prospect, and sets `automatic_action: false` on every item.

`intelligence-summary --limit N` gives one bounded read-only overview of identity-status distribution, evidence-completeness distribution, next-best-evidence actions, review-queue size, source count, and source-diagnostic distribution. It fetches one extra row to report truncation accurately rather than treating an exact-limit result as truncated.

## Counterfactual explanations

`intelligence-prospect` now also returns an explanatory counterfactual block.

It can state, for example:
- that commercial evidence is still missing,
- that technical qualification remains unknown without a valid audit,
- the current v45 commercial threshold (30) and technical threshold (40),
- the numerical gap to a threshold when a valid score exists,
- that contradictory identity evidence must be resolved by human review.

These are explanations of the current rules only. Every counterfactual is marked:
- `explanatory_only: true`,
- `automatic_action: false`,
- `guarantees_decision_change: false`.

The system therefore explains what would have to be different without claiming that a new observation will necessarily be found or that a state transition should occur.

## Safety invariants

- No paid model calls.
- No external sends.
- No automatic threshold changes.
- No automatic candidate resurrection.
- No approval changes.
- No pipeline-state mutation from the intelligence module.
- No source/query auto-promotion.
- No hidden conversion of missing evidence into negative evidence.
- Review-queue generation is read-only and cannot resurrect or transition a prospect.
- Human review is required for conflicting identity evidence.

## Tests

`money-machine/test_opportunity_intelligence.py` covers aligned identity, weak/missing identity staying unknown rather than conflicting, conflicting discovery identity, evidence-completeness semantics, next-best-evidence selection, explanatory counterfactuals, human-review routing on conflict, prospect snapshots, source/query yield and outcome aggregation, minimum-sample source diagnostics, operation without optional tables, and worker shadow integration without target-state or verdict changes.

## Promotion policy

This layer remains **shadow-only** until its recommendations are replayed against historical/human-corrected outcomes and demonstrate measurable improvement.

Future promotion work should require hard-case replay, human-correction agreement, source/query calibration, no safety regression, and explicit human approval before any production decision rule consumes these signals.

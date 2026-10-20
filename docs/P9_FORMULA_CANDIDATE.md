# P9 formula candidate

This isolated module implements the exact product/division formula in `MASTER_PLAN.yaml`. It does not replace the existing six-component score or eleven-dimension commercial scenario. Those are different algorithms and their historical results must remain versioned separately.

## Input contract

`mm_opportunity_formula.score_opportunity(document)` accepts an exact JSON-compatible snapshot: `schema_version: 1`, `algorithm_version: master-plan-p9-product-v1`, an explicit timezone-bearing `as_of`, and six named `factors`.

The five numerator values (`need`, `business_value`, `contactability`, `fixability`, `confidence`) use an explicit normalised 0–1 scale. `delivery_effort` is 0.01–10,000 hours. This scale is a proposed contract for review; the plan does not specify units. The output is a priority index per hour, not a 0–100 score. There is no automatic threshold or mapping to the legacy shortlist threshold of 65.

Each known factor contains `value`, `basis` (`observed_fact` or `human_assumption`), `source_ref`, and the referenced source's `source_sha256`. An unknown contains `value: null`, `basis: unknown`, and null provenance. Unknowns hold calculation; they are never filled with defaults, converted into negative evidence, or interpreted as zero. Zero is a valid known numerator value. Zero effort is rejected.

Assessment factors must be labelled as assumptions unless independently supportable as observations. Contactability is an assessment of evidenced reachability, never consent or contact permission. Business value is a normalised assessment, never an inferred revenue or willingness-to-pay claim.

The module validates provenance syntax and saves its binding; it does **not** attest source files, freshness, identity, contact permission, customer access or input accuracy. `provenance_verified` remains false. Callers must perform those checks separately. Mixed formulas and unsupported units must not be silently converted.

## Replay and isolation

The canonical input snapshot hashes all fields, including version and as-of. Decimal arithmetic and a fixed 12-place output make the whole calculation receipt reproducible without consulting the current clock, SQLite, model services or external resources. `replay(snapshot, receipt)` compares the complete receipt and detects input/receipt changes.

The module imports no CRM or network client and performs no writes. It grants no approvals or shortlist decision. No live database score, pipeline transition or routing policy has been changed. This candidate still needs focused regression evidence, input-contract review and promotion; it is not connected to the frozen runtime.

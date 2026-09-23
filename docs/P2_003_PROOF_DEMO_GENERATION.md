# P2-003 — Before/After Proof + Automated Demo Generation v39

## Core Rule
**The demo generator proposes. The verifier proves. The human decides.**

## Proof Contract

Proof generation:
- NEVER invents a defect
- NEVER declares its own fix successful
- NEVER modifies the live site
- NEVER submits forms or sends external requests

Verification:
- ALWAYS performed by independent module (not generator)
- ALWAYS replays original detector
- ALWAYS checks for regressions
- ALWAYS matches capture environment

## Architecture

```
auditor_toolkit/proof/
├── schema.py          — ProofPackage, BeforeState, AfterState, VerificationResult
├── environment.py     — ProofEnvironment with browser/viewport/font probing
├── capture.py         — Before/after state capture via Playwright
├── regions.py         — Issue region extraction with fallback chain
├── prototype.py       — Sandboxed prototype generation (local only)
├── patches.py         — Deterministic patch rules (form labels, overflow, etc.)
├── screenshot.py      — Screenshot capture with viewport/device pins
├── visual_diff.py     — Pixel-level diff with change region detection
├── dom_diff.py        — DOM tree diff with accessibility awareness
├── verifier.py        — Independent verification (never self-verify)
├── regression.py      — Regression detection across viewports/components
├── scoring.py         — Proof reliability scoring (not aesthetics)
├── pipeline.py        — Full pipeline: capture → prototype → verify → report
├── report.py          — Markdown/JSON review package generation
└── adapters/
    ├── playwright.py  — Playwright browser adapter
    ├── local_renderer.py — Local HTTP server for prototype demos
    ├── ai_generator.py   — Optional AI prototype (v36-gated)
    └── v36_evaluator.py  — v36 evaluation harness integration
```

## Capture Environment

All captures pinned:
- Browser: Chromium version
- Playwright version
- Viewport: width × height
- Device scale factor
- Locale: en-NZ
- Timezone: Pacific/Auckland
- Reduced motion: enabled
- Color scheme: light
- Fonts: system default

Animation disabled via CSS injection ONLY in proof captures — never injected into live site.

## Region Extraction

Fallback chain:
1. CSS selector from finding
2. Role + accessible name match
3. DOM similarity score
4. Finding evidence bounding box
5. → NEEDS_REVIEW

Context padding: 80px horizontal, 100px vertical (configurable).

## Patch Types (deterministic first)

| Type | Example |
|------|---------|
| CSS_PATCH | Fix overflow, contrast, spacing |
| HTML_ATTRIBUTE_PATCH | Add alt, dimensions, aria-label |
| TEXT_LABEL_PATCH | Add missing form label |
| LAYOUT_PATCH | Fix mobile clipping |
| ACCESSIBILITY_PATCH | Add roles, landmarks |
| CTA_PATCH | Fix broken booking URL |
| FORM_LABEL_PATCH | Associate label with input |

AI-generated prototypes are optional and lower-trust. Always pass through v36 evaluation.

## Verification Pipeline

```
VERIFIED FINDING → BEFORE CAPTURE → PROTOTYPE GENERATION
    → AFTER CAPTURE → INDEPENDENT VERIFIER → REVIEW PACKAGE
```

Verifier checks:
1. Original defect is gone (replay original detector)
2. No new axe violations introduced
3. No new console errors
4. No regressions in neighboring components
5. Visual diff is confined to expected region

## Verification Statuses

| Status | Meaning |
|--------|---------|
| VERIFIED_FIX | Original defect gone, no regressions |
| PARTIAL_FIX | Some improvement but defect persists |
| REGRESSION_DETECTED | New defects introduced |
| NO_EFFECT | No observable change |
| WRONG_TARGET | Fix applied to wrong element |
| UNVERIFIABLE | Cannot verify (stale source, missing evidence) |
| STALE_SOURCE | Original finding no longer applies |

## Eligibility

Not every finding gets a proof. Require:
- Finding status: CONFIRMED
- Minimum confidence: 0.90
- Business relevance: MEDIUM or higher
- Proofability: deterministic patch or high-confidence AI
- Source snapshot: fresh (not stale)
- Identity confidence: above configured threshold

## Review Package

Human reviewer receives:
- Business + opportunity context
- Original finding with evidence
- Before screenshot + DOM
- Proposed fix with patch manifest
- After screenshot
- Verification result (detector replay, regression checks)
- Visual + DOM diff
- Business relevance assessment
- Suggested offer type
- Limitations and provenance
- Explicit human action required

## Integration Points

- **v36 Evaluation**: AI prototypes pass through v36 deterministic graders
- **ApprovalStore**: Reused for proof approval decisions
- **AuditLog**: All proof actions logged
- **Review queue**: Existing reviewer actions handle proof review

## Acceptance Gates (15)

| Gate | Target |
|------|--------|
| verified_findings_only | PASS |
| live_site_writes | 0 |
| external_form_submissions | 0 |
| before_after_environment_match | 100% |
| original_detector_replayed | 100% |
| generator_self_verification | DISABLED |
| seeded_bad_fix_rejection | 100% |
| regression_detection | ≥98% |
| provenance_coverage | 100% |
| artifact_hashing | 100% |
| unexpected_external_network_writes | 0 |
| golden_corpus_retention | 1.0 |
| high_confidence_false_proof_rate | <2% |
| existing_review_system_reused | PASS |
| benchmark_generated | PASS |

## Benchmark Output
- `reports/proof/benchmarks/v39-baseline.json`
- `reports/proof/benchmarks/P2_003_V39_BENCHMARK.md`

## Known Limitations
- Proof only covers findings with clear DOM-level defects
- Complex business logic fixes not yet supported
- AI-generated prototypes have lower trust scores
- Visual diff may flag legitimate content changes as differences
- Multi-page flows not fully tested

## Deferred
- Live WordPress/Shopify editing
- Automatic deployment (Vercel/Netlify)
- Production Git pushes
- Customer CMS login
- Automatic outreach
- Conversion improvement claims
- Full-site AI rebuild

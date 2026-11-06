# V45 Baseline — Ground Truth, Isolation, and Existing Work

## Environment Verification

- **Working directory:** `/Users/dd/WEBSITE-AUDITOR-v45`
- **Branch:** `intelligence/v45-opportunity-quality`
- **Base SHA:** `eb06f5abc23649bf78f4b38f38e7ef58f6532614`
- **v44 isolation:** v44 worktree at `/Users/dd/WEBSITE-AUDITOR` (NOT touched by v45 work)
- **Paid calls:** 0 (policy: `paid_allowed=false`, `max_cost_usd=0`)
- **External sends:** 0 (policy: `live_outreach=false`)

## Existing v45 Modifications

| File | Description |
|---|---|
| `money-machine/mm_workers.py` | Deterministic stage handlers for the continuous pipeline |
| `money-machine/test_pipeline.py` | Behavioral tests for pipeline state machine and workers |
| `reports/intelligence/` | Intelligence report directory (this file is the first) |

## Data Flow Map (Canonical Pipeline)

### Search → Candidate Extraction → Normalization → Dedupe → Intake
1. **Discovery sources:** SearXNG (local, loopback-only), import files, batch queries
2. **Candidate extraction:** `mm_discovery.py::normalize_candidate`, `root_url()`, `root_url()`
3. **Normalization:** `mm_discovery.py::normalize_intake_url()` — validates public URLs, strips www, normalizes port/scheme, rejects private IPs/reserved TLDs
4. **Dedupe:** Host-based dedup in `mm_discovery.py::collect_multi_source()`, plus DB-level dedup in `_normalize_intake()`
5. **Intake:** `mm_discovery.py::intake_candidates()` → creates `businesses` rows, enqueues `pipeline_items` in `DISCOVERED` state

### Identity → Qualification → Audit → Scoring → Contact → Demo → Review → Terminal
- **Identity:** `mm_workers.py::identity_handler` — resolves canonical host from declared public_website
- **Audit:** `mm_workers.py::audit_handler` — runs `auditor_toolkit` deterministic audit (static profile, no browser/AI)
- **Understanding:** `mm_workers.py::understanding_worker_handler` — scores available evidence, prepares for qualification
- **Qualification:** `mm_workers.py::qualification_handler` — combines commercial (mm_lead_qualifier) and technical (audit score) evidence
- **Contact:** `mm_workers.py::contact_handler` — Email Finder V2 with strict release gates
- **Demo/QA:** `mm_workers.py::demo_handler`, `qa_handler` — supervised/model work, never fabricates
- **Outreach gate:** `mm_workers.py::outreach_handler` — gates into approval lane, never sends

### Pipeline State Machine
```
DISCOVERED → IDENTITY_PENDING → IDENTITY_RESOLVED → AUDIT_PENDING → AUDITED
  → QUALIFICATION_PENDING → QUALIFIED → CONTACT_PENDING → CONTACT_RESOLVED
  → VERIFICATION_PENDING → VERIFIED → REMEDIATION_PENDING → DEMO_PENDING
  → DEMO_READY → QA_PENDING → OUTREACH_PENDING → APPROVAL_PENDING
  → APPROVED → READY_TO_SEND → SENT → RESPONDED → CONVERTED (terminal)

Alternate paths: REJECTED, NO_VERIFIED_EMAIL, NEEDS_REVIEW, RETRYABLE_FAILURE,
  PERMANENT_FAILURE, SUPPRESSED, DUPLICATE, DEPLOYMENT_FAILED (all terminal except
  NEEDS_REVIEW and RETRYABLE_FAILURE which can recover)
```

### Stage Handlers (WORKERS registry in mm_workers.py)
| Worker | Input States | Handler |
|---|---|---|
| identity | DISCOVERED | `identity_handler` |
| audit | AUDIT_PENDING, IDENTITY_RESOLVED | `audit_handler` |
| understanding | AUDITED | `understanding_worker_handler` |
| qualification | QUALIFICATION_PENDING | `qualification_handler` |
| contact | QUALIFIED, CONTACT_PENDING | `contact_handler` |
| preparation | VERIFIED, REMEDIATION_PENDING, DEMO_PENDING, DEMO_READY, QA_PENDING | `preparation_worker_handler` |
| outreach_gate | OUTREACH_PENDING | `outreach_handler` |

## Candidate States & Transition Rules

### Current States (from schema + pipeline)
- **Pipeline item states:** DISCOVERED, IDENTITY_PENDING, IDENTITY_RESOLVED, AUDIT_PENDING, AUDITED, QUALIFICATION_PENDING, QUALIFIED, CONTACT_PENDING, CONTACT_RESOLVED, VERIFICATION_PENDING, VERIFIED, REMEDIATION_PENDING, DEMO_PENDING, DEMO_READY, QA_PENDING, OUTREACH_PENDING, APPROVAL_PENDING, APPROVED, READY_TO_SEND, SENT, RESPONDED, CONVERTED, REJECTED, NO_VERIFIED_EMAIL, NEEDS_REVIEW, RETRYABLE_FAILURE, PERMANENT_FAILURE, SUPPRESSED, DUPLICATE, DEPLOYMENT_FAILED
- **Business status (schema):** discovered, audited, scored, offer_drafted, human_review, approved, rejected
- **Deal stage:** DISCOVERED, VERIFIED, AUDITED, QUALIFIED, DRAFT_READY, AWAITING_APPROVAL, APPROVED_TO_SEND, SENT, REPLIED, CALL_OR_DISCOVERY, PROPOSAL_READY, PROPOSAL_SENT, WON, LOST, SUPPRESSED

### Transition Rules
- **Forward:** Happy path chain only (enforced by `TRANSITIONS` dict)
- **To alternate:** Any non-terminal state can go to REJECTED, NO_VERIFIED_EMAIL, NEEDS_REVIEW, RETRYABLE_FAILURE, PERMANENT_FAILURE, SUPPRESSED, DUPLICATE
- **Recovery:** NEEDS_REVIEW → {IDENTITY_PENDING, AUDIT_PENDING, QUALIFICATION_PENDING, CONTACT_PENDING, VERIFICATION_PENDING, SUPPRESSED, REJECTED}; RETRYABLE_FAILURE → any *_PENDING state
- **POST_APPROVAL boundary:** Handlers cannot cross APPROVED, READY_TO_SEND, SENT, RESPONDED, CONVERTED (only `mark_sent` can enter SENT)
- **Backward:** Illegal (raises ValueError)

## Rejection Logic (Current)

### Terminal rejection paths:
1. **QUALIFICATION_TUNNELVISION:** `qualification_handler` — if neither commercial_score >= 30 nor technical_score >= 40, → REJECTED
   - Commercial score from `mm_lead_qualifier::qualify_lead` on business name + region text
   - Technical score from audit defects (must be >= 40, or >= 70 for HIGH_NEED)
2. **DEAD_LETTER:** `pipeline::fail()` — after max_attempts (default 5) retries, → RETRYABLE_FAILURE or PERMANENT_FAILURE
   - Transient DB errors → RetryableError (backoff)
   - Schema/Integrity/AttributeError → PermanentError (dead-letter)
3. **SUPPRESSED:** `discover_worker_handler` — insufficient evidence from discovery
4. **DUPLICATE:** Deduplicated by canonical_host/name during intake
5. **NO_VERIFIED_EMAIL:** Contact handler finds no VERIFIED_HIGH email after running Email Finder V2
6. **PERMANENT_FAILURE:** Handler contract bugs, schema drift, integrity errors

### Primary rejection reasons (from pipeline events)
- `not qualified: commercial=X, technical=Y` (qualification_handler)
- `dead-lettered after N attempts: <error>` (pipeline::fail)
- `No viable opportunity discovered` (discovery worker)
- `Insufficient evidence for meaningful opportunity` (discovery worker)

## Qualification Gates

| Gate | Requirement | Source |
|---|---|---|
| Identity | `public_website` present and valid | `identity_handler` |
| Audit | `auditor_toolkit` run completes with all required checks passing | `audit_handler` |
| Commercial | `commercial_score >= 30` (from mm_lead_qualifier on name+region) | `qualification_handler` |
| Technical | `technical_score >= 40` (audit defect score) OR one of commercial basis met | `qualification_handler` |
| Contact | Email Finder V2 production release gate open + VERIFIED_HIGH email | `contact_handler` |
| Outreach | All approval gates pass | `mm_approval.evaluate` |

## Score Formulas

### Opportunity Score (6-component, from mm_core)
Uses `opportunity_score_6_component(supported_problem, evidence_to_solution_fit, business_and_campaign_fit, bounded_delivery_feasibility, evidence_quality_freshness, supported_reason_to_act_now)` — returns weighted average scaled 0-100.

### Qualification Scoring (mm_lead_qualifier)
- `qualify_lead(text, industry)` → returns `{'qualification_score': 0-100, 'tier': str, 'reasons': [...]}`
- Job signals (high/medium/low keyword regex)
- Budget signals (currency amounts, project sizes)
- Industry-aware freshness windows
- Commercial score >= 30 = commercial pass

### Intelligence Score (mm_intelligence)
- 11 dimensions: pain, evidence_confidence, freshness, fit, ability_to_pay, urgency, decision_access, demoability, ease, upsell, recurring
- Evidence confidence derived from mm_evidence status
- Freshness decays linearly over 7 days
- Score = 0 if any eligibility blocker (missing evidence, etc.)

## Identity Resolution (Current)
- Canonical host from `mm_core::public_url()` — strips www, validates public scheme, rejects private IPs
- Business identity: name + public_website + region + source
- Duplicate detection: host-based (canonical_host) and name-based during intake
- No confidence score — binary resolved/unresolved

## Discovery Sources & Evidence Available

| Source | Evidence Field | Quality Signal |
|---|---|---|
| SearXNG local search | url, title, content | Query yield, junk rate |
| Import files (CSV/JSON) | legal_name, trading_name, nzbn, domain | Source yield, new prospect rate |
| Batch search queries | searxng-local:{query_ref} | Query-family performance |

### Runtime Evidence Available
- `mm_evidence`: url, observation, limitation, checked_at (verified status)
- `mm_evidence_meta`: status (verified/unverified), confidence
- `audits`: mobile_quality, conversion_quality, quote_flow, booking_flow, seo_basics, trust_signals, page_speed, accessibility, defect counts
- `pipeline_events`: full transition history with evidence JSON

## Current Data Gaps (Pre-v45)

1. **No rejection taxonomy** — rejections are free-text reasons, not classified categories
2. **No experience/learning memory** — decisions are not recorded as structured learning examples
3. **No error mining engine** — false positives/negatives are not automatically detected or clustered
4. **No search-result quality classifier** — raw search results are not classified before expensive processing
5. **No identity confidence scoring** — identity is binary, not confidence-based
6. **No evidence graph** — evidence is flat fields, not explicit relationships
7. **No uncertainty engine** — missing evidence is implicitly negative, not explicitly unknown
8. **No counterfactual reasoning** — cannot answer "what would change this decision?"
9. **No information-gain planner** — next action is not chosen by expected information gain
10. **No source/query intelligence** — source yield and query quality are not measured
11. **No hard-case memory** — hard cases are not automatically captured into a growing evaluation set
12. **No challenger arena** — alternative strategies cannot be tested offline before promotion
13. **No calibration tracking** — confidence values are not compared to actual correctness

## Known Architectural Constraints

1. **v44 isolation:** All v45 work is in `/Users/dd/WEBSITE-AUDITOR-v45`, separate worktree
2. **Zero paid cost:** No model calls that incur cost; `model_request` in mm_intelligence blocks all non-free routes
3. **No external sends:** Outreach handler gates into APPROVAL_PENDING; `mark_sent` requires provider-verified ledger row
4. **Determinism at safety boundaries:** SSRF protections, private IP policy, no secrets in logs
5. **Append-only event log:** `pipeline_events` preserves all history; schema drift repaired in-place
6. **Circuit breakers + rate limits:** Per-service circuit breakers and fixed-window rate limits
7. **Bounded retries:** Exponential backoff with jitter; dead-letter after max_attempts
8. **Lease-based work queue:** Workers lease items; expired leases are reclaimed

## V45 Implementation Plan Priority

**Wave 1 (CRITICAL):** P0 baseline, P1 experience memory, P2 rejection intelligence, P3 error mining
**Wave 2 (CRITICAL):** P4 search-result classifier, P5 identity resolution, P6 evidence graph, P7 commercial evidence, P8 uncertainty
**Wave 3+:** Full recursive intelligence stack

## Baseline Metrics (Pre-v45, Post-fixture)

- Money Machine tests: 83 passed (test_pipeline, test_qualification_corrections, test_opportunity_score, test_lead_qualifier)
- Pre-existing failures: 97 failed (due to missing source DB fixture for acceptance tests — environment issue, not code)
- Pre-existing skips: 11 skipped (intentional safety skips)
- E2E browser tests: not run (opt-in, require WA_BROWSER_E2E=1)

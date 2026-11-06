# V44 Rejection Intelligence Analysis

**Branch:** `integration/v44-local-machine-convergence` (head `eb06f5ab`)
**Date:** 2026-09-29
**Author:** Intelligence phase analysis
**Scope:** Read-only analysis of pipeline design and code; no live database

## Executive Summary

Nearly all live-discovered businesses end in `REJECTED` because the pipeline's qualification gate requires **two independent evidence axes** (commercial ≥ 30 AND technical ≥ 40), and **both are structurally difficult to satisfy from discovery intake alone**. The pipeline itself is sound — the gates are correctly implemented — but the discovery-to-qualification chain has design weaknesses that produce systematic false negatives without any live data to observe.

Three root causes dominate:

1. **Commercial qualification has no credibility signals to work with** (discovery only provides name + region)
2. **Audit evidence is consumed for need-scoring, not for qualification** (defect count → need proxy instead of health → commercial value)
3. **Qualifying evidence never reaches the qualification stage** (contact evidence is for outreach eligibility, not for qualification scoring)

---

## 1. Pipeline Architecture Summary

The pipeline is a linear multi-stage state machine:

```
DISCOVERED → IDENTITY_PENDING → IDENTITY_RESOLVED → AUDIT_PENDING → AUDITED
→ QUALIFICATION_PENDING → QUALIFIED → CONTACT_PENDING → ... → CONVERTED
```

**Relevant handlers (mm_workers.py):**

| Stage | Handler | What it produces |
|---|---|---|
| `AUDIT_PENDING` | `audit_handler` | `AUDITED` → audit evidence (score, defect_count, health_score) |
| `AUDITED` | `understanding_worker_handler` | `QUALIFICATION_PENDING` → opportunity_score (6-component), evidence_count |
| `QUALIFICATION_PENDING` | `qualification_handler` | `CONTACT_PENDING` or `REJECTED` → commercial_score + technical_score |

**The qualification gate (qualification_handler, line 152):**

```python
commercial_pass = commercial_score >= 30   # from qualify_lead(name+region, industry='')
technical_pass = technical_score is not None and technical_score >= 40  # from audit evidence
```

Both must pass. Either failing → `REJECTED`.

---

## 2. Rejection Reason Distribution (Design-Level Analysis)

### 2a. Commercial failure: score < 30 (PRIMARY)

**Mechanism:** `qualification_handler` calls `qualify_lead(text, industry='')` where `text = b['name'] + ' ' + b['region']`.

This produces a score of 0 for virtually every discovery-originated business:

```
qualify_lead("Fixture Plumbing Canterbury", industry="")
# → {'qualification_score': 0, 'tier': 'COLD',
#    'reasons': [
#      'Insufficient substantive evidence for qualification readiness',
#      'Insufficient signals for qualification - basic identification only'
#    ]}
```

**Why:** `qualify_lead` requires at least one "substantive signal" (job active, budget active, industry discussed) to score above 20. A business name + region provides nothing — no job postings, no budget statements, no industry discussion. The function is designed for operating on real evidence text (audit observations, website copy, job pages), not on bare identifiers.

**Impact:** This is the dominant rejection cause. Nearly 100% of discovery-originated businesses fail commercial qualification exclusively because the input to `qualify_lead` is the wrong kind of text.

### 2b. Technical failure: score < 40 OR score is None

Two sub-cases:

**2b-i. Field name mismatch: `defect_score` vs `score`**

`_audit_evidence()` reads `report.get('defect_score')` but `run_audit()` produces `report['score']` (the severity sum from `score_findings()`). The field name mismatch means `_audit_evidence()` stores `score=None` for every audit.

```
run_audit() report: {'score': 12, 'severity_score': 12, 'health_score': 88, 'defect_count': 2, ...}
_audit_evidence reads: report.get('defect_score')  # → None (key doesn't exist)
```

Result: `_technical_opportunity()` always gets `score=None` → `technical_score=None` → `technical_pass = False` (because `None is not >= 40`).

This is a **silent** bug: the audit completes successfully, produces a valid score, stores it under the wrong field name, and the qualification stage reads None. The defect_count is still stored correctly, so defect_count-based filtering works.

**2b-ii. Zero-defect healthy sites: correct by design, but lost opportunity**

`_technical_opportunity()` returns `(None, 0)` when `defect_count == 0`:

```python
def _technical_opportunity(audit_evidence):
    defect_count = max(0, int(audit_evidence.get('defect_count', 0)))
    if defect_count == 0:
        return None, defect_count   # ← intentional: no defects = no technical need
    return _bounded_score(audit_evidence.get('score')), defect_count
```

This is **correct for need-scoring** (a business with zero defects has no technical remediation need) but **incorrect for commercial qualification**. A healthy business with a high-value commercial profile should still qualify on commercial grounds. The bug above (2b-i) masks this issue for now, but even after fixing the field name mismatch, 0-defect sites will still fail technical qualification — meaning they rely entirely on commercial.

**2b-iii. Low-severity-only audits: score < 40 threshold**

Even after the field name fix, businesses with only low-severity defects (score=4-12) fail technical_pass (>=40). These are businesses with minor issues (missing title, no viewport, no canonical tag) — not material technical need, but also not "low or unknown" in a negative sense.

### 2c. Both axes fail (typical discovery business)

For a typical discovered business:
- Commercial score = 0 (name+region, no signals) → fails
- Technical score = None (field name bug) → fails
- Result: `REJECTED`, reasons: `not qualified: commercial=0, technical=None`

---

## 3. Technical Score Distribution (Design-Level)

### 3a. With the current bug (defect_score key not found)

All audits produce `technical_score = None` because `_audit_evidence` reads the wrong key. The distribution is:

```
100% None
```

### 3b. After fixing the field name mismatch

Using the `score` field that `run_audit` actually produces:

| Defect scenario | severity score | _technical_opportunity | technical_pass (>=40) |
|---|---|---|---|
| 0 defects (healthy) | N/A | None (defect_count=0) | False |
| 1 low defect (4 pts) | 4 | 4.0 | False |
| 1 low defect (8 pts) | 8 | 8.0 | False |
| 2 low defects (8+4=12) | 12 | 12.0 | False |
| 3 medium defects (8×3=24) | 24 | 24.0 | False |
| 2 medium + 1 high (8+8+16=32) | 32 | 32.0 | False |
| 4 mixed (8+8+16+8=40) | 40 | 40.0 | True |
| 1 critical (30 pts) | 30 | 30.0 | False |
| 1 critical + 1 low (30+4=34) | 34 | 34.0 | False |
| 1 critical + 1 medium (30+8=38) | 38 | 38.0 | False |
| 1 critical + 1 medium + 1 low (30+8+4=42) | 42 | 42.0 | True |

**Observation:** The 40-point threshold is high relative to typical static audit findings. Most small business sites have 1-3 low/medium defects = score 4-24. Only sites with a high-severity or critical defect (or many medium defects) clear 40.

### 3c. The health_score inversion

The audit toolkit produces `health_score = 100 - severity_score`. For opportunity qualification, **we want high severity (many problems) = high technical need**, which is exactly what `score_findings` returns. The health score (high = good) is the opposite. Currently `_audit_evidence` stores both `score` (= severity/need) and `health_score` (= quality/good). The qualification stage only uses `score`. The `health_score` is stored but never consumed.

---

## 4. Commercial Score Distribution (Design-Level)

### 4a. Current behavior: name + region → score 0

`qualify_lead` with the text that `qualification_handler` produces (business_name + region, industry=''):

```
All businesses: score = 0, tier = COLD
```

This is deterministic and correct given the input. The problem is the input, not the scorer.

### 4b. What qualify_lead CAN score

`qualify_lead` is designed to score **evidence text**, not identifier text. When called with real evidence (e.g., "We are hiring 3 developers", "Budget approved for Q4", industry-discussion text), it can produce scores in the 30-80+ range.

The scoring function has these signal types:
- Job signals (high/medium/low strength, with substantive check)
- Budget signals (high/medium/low strength, with investment-vs-product check)
- Industry identification (reduced weight for mere mentions)
- Extra signals from operator (recent_job_post, budget_mentioned, high_authority_domain, etc.)

None of these are available when the input is just "Business Name Region".

### 4c. industry parameter is hardcoded to empty

```python
commercial_lead = lq.qualify_lead(text, industry='')
```

The `industry` parameter is always empty. Even if we could pass a detected industry, `qualify_lead` would give at most +8 for industry identification (and capped at 15 without substantive signals). The industry parameter alone cannot bridge the gap from 0 to 30.

---

## 5. Evidence Gaps

### Gap 1: No commercial evidence in the qualification pipeline

The qualification stage receives:
- `audit_evidence` from `AUDITED` stage (defect_count, score, health_score)
- `understanding` from `QUALIFICATION_PENDING` stage (opportunity_score, evidence_count)

Neither contains commercial signals. The `qualification_handler` fabricates commercial input by concatenating name + region, which is not evidence.

### Gap 2: Audit evidence used for technical scoring only, not commercial

`_audit_evidence` stores `health_score` (e.g., 88 for a site with 12 points of defects) but this is never read by `qualification_handler`. A high health_score could indicate a business that values quality and would be commercially receptive — but this signal is discarded.

### Gap 3: Understanding worker produces opportunity_score but it's not used for qualification

The `understanding_worker_handler` produces `opportunity_score` via `opportunity_score_6_component`, which is stored in pipeline_events under `QUALIFICATION_PENDING`. The `qualification_handler` reads this as `commercial_opportunity_score` but **does not use it for the commercial_pass threshold**. The commercial_pass is determined solely by `qualify_lead(name+region)`.

```python
# qualification_handler, line 162-177
raw_opportunity = understanding.get('opportunity_score')
commercial_opportunity = (raw_opportunity if isinstance(raw_opportunity, dict) else None)
commercial_opportunity_score = (
    _bounded_score(commercial_opportunity.get('score'))
    if commercial_opportunity else None
)
# This score is stored in the result but NOT used for commercial_pass
```

### Gap 4: Contact evidence is for outreach, not qualification

`mm_contact_evidence` and `mm_email_store` produce verified contact data, but this happens at `CONTACT_PENDING` stage — which is AFTER qualification. A business that passes qualification can then have its contact verified; a business that fails qualification never gets contact verification. There's no feedback loop from contact quality to qualification scoring.

### Gap 5: No discovery data enrichment before qualification

Discovery produces: name, region, canonical_host, source, nzbn (sometimes). None of these are passed to `qualify_lead` as substantive evidence. The NZBN data (legal name, trading name) is stored in pipeline_events under `DISCOVERED` but never surfaced to the qualification stage.

---

## 6. Examples

### 6a. Correctly rejected prospects (legitimate rejections)

**Case 1: A personal blog in a non-commercial region**
- Discovery: "John's Photography Hobbies", region="Canterbury"
- Audit: 0 defects (healthy personal site)
- Qualification: commercial=0 (no commercial signals), technical=None (0 defects)
- Result: REJECTED — correctly. This is not a commercial prospect.

**Case 2: A local club with no commercial intent**
- Discovery: "Northside Sports Club", region="Auckland"
- Audit: 2 low defects (missing meta description, no viewport) → score=12
- Qualification: commercial=0, technical=12 (< 40)
- Result: REJECTED — correctly. Minor technical issues + no commercial signals.

### 6b. Potentially false-negative prospects (rejected despite being real businesses)

**Case 3: A real plumbing business with a basic website**
- Discovery: "Fast Plumbing Solutions Ltd", region="Christchurch"
- NZBN: 942318421 (reachable via NZBN import)
- Website: https://fastplumbing.co.nz (basic HTML, 2 medium defects → score=16)
- Commercial qualification: score=0 (input is "Fast Plumbing Solutions Ltd Christchurch", no job/budget signals detectable from name alone)
- Technical qualification: score=16 (< 40)
- Result: REJECTED

**Why this is a false negative:** This is a real NZBN-registered plumbing business in Christchurch. A human reviewer would immediately recognize commercial intent. The pipeline rejects because:
1. It cannot detect commercial signals from a business name + region
2. The website has minor defects (score 16) which don't cross the 40 threshold
3. It has no access to the NZBN registration as a commercial signal

**Case 4: A construction company with a high-value website**
- Discovery: "Elevate Construction", region="Wellington"
- Website: modern React site, 3 low defects → score=12
- Commercial qualification: score=0
- Technical qualification: score=12 (< 40)
- Result: REJECTED

**Why this is a false negative:** A modern React website with 3 minor defects is a business actively investing in its digital presence. The audit would flag this as a health_score of 88 (good). The commercial intent is implied by the investment in web presence, but the pipeline has no signal for "this business cares about its website" because it only sees defect severity, not health quality or investment signals.

**Case 5: A business with verified email but rejected at qualification**
- Discovery → AUDIT → QUALIFICATION_PENDING
- At QUALIFICATION_PENDING: commercial=0, technical=12 → REJECTED
- Contact evidence exists elsewhere in the system but was never reached because the business never passed qualification
- Result: REJECTED before contact verification could even run

---

## 7. Diagnosis: Why the Pipeline Produces Systematic False Negatives

### Root cause 1: Input mismatch for commercial qualification

`qualification_handler` passes `b['name'] + ' ' + b['region']` to `qualify_lead`. This is identifier text, not evidence text. `qualify_lead` is designed to score evidence text (job postings, budget discussions, industry signals). The mismatch is the primary driver of commercial failure.

### Root cause 2: Field name mismatch in audit evidence projection

`_audit_evidence` uses `report.get('defect_score')` but `run_audit` uses `report['score']` (from `score_findings`). This silently breaks technical scoring for every audit. Even audits with material defects (score 40+) won't count because the score is read as None.

### Root cause 3: Technical scoring only for defect-driven need, not for commercial quality

The technical axis is scored as "how many defects = how much remediation need." This is appropriate for a remediation-selling model, but it ignores:
- Businesses with healthy sites (0 defects) that still need commercial services
- Businesses with high-quality sites that demonstrate digital investment willingness
- The health_score as a commercial quality signal

### Root cause 4: No enrichment between discovery and qualification

Discovery data (name, region, canonical_host, possibly NZBN) is not enriched before reaching qualification. There's no step that:
- Detects industry from name/signature
- Detects commercial category from NZBN data
- Identifies whether a business is commercial vs. non-commercial
- Collects any commercial signals before qualification

### Root cause 5: Thresholds designed for evidence-rich input

The thresholds (commercial >= 30, technical >= 40) are reasonable when the input contains evidence. They're too high when the input is bare identifiers. The pipeline needs either:
- Better input (enriched evidence before qualification), or
- Lower thresholds for discovery-originated businesses with evidence of commercial identity (NZBN registration, commercial email domain, commercial category detection)

---

## 8. Recommended Changes (Ranked by Evidence Strength)

### Priority 1: Fix the `_audit_evidence` field name mismatch

**Change:** `mm_workers.py:_audit_evidence`, line 51: change `report.get('defect_score')` to `report.get('score')`.

**Evidence:** Deterministic. `run_audit` always produces `score`, never `defect_score`. The field name is wrong.

**Impact:** After this fix, technical_score will be populated from audit results. Businesses with 40+ severity score will pass technical qualification. Businesses with < 40 will still fail, but now for legitimate reasons (low technical need) rather than a silent bug.

**Risk:** Low. This changes only what evidence is stored, not the qualification logic.

---

### Priority 2: Pass audit evidence to qualification for commercial interpretation

**Change:** In `qualification_handler`, read `health_score` from audit evidence and use it as a commercial signal (high health = quality-conscious business = commercial fit signal). Also pass `defect_count` as a commercial opportunity signal (more defects = more potential work).

**Current code (line 159-162):**
```python
audit_evidence = _latest_pipeline_evidence(d, b['id'], 'AUDITED')
technical_score, defect_count = _technical_opportunity(audit_evidence)
```

**Should also extract:**
```python
health_score = audit_evidence.get('health_score')  # currently stored but never read
```

**Evidence:** The `health_score` is already stored in `_audit_evidence` output. The understanding worker and qualification handler don't use it. A high health_score (80+) indicates a business that invests in quality — a commercial signal.

**Risk:** Low. Adding a read of an existing field.

---

### Priority 3: Detect commercial category from discovery data

**Change:** Before qualification, enrich the business record with a `commercial_category` derived from:
- NZBN data (if present): legal form, industry codes, trading name patterns
- Website domain patterns: `.co.nz` commercial domains vs `.org.nz` non-profit
- Name patterns: "Ltd", "Limited", "Inc", "LLC" → commercial; "Club", "Society", "Trust" → possibly non-commercial

**Evidence:** NZBN data is already collected in discovery and stored in pipeline_events. The qualification stage doesn't read it. A NZBN-registered business is, by definition, a commercial entity.

**Risk:** Medium. Requires new classification logic. Must be conservative (unknown → not commercial) to avoid false positives.

---

### Priority 4: Lower commercial threshold for NZBN-verified businesses

**Change:** When a business has NZBN data (commercial registration), reduce the commercial_pass threshold from 30 to a lower value (e.g., 15) and accept the NZBN registration as a commercial signal.

**Evidence:** NZBN registration is a regulatory confirmation of commercial status. It's stronger evidence than name+region alone. The current pipeline ignores it for qualification.

**Risk:** Low-Medium. Reducing thresholds should be accompanied by clear labeling of why the business qualified (NZBN-verified).

---

### Priority 5: Pass substantive evidence to qualify_lead

**Change:** Instead of passing `name + ' ' + region` to `qualify_lead`, pass any available evidence text:
- Website meta description / homepage text (from audit)
- NZBN trading name + legal name + industry description
- Any captured business description from discovery source

**Evidence:** `qualify_lead` is designed to score evidence text. Currently it gets identifiers. The audit URL is fetched and analyzed — the homepage text is available in the audit evidence. Passing this to `qualify_lead` would give it real signals to work with.

**Risk:** Medium. Requires extracting text from audit evidence and passing it appropriately.

---

### Priority 6: Separate "commercial identity confirmed" from "commercial score"

**Change:** Introduce a `commercial_identity` axis that is satisfied by:
- NZBN registration
- Commercial domain pattern
- Detected commercial category

This is separate from the `commercial_score` from `qualify_lead`. A business can pass commercial_identity without a high commercial_score.

**Evidence:** The current pipeline conflates "is this a real business" with "does this business have strong commercial signals." These are different questions. NZBN registration answers the first but not the second.

**Risk:** Medium. Architecture change.

---

## 9. What NOT to Change

- **Do not lower thresholds blindly.** The 30/40 thresholds are reasonable for evidence-rich input. Lowering them without improving input quality would produce false positives (non-commercial entities qualifying).
- **Do not weaken `qualify_lead`'s substantive signal requirement.** The requirement that qualification needs at least one substantive signal is correct. The fix is to provide substantive signals, not to bypass the check.
- **Do not merge commercial and technical scores.** The current separation (qualification_basis = ['commercial'], ['technical'], or both) is correct. Keep them independent.
- **Do not auto-qualify based on discovery source alone.** A SearXNG result or import row is not commercial proof. NZBN registration is closer but still requires confirmation.

---

## 10. Summary Table

| Issue | Type | Impact | Fix priority |
|---|---|---|---|
| `qualify_lead` receives name+region, not evidence | Design | Commercial score = 0 for all discovery businesses | P1 |
| `_audit_evidence` reads wrong field (`defect_score` vs `score`) | Bug | Technical score always None | P1 |
| `health_score` stored but never consumed | Gap | Commercial quality signal lost | P2 |
| No commercial category detection from NZBN/discovery | Gap | Commercial identity unknown | P3 |
| No NZBN verification used for qualification | Gap | Verified commercial entities rejected | P4 |
| No substantive evidence text passed to `qualify_lead` | Gap | Scorer cannot detect signals | P5 |
| Commercial identity conflated with commercial score | Design | Binary commercial pass/fail without identity check | P6 |

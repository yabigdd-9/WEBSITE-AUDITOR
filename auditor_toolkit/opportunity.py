"""Commercial opportunity scoring (P9): worth pursuing, not just how broken.

Separates the TECHNICAL score (how weak the site is — P5 breakdown) from the
OPPORTUNITY score (how worthwhile the prospect is). Deterministic and
inspectable: every input is stored, the formula is versioned, and the score
can be reproduced byte-for-byte from stored inputs. An LLM may *explain* the
score but must never *determine* it.

Formula (v1), every component 0..1 unless stated:
    opportunity = 100 * need * business_value * contact * fixability * confidence
                  / (1 + effort)
"""
from __future__ import annotations

import math

FORMULA_VERSION = "opportunity-v1"

NEED_KEYS = frozenset({
    "no-contact-path",
    "thin_content_200_words",
    "missing_title",
    "missing_meta_description",
    "viewport",
    "consent_prechecked",
    "mixed-content",
    "broken-internal-link",
    "sitemap-missing",
    "sitemap-malformed",
    "missing_canonical_url",
    "schema_missing",
})

CERTAINTY_MAP = {
    "VERIFIED_HIGH": 0.95,
    "VERIFIED": 0.95,
    "VERIFIED_MEDIUM": 0.65,
    "OBSERVED": 0.4,
    "STRONG_EVIDENCE": 0.8,
    "CANDIDATE": 0.5,
    "CATCH_ALL": 0.3,
    "UNVERIFIED": 0.2,
    "REJECTED": 0.0,
    "SUPPRESSED": 0.0,
    "NO_VERIFIED_EMAIL": 0.0,
    "INVALID": 0.0,
}

# Strict input envelopes: fail closed rather than filling unknowns with flattering
# defaults. All opportunity inputs are 0..1 unless otherwise noted.


def _clamp01(value):
    if isinstance(value, bool):
        raise ValueError("opportunity input must be numeric, not boolean")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"opportunity input must be numeric, got {value!r}")
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError(f"opportunity input out of range [0,1]: {value!r}")
    return number


def opportunity_formula(
    need: float,
    business_value: float,
    contactability: float,
    fixability: float,
    confidence: float,
    effort: float,
) -> dict:
    """Pure deterministic compute step. No LLM, no business context.

    `confidence` here is the *findings/contact* certainty, not a flattering
    'I feel good about this' number — if you cannot justify it, it should be
    low (NO_VERIFIED_EMAIL=0 -> product=0 -> opportunity=0).
    """
    n = _clamp01(need)
    v = _clamp01(business_value)
    c = _clamp01(contactability)
    f = _clamp01(fixability)
    cf = _clamp01(confidence)
    e = _clamp01(effort)
    numerator = 100.0 * n * v * c * f * cf
    score = round(numerator / (1.0 + e), 1)
    return {
        "formula_version": FORMULA_VERSION,
        "opportunity_score": score,
        "components": {
            "need": n,
            "business_value": v,
            "contactability": c,
            "fixability": f,
            "confidence": cf,
            "effort": e,
        },
        "explanation": (
            f"100 * {n} (need) * {v} (value) * {c} (contact) * "
            f"{f} (fix) * {cf} (conf) / (1 + {e}) = {score}"
        ),
        "inputs_used": {
            "need": need,
            "business_value": business_value,
            "contactability": contactability,
            "fixability": fixability,
            "confidence": confidence,
            "effort": effort,
        },
    }


def opportunity_from_packet_evidence(
    report: dict, remediation: dict, quote: dict, contact: dict | None = None
) -> dict:
    """Derive a packet score from the same evidence-bound delivery artifacts.

    The technical health score remains a separate report field. Missing verified
    commercial evidence or contact provenance contributes zero, never a default
    positive value. Four distinct material findings saturate the need factor;
    quote hours are normalized against the quote engine's 60-hour XL ceiling,
    with larger combined quotes capped at the maximum effort factor.
    """
    defects = report.get("defects")
    if not isinstance(defects, list):
        raise ValueError("Audit report defects required for opportunity scoring")
    run_id = report.get("run_id")
    if not run_id or remediation.get("source_run_id") != run_id or quote.get("source_run_id") != run_id:
        raise ValueError("Opportunity evidence must bind to the same audit run")

    from .quote import EFFORT_HOURS
    from .remediation import CLASSES

    need_keys = set()
    confidence_values = []
    evidence_findings = []
    for finding in defects:
        if not isinstance(finding, dict) or not finding.get("finding_id"):
            continue
        if not (finding.get("observed") or finding.get("evidence_summary") or finding.get("evidence_ref")):
            continue
        evidence_findings.append(finding)
        key = str(finding.get("defect_key") or "").replace("_", "-")
        if key in NEED_KEYS:
            need_keys.add(key)
        confidence_values.append({"observed": 0.95, "derived": 0.8, "heuristic": 0.5}.get(
            finding.get("confidence"), 0.5
        ))
    need = min(len(need_keys) / 4.0, 1.0)

    commercial_score = report.get("commercial_score")
    commercial_ids = report.get("commercial_score_evidence_ids")
    if (
        isinstance(commercial_score, bool)
        or not isinstance(commercial_score, (int, float))
        or not math.isfinite(float(commercial_score))
        or not 0 <= commercial_score <= 100
        or not isinstance(commercial_ids, list)
        or not commercial_ids
        or any(
            not isinstance(item, (str, int)) or not str(item).strip()
            for item in commercial_ids
        )
    ):
        business_value = 0.0
        commercial_ids = []
    else:
        business_value = float(commercial_score) / 100.0

    selected = (contact or {}).get("selected") or {}
    label = selected.get("confidence_label") or (contact or {}).get("verification") or "NO_VERIFIED_EMAIL"
    contactability = CERTAINTY_MAP.get(label, 0.0)
    remediation_items = remediation.get("items")
    if not isinstance(remediation_items, list):
        raise ValueError("Remediation items required for opportunity scoring")
    remediation_weights = {
        "AUTO_SAFE": 1.0,
        "AUTO_PREVIEW": 0.85,
        "HUMAN_REVIEW": 0.6,
        "CLIENT_ACCESS_REQUIRED": 0.25,
        "UNSUPPORTED": 0.0,
    }
    evidence_finding_ids = {str(item["finding_id"]) for item in evidence_findings}
    classes = [
        item.get("classification") for item in remediation_items
        if str(item.get("finding_id")) in evidence_finding_ids
    ]
    if any(name not in CLASSES for name in classes):
        raise ValueError("Invalid remediation class in opportunity evidence")
    fixability = sum(remediation_weights[name] for name in classes) / len(classes) if classes else 0.0

    bands = [finding.get("effort_band") for finding in evidence_findings]
    if any(band not in EFFORT_HOURS for band in bands):
        raise ValueError("Invalid effort band in opportunity evidence")
    hours = quote.get("estimated_hours", {}).get("high")
    try:
        effort_hours = float(hours)
    except (TypeError, ValueError):
        raise ValueError("Quote high effort estimate required for opportunity scoring") from None
    if not math.isfinite(effort_hours) or effort_hours < 0:
        raise ValueError("Quote effort estimate must be finite and non-negative")
    effort = min(effort_hours / 60.0, 1.0)

    finding_confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
    confidence = min(finding_confidence, contactability)
    result = opportunity_formula(
        need=need,
        business_value=business_value,
        contactability=contactability,
        fixability=fixability,
        confidence=confidence,
        effort=effort,
    )
    result["provenance"] = {
        "audit_run_id": run_id,
        "finding_ids": [str(f["finding_id"]) for f in evidence_findings],
        "commercial_score": commercial_score if business_value else 0,
        "commercial_score_evidence_ids": commercial_ids,
        "contact_confidence_label": label,
        "remediation_classes": classes,
        "quote_rules_version": quote.get("rules_version"),
        "effort_hours_high": effort_hours,
        "mapping_version": "packet-opportunity-evidence-v1",
    }
    return result

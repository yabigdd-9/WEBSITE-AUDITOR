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
    "STRONG_EVIDENCE": 0.8,
    "CANDIDATE": 0.5,
    "CATCH_ALL": 0.3,
    "UNVERIFIED": 0.2,
    "NO_VERIFIED_EMAIL": 0.0,
    "INVALID": 0.0,
}

# Strict input envelopes: fail closed rather than filling unknowns with flattering
# defaults. All opportunity inputs are 0..1 unless otherwise noted.


def _clamp01(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"opportunity input must be numeric, got {value!r}")
    if not 0.0 <= number <= 1.0:
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


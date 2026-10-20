"""Candidate P9 product formula; pure calculation, with no CRM or network access.

The five numerator factors are explicitly normalised human-review inputs, not
conversion probabilities. Delivery effort is hours. The result is an index per
hour, not a 0-100 score, price, shortlist decision or permission to contact.
"""

import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation, localcontext

VERSION = "master-plan-p9-product-v1"
NUMERATOR = ("need", "business_value", "contactability", "fixability", "confidence")
FACTORS = (*NUMERATOR, "delivery_effort")
FACTOR_FIELDS = {"value", "basis", "source_ref", "source_sha256"}
DOCUMENT_FIELDS = {"schema_version", "algorithm_version", "as_of", "factors"}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(name + " requires an explicit number or decimal string")
    token = str(value)
    if len(token) > 32:
        raise ValueError(name + " number is too long")
    try:
        number = Decimal(token)
    except InvalidOperation as error:
        raise ValueError(name + " is not a decimal number") from error
    if not number.is_finite():
        raise ValueError(name + " must be finite")
    if number.as_tuple().exponent < -18 or len(number.as_tuple().digits) > 18:
        raise ValueError(name + " supports at most 18 decimal digits")
    low, high = (Decimal("0.01"), Decimal("10000")) if name == "delivery_effort" else (Decimal(0), Decimal(1))
    if not low <= number <= high:
        raise ValueError(name + " outside the declared input range")
    return number


def score_opportunity(document):
    """Calculate from a complete, versioned snapshot; explicit unknowns hold it.

    Provenance references are preserved and syntactically checked, not attested.
    A caller must separately verify referenced captures and review assessments.
    No factor is inferred from an email, defect count, current clock or price.
    """
    if not isinstance(document, dict) or set(document) != DOCUMENT_FIELDS:
        raise ValueError("Exact versioned input snapshot fields required")
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise ValueError("Input schema version 1 required")
    if document["algorithm_version"] != VERSION:
        raise ValueError("Unknown algorithm version; historical formulas are separate")
    as_of = document["as_of"]
    if not isinstance(as_of, str) or len(as_of) > 40:
        raise ValueError("Explicit bounded as_of timestamp required")
    try:
        timestamp = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Valid as_of timestamp required") from error
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("as_of must include its timezone")
    factors = document["factors"]
    if not isinstance(factors, dict) or set(factors) != set(FACTORS):
        raise ValueError("All six factors required; represent unknowns explicitly")
    values, unknown, assumptions = {}, [], []
    for name in FACTORS:
        factor = factors[name]
        if not isinstance(factor, dict) or set(factor) != FACTOR_FIELDS:
            raise ValueError(name + " requires value, basis and provenance fields")
        if factor["value"] is None:
            if factor["basis"] != "unknown" or factor["source_ref"] is not None or factor["source_sha256"] is not None:
                raise ValueError(name + " unknown value requires unknown basis and null provenance")
            unknown.append(name)
            continue
        if factor["basis"] not in ("observed_fact", "human_assumption"):
            raise ValueError(name + " requires observed_fact or human_assumption basis")
        reference = factor["source_ref"]
        digest = factor["source_sha256"]
        if not isinstance(reference, str) or not reference.strip() or len(reference) > 512 or any(ord(c) < 32 for c in reference):
            raise ValueError(name + " requires a bounded provenance reference")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError(name + " requires the referenced source SHA-256")
        values[name] = _number(factor["value"], name)
        if factor["basis"] == "human_assumption":
            assumptions.append(name)
    input_hash = hashlib.sha256(_canonical(document).encode()).hexdigest()
    index = None
    if not unknown:
        with localcontext() as context:
            context.prec = 50
            product = Decimal(1)
            for name in NUMERATOR:
                product *= values[name]
            index = format((product / values["delivery_effort"]).quantize(Decimal("0.000000000001")), "f")
    return {
        "schema_version": 1,
        "algorithm_version": VERSION,
        "input_sha256": input_hash,
        "as_of": as_of,
        "formula": "need * business_value * contactability * fixability * confidence / delivery_effort",
        "priority_index_per_hour": index,
        "status": "HELD_MISSING_INPUTS" if unknown else "CALCULATED_REQUIRES_REVIEW",
        "unknown_factors": unknown,
        "assumption_factors": assumptions,
        "provisional": bool(assumptions or unknown),
        "provenance_verified": False,
        "shortlist_decision": None,
        "approval_granted": False,
        "external_send_performed": False,
        "crm_state_changed": False,
    }


def replay(input_snapshot, receipt):
    """Replay the whole receipt from stored inputs; tampering is a mismatch."""
    if not isinstance(receipt, dict):
        raise ValueError("Stored calculation receipt required")
    computed = score_opportunity(input_snapshot)
    return {"match": _canonical(computed) == _canonical(receipt), "computed": computed}

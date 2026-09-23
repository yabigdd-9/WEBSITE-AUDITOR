"""Phone number normalization and comparison using E.164.

Uses the phonenumbers library (Google libphonenumber port) for parsing,
validation, and canonical formatting. Formatting differences alone never
become contradictions.
"""

from __future__ import annotations

import phonenumbers

from .schema import ConsistencyStatus, NormalizedPhone

# ---------------------------------------------------------------------------
# Phone normalization
# ---------------------------------------------------------------------------

_DEFAULT_REGIONS = ["NZ", "AU", "US", "GB"]


def normalize_phone(
    raw: str,
    default_region: str = "NZ",
    source: str = "",
) -> NormalizedPhone:
    """Parse and normalizeize a phone number to E.164.

    Returns a NormalizedPhone with parsed details.
    """
    if not raw or not raw.strip():
        return NormalizedPhone(raw=raw, source=source)

    cleaned = raw.strip()

    try:
        parsed = phonenumbers.parse(cleaned, default_region)
        is_valid = phonenumbers.is_valid_number(parsed)
        is_possible = phonenumbers.is_possible_number(parsed)
        e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        region = phonenumbers.region_code_for_number(parsed)
        phone_type = _type_name(phonenumbers.number_type(parsed))
    except phonenumbers.NumberParseException:
        return NormalizedPhone(
            raw=cleaned,
            e164="",
            region=default_region,
            possible=False,
            valid=False,
            source=source,
        )

    return NormalizedPhone(
        raw=cleaned,
        e164=e164 if is_valid else "",
        region=region or default_region,
        possible=is_possible,
        valid=is_valid,
        phone_type=phone_type,
        source=source,
    )


def _type_name(num_type: int) -> str:
    """Convert phonenumbers type code to human-readable name."""
    type_map = {
        phonenumbers.PhoneNumberType.FIXED_LINE: "fixed_line",
        phonenumbers.PhoneNumberType.MOBILE: "mobile",
        phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE: "fixed_line_or_mobile",
        phonenumbers.PhoneNumberType.TOLL_FREE: "toll_free",
        phonenumbers.PhoneNumberType.PREMIUM_RATE: "premium_rate",
        phonenumbers.PhoneNumberType.SHARED_COST: "shared_cost",
        phonenumbers.PhoneNumberType.VOIP: "voip",
        phonenumbers.PhoneNumberType.PERSONAL_NUMBER: "personal_number",
        phonenumbers.PhoneNumberType.PAGER: "pager",
        phonenumbers.PhoneNumberType.UAN: "uan",
        phonenumbers.PhoneNumberType.VOICEMAIL: "voicemail",
        phonenumbers.PhoneNumberType.UNKNOWN: "unknown",
    }
    return type_map.get(num_type, "unknown")


# ---------------------------------------------------------------------------
# Phone comparison
# ---------------------------------------------------------------------------


def compare_phones(a: NormalizedPhone, b: NormalizedPhone) -> ConsistencyStatus:
    """Compare two normalized phone numbers.

    Formatting differences (e.g., E.164 vs national format) are equivalent.
    Different digits = contradiction.
    """
    if _missing_phone_evidence(a) or _missing_phone_evidence(b):
        return "INSUFFICIENT_EVIDENCE"

    if a.e164 and b.e164:
        return "MATCH" if a.e164 == b.e164 else "CONTRADICTION"

    parsed_result = _compare_phone_with_one_e164(a, b)
    if parsed_result is not None:
        return parsed_result

    return "EQUIVALENT_FORMAT" if _raw_equivalent(a.raw, b.raw) else "CONTRADICTION"


def _missing_phone_evidence(phone: NormalizedPhone) -> bool:
    return not phone.raw and not phone.e164


def _compare_phone_with_one_e164(
    a: NormalizedPhone, b: NormalizedPhone
) -> ConsistencyStatus | None:
    e164 = a.e164 or b.e164
    raw_side = b if a.e164 else a
    if not e164 or not raw_side.raw:
        return None
    return _compare_raw_to_e164(e164, raw_side.raw, raw_side.region or "NZ")


def _compare_raw_to_e164(e164: str, raw: str, region: str) -> ConsistencyStatus | None:
    try:
        parsed = phonenumbers.parse(raw, region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    formatted = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    return "EQUIVALENT_FORMAT" if formatted == e164 else "CONTRADICTION"


def _raw_equivalent(a_raw: str, b_raw: str) -> bool:
    """Check if two raw phone strings are formatting-only variants."""
    # Strip non-digits and compare
    a_digits = "".join(c for c in a_raw if c.isdigit())
    b_digits = "".join(c for c in b_raw if c.isdigit())

    if not a_digits or not b_digits:
        return False

    # Same digit sequence (allowing for country code prefix differences)
    if a_digits == b_digits:
        return True

    # One might have country code prefix (e.g., 0064 vs +64 vs 0)
    # Strip common NZ leading zero vs country code
    if len(a_digits) == len(b_digits) + 2 and a_digits.startswith("64"):
        # a has country code, b might be local
        return a_digits[2:] == b_digits
    if len(b_digits) == len(a_digits) + 2 and b_digits.startswith("64"):
        return b_digits[2:] == a_digits

    # Handle NZ 0-prefixed vs country code
    if a_digits.startswith("0") and b_digits.startswith("64"):
        return a_digits[1:] == b_digits[2:]
    if b_digits.startswith("0") and a_digits.startswith("64"):
        return b_digits[1:] == a_digits[2:]

    return False

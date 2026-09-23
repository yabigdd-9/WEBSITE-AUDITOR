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
    if not a.raw and not a.e164:
        return "INSUFFICIENT_EVIDENCE"
    if not b.raw and not b.e164:
        return "INSUFFICIENT_EVIDENCE"

    # Both have E.164 — compare canonical form
    if a.e164 and b.e164:
        if a.e164 == b.e164:
            return "MATCH"
        # Different E.164 = material difference
        return "CONTRADICTION"

    # One has E.164, other doesn't — try to compare raw
    if a.e164 or b.e164:
        # Try parsing the one without E.164
        if a.e164 and b.raw:
            try:
                parsed = phonenumbers.parse(b.raw, b.region or "NZ")
                if phonenumbers.is_valid_number(parsed):
                    e164 = phonenumbers.format_number(
                        parsed, phonenumbers.PhoneNumberFormat.E164
                    )
                    if e164 == a.e164:
                        return "EQUIVALENT_FORMAT"
                    return "CONTRADICTION"
            except phonenumbers.NumberParseException:
                pass

    # Neither has E.164 — compare raw
    if _raw_equivalent(a.raw, b.raw):
        return "EQUIVALENT_FORMAT"

    return "CONTRADICTION"


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

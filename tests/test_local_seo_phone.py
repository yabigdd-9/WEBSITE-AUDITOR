"""Tests for phone normalization and comparison."""

from auditor_toolkit.local_seo.phone import compare_phones, normalize_phone
from auditor_toolkit.local_seo.schema import NormalizedPhone


# Use valid NZ phone number formats
_VALID_NZ_LANDLINE = "+64 3 379 5555"
_VALID_NZ_LOCAL = "03 379 5555"
_VALID_NZ_INTL_PREFIX = "0064 3 379 5555"
_VALID_NZ_MOBILE = "021 123 4567"
_VALID_NZ_LANDLINE_OTHER = "+64 3 380 1234"


def test_normalize_phone_nz_local():
    phone = normalize_phone(_VALID_NZ_LOCAL)
    assert phone.valid
    assert phone.e164 == "+6433795555"


def test_normalize_phone_e164():
    phone = normalize_phone(_VALID_NZ_LANDLINE)
    assert phone.valid
    assert phone.e164 == "+6433795555"


def test_normalize_phone_international_prefix():
    phone = normalize_phone(_VALID_NZ_INTL_PREFIX)
    assert phone.valid
    assert phone.e164 == "+6433795555"


def test_normalize_phone_mobile():
    phone = normalize_phone(_VALID_NZ_MOBILE)
    assert phone.valid
    assert phone.phone_type == "mobile"


def test_normalize_phone_invalid():
    phone = normalize_phone("12345")
    assert not phone.valid
    assert not phone.e164


def test_normalize_phone_empty():
    phone = normalize_phone("")
    assert not phone.raw
    assert not phone.valid


def test_compare_phones_match():
    a = normalize_phone(_VALID_NZ_LANDLINE)
    b = normalize_phone(_VALID_NZ_LANDLINE)
    status = compare_phones(a, b)
    assert status == "MATCH"


def test_compare_phones_equivalent_format():
    a = normalize_phone(_VALID_NZ_LANDLINE)
    b = normalize_phone(_VALID_NZ_LOCAL)
    status = compare_phones(a, b)
    assert status in ("MATCH", "EQUIVALENT_FORMAT")


def test_compare_phones_equivalent_international():
    a = normalize_phone(_VALID_NZ_LANDLINE)
    b = normalize_phone(_VALID_NZ_INTL_PREFIX)
    status = compare_phones(a, b)
    assert status in ("MATCH", "EQUIVALENT_FORMAT")


def test_compare_phones_contradiction():
    a = normalize_phone(_VALID_NZ_LANDLINE)
    b = normalize_phone(_VALID_NZ_LANDLINE_OTHER)
    status = compare_phones(a, b)
    assert status == "CONTRADICTION"


def test_compare_phones_insufficient():
    empty = NormalizedPhone()
    filled = normalize_phone(_VALID_NZ_LANDLINE)
    assert compare_phones(empty, filled) == "INSUFFICIENT_EVIDENCE"
    assert compare_phones(filled, empty) == "INSUFFICIENT_EVIDENCE"


def test_compare_phones_format_only():
    a = NormalizedPhone(raw="03-379-5555", source="page")
    b = NormalizedPhone(raw="03 379 5555", source="schema")
    status = compare_phones(a, b)
    assert status in ("MATCH", "EQUIVALENT_FORMAT")

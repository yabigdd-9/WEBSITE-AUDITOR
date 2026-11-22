"""Tests for address normalization and comparison."""

from auditor_toolkit.local_seo.address import (
    _clean,
    _split_address,
    compare_addresses,
    normalize_address,
)
from auditor_toolkit.local_seo.schema import NormalizedAddress


def test_clean_lowercase():
    assert _clean("HIGH Street") == "high street"


def test_clean_collapse_whitespace():
    assert _clean("High   Street") == "high street"


def test_split_address_nz():
    parts = _split_address("17 High St, Wellington 6011")
    assert parts.get("number") == "17"
    assert "high" in parts.get("street", "").lower()


def test_split_address_expands_suffix():
    parts = _split_address("17 High St")
    # Suffix expanded but case preserved from input
    assert "street" in parts.get("street", "").lower()


def test_normalize_address_full():
    addr = normalize_address("17 High St, Wellington 6011")
    assert addr.raw == "17 High St, Wellington 6011"
    assert addr.street_number == "17"
    assert "street" in addr.street_name.lower()
    assert "wellington" in addr.locality.lower()


def test_normalize_address_expansion():
    addr = normalize_address("10 Queen St, Auckland")
    assert "street" in addr.street_name.lower()
    assert "auckland" in addr.locality.lower()


def test_normalize_address_unit():
    addr = normalize_address("Unit 3, 17 High St, Wellington 6011")
    assert addr.unit == "3"


def test_normalize_address_empty():
    addr = normalize_address("")
    assert not addr.raw
    assert not addr.normalized


def test_normalize_address_17_vs_71():
    a1 = normalize_address("17 High Street, Wellington 6011")
    a2 = normalize_address("71 High Street, Wellington 6011")
    status = compare_addresses(a1, a2)
    assert status == "CONTRADICTION"


def test_normalize_address_equivalent():
    a1 = normalize_address("17 High St, Wellington 6011")
    a2 = normalize_address("17 High Street, Wellington 6011")
    status = compare_addresses(a1, a2)
    assert status in ("MATCH", "EQUIVALENT_FORMAT", "PROBABLE_MATCH")


def test_normalize_address_same():
    addr = normalize_address("17 High St, Wellington 6011")
    status = compare_addresses(addr, addr)
    assert status == "MATCH"


def test_compare_addresses_empty():
    empty = NormalizedAddress()
    addr = normalize_address("17 High St")
    assert compare_addresses(empty, addr) == "INSUFFICIENT_EVIDENCE"
    assert compare_addresses(addr, empty) == "INSUFFICIENT_EVIDENCE"


def test_compare_addresses_different_postal():
    a1 = normalize_address("17 High St, Wellington 6011")
    a2 = normalize_address("17 High St, Wellington 6022")
    assert compare_addresses(a1, a2) == "CONTRADICTION"


def test_compare_addresses_different_country():
    a1 = NormalizedAddress(
        street_number="17",
        street_name="high street",
        country="NZ",
        normalized="17, high street, NZ",
    )
    a2 = NormalizedAddress(
        street_number="17",
        street_name="high street",
        country="AU",
        normalized="17, high street, AU",
    )
    assert compare_addresses(a1, a2) == "CONTRADICTION"

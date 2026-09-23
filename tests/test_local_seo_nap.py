"""Tests for NAP (Name, Address, Phone) normalization."""

from auditor_toolkit.local_seo.nap import (
    aggregate_names,
    collect_nap_from_page,
    compare_nap,
    names_equivalent,
    normalize_name,
)
from auditor_toolkit.local_seo.schema import ConsistencyStatus


# --- Name normalization ---


def test_normalize_name_lowercase():
    assert normalize_name("ABC Plumbing") == "abc plumbing"


def test_normalize_name_strip():
    assert normalize_name("  ABC Plumbing  ") == "abc plumbing"


def test_normalize_name_whitespace():
    assert normalize_name("ABC   Plumbing") == "abc plumbing"


def test_normalize_name_ampersand():
    assert normalize_name("Smith & Sons") == "smith and sons"


def test_normalize_name_strip_punctuation():
    assert normalize_name("ABC Plumbing, Ltd.") == "abc plumbing ltd"


# --- Name equivalence ---


def test_names_exact_match():
    eq, status = names_equivalent("ABC Plumbing", "ABC Plumbing")
    assert eq
    assert status == "MATCH"


def test_names_case_equivalent():
    eq, status = names_equivalent("abc plumbing", "ABC Plumbing")
    assert eq
    assert status == "MATCH"


def test_names_ltd_limited_equivalent():
    eq, status = names_equivalent("ABC Plumbing Ltd", "ABC Plumbing Limited")
    assert eq
    assert status == "EQUIVALENT_FORMAT"


def test_names_amp_and_equivalent():
    eq, status = names_equivalent("Smith & Sons", "Smith and Sons")
    assert eq
    # Both normalize to same after & → and replacement
    assert status in ("MATCH", "EQUIVALENT_FORMAT")


def test_names_substring_probable():
    eq, status = names_equivalent("ABC Plumbing", "ABC")
    assert eq
    assert status == "PROBABLE_MATCH"


def test_names_different():
    eq, status = names_equivalent("ABC Plumbing", "XYZ Electrical")
    assert not eq
    assert status == "CONTRADICTION"


# --- Collect NAP ---


def test_collect_nap_from_page():
    result = collect_nap_from_page(
        name="ABC Plumbing",
        address_raw="17 High St, Wellington 6011",
        phone_raw="03 123 4567",
        source="contact_page",
    )
    assert result["name_raw"] == "ABC Plumbing"
    assert result["address"].raw == "17 High St, Wellington 6011"
    assert result["phone"].raw == "03 123 4567"


def test_collect_nap_empty():
    result = collect_nap_from_page()
    assert result["name_raw"] == ""
    assert not result["address"].raw
    assert not result["phone"].raw


# --- Compare NAP ---


def test_compare_nap_match():
    a = collect_nap_from_page(
        name="ABC Plumbing",
        address_raw="17 High Street, Wellington 6011",
        phone_raw="+64 3 379 5555",
        source="homepage",
    )
    b = collect_nap_from_page(
        name="ABC Plumbing Ltd",
        address_raw="17 High St, Wellington 6011",
        phone_raw="03 379 5555",
        source="contact",
    )
    result = compare_nap(a, b)
    assert result["name_equivalent"]
    assert not result["material_contradiction"]


def test_compare_nap_contradiction():
    a = collect_nap_from_page(
        name="ABC Plumbing",
        address_raw="17 High Street, Wellington 6011",
        phone_raw="+64 3 379 5555",
    )
    b = collect_nap_from_page(
        name="XYZ Electrical",
        address_raw="71 High Street, Wellington 6011",
        phone_raw="+64 3 380 1234",
    )
    result = compare_nap(a, b)
    assert not result["name_equivalent"]
    assert result["material_contradiction"]


# --- Aggregate names ---


def test_aggregate_names_dedup():
    names = [
        ("ABC Plumbing", "homepage"),
        ("ABC Plumbing", "contact"),
        ("abc plumbing", "schema"),
    ]
    result = aggregate_names(names)
    assert len(result) == 1  # All normalize to same


def test_aggregate_names_variants():
    names = [
        ("ABC Plumbing", "homepage"),
        ("ABC Plumbing Ltd", "schema"),
    ]
    result = aggregate_names(names)
    assert len(result) == 2  # Different canonical forms

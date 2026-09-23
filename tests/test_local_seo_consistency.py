"""Tests for local SEO consistency checking."""

from auditor_toolkit.local_seo.address import normalize_address
from auditor_toolkit.local_seo.consistency import (
    ConsistencyContradiction,
    check_nap_consistency,
    check_schema_visible_consistency,
)
from auditor_toolkit.local_seo.phone import normalize_phone


def test_contradiction_record():
    rec = ConsistencyContradiction(
        field="phone",
        status="CONTRADICTION",
        schema_value="+6433795555",
        visible_value="+6433801234",
        confidence=0.99,
    )
    assert rec.field == "phone"
    assert rec.is_contradiction


def test_check_nap_consistency_no_contradiction():
    results = check_nap_consistency(
        schema_name="ABC Plumbing",
        schema_address=normalize_address("17 High Street, Wellington 6011"),
        schema_phones=[normalize_phone("+6433795555")],
        visible_name="ABC Plumbing",
        visible_address=normalize_address("17 High St, Wellington 6011"),
        visible_phones=[normalize_phone("03 379 5555")],
    )
    assert not any(item.status == "CONTRADICTION" for item in results)


def test_check_nap_consistency_material_conflict():
    results = check_nap_consistency(
        schema_name="ABC Plumbing",
        schema_phones=[normalize_phone("+6433795555")],
        visible_name="XYZ Electrical",
        visible_phones=[normalize_phone("+6433801234")],
    )
    assert any(item.status == "CONTRADICTION" for item in results)


def test_check_schema_visible_consistency_alias():
    results = check_schema_visible_consistency(
        schema_name="ABC Plumbing Ltd",
        schema_phones=[normalize_phone("+6433795555")],
        visible_name="ABC Plumbing Limited",
        visible_phones=[normalize_phone("03 379 5555")],
    )
    assert not any(item.status == "CONTRADICTION" for item in results)

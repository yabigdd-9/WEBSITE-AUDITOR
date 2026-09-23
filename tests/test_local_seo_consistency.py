"""Tests for local SEO consistency checking."""

from auditor_toolkit.local_seo.consistency import (
    check_nap_consistency,
        ConsistencyContradiction,
)
from auditor_toolkit.local_seo.schema import ConsistencyStatus


def test_contradiction_record():
    rec = ConsistencyContradiction(
        field="phone",
        status="CONTRADICTION",
        schema_value="+6431234567",
        visible_value="+6439999999",
        confidence=0.99,
        rule_id="LOCAL.NAP.PHONE.CONTRADICTION",
    )
    assert rec.field == "phone"
    assert rec.status == "CONTRADICTION"


def test_check_nap_consistency_no_contradiction():
    nap_data = {
        "name": "ABC Plumbing",
        "address": "17 High St, Wellington 6011",
        "phone": "+6431234567",
    }
    schema_data = {
        "name": "ABC Plumbing",
        "address": "17 High Street, Wellington 6011",
        "phone": "+64 3 123 4567",
    }
    contradictions = check_nap_consistency(nap_data, schema_data)
    # Formatting differences should not become contradictions
    for c in contradictions:
        assert c.status != "CONTRADICTION"


def test_check_nap_consistency_material_conflict():
    nap_data = {
        "name": "ABC Plumbing",
        "phone": "+6431234567",
    }
    schema_data = {
        "name": "XYZ Electrical",
        "phone": "+6439999999",
    }
    contradictions = check_nap_consistency(nap_data, schema_data)
    assert len(contradictions) > 0


def test_check_schema_visible_consistency():
    schema = {"name": "ABC Plumbing", "telephone": "+6431234567"}
    visible = {"name": "ABC Plumbing Ltd", "telephone": "+64 3 123 4567"}
    result = check_schema_visible_consistency(schema, visible)
    # Formatting differences should not be contradictions
    for field_name, status in result.items():
        if field_name == "status":
            continue

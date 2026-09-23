"""Tests for business identity resolution."""

from auditor_toolkit.local_seo.identity import (
    IdentityFeatures,
    build_identity,
    merge_entities,
)
from auditor_toolkit.local_seo.schema import LocalBusinessEntity, NamedValue


def test_build_identity_minimal():
    entity = build_identity(business_id="biz_001")
    assert entity.business_id == "biz_001"
    assert entity.canonical_name == ""


def test_build_identity_with_names():
    entity = build_identity(
        business_id="biz_001",
        names=[
            ("ABC Plumbing", "homepage"),
            ("ABC Plumbing Ltd", "schema"),
        ],
    )
    # Canonical name is the longest (most complete) variant
    assert len(entity.names) == 2
    assert "ABC Plumbing" in entity.canonical_name


def test_build_identity_with_domain():
    entity = build_identity(
        business_id="biz_001",
        domain="abcplumbing.co.nz",
    )
    assert entity.canonical_domain == "abcplumbing.co.nz"
    assert "abcplumbing.co.nz" in entity.domains


def test_build_identity_with_emails():
    entity = build_identity(
        business_id="biz_001",
        emails=["info@abc.co.nz"],
    )
    assert "info@abc.co.nz" in entity.emails


def test_build_identity_with_phones():
    entity = build_identity(
        business_id="biz_001",
        phones=[("+6433795555", "contact_page")],
    )
    assert len(entity.phones) == 1
    assert entity.phones[0].e164 == "+6433795555"


def test_build_identity_with_addresses():
    entity = build_identity(
        business_id="biz_001",
        addresses=[("17 High St, Wellington 6011", "homepage")],
    )
    assert len(entity.locations) == 1
    assert entity.locations[0].address.raw == "17 High St, Wellington 6011"


def test_build_identity_confidence_increases():
    entity_minimal = build_identity(business_id="biz_001")
    entity_full = build_identity(
        business_id="biz_002",
        names=[("ABC Plumbing", "homepage")],
        addresses=[("17 High St, Wellington 6011", "homepage")],
        phones=[("+6433795555", "contact")],
        emails=["info@abc.co.nz"],
    )
    assert entity_full.confidence > entity_minimal.confidence


def test_merge_entities():
    a = build_identity(
        business_id="biz_a",
        names=[("ABC Plumbing", "homepage")],
        phones=[("+6433795555", "contact")],
        emails=["info@abc.co.nz"],
    )
    b = build_identity(
        business_id="biz_b",
        names=[("ABC Plumbing Ltd", "schema")],
        phones=[("+6433801234", "branch")],
        emails=["wellington@abc.co.nz"],
    )
    merged = merge_entities(a, b)
    assert len(merged.names) == 2
    assert len(merged.phones) == 2
    assert len(merged.emails) == 2


def test_merge_entities_dedup_phones():
    a = build_identity(
        business_id="biz_a",
        phones=[("+6433795555", "contact")],
    )
    b = build_identity(
        business_id="biz_b",
        phones=[("+6433795555", "schema")],
    )
    merged = merge_entities(a, b)
    assert len(merged.phones) == 1  # Deduplicated


def test_merge_entities_branch_no_merge():
    a = build_identity(business_id="biz_a", names=[("Parent Corp", "homepage")])
    b = build_identity(business_id="biz_b", names=[("Child Branch", "page")])
    merged = merge_entities(a, b, branch_relationship="parent")
    # Should not merge — parent/child kept separate
    assert len(merged.names) == 1
    assert b.parent_entity_id == "biz_a"


def test_identity_features():
    features = IdentityFeatures(
        name_source_count=3,
        address_source_count=2,
        phone_source_count=1,
        schema_visibility_match=True,
        contradiction_count=0,
        evidence_count=10,
    )
    assert features.name_source_count == 3
    assert features.schema_visibility_match

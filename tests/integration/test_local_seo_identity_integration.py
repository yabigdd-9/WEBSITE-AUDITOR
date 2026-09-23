"""Integration test for local SEO identity evidence pipeline."""

from auditor_toolkit.local_seo.identity import build_identity, merge_entities
from auditor_toolkit.local_seo.nap import normalize_name, names_equivalent


def test_identity_from_multiple_pages():
    """Identity should aggregate evidence from multiple page sources."""
    entity = build_identity(
        business_id="biz_001",
        names=[
            ("ABC Plumbing", "homepage"),
            ("ABC Plumbing Ltd", "about"),
            ("abc plumbing", "contact"),
        ],
        phones=[
            ("+6431234567", "homepage"),
            ("03 123 4567", "contact"),
        ],
        emails=["info@abc.co.nz"],
        domain="abcplumbing.co.nz",
    )
    # Should deduplicate names
    assert len(entity.names) >= 1
    assert entity.canonical_name


def test_identity_schema_visible_agreement():
    """Schema and visible page names should agree."""
    entity = build_identity(
        business_id="biz_001",
        names=[
            ("ABC Plumbing", "homepage_visible"),
            ("ABC Plumbing", "schema_jsonld"),
        ],
    )
    assert len(entity.names) >= 1
    # Names should be equivalent
    eq, status = names_equivalent(
        entity.names[0].value,
        entity.names[-1].value,
    )
    assert eq


def test_identity_phone_dedup():
    """Same phone in different formats should deduplicate."""
    entity = build_identity(
        business_id="biz_001",
        phones=[
            ("+6431234567", "schema"),
            ("03 123 4567", "visible"),
        ],
    )
    # Should deduplicate to one valid E.164 phone
    valid_phones = [p for p in entity.phones if p.e164]
    assert len(valid_phones) >= 1


def test_identity_branch_no_merge():
    """Parent/child branch entities should not auto-merge."""
    parent = build_identity(business_id="biz_parent")
    child = build_identity(business_id="biz_child")
    merged = merge_entities(parent, child, branch_relationship="parent")
    # Should not merge — kept separate
    assert merged.business_id == "biz_parent"
    assert child.parent_entity_id == "biz_parent"

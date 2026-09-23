"""Integration test for local SEO identity evidence pipeline."""

from auditor_toolkit.local_seo.identity import build_identity, merge_entities
from auditor_toolkit.local_seo.nap import names_equivalent


def test_identity_from_multiple_pages():
    entity = build_identity(
        business_id="biz_001",
        names=[
            ("ABC Plumbing", "homepage"),
            ("ABC Plumbing Ltd", "about"),
            ("abc plumbing", "contact"),
        ],
        phones=[
            ("+6433795555", "homepage"),
            ("03 379 5555", "contact"),
        ],
        emails=["info@abc.co.nz"],
        domain="abcplumbing.co.nz",
    )
    assert len(entity.names) >= 1
    assert entity.canonical_name


def test_identity_schema_visible_agreement():
    entity = build_identity(
        business_id="biz_001",
        names=[
            ("ABC Plumbing", "homepage_visible"),
            ("ABC Plumbing", "schema_jsonld"),
        ],
    )
    eq, _ = names_equivalent(entity.names[0].value, entity.names[-1].value)
    assert eq


def test_identity_phone_dedup():
    entity = build_identity(
        business_id="biz_001",
        phones=[
            ("+6433795555", "schema"),
            ("03 379 5555", "visible"),
        ],
    )
    valid_phones = [phone for phone in entity.phones if phone.e164]
    assert len(valid_phones) == 1
    assert valid_phones[0].e164 == "+6433795555"


def test_identity_branch_no_merge():
    parent = build_identity(business_id="biz_parent")
    child = build_identity(business_id="biz_child")
    merged = merge_entities(parent, child, branch_relationship="parent")
    assert merged.business_id == "biz_parent"
    assert child.parent_entity_id == "biz_parent"

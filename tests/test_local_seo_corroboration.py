"""Tests for external evidence corroboration."""

from auditor_toolkit.local_seo.corroboration import (
    create_external_evidence,
    ExternalLocalEvidence,
    corroborate_record,
)


def test_external_evidence_creation():
    ev = ExternalLocalEvidence(
        provider="nominatim",
        retrieved_at="2026-01-01T00:00:00Z",
        query="ABC Plumbing Wellington",
        name="ABC Plumbing",
        address="17 High St, Wellington",
        source_confidence=0.7,
    )
    assert ev.provider == "nominatim"


def test_corroboration_score_increases():
    from auditor_toolkit.local_seo.schema import LocalBusinessEntity

    entity = LocalBusinessEntity(
        business_id="biz_001",
        canonical_name="ABC Plumbing",
    )

    score_before = corroborate_record(entity)

    evidence = ExternalLocalEvidence(
        provider="nominatim",
        retrieved_at="2026-01-01",
        query="test",
        name="ABC Plumbing",
        source_confidence=0.7,
    )
    entity = create_external_evidence(entity, evidence)

    score_after = corroborate_record(entity)
    assert score_after >= score_before


def test_corroboration_no_overwrite():
    """External evidence should not overwrite canonical values."""
    from auditor_toolkit.local_seo.schema import LocalBusinessEntity

    entity = LocalBusinessEntity(
        business_id="biz_001",
        canonical_name="ABC Plumbing",
    )

    evidence = ExternalLocalEvidence(
        provider="osm",
        retrieved_at="2026-01-01",
        query="test",
        name="ABC Plumbing OSM Name",
        source_confidence=0.5,
    )
    entity = create_external_evidence(entity, evidence)

    # Canonical name should NOT be overwritten
    assert entity.canonical_name == "ABC Plumbing"

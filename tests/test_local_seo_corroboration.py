"""Tests for external evidence corroboration."""

from auditor_toolkit.local_seo.corroboration import (
    corroborate_record,
    create_external_evidence,
)
from auditor_toolkit.local_seo.schema import ExternalLocalEvidence, LocalBusinessEntity


def test_external_evidence_creation():
    evidence = create_external_evidence(
        provider="nominatim",
        query="ABC Plumbing Wellington",
        raw_artifact={"name": "ABC Plumbing"},
        name="ABC Plumbing",
        address="17 High St, Wellington",
        source_confidence=0.7,
    )
    assert isinstance(evidence, ExternalLocalEvidence)
    assert evidence.provider == "nominatim"
    assert evidence.evidence_id
    assert evidence.raw_artifact_hash


def test_corroboration_score_increases_with_matching_evidence():
    before = corroborate_record(canonical_name="ABC Plumbing")
    evidence = create_external_evidence(
        provider="nominatim",
        query="test",
        name="ABC Plumbing",
        source_confidence=0.7,
    )
    after = corroborate_record(
        canonical_name="ABC Plumbing",
        external_records=[evidence],
    )
    assert after.overall_confidence > before.overall_confidence
    assert len(after.matches) == 1


def test_corroboration_does_not_overwrite_canonical_values():
    entity = LocalBusinessEntity(
        business_id="biz_001",
        canonical_name="ABC Plumbing",
    )
    evidence = create_external_evidence(
        provider="osm",
        query="test",
        name="ABC Plumbing OSM Name",
        source_confidence=0.5,
    )
    corroborate_record(
        canonical_name=entity.canonical_name,
        external_records=[evidence],
    )
    assert entity.canonical_name == "ABC Plumbing"

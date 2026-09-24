"""Tests for local SEO schema data models."""

from auditor_toolkit.local_seo.schema import (
    BusinessLocation,
    ExternalLocalEvidence,
    GeoCoordinates,
    LocalBusinessEntity,
    NamedValue,
    NormalizedAddress,
    NormalizedPhone,
    OpeningHour,
)


def test_geo_coordinates_creation():
    geo = GeoCoordinates(latitude=-41.2865, longitude=174.7762)
    assert geo.latitude == -41.2865
    assert geo.longitude == 174.7762


def test_geo_haversine():
    a = GeoCoordinates(latitude=0.0, longitude=0.0)
    b = GeoCoordinates(latitude=0.0, longitude=1.0)
    distance = a.haversine_km(b)
    assert distance > 0
    assert distance < 200  # ~111 km at equator for 1 degree


def test_normalized_address():
    addr = NormalizedAddress(
        raw="17 High St, Wellington 6011",
        street_number="17",
        street_name="high street",
        locality="wellington",
        postal_code="6011",
        normalized="17, high street, wellington, 6011",
    )
    assert addr.raw == "17 High St, Wellington 6011"
    assert addr.signature()


def test_normalized_address_signature():
    a1 = NormalizedAddress(
        street_number="17",
        street_name="high street",
        locality="wellington",
        postal_code="6011",
    )
    a2 = NormalizedAddress(
        street_number="17",
        street_name="high street",
        locality="wellington",
        postal_code="6011",
        unit="3",
    )
    # Signature excludes unit
    assert a1.signature() == a2.signature()


def test_normalized_phone():
    phone = NormalizedPhone(
        raw="03 123 4567",
        e164="+6431234567",
        region="NZ",
        possible=True,
        valid=True,
        phone_type="fixed_line",
        source="contact_page",
    )
    assert phone.e164 == "+6431234567"
    assert phone.valid


def test_opening_hour():
    hour = OpeningHour(
        day="Monday",
        opens="09:00",
        closes="17:00",
        source="contact_page",
    )
    assert hour.day == "Monday"
    assert not hour.closed
    assert not hour.overnight


def test_opening_hour_closed():
    hour = OpeningHour(day="Sunday", closed=True, source="schema")
    assert hour.closed
    assert not hour.opens


def test_opening_hour_special():
    hour = OpeningHour(
        day="Monday",
        special_text="By appointment",
        source="visible",
    )
    assert hour.special_text == "By appointment"


def test_named_value():
    nv = NamedValue(value="ABC Plumbing", source="homepage", confidence=0.95)
    assert nv.value == "ABC Plumbing"


def test_business_location():
    loc = BusinessLocation(
        location_id="loc_001",
        business_id="biz_001",
        name="ABC Plumbing Wellington",
    )
    assert loc.location_id == "loc_001"
    assert loc.business_id == "biz_001"


def test_business_location_to_dict():
    loc = BusinessLocation(
        location_id="loc_001",
        business_id="biz_001",
        name="Test",
    )
    d = loc.to_dict()
    assert d["location_id"] == "loc_001"


def test_local_business_entity():
    entity = LocalBusinessEntity(
        business_id="biz_001",
        canonical_name="ABC Plumbing",
        canonical_domain="abcplumbing.co.nz",
    )
    assert entity.business_id == "biz_001"
    assert entity.confidence == 0.0


def test_local_business_entity_to_dict():
    entity = LocalBusinessEntity(
        business_id="biz_001",
        canonical_name="Test",
    )
    d = entity.to_dict()
    assert d["business_id"] == "biz_001"


def test_external_local_evidence():
    ev = ExternalLocalEvidence(
        provider="nominatim",
        retrieved_at="2026-01-01T00:00:00Z",
        query="ABC Plumbing Wellington",
        source_confidence=0.7,
    )
    assert ev.provider == "nominatim"


def test_external_local_evidence_to_dict():
    ev = ExternalLocalEvidence(
        provider="osm",
        retrieved_at="2026-01-01",
        query="test",
    )
    d = ev.to_dict()
    assert d["provider"] == "osm"

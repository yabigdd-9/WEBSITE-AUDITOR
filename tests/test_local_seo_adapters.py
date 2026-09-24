"""Offline tests for optional public geocoding and OSM adapters."""

from types import SimpleNamespace

import httpx
import pytest

from auditor_toolkit.local_seo.adapters import nominatim, overpass
from auditor_toolkit.local_seo.schema import NormalizedAddress


@pytest.fixture
def address():
    return NormalizedAddress(
        raw="17 High Street, Wellington 6011",
        street_number="17",
        street_name="High Street",
        locality="Wellington",
        postal_code="6011",
        country="New Zealand",
        normalized="17 high street, wellington, 6011",
    )


def test_nominatim_is_disabled_by_default(address):
    assert nominatim.geocode(address) is None


def test_nominatim_requires_descriptive_user_agent(address):
    with pytest.raises(ValueError, match="descriptive User-Agent"):
        nominatim.geocode(address, user_agent="bad", enable_nominatim=True)


def test_nominatim_parses_and_caches_successful_result(monkeypatch, address):
    nominatim._cache.clear()
    monkeypatch.setattr(nominatim, "_respect_rate_limit", lambda: None)
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: [{
                "lat": "-41.2865",
                "lon": "174.7762",
                "display_name": "17 High Street, Wellington",
                "place_id": 123,
                "osm_type": "way",
                "osm_id": 456,
                "type": "house",
                "importance": 0.8,
            }],
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    first = nominatim.geocode(address, enable_nominatim=True)
    second = nominatim.geocode(address, enable_nominatim=True)

    assert first is second
    assert first is not None
    assert first.geo.latitude == pytest.approx(-41.2865)
    assert first.confidence == 1.0
    assert len(calls) == 1
    assert calls[0][1]["headers"]["User-Agent"] == "WEBSITE-AUDITOR/1.0"
    nominatim._cache.clear()


def test_nominatim_caches_empty_search_and_handles_http_errors(monkeypatch, address):
    nominatim._cache.clear()
    monkeypatch.setattr(nominatim, "_respect_rate_limit", lambda: None)
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *_args, **_kwargs: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: [],
        ),
    )
    empty = nominatim.geocode(address, enable_nominatim=True)
    assert empty is not None and empty.confidence == 0.0
    assert nominatim.geocode(address, enable_nominatim=True) is empty

    nominatim._cache.clear()
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(httpx.TimeoutException("timeout")),
    )
    assert nominatim.geocode(address, enable_nominatim=True) is None
    nominatim._cache.clear()


def test_nominatim_query_confidence_and_batch(monkeypatch, address):
    assert nominatim._build_query(address) == "17 High Street, Wellington, 6011, New Zealand"
    assert nominatim._compute_confidence({"type": "street"}) == 0.8
    assert nominatim._compute_confidence({"type": "city", "importance": 0.8}) == 0.4
    assert nominatim._build_query(NormalizedAddress(raw="Raw address")) == "Raw address"

    result = nominatim.GeocodeResult(address="Wellington")
    monkeypatch.setattr(nominatim, "geocode", lambda *_args, **_kwargs: result)
    batch = nominatim.geocode_batch([address], enable_nominatim=True)
    assert batch[address.signature()] is result


def test_overpass_builds_queries_and_parses_business_details(address):
    nearby_query = overpass._build_localbusiness_query(-41.2, 174.7, business_type="cafe")
    assert '"amenity"="cafe"' in nearby_query
    assert "around:1000.0,-41.2,174.7" in nearby_query
    assert "" == overpass._build_address_query()
    assert "addr:postcode" in overpass._build_address_query(postcode="6011")

    nodes = overpass._parse_elements({
        "elements": [
            {
                "type": "node",
                "id": 1,
                "lat": -41.2,
                "lon": 174.7,
                "tags": {
                    "name": "Cafe",
                    "shop": "coffee",
                    "phone": "123",
                    "addr:housenumber": "17",
                    "addr:street": "High Street",
                    "addr:city": "Wellington",
                },
            },
            {
                "type": "way",
                "id": 2,
                "center": {"lat": -41.3, "lon": 174.8},
                "tags": {"name": "Bakery", "amenity": "cafe"},
            },
        ]
    })
    assert nodes[1].lat == -41.3
    info = overpass.osm_to_business_info(nodes[0])
    assert info["name"] == "Cafe"
    assert info["phone"] == "123"
    assert info["address"] == "17, High Street, Wellington"
    assert info["categories"] == ["shop:coffee"]
    assert info["geo"].latitude == -41.2


@pytest.mark.parametrize("payload", [None, "invalid", {"elements": None}, {"elements": [None]}])
def test_overpass_ignores_malformed_payload_entries(payload):
    assert overpass._parse_elements(payload if isinstance(payload, dict) else {}) == []


def test_overpass_public_queries_are_mockable_and_fail_closed(monkeypatch, address):
    monkeypatch.setattr(overpass, "_respect_rate_limit", lambda: None)
    response_data = {"elements": [{"type": "node", "id": 4, "tags": {"name": "Shop"}}]}
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *_args, **_kwargs: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: response_data,
        ),
    )
    result = overpass.find_nearby_businesses(-41.2, 174.7)
    assert result.elements[0].name == "Shop"
    assert result.raw_response is response_data

    monkeypatch.setattr(
        httpx,
        "post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(httpx.TimeoutException("timeout")),
    )
    failed = overpass.find_by_address(address)
    assert "timeout" in failed.error
    assert not failed.elements

"""Tests for local SEO geographic corroboration."""

from auditor_toolkit.local_seo.geo import (
    haversine_distance,
    GeoStatus,
    corroborate_geo,
)
from auditor_toolkit.local_seo.schema import GeoCoordinates


def test_haversine_distance():
    a = GeoCoordinates(latitude=0.0, longitude=0.0)
    b = GeoCoordinates(latitude=0.0, longitude=0.0)
    distance = haversine_distance(a, b)
    assert distance == 0.0


def test_haversine_nonzero():
    a = GeoCoordinates(latitude=0.0, longitude=0.0)
    b = GeoCoordinates(latitude=1.0, longitude=0.0)
    distance = haversine_distance(a, b)
    assert distance > 100  # > 100 km


def test_compare_geo_consistent():
    a = GeoCoordinates(latitude=-41.2865, longitude=174.7762)
    b = GeoCoordinates(latitude=-41.2870, longitude=174.7770)
    status = corroborate_geo(a, b)
    assert status == "CONSISTENT"


def test_compare_geo_nearby():
    a = GeoCoordinates(latitude=-41.2865, longitude=174.7762)
    b = GeoCoordinates(latitude=-41.2900, longitude=174.7800)
    status = corroborate_geo(a, b)
    assert status in ("CONSISTENT", "NEARBY")


def test_compare_geo_material_conflict():
    a = GeoCoordinates(latitude=-41.2865, longitude=174.7762)
    b = GeoCoordinates(latitude=-36.8485, longitude=174.7633)  # Auckland
    status = corroborate_geo(a, b)
    assert status == "MATERIAL_CONFLICT"


def test_haversine_distance():
    a = GeoCoordinates(latitude=0.0, longitude=0.0)
    b = GeoCoordinates(latitude=0.0, longitude=1.0)
    km = haversine_distance(a, b)
    assert 100 < km < 120  # ~111 km at equator

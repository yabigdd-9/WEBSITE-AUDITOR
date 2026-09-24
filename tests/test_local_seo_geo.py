"""Tests for local SEO geographic corroboration."""

from auditor_toolkit.local_seo.geo import corroborate_geo, haversine_distance
from auditor_toolkit.local_seo.schema import GeoCoordinates


def test_haversine_zero_distance():
    a = GeoCoordinates(latitude=0.0, longitude=0.0)
    assert haversine_distance(a, a) == 0.0


def test_haversine_nonzero():
    a = GeoCoordinates(latitude=0.0, longitude=0.0)
    b = GeoCoordinates(latitude=1.0, longitude=0.0)
    assert haversine_distance(a, b) > 100


def test_compare_geo_consistent():
    a = GeoCoordinates(latitude=-41.2865, longitude=174.7762)
    b = GeoCoordinates(latitude=-41.2870, longitude=174.7770)
    assert corroborate_geo(a, b).status == "CONSISTENT"


def test_compare_geo_nearby():
    a = GeoCoordinates(latitude=-41.2865, longitude=174.7762)
    b = GeoCoordinates(latitude=-41.2900, longitude=174.7800)
    assert corroborate_geo(a, b).status in ("CONSISTENT", "NEARBY")


def test_compare_geo_material_conflict():
    a = GeoCoordinates(latitude=-41.2865, longitude=174.7762)
    b = GeoCoordinates(latitude=-36.8485, longitude=174.7633)
    assert corroborate_geo(a, b).status == "MATERIAL_CONFLICT"


def test_haversine_one_degree_longitude():
    a = GeoCoordinates(latitude=0.0, longitude=0.0)
    b = GeoCoordinates(latitude=0.0, longitude=1.0)
    km = haversine_distance(a, b)
    assert 100 < km < 120

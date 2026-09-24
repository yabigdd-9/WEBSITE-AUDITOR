"""Tests for service-area business classification."""

from auditor_toolkit.local_seo.service_area import (
    classify_business_type,
    classify_service_area,
    should_flag_missing_address,
)


def test_classify_service_area():
    analysis = classify_business_type(
        has_address=False,
        has_service_area_schema=True,
        areas_served=["Wellington", "Auckland"],
    )
    assert analysis.is_service_area
    assert not analysis.is_physical


def test_classify_physical_location():
    analysis = classify_business_type(
        has_address=True,
        has_service_area_schema=False,
        areas_served=[],
    )
    assert not analysis.is_service_area


def test_classify_hybrid():
    analysis = classify_business_type(
        has_address=True,
        has_service_area_schema=True,
        areas_served=["Wellington"],
    )
    assert analysis.classification == "HYBRID"
    assert not analysis.is_service_area


def test_service_area_missing_address_is_not_auto_defect():
    analysis = classify_business_type(
        has_address=False,
        has_service_area_schema=True,
        areas_served=["Wellington"],
    )
    assert not should_flag_missing_address(analysis)
    assert not analysis.requires_address


def test_physical_business_missing_address_can_be_flagged():
    analysis = classify_service_area(
        has_address=False,
        page_text="Visit us at our office for an appointment.",
    )
    assert analysis.classification == "PHYSICAL_LOCATION"
    assert should_flag_missing_address(analysis)


def test_unknown_business_is_fail_closed():
    analysis = classify_business_type(
        has_address=False,
        has_service_area_schema=False,
        areas_served=[],
    )
    assert analysis.classification == "UNKNOWN"
    assert not should_flag_missing_address(analysis)


def test_legacy_boolean_wrapper_preserves_service_area_safety():
    assert not should_flag_missing_address(
        has_address=False,
        has_area_served=True,
    )

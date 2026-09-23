"""Tests for service-area business classification."""

from auditor_toolkit.local_seo.service_area import (
    classify_service_area,
    should_flag_missing_address,
    ServiceAreaClassification,
)
# ServiceAreaClassification imported from service_area module


def test_classify_service_area():
    classification = classify_service_area(
        has_address=False,
        has_service_area_schema=True,
        areas_served=["Wellington", "Auckland"],
    )
    assert classification.is_service_area == True
    assert not classification.is_physical


def test_classify_physical_location():
    classification = classify_service_area(
        has_address=True,
        has_service_area_schema=False,
        areas_served=[],
    )
    assert classification.is_service_area == False


def test_classify_hybrid():
    classification = classify_service_area(
        has_address=True,
        has_service_area_schema=True,
        areas_served=["Wellington"],
    )
    assert classification.is_service_area == False


def test_should_flag_missing_address_true():
    assert should_flag_missing_address(
        has_address=False,
        has_area_served=True,
    )


def test_should_flag_missing_address_false_with_address():
    assert not should_flag_missing_address(
        has_address=True,
        has_area_served=False,
    )


def test_service_area_no_auto_defect():
    """Service-area businesses legitimately hide addresses."""
    classification = classify_service_area(
        has_address=False,
        has_service_area_schema=True,
        areas_served=["Wellington"],
    )
    assert not classification.requires_address


def test_classify_unknown():
    classification = classify_service_area(
        has_address=False,
        has_service_area_schema=False,
        areas_served=[],
    )
    assert classification.is_service_area == False

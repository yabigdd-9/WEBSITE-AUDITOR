"""Regression tests for business category extraction and comparison."""

from auditor_toolkit.local_seo.categories import (
    BusinessCategory,
    compare_categories,
    extract_categories_from_schema,
    extract_categories_from_text,
    normalize_category,
)


def test_normalize_category_alias_and_prefix():
    assert normalize_category("We are a plumber") == "Plumber"
    assert normalize_category("property management") == "Real Estate Agency"


def test_extract_schema_categories_skips_generic_types_from_type_list():
    categories = extract_categories_from_schema(
        {"@type": ["LocalBusiness", "Dentist"], "additionalType": "Dental clinic"}
    )
    assert [category.normalized for category in categories] == ["Dentist", "Dentist"]


def test_extract_text_categories_deduplicates_aliases():
    categories = extract_categories_from_text("Our dentist is a dental clinic")
    assert [category.normalized for category in categories] == ["Dentist"]


def test_compare_categories_flags_only_single_schema_conflict():
    schema = [BusinessCategory(raw="dentist", normalized="Dentist", source="schema")]
    page = [BusinessCategory(raw="plumber", normalized="Plumber", source="visible")]
    result = compare_categories(schema, page)
    assert result.primary_category == "Dentist"
    assert len(result.conflicts) == 1

    multiple_schema = schema + [
        BusinessCategory(raw="clinic", normalized="Clinic", source="schema")
    ]
    assert compare_categories(multiple_schema, page).conflicts == []

"""Extract and normalize business categories from schema and page content.

Categories help distinguish business types and detect cross-listing
inconsistencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_REAL_ESTATE_AGENCY = "Real Estate Agency"
_AUTO_REPAIR = "Auto Repair"
_HAIR_SALON = "Hair Salon"


@dataclass(frozen=True)
class BusinessCategory:
    """A normalized business category with source and confidence."""

    raw: str
    normalized: str
    source: str = ""
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw": self.raw,
            "normalized": self.normalized,
            "source": self.source,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class CategoryAnalysis:
    """Analysis of business categories across sources."""

    primary_category: str = ""
    all_categories: list[BusinessCategory] = field(default_factory=list)
    schema_categories: list[BusinessCategory] = field(default_factory=list)
    page_categories: list[BusinessCategory] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_category": self.primary_category,
            "all_categories": [c.to_dict() for c in self.all_categories],
            "schema_categories": [c.to_dict() for c in self.schema_categories],
            "page_categories": [c.to_dict() for c in self.page_categories],
            "conflicts": self.conflicts,
        }


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

# Common category aliases — maps variants to canonical form
_CATEGORY_ALIASES: dict[str, str] = {
    "plumber": "Plumber",
    "plumbing": "Plumber",
    "electrician": "Electrician",
    "electrical": "Electrician",
    "general contractor": "General Contractor",
    "builder": "Builder",
    "building contractor": "Builder",
    "construction company": "Builder",
    "dentist": "Dentist",
    "dental clinic": "Dentist",
    "dental practice": "Dentist",
    "doctor": "Physician",
    "physician": "Physician",
    "gp": "Physician",
    "general practitioner": "Physician",
    "restaurant": "Restaurant",
    "cafe": "Cafe",
    "café": "Cafe",
    "coffee shop": "Cafe",
    "lawyer": "Lawyer",
    "attorney": "Lawyer",
    "legal services": "Lawyer",
    "accountant": "Accountant",
    "accounting": "Accountant",
    "tax preparation": "Accountant",
    "real estate agent": _REAL_ESTATE_AGENCY,
    "realty": _REAL_ESTATE_AGENCY,
    "property management": _REAL_ESTATE_AGENCY,
    "hair salon": _HAIR_SALON,
    "hairdresser": _HAIR_SALON,
    "barber": _HAIR_SALON,
    "mechanic": _AUTO_REPAIR,
    "auto repair": _AUTO_REPAIR,
    "car repair": _AUTO_REPAIR,
    "gym": "Gym",
    "fitness center": "Gym",
    "fitness centre": "Gym",
}


def normalize_category(raw: str) -> str:
    """Normalize a category string to a canonical form."""
    cleaned = raw.strip().lower()
    # Remove leading "we are a/an" or similar
    for prefix in ("we are a ", "we are an ", "we are ", "your ", "the "):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]

    # Check aliases
    for variant, canonical in _CATEGORY_ALIASES.items():
        if cleaned == variant or cleaned.startswith(variant + " "):
            return canonical

    # Title case as fallback
    return cleaned.title()


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def extract_categories_from_schema(
    schema_entity: dict[str, Any],
    source: str = "",
) -> list[BusinessCategory]:
    """Extract categories from a JSON-LD schema entity."""
    categories: list[BusinessCategory] = []

    at_type = schema_entity.get("@type", "")
    if isinstance(at_type, str) and at_type:
        categories.append(_schema_category(at_type, source, "schema:@type"))
    elif isinstance(at_type, list):
        categories.extend(
            _schema_category(value, source, "schema:@type")
            for value in at_type
            if isinstance(value, str) and value not in ("LocalBusiness", "Organization", "Place")
        )

    for key, origin in (("additionalType", "schema:additionalType"), ("category", "schema:category")):
        value = schema_entity.get(key, "")
        if isinstance(value, str) and value:
            categories.append(_schema_category(value, source, origin))

    return categories


def _schema_category(raw: str, source: str, fallback_source: str) -> BusinessCategory:
    return BusinessCategory(
        raw=raw,
        normalized=normalize_category(raw),
        source=source or fallback_source,
    )


def extract_categories_from_text(
    text: str,
    source: str = "",
) -> list[BusinessCategory]:
    """Extract category-like terms from page text.

    Simple keyword-based extraction. For production, this could use
    NLP classification.
    """
    categories: list[BusinessCategory] = []
    text_lower = text.lower()

    for variant, canonical in _CATEGORY_ALIASES.items():
        if variant in text_lower:
            categories.append(BusinessCategory(
                raw=variant,
                normalized=canonical,
                source=source,
                confidence=0.6,
            ))

    # Deduplicate by normalized form
    seen: set[str] = set()
    unique: list[BusinessCategory] = []
    for cat in categories:
        if cat.normalized not in seen:
            seen.add(cat.normalized)
            unique.append(cat)

    return unique


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def compare_categories(
    schema_categories: list[BusinessCategory],
    page_categories: list[BusinessCategory],
) -> CategoryAnalysis:
    """Compare categories across schema and page sources.

    Returns analysis with primary category, all categories, and any conflicts.
    """
    all_cats: list[BusinessCategory] = []
    conflicts: list[dict[str, Any]] = []

    seen_normalized: dict[str, str] = {}  # normalized -> source

    for cat in schema_categories:
        if cat.normalized not in seen_normalized:
            seen_normalized[cat.normalized] = cat.source
        all_cats.append(cat)

    for cat in page_categories:
        conflict = _category_conflict(cat, seen_normalized)
        if conflict:
            conflicts.append(conflict)
        all_cats.append(cat)

    # Determine primary category (highest confidence, schema preferred)
    primary = ""
    for cat in schema_categories + page_categories:
        if cat.confidence >= 0.8:
            primary = cat.normalized
            break
    if not primary and all_cats:
        primary = all_cats[0].normalized

    return CategoryAnalysis(
        primary_category=primary,
        all_categories=all_cats,
        schema_categories=schema_categories,
        page_categories=page_categories,
        conflicts=conflicts,
    )


def _category_conflict(
    category: BusinessCategory,
    seen_normalized: dict[str, str],
) -> dict[str, Any] | None:
    if category.normalized in seen_normalized or len(seen_normalized) != 1:
        return None
    return {
        "field": "category",
        "status": "CONTRADICTION",
        "schema_value": list(seen_normalized.keys()),
        "page_value": category.normalized,
        "detail": f"Page category '{category.normalized}' not in schema categories",
    }


def deduplicate_categories(
    categories: list[BusinessCategory],
) -> list[str]:
    """Return unique normalized category names."""
    seen: set[str] = set()
    result: list[str] = []
    for cat in categories:
        if cat.normalized not in seen:
            seen.add(cat.normalized)
            result.append(cat.normalized)
    return result

"""Extract LocalBusiness/Organization/PostalAddress/GeoCoordinates from JSON-LD.

Uses extruct to parse JSON-LD blocks from rendered HTML and compares schema
values against visible page values. Produces a list of ConsistencyStatus records.
"""

from __future__ import annotations

from typing import Any

from .address import normalize_address
from .hours import normalize_hours
from .phone import normalize_phone
from .schema import (
    ConsistencyStatus,
    GeoCoordinates,
    NormalizedAddress,
    NormalizedPhone,
    OpeningHour,
)

# ---------------------------------------------------------------------------
# JSON-LD entity types we recognise as "local"
# ---------------------------------------------------------------------------

_LOCAL_TYPES = frozenset(
    {
        "LocalBusiness",
        "Organization",
        "Restaurant",
        "MedicalBusiness",
        "Dentist",
        "Physician",
        "HomeAndConstructionBusiness",
        "AutoRepair",
        "Store",
        "ProfessionalService",
        "FinancialService",
        "LodgingBusiness",
        "TouristAttraction",
    }
)
_SCHEMA_TYPE_KEY = "@type"
_JSON_LD_GRAPH_KEY = "@graph"

# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------


def _extract_jsonld(html: str) -> list[dict[str, Any]]:
    """Parse JSON-LD blocks from HTML using declared runtime dependencies.

    Invalid JSON-LD blocks are ignored individually so one malformed script
    does not suppress valid structured data elsewhere on the page.
    """
    import json

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    blocks: list[dict[str, Any]] = []

    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text()
        if not raw or not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue

        if isinstance(data, dict):
            blocks.append(data)
        elif isinstance(data, list):
            blocks.extend(item for item in data if isinstance(item, dict))

    return blocks


def _find_local_entities(jsonld_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return blocks whose @type matches a local-business type."""
    results: list[dict[str, Any]] = []
    for block in jsonld_blocks:
        types = _to_list(block.get(_SCHEMA_TYPE_KEY, []))
        if any(t in _LOCAL_TYPES or t.startswith("LocalBusiness") for t in types):
            results.append(block)
        elif any(t == "Organization" for t in types):
            # Organizations can have location with LocalBusiness
            results.append(block)
        elif _JSON_LD_GRAPH_KEY in block:
            for item in block[_JSON_LD_GRAPH_KEY]:
                item_types = _to_list(item.get(_SCHEMA_TYPE_KEY, []))
                if any(t in _LOCAL_TYPES for t in item_types):
                    results.append(item)
    return results


def _to_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def _extract_address(obj: dict[str, Any]) -> NormalizedAddress:
    """Extract and normalize address from schema object."""
    raw = ""
    addr_obj = obj.get("address")
    if isinstance(addr_obj, dict):
        parts = []
        for key in ("streetAddress", "addressLocality", "addressRegion",
                     "postalCode", "addressCountry"):
            val = addr_obj.get(key, "")
            if val:
                parts.append(str(val))
        raw = ", ".join(parts)
    elif isinstance(addr_obj, str):
        raw = addr_obj
    return normalize_address(raw) if raw else NormalizedAddress()


def _extract_geo(obj: dict[str, Any]) -> GeoCoordinates | None:
    """Extract GeoCoordinates from schema geo or map."""
    geo = obj.get("geo")
    if isinstance(geo, dict):
        try:
            lat = float(geo.get("latitude", 0))
            lon = float(geo.get("longitude", 0))
            if lat or lon:
                return GeoCoordinates(latitude=lat, longitude=lon)
        except (ValueError, TypeError):
            pass
    return None


def _extract_phones(obj: dict[str, Any], source: str = "") -> list[NormalizedPhone]:
    """Extract phone numbers from schema telephone property."""
    phones: list[NormalizedPhone] = []
    raw = obj.get("telephone", "")
    if isinstance(raw, str) and raw.strip():
        phones.append(normalize_phone(raw, source=source))
    elif isinstance(raw, list):
        for p in raw:
            if isinstance(p, str) and p.strip():
                phones.append(normalize_phone(p, source=source))
    return phones


def _extract_hours(obj: dict[str, Any], source: str = "") -> list[OpeningHour]:
    """Extract opening hours from schema."""
    hours_raw = obj.get("openingHours", [])
    if isinstance(hours_raw, str):
        hours_raw = [hours_raw]
    if not isinstance(hours_raw, list):
        return []

    result: list[OpeningHour] = []
    for h in hours_raw:
        if isinstance(h, str) and h.strip():
            result.extend(normalize_hours(h, source=source))
    return result


def _extract_name(obj: dict[str, Any]) -> str:
    return str(obj.get("name", "")).strip()


# ---------------------------------------------------------------------------
# Public extraction API
# ---------------------------------------------------------------------------


def extract_local_business_from_html(
    html: str,
    source_url: str = "",
) -> list[dict[str, Any]]:
    """Extract LocalBusiness entities from HTML page.

    Returns list of dicts with keys: entity_type, name, address, phones,
    geo, opening_hours, raw_block.
    """
    blocks = _extract_jsonld(html)
    entities = _find_local_entities(blocks)

    results: list[dict[str, Any]] = []
    for entity in entities:
        record = {
            "entity_type": _to_list(entity.get("@type", [])),
            "entity_id": entity.get("@id", ""),
            "name": _extract_name(entity),
            "address": _extract_address(entity),
            "phones": _extract_phones(entity, source=source_url),
            "geo": _extract_geo(entity),
            "opening_hours": _extract_hours(entity, source=source_url),
            "url": str(entity.get("url", "")),
            "same_as": _to_list(entity.get("sameAs", [])),
            "raw_block": entity,
            "source_url": source_url,
        }
        results.append(record)
    return results


# ---------------------------------------------------------------------------
# Schema vs visible comparison
# ---------------------------------------------------------------------------


def compare_schema_to_visible(
    schema_name: str = "",
    schema_address: NormalizedAddress | None = None,
    schema_phone: NormalizedPhone | None = None,
    schema_hours: list[OpeningHour] | None = None,
    visible_name: str = "",
    visible_address: NormalizedAddress | None = None,
    visible_phone: NormalizedPhone | None = None,
    visible_hours: list[OpeningHour] | None = None,
) -> list[dict[str, Any]]:
    """Compare schema values against visible page values.

    Returns list of contradiction records with field, status, schema_value,
    visible_value, and confidence.
    """
    return (
        _compare_schema_name(schema_name, visible_name)
        + _compare_schema_address(schema_address, visible_address)
        + _compare_schema_phone(schema_phone, visible_phone)
        + _compare_schema_hours(schema_hours, visible_hours)
    )


def _compare_schema_name(schema_name: str, visible_name: str) -> list[dict[str, Any]]:
    if not schema_name and not visible_name:
        return []

    if not schema_name or not visible_name:
        return [{
            "field": "name",
            "status": "INSUFFICIENT_EVIDENCE",
            "schema_value": schema_name,
            "visible_value": visible_name,
        }]

    from .nap import names_equivalent

    equivalent, status = names_equivalent(schema_name, visible_name)
    return [{
        "field": "name",
        "status": status,
        "schema_value": schema_name,
        "visible_value": visible_name,
        "equivalent": equivalent,
    }]


def _compare_schema_address(
    schema_address: NormalizedAddress | None,
    visible_address: NormalizedAddress | None,
) -> list[dict[str, Any]]:
    if not schema_address and not visible_address:
        return []

    schema_value = schema_address.normalized if schema_address else ""
    visible_value = visible_address.normalized if visible_address else ""
    if not schema_address or not visible_address:
        status = "INSUFFICIENT_EVIDENCE"
    else:
        from .address import compare_addresses

        status = compare_addresses(schema_address, visible_address)
    return [{
        "field": "address",
        "status": status,
        "schema_value": schema_value,
        "visible_value": visible_value,
    }]


def _compare_schema_phone(
    schema_phone: NormalizedPhone | None,
    visible_phone: NormalizedPhone | None,
) -> list[dict[str, Any]]:
    if not schema_phone or not visible_phone:
        return []
    return [{
        "field": "phone",
        "status": _compare_phone_status(schema_phone, visible_phone),
        "schema_value": schema_phone.e164 or schema_phone.raw,
        "visible_value": visible_phone.e164 or visible_phone.raw,
    }]


def _compare_schema_hours(
    schema_hours: list[OpeningHour] | None,
    visible_hours: list[OpeningHour] | None,
) -> list[dict[str, Any]]:
    if not schema_hours or not visible_hours:
        return []

    from .hours import hours_match

    match, detail = hours_match(schema_hours, visible_hours)
    return [{
        "field": "hours",
        "status": "MATCH" if match else "CONTRADICTION",
        "schema_value": f"{len(schema_hours)} rules",
        "visible_value": f"{len(visible_hours)} rules",
        "detail": detail,
    }]


def _compare_phone_status(a: NormalizedPhone, b: NormalizedPhone) -> ConsistencyStatus:
    """Compare two phone numbers and return status."""
    from .phone import compare_phones

    return compare_phones(a, b)


# ---------------------------------------------------------------------------
# Schema quality check
# ---------------------------------------------------------------------------


def validate_localbusiness_schema(
    entity: dict[str, Any],
) -> list[dict[str, str]]:
    """Check if a LocalBusiness schema entity is well-formed.

    Returns list of issues with field, severity, and message.
    """
    issues: list[dict[str, str]] = []
    _ = entity.get("entity_type", [])  # noqa: F841

    # Must have name
    if not entity.get("name"):
        issues.append({
            "field": "name",
            "severity": "error",
            "message": "LocalBusiness schema missing name property",
        })

    # Must have address or serviceArea
    addr = entity.get("address")
    has_address = bool(
        addr
        and (
            getattr(addr, "normalized", "")
            or getattr(addr, "raw", "")
            or (isinstance(addr, str) and addr.strip())
        )
    )
    raw_block = entity.get("raw_block")
    has_service_area = (
        bool(raw_block.get("serviceArea"))
        if isinstance(raw_block, dict)
        else False
    )
    if not has_address and not has_service_area:
        issues.append({
            "field": "address",
            "severity": "warning",
            "message": "LocalBusiness has no address or serviceArea",
        })

    # Should have telephone
    if not entity.get("phones"):
        issues.append({
            "field": "telephone",
            "severity": "warning",
            "message": "LocalBusiness has no telephone",
        })

    # Should have geo coordinates
    if not entity.get("geo"):
        issues.append({
            "field": "geo",
            "severity": "info",
            "message": "LocalBusiness has no geo coordinates",
        })

    return issues

extract_localbusiness_schema = extract_local_business_from_html

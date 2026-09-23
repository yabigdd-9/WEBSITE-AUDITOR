"""Overpass API adapter (stub/optional).

For querying OpenStreetMap data via the Overpass API.
This is a lightweight adapter — the Overpass query language is complex
and full coverage requires a separate module. This provides common
local-business queries.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from ..schema import GeoCoordinates, NormalizedAddress


@dataclass(frozen=True)
class OverpassNode:
    """A single OSM node/way/relation result."""

    osm_type: str = ""  # node, way, relation
    osm_id: str = ""
    lat: float = 0.0
    lon: float = 0.0
    tags: dict[str, str] = field(default_factory=dict)
    name: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "osm_type": self.osm_type,
            "osm_id": self.osm_id,
            "lat": self.lat,
            "lon": self.lon,
            "tags": self.tags,
            "name": self.name,
        }


@dataclass(frozen=True)
class OverpassResult:
    """Result from an Overpass query."""

    elements: list[OverpassNode] = field(default_factory=list)
    query: str = ""
    raw_response: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "elements": [e.to_dict() for e in self.elements],
            "query": self.query,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Query templates
# ---------------------------------------------------------------------------


def _build_localbusiness_query(
    lat: float,
    lon: float,
    radius_m: float = 1000.0,
    business_type: str = "",
) -> str:
    """Build Overpass QL for finding LocalBusiness-like OSM objects near a point."""
    # OSM tags that correspond to local businesses
    tag_filters = ['"shop"', '"office"', '"amenity"', '"tourism"', '"leisure"']
    if business_type:
        tag_filters = [f'"amenity"="{business_type}"', f'"shop"="{business_type}"']

    filter_clause = " or ".join(f"n[{t}]" for t in tag_filters)

    return f"""
[out:json][timeout:30];
(
  {filter_clause}(around:{radius_m},{lat},{lon});
  way(around:{radius_m},{lat},{lon}){"".join(f'[{t.split("=")[0]}]' for t in tag_filters)};
);
out center qt;
"""


def _build_address_query(
    street: str = "",
    city: str = "",
    postcode: str = "",
) -> str:
    """Build Overpass QL for finding a specific address."""
    filters = []
    if street:
        filters.append(f'"addr:street"~"{street}"')
    if city:
        filters.append(f'"addr:city"~"{city}"')
    if postcode:
        filters.append(f'"addr:postcode"="{postcode}"')

    if not filters:
        return ""

    filter_clause = " and ".join(f"n[{f}]" for f in filters)

    return f"""
[out:json][timeout:30];
(
  {filter_clause};
);
out;
"""


# ---------------------------------------------------------------------------
# Query execution
# ---------------------------------------------------------------------------

_default_endpoint = "https://overpass-api.de/api/interpreter"
_rate_limit_seconds = 2.0
_last_request_time: float = 0.0


def _respect_rate_limit() -> None:
    global _last_request_time
    now = time.monotonic()
    elapsed = now - _last_request_time
    if elapsed < _rate_limit_seconds:
        time.sleep(_rate_limit_seconds - elapsed)
    _last_request_time = time.monotonic()


def query(
    query_text: str,
    endpoint: str = _default_endpoint,
    timeout: float = 30.0,
) -> OverpassResult:
    """Execute a raw Overpass QL query.

    Returns OverpassResult with parsed elements.
    """
    _respect_rate_limit()

    try:
        import httpx

        response = httpx.post(
            endpoint,
            data={"data": query_text},
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        return OverpassResult(
            query=query_text,
            error=str(exc),
        )

    elements = _parse_elements(data)
    return OverpassResult(
        elements=elements,
        query=query_text,
        raw_response=data,
    )


def find_nearby_businesses(
    lat: float,
    lon: float,
    radius_m: float = 1000.0,
    business_type: str = "",
    endpoint: str = _default_endpoint,
) -> OverpassResult:
    """Find OSM business nodes near a coordinate."""
    ql = _build_localbusiness_query(lat, lon, radius_m, business_type)
    if not ql:
        return OverpassResult(error="Could not build query")
    return query(ql, endpoint=endpoint)


def find_by_address(
    address: NormalizedAddress,
    endpoint: str = _default_endpoint,
) -> OverpassResult:
    """Find OSM nodes matching an address."""
    ql = _build_address_query(
        street=address.street_name,
        city=address.locality,
        postcode=address.postal_code,
    )
    if not ql:
        return OverpassResult(error="Could not build address query")
    return query(ql, endpoint=endpoint)


def _parse_elements(data: dict[str, Any]) -> list[OverpassNode]:
    """Parse Overpass JSON response into OverpassNode objects."""
    elements: list[OverpassNode] = []
    for elem in data.get("elements", []):
        etype = elem.get("type", "")
        tags = elem.get("tags", {})

        # For ways, get center coordinates
        if etype == "way":
            lat = elem.get("center", {}).get("lat", 0)
            lon = elem.get("center", {}).get("lon", 0)
        else:
            lat = elem.get("lat", 0)
            lon = elem.get("lon", 0)

        node = OverpassNode(
            osm_type=etype,
            osm_id=str(elem.get("id", "")),
            lat=lat,
            lon=lon,
            tags=tags,
            name=tags.get("name", ""),
            raw=elem,
        )
        elements.append(node)

    return elements


# ---------------------------------------------------------------------------
# Business data extraction
# ---------------------------------------------------------------------------


def osm_to_business_info(node: OverpassNode) -> dict[str, Any]:
    """Extract business-relevant data from an OSM node."""
    tags = node.tags
    return {
        "name": tags.get("name", ""),
        "phone": tags.get("phone", tags.get("contact:phone", "")),
        "website": tags.get("website", tags.get("contact:website", "")),
        "email": tags.get("email", tags.get("contact:email", "")),
        "address": _osm_address(tags),
        "opening_hours": tags.get("opening_hours", ""),
        "categories": _osm_categories(tags),
        "geo": GeoCoordinates(latitude=node.lat, longitude=node.lon) if node.lat and node.lon else None,
        "osm_type": node.osm_type,
        "osm_id": node.osm_id,
    }


def _osm_address(tags: dict[str, str]) -> str:
    """Build address string from OSM address tags."""
    parts = []
    if tags.get("addr:housenumber"):
        parts.append(tags["addr:housenumber"])
    if tags.get("addr:street"):
        parts.append(tags["addr:street"])
    if tags.get("addr:city"):
        parts.append(tags["addr:city"])
    if tags.get("addr:postcode"):
        parts.append(tags["addr:postcode"])
    if tags.get("addr:country"):
        parts.append(tags["addr:country"])
    return ", ".join(parts)


def _osm_categories(tags: dict[str, str]) -> list[str]:
    """Extract categories from OSM tags."""
    cats = []
    if tags.get("shop"):
        cats.append(f"shop:{tags['shop']}")
    if tags.get("amenity"):
        cats.append(f"amenity:{tags['amenity']}")
    if tags.get("office"):
        cats.append(f"office:{tags['office']}")
    if tags.get("tourism"):
        cats.append(f"tourism:{tags['tourism']}")
    if tags.get("cuisine"):
        cats.append(f"cuisine:{tags['cuisine']}")
    return cats

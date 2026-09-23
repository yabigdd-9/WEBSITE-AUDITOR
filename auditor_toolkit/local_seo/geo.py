"""Geographic corroboration.

Haversine distance between schema geo and geocoder coordinates.
Statuses: CONSISTENT (<500m urban, <2km rural), NEARBY, AMBIGUOUS,
MATERIAL_CONFLICT. Cache by normalized address hash.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Literal

from .schema import ConsistencyStatus, GeoCoordinates, NormalizedAddress

GeoStatus = Literal[
    "CONSISTENT",
    "NEARBY",
    "AMBIGUOUS",
    "MATERIAL_CONFLICT",
]


@dataclass(frozen=True)
class GeoCorroboration:
    """Result of geographic corroboration between two coordinate sets."""

    status: GeoStatus
    distance_km: float = 0.0
    schema_geo: GeoCoordinates | None = None
    geocoder_geo: GeoCoordinates | None = None
    address_hash: str = ""
    threshold_m: float = 500.0
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "distance_km": self.distance_km,
            "schema_geo": {
                "latitude": self.schema_geo.latitude,
                "longitude": self.schema_geo.longitude,
            } if self.schema_geo else None,
            "geocoder_geo": {
                "latitude": self.geocoder_geo.latitude,
                "longitude": self.geocoder_geo.longitude,
            } if self.geocoder_geo else None,
            "address_hash": self.address_hash,
            "threshold_m": self.threshold_m,
            "detail": self.detail,
        }


# ---------------------------------------------------------------------------
# Distance computation
# ---------------------------------------------------------------------------


def haversine_distance(a: GeoCoordinates, b: GeoCoordinates) -> float:
    """Haversine distance in kilometres."""
    return a.haversine_km(b)


# ---------------------------------------------------------------------------
# Address hash for caching
# ---------------------------------------------------------------------------


def address_cache_key(address: NormalizedAddress) -> str:
    """Create a cache key from a normalized address.

    Uses SHA-256 of the address signature + provider version.
    """
    sig = address.signature()
    raw = f"{sig}|v1"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Status classification
# ---------------------------------------------------------------------------


def classify_geo_status(
    distance_km: float,
    is_urban: bool = True,
) -> GeoStatus:
    """Classify the geographic distance between two points.

    Urban threshold: 500m
    Rural threshold: 2km
    """
    distance_m = distance_km * 1000
    threshold = 500.0 if is_urban else 2000.0

    if distance_m <= threshold:
        return "CONSISTENT"
    if distance_m <= threshold * 4:
        return "NEARBY"
    if distance_m <= threshold * 10:
        return "AMBIGUOUS"
    return "MATERIAL_CONFLICT"


# ---------------------------------------------------------------------------
# Main corroboration
# ---------------------------------------------------------------------------


def corroborate_geo(
    schema_geo: GeoCoordinates,
    geocoder_geo: GeoCoordinates,
    address: NormalizedAddress | None = None,
    is_urban: bool = True,
) -> GeoCorroboration:
    """Compare schema geo coordinates against geocoder coordinates.

    Returns a GeoCorroboration with status, distance, and cache key.
    """
    distance = haversine_distance(schema_geo, geocoder_geo)
    status = classify_geo_status(distance, is_urban)
    addr_hash = address_cache_key(address) if address else ""

    threshold_m = 500.0 if is_urban else 2000.0

    return GeoCorroboration(
        status=status,
        distance_km=round(distance, 3),
        schema_geo=schema_geo,
        geocoder_geo=geocoder_geo,
        address_hash=addr_hash,
        threshold_m=threshold_m,
        detail=f"Distance: {distance*1000:.0f}m (threshold: {threshold_m:.0f}m, {'urban' if is_urban else 'rural'})",
    )


def geo_to_consistency_status(status: GeoStatus) -> ConsistencyStatus:
    """Map GeoStatus to ConsistencyStatus for the broader system."""
    mapping: dict[GeoStatus, ConsistencyStatus] = {
        "CONSISTENT": "MATCH",
        "NEARBY": "PROBABLE_MATCH",
        "AMBIGUOUS": "INSUFFICIENT_EVIDENCE",
        "MATERIAL_CONFLICT": "CONTRADICTION",
    }
    return mapping.get(status, "INSUFFICIENT_EVIDENCE")


# ---------------------------------------------------------------------------
# Cache (in-memory, simple)
# ---------------------------------------------------------------------------

_geo_cache: dict[str, GeoCorroboration] = {}


def get_cached_geo(address_hash: str) -> GeoCorroboration | None:
    """Retrieve a cached geo corroboration result."""
    return _geo_cache.get(address_hash)


def cache_geo(address_hash: str, result: GeoCorroboration) -> None:
    """Cache a geo corroboration result."""
    _geo_cache[address_hash] = result


def clear_geo_cache() -> None:
    """Clear the geo cache (e.g., between audit runs)."""
    _geo_cache.clear()


def cache_size() -> int:
    """Return number of cached entries."""
    return len(_geo_cache)

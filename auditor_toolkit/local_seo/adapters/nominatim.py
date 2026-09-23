"""Nominatim geocoding adapter.

RESPECTS POLICY:
- Max 1 request/sec between calls
- Requires User-Agent header
- Disabled by default (enable_nominatim must be True)
- Caches results: cache key = sha256(normalized_address + provider_version)
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any

from ..schema import GeoCoordinates, NormalizedAddress


@dataclass(frozen=True)
class GeocodeResult:
    """Result from a Nominatim geocode query."""

    address: str = ""
    geo: GeoCoordinates | None = None
    display_name: str = ""
    place_id: str = ""
    osm_type: str = ""
    osm_id: str = ""
    confidence: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "geo": {
                "latitude": self.geo.latitude,
                "longitude": self.geo.longitude,
            } if self.geo else None,
            "display_name": self.display_name,
            "place_id": self.place_id,
            "osm_type": self.osm_type,
            "osm_id": self.osm_id,
            "confidence": self.confidence,
        }


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_provider_version = "nominatim-v1"
_cache: dict[str, GeocodeResult] = {}
_last_request_time: float = 0.0


def _cache_key(address: NormalizedAddress) -> str:
    """Cache key = sha256(normalized_address + provider_version)."""
    sig = address.signature() or address.raw
    raw = f"{sig}|{_provider_version}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def get_cached(address: NormalizedAddress) -> GeocodeResult | None:
    """Get cached geocode result."""
    return _cache.get(_cache_key(address))


def set_cached(address: NormalizedAddress, result: GeocodeResult) -> None:
    """Cache a geocode result."""
    _cache[_cache_key(address)] = result


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

_RATE_LIMIT_SECONDS = 1.0


def _respect_rate_limit() -> None:
    """Ensure at least 1 second between requests."""
    global _last_request_time
    now = time.monotonic()
    elapsed = now - _last_request_time
    if elapsed < _RATE_LIMIT_SECONDS:
        time.sleep(_RATE_LIMIT_SECONDS - elapsed)
    _last_request_time = time.monotonic()


# ---------------------------------------------------------------------------
# Geocoding
# ---------------------------------------------------------------------------


def geocode(
    address: NormalizedAddress,
    user_agent: str = "WEBSITE-AUDITOR/1.0",
    enable_nominatim: bool = False,
    timeout: float = 10.0,
) -> GeocodeResult | None:
    """Geocode a normalized address via Nominatim.

    Args:
        address: NormalizedAddress to geocode.
        user_agent: Required User-Agent for Nominatim policy compliance.
        enable_nominatim: Must be True to enable (disabled by default).
        timeout: HTTP timeout in seconds.

    Returns:
        GeocodeResult or None if disabled/fails.
    """
    if not enable_nominatim:
        return None

    if not user_agent or len(user_agent) < 5:
        raise ValueError("Nominatim requires a descriptive User-Agent header")

    # Check cache first
    cached = get_cached(address)
    if cached:
        return cached

    # Build query
    query = _build_query(address)
    if not query:
        return None

    # Rate limit
    _respect_rate_limit()

    try:
        import httpx

        params = {
            "q": query,
            "format": "json",
            "limit": "1",
            "addressdetails": "1",
        }

        headers = {"User-Agent": user_agent}

        response = httpx.get(
            "https://nominatim.openstreetmap.org/search",
            params=params,
            headers=headers,
            timeout=timeout,
        )
        response.raise_for_status()

        results = response.json()
        if not results:
            result = GeocodeResult(
                address=address.normalized,
                confidence=0.0,
            )
        else:
            first = results[0]
            lat = float(first.get("lat", 0))
            lon = float(first.get("lon", 0))
            geo = GeoCoordinates(latitude=lat, longitude=lon)

            result = GeocodeResult(
                address=first.get("display_name", ""),
                geo=geo,
                display_name=first.get("display_name", ""),
                place_id=str(first.get("place_id", "")),
                osm_type=first.get("osm_type", ""),
                osm_id=str(first.get("osm_id", "")),
                confidence=_compute_confidence(first),
                raw=first,
            )

        set_cached(address, result)
        return result

    except Exception:
        return None


def _build_query(address: NormalizedAddress) -> str:
    """Build a search query from normalized address components."""
    parts = []
    if address.street_number and address.street_name:
        parts.append(f"{address.street_number} {address.street_name}")
    elif address.street_name:
        parts.append(address.street_name)
    if address.unit:
        parts.append(f"Unit {address.unit}")
    if address.locality:
        parts.append(address.locality)
    if address.region:
        parts.append(address.region)
    if address.postal_code:
        parts.append(address.postal_code)
    if address.country:
        parts.append(address.country)

    if not parts:
        return address.raw or ""

    return ", ".join(parts)


def _compute_confidence(result: dict[str, Any]) -> float:
    """Estimate confidence from Nominatim result quality."""
    confidence = 0.5  # Base

    # Higher confidence for street-level results
    addr_type = result.get("type", "")
    if addr_type in ("house", "building", "residential"):
        confidence = 0.95
    elif addr_type == "street":
        confidence = 0.8
    elif addr_type in ("postcode", "suburb"):
        confidence = 0.5
    elif addr_type in ("city", "town", "village"):
        confidence = 0.3

    # Importance score from Nominatim
    importance = result.get("importance", 0)
    if importance > 0.7:
        confidence = min(confidence + 0.1, 1.0)

    return round(confidence, 2)


# ---------------------------------------------------------------------------
# Batch geocoding (rate-limited)
# ---------------------------------------------------------------------------


def geocode_batch(
    addresses: list[NormalizedAddress],
    user_agent: str = "WEBSITE-AUDITOR/1.0",
    enable_nominatim: bool = False,
) -> dict[str, GeocodeResult | None]:
    """Geocode multiple addresses with rate limiting.

    Returns dict mapping address signature to result.
    """
    results: dict[str, GeocodeResult | None] = {}
    for addr in addresses:
        sig = addr.signature() or addr.raw
        result = geocode(addr, user_agent=user_agent, enable_nominatim=enable_nominatim)
        results[sig] = result
    return results

"""Google Business Profile adapter (OPTIONAL, DISABLED BY DEFAULT).

Only activates with explicit OAuth authorization. GBP credentials must
NEVER be put in ordinary crawlers or passed through standard audit flows.

This adapter requires:
1. OAuth 2.0 credentials (client_id, client_secret, refresh_token)
2. User consent with the `https://www.googleapis.com/auth/business.manage` scope
3. An explicit `enable_gbp=True` flag at call time

Without all three, this adapter returns empty results and logs a warning.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..schema import ExternalLocalEvidence, GeoCoordinates


@dataclass(frozen=True)
class GBPAuthConfig:
    """OAuth configuration for GBP access."""

    client_id: str = ""
    client_secret: str = ""
    refresh_token: str = ""
    access_token: str = ""
    token_expires_at: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and (self.access_token or self.refresh_token))


@dataclass(frozen=True)
class GBPLocation:
    """A Google Business Profile location."""

    name: str = ""
    store_code: str = ""
    address: str = ""
    phone: str = ""
    website: str = ""
    categories: list[str] = field(default_factory=list)
    geo: GeoCoordinates | None = None
    hours: dict[str, str] = field(default_factory=dict)
    state: str = ""  # OPEN, CLOSED, etc.
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "store_code": self.store_code,
            "address": self.address,
            "phone": self.phone,
            "website": self.website,
            "categories": self.categories,
            "geo": {
                "latitude": self.geo.latitude,
                "longitude": self.geo.longitude,
            } if self.geo else None,
            "hours": self.hours,
            "state": self.state,
        }

    def to_external_evidence(self) -> ExternalLocalEvidence:
        """Convert to ExternalLocalEvidence for the corroboration pipeline."""
        artifact_hash = hashlib.sha256(
            json.dumps(self.raw, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
        evidence_id = hashlib.sha256(
            f"gbp:{self.store_code}:{artifact_hash}".encode()
        ).hexdigest()[:24]

        return ExternalLocalEvidence(
            provider="Google Business Profile",
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            query=self.store_code or self.name,
            name=self.name,
            address=self.address,
            phone=self.phone,
            geo=self.geo,
            categories=self.categories,
            source_confidence=0.95,  # GBP is authoritative for its own listings
            freshness=self.state,
            raw_artifact_hash=artifact_hash,
            evidence_id=evidence_id,
        )


# ---------------------------------------------------------------------------
# Auth state
# ---------------------------------------------------------------------------

_auth_config = GBPAuthConfig()
_enabled = False  # Disabled by default — requires explicit opt-in


def configure_auth(
    client_id: str = "",
    client_secret: str = "",
    refresh_token: str = "",
) -> None:
    """Configure OAuth credentials. Does NOT enable GBP access."""
    global _auth_config
    _auth_config = GBPAuthConfig(
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
    )


def enable_gbp() -> bool:
    """Attempt to enable GBP access.

    Returns True only if auth is configured.
    """
    global _enabled
    if not _auth_config.is_configured:
        _enabled = False
        return False
    _enabled = True
    return True


def disable_gbp() -> None:
    """Disable GBP access."""
    global _enabled
    _enabled = False


def is_enabled() -> bool:
    """Check if GBP access is currently enabled."""
    return _enabled and _auth_config.is_configured


# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------

_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


def _refresh_access_token() -> str | None:
    """Refresh OAuth access token using refresh token."""
    global _auth_config
    if not _auth_config.refresh_token:
        return None

    try:
        import httpx

        response = httpx.post(
            _TOKEN_ENDPOINT,
            data={
                "client_id": _auth_config.client_id,
                "client_secret": _auth_config.client_secret,
                "refresh_token": _auth_config.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        response.raise_for_status()
        data = response.json()

        access_token = data.get("access_token", "")
        expires_in = data.get("expires_in", 3600)

        from datetime import timedelta
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        _auth_config = GBPAuthConfig(
            client_id=_auth_config.client_id,
            client_secret=_auth_config.client_secret,
            refresh_token=_auth_config.refresh_token,
            access_token=access_token,
            token_expires_at=expires_at.isoformat(),
        )

        return access_token
    except Exception:
        return None


def _get_access_token() -> str | None:
    """Get a valid access token, refreshing if needed."""
    if not _auth_config.access_token:
        return _refresh_access_token()

    # Check expiry
    if _auth_config.token_expires_at:
        try:
            expires = datetime.fromisoformat(_auth_config.token_expires_at)
            if datetime.now(timezone.utc) >= expires:
                return _refresh_access_token()
        except ValueError:
            return _refresh_access_token()

    return _auth_config.access_token


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

_GBP_ENDPOINT = "https://mybusiness.googleapis.com/v4"


def list_locations(
    account_name: str = "",
    enable: bool = False,
) -> list[GBPLocation]:
    """List all GBP locations for an account.

    Args:
        account_name: Google Business Profile account name (e.g., "accounts/123").
        enable: Must be True to actually query GBP.

    Returns:
        List of GBPLocation objects. Empty if GBP is not enabled.
    """
    if not enable or not is_enabled():
        return []

    token = _get_access_token()
    if not token:
        return []

    try:
        import httpx

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        response = httpx.get(
            f"{_GBP_ENDPOINT}/{account_name}/locations",
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()

        data = response.json()
        locations_data = data.get("locations", [])

        return [_parse_gbp_location(loc) for loc in locations_data]

    except Exception:
        return []


def get_location(
    location_name: str = "",
    enable: bool = False,
) -> GBPLocation | None:
    """Get a single GBP location by resource name.

    Args:
        location_name: Full resource name (e.g., "accounts/123/locations/456").
        enable: Must be True to actually query GBP.
    """
    if not enable or not is_enabled():
        return None

    token = _get_access_token()
    if not token:
        return None

    try:
        import httpx

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        response = httpx.get(
            f"{_GBP_ENDPOINT}/{location_name}",
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()

        return _parse_gbp_location(response.json())

    except Exception:
        return None


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _parse_gbp_location(data: dict[str, Any]) -> GBPLocation:
    """Parse a GBP API location response into GBPLocation."""
    address_info = data.get("address", {})
    address_lines = address_info.get("addressLines", [])
    address_str = ", ".join(str(a) for a in address_lines) if address_lines else ""

    latlng = data.get("latlng", {})
    geo = None
    if latlng.get("latitude") and latlng.get("longitude"):
        geo = GeoCoordinates(
            latitude=float(latlng["latitude"]),
            longitude=float(latlng["longitude"]),
        )

    # Categories
    categories = []
    primary = data.get("primaryCategory", {})
    if primary.get("displayName"):
        categories.append(primary["displayName"])
    for cat in data.get("additionalCategories", []):
        if cat.get("displayName"):
            categories.append(cat["displayName"])

    # Hours
    hours = {}
    regular = data.get("regularHours", {})
    for period in regular.get("periods", []):
        day = period.get("openDay", "")
        opens = period.get("openTime", "")
        closes = period.get("closeTime", "")
        if day:
            hours[day] = f"{opens}-{closes}"

    return GBPLocation(
        name=data.get("title", ""),
        store_code=data.get("storeCode", ""),
        address=address_str,
        phone=data.get("primaryPhone", ""),
        website=data.get("websiteUri", ""),
        categories=categories,
        geo=geo,
        hours=hours,
        state=data.get("state", ""),
        raw=data,
    )

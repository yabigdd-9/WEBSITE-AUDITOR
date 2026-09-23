"""Compare schema vs visible page evidence for NAP+H fields.

Returns a list of contradiction records with status, evidence, and confidence.
Fields checked: NAME, ADDRESS, PHONE, HOURS, URL, GEO.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Literal

from .address import compare_addresses
from .hours import hours_match
from .nap import names_equivalent
from .phone import compare_phones
from .schema import (
    ConsistencyStatus,
    GeoCoordinates,
    NormalizedAddress,
    NormalizedPhone,
    OpeningHour,
)

ContradictionField = Literal["name", "address", "phone", "hours", "url", "geo"]


@dataclass(frozen=True)
class ConsistencyContradiction:
    """A single contradiction between schema and visible evidence."""

    field: ContradictionField
    status: ConsistencyStatus
    schema_value: str = ""
    visible_value: str = ""
    evidence: list[str] = field(default_factory=list)
    confidence: float = 1.0
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "status": self.status,
            "schema_value": self.schema_value,
            "visible_value": self.visible_value,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "detail": self.detail,
        }

    @property
    def is_contradiction(self) -> bool:
        return self.status == "CONTRADICTION"

    @property
    def is_consistent(self) -> bool:
        return self.status in ("MATCH", "EQUIVALENT_FORMAT", "PROBABLE_MATCH")


# ---------------------------------------------------------------------------
# Consistency check
# ---------------------------------------------------------------------------


def check_nap_consistency(
    schema_name: str = "",
    schema_address: NormalizedAddress | None = None,
    schema_phones: list[NormalizedPhone] | None = None,
    schema_hours: list[OpeningHour] | None = None,
    schema_geo: GeoCoordinates | None = None,
    schema_url: str = "",
    visible_name: str = "",
    visible_address: NormalizedAddress | None = None,
    visible_phones: list[NormalizedPhone] | None = None,
    visible_hours: list[OpeningHour] | None = None,
    visible_geo: GeoCoordinates | None = None,
    visible_url: str = "",
) -> list[ConsistencyContradiction]:
    """Check consistency between schema and visible page values.

    Returns list of contradictions. Empty list means all fields match or
    there is insufficient evidence to compare.
    """
    contradictions: list[ConsistencyContradiction] = []

    # --- Name ---
    contradictions.extend(
        _check_name(schema_name, visible_name)
    )

    # --- Address ---
    contradictions.extend(
        _check_address(schema_address, visible_address)
    )

    # --- Phone ---
    contradictions.extend(
        _check_phones(schema_phones, visible_phones)
    )

    # --- Hours ---
    contradictions.extend(
        _check_hours(schema_hours, visible_hours)
    )

    # --- URL ---
    contradictions.extend(
        _check_url(schema_url, visible_url)
    )

    # --- Geo ---
    contradictions.extend(
        _check_geo(schema_geo, visible_geo)
    )

    return contradictions


def _check_name(
    schema_name: str,
    visible_name: str,
) -> list[ConsistencyContradiction]:
    if not schema_name and not visible_name:
        return []

    if schema_name and visible_name:
        eq, status = names_equivalent(schema_name, visible_name)
        return [ConsistencyContradiction(
            field="name",
            status=status,
            schema_value=schema_name,
            visible_value=visible_name,
            confidence=0.95 if status == "CONTRADICTION" else 0.8,
            detail="Names differ beyond known equivalences",
        )]

    # One side missing
    field_name = "name"
    return [ConsistencyContradiction(
        field=field_name,
        status="INSUFFICIENT_EVIDENCE",
        schema_value=schema_name,
        visible_value=visible_name,
        confidence=0.5,
        detail="Value present in only one source",
    )]


def _check_address(
    schema_addr: NormalizedAddress | None,
    visible_addr: NormalizedAddress | None,
) -> list[ConsistencyContradiction]:
    if schema_addr and visible_addr:
        status = compare_addresses(schema_addr, visible_addr)
        return [ConsistencyContradiction(
            field="address",
            status=status,
            schema_value=schema_addr.normalized,
            visible_value=visible_addr.normalized,
            confidence=0.9 if status == "CONTRADICTION" else 0.7,
        )]

    if schema_addr or visible_addr:
        return [ConsistencyContradiction(
            field="address",
            status="INSUFFICIENT_EVIDENCE",
            schema_value=schema_addr.normalized if schema_addr else "",
            visible_value=visible_addr.normalized if visible_addr else "",
            confidence=0.5,
            detail="Address present in only one source",
        )]

    return []


def _check_phones(
    schema_phones: list[NormalizedPhone] | None,
    visible_phones: list[NormalizedPhone] | None,
) -> list[ConsistencyContradiction]:
    if not schema_phones and not visible_phones:
        return []

    if not schema_phones or not visible_phones:
        return [ConsistencyContradiction(
            field="phone",
            status="INSUFFICIENT_EVIDENCE",
            schema_value=", ".join(p.e164 or p.raw for p in (schema_phones or [])),
            visible_value=", ".join(p.e164 or p.raw for p in (visible_phones or [])),
            confidence=0.5,
            detail="Phone present in only one source",
        )]

    # Compare each schema phone against each visible phone
    results: list[ConsistencyContradiction] = []
    for sp in schema_phones:
        best_status: ConsistencyStatus = "INSUFFICIENT_EVIDENCE"
        best_vp: NormalizedPhone | None = None
        for vp in visible_phones:
            status = compare_phones(sp, vp)
            if status == "MATCH":
                best_status = "MATCH"
                best_vp = vp
                break
            if status in ("EQUIVALENT_FORMAT", "PROBABLE_MATCH"):
                best_status = status
                best_vp = vp
            elif best_status == "INSUFFICIENT_EVIDENCE":
                best_status = status
                best_vp = vp

        results.append(ConsistencyContradiction(
            field="phone",
            status=best_status,
            schema_value=sp.e164 or sp.raw,
            visible_value=best_vp.e164 or best_vp.raw if best_vp else "",
            confidence=0.9 if best_status == "CONTRADICTION" else 0.7,
        ))

    return results


def _check_hours(
    schema_hours: list[OpeningHour] | None,
    visible_hours: list[OpeningHour] | None,
) -> list[ConsistencyContradiction]:
    if not schema_hours and not visible_hours:
        return []

    if not schema_hours or not visible_hours:
        return [ConsistencyContradiction(
            field="hours",
            status="INSUFFICIENT_EVIDENCE",
            schema_value=f"{len(schema_hours or [])} rules",
            visible_value=f"{len(visible_hours or [])} rules",
            confidence=0.5,
            detail="Hours present in only one source",
        )]

    match, detail = hours_match(schema_hours, visible_hours)
    return [ConsistencyContradiction(
        field="hours",
        status="MATCH" if match else "CONTRADICTION",
        schema_value=f"{len(schema_hours)} rules",
        visible_value=f"{len(visible_hours)} rules",
        confidence=0.85,
        detail=detail,
    )]


def _check_url(
    schema_url: str,
    visible_url: str,
) -> list[ConsistencyContradiction]:
    if not schema_url and not visible_url:
        return []

    if schema_url and visible_url:
        # Normalize URLs for comparison
        norm_schema = schema_url.rstrip("/").lower()
        norm_visible = visible_url.rstrip("/").lower()

        if norm_schema == norm_visible:
            return [ConsistencyContradiction(
                field="url",
                status="MATCH",
                schema_value=schema_url,
                visible_value=visible_url,
            )]

        # Check if one is a subdomain of the other
        schema_domain = _extract_domain(norm_schema)
        visible_domain = _extract_domain(norm_visible)
        if schema_domain == visible_domain:
            return [ConsistencyContradiction(
                field="url",
                status="PROBABLE_MATCH",
                schema_value=schema_url,
                visible_value=visible_url,
                confidence=0.6,
                detail="Same domain but different paths",
            )]

        return [ConsistencyContradiction(
            field="url",
            status="CONTRADICTION",
            schema_value=schema_url,
            visible_value=visible_url,
            confidence=0.9,
            detail="Different domains",
        )]

    return [ConsistencyContradiction(
        field="url",
        status="INSUFFICIENT_EVIDENCE",
        schema_value=schema_url,
        visible_value=visible_url,
        confidence=0.5,
    )]


def _check_geo(
    schema_geo: GeoCoordinates | None,
    visible_geo: GeoCoordinates | None,
) -> list[ConsistencyContradiction]:
    if not schema_geo and not visible_geo:
        return []

    if schema_geo and visible_geo:
        distance = schema_geo.haversine_km(visible_geo)
        if distance < 0.1:  # < 100m
            status: ConsistencyStatus = "MATCH"
        elif distance < 1.0:
            status = "PROBABLE_MATCH"
        elif distance < 5.0:
            status = "EQUIVALENT_FORMAT"
        else:
            status = "CONTRADICTION"

        return [ConsistencyContradiction(
            field="geo",
            status=status,
            schema_value=f"{schema_geo.latitude:.6f},{schema_geo.longitude:.6f}",
            visible_value=f"{visible_geo.latitude:.6f},{visible_geo.longitude:.6f}",
            confidence=0.9 if status == "CONTRADICTION" else 0.7,
            detail=f"Haversine distance: {distance:.1f} km",
        )]

    return [ConsistencyContradiction(
        field="geo",
        status="INSUFFICIENT_EVIDENCE",
        schema_value=f"{schema_geo.latitude:.6f},{schema_geo.longitude:.6f}" if schema_geo else "",
        visible_value=f"{visible_geo.latitude:.6f},{visible_geo.longitude:.6f}" if visible_geo else "",
        confidence=0.5,
        detail="Geo coordinates present in only one source",
    )]


def _extract_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.hostname or ""
    except Exception:
        return url.split("/")[0] if "/" in url else url


# ---------------------------------------------------------------------------
# Finding generation
# ---------------------------------------------------------------------------


def contradictions_to_findings(
    contradictions: list[ConsistencyContradiction],
    source_url: str = "",
    page_url: str = "",
) -> list[dict[str, Any]]:
    """Convert contradictions to finding dicts for the report system."""
    findings: list[dict[str, Any]] = []

    for c in contradictions:
        if c.is_contradiction:
            finding_id = hashlib.sha256(
                f"local_seo:{c.field}:{source_url}:{page_url}".encode()
            ).hexdigest()[:24]

            findings.append({
                "finding_id": finding_id,
                "check": "local_seo_consistency",
                "defect_key": f"schema_visible_{c.field}_mismatch",
                "defect": f"Schema {c.field} contradicts visible page {c.field}",
                "impact": "high" if c.field in ("name", "address", "phone") else "medium",
                "severity": "high" if c.confidence > 0.8 else "medium",
                "source_url": source_url,
                "confidence": "high" if c.confidence > 0.8 else "medium",
                "observed": c.detail or f"Schema: {c.schema_value} | Visible: {c.visible_value}",
                "evidence_source": c.field,
                "business_impact": f"Inconsistent {c.field} may harm local search rankings",
                "review_required": True,
            })

    return findings

check_schema_visible_consistency = check_nap_consistency

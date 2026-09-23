"""External evidence corroboration.

Each external record becomes an ExternalLocalEvidence with provider, provenance,
and hash. External values are NEVER copied into the canonical record without
provenance.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .nap import names_equivalent
from .schema import ExternalLocalEvidence, GeoCoordinates


@dataclass(frozen=True)
class CorroborationResult:
    """Result of corroborating a business record against external sources."""

    evidence: list[ExternalLocalEvidence] = field(default_factory=list)
    matches: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    unmatched: list[dict[str, Any]] = field(default_factory=list)
    overall_confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence": [e.to_dict() for e in self.evidence],
            "matches": self.matches,
            "conflicts": self.conflicts,
            "unmatched": self.unmatched,
            "overall_confidence": self.overall_confidence,
        }


# ---------------------------------------------------------------------------
# Evidence creation
# ---------------------------------------------------------------------------


def create_external_evidence(
    provider: str,
    query: str,
    raw_artifact: dict[str, Any] | None = None,
    name: str = "",
    address: str = "",
    phone: str = "",
    geo: GeoCoordinates | None = None,
    categories: list[str] | None = None,
    source_confidence: float = 0.0,
    freshness: str = "",
) -> ExternalLocalEvidence:
    """Create an ExternalLocalEvidence record from external source data.

    The raw_artifact_hash is computed from the raw data to ensure provenance.
    """
    artifact_hash = ""
    if raw_artifact is not None:
        artifact_hash = hashlib.sha256(
            json.dumps(raw_artifact, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]

    evidence_id = hashlib.sha256(
        f"external:{provider}:{query}:{artifact_hash}".encode()
    ).hexdigest()[:24]

    return ExternalLocalEvidence(
        provider=provider,
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        query=query,
        name=name,
        address=address,
        phone=phone,
        geo=geo,
        categories=categories or [],
        source_confidence=source_confidence,
        freshness=freshness,
        raw_artifact_hash=artifact_hash,
        evidence_id=evidence_id,
    )


# ---------------------------------------------------------------------------
# Corroboration logic
# ---------------------------------------------------------------------------


def corroborate_record(
    canonical_name: str,
    canonical_address_normalized: str = "",
    canonical_phone_e164: str = "",
    external_records: list[ExternalLocalEvidence] | None = None,
    name_threshold: float = 0.75,
) -> CorroborationResult:
    """Compare a canonical record against external evidence sources.

    Returns matches, conflicts, and unmatched records with confidence scores.
    """

    ext_records = external_records or []

    matches: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []

    for ext in ext_records:
        comparison = _compare_external_to_canonical(
            ext,
            canonical_name,
            canonical_address_normalized,
            canonical_phone_e164,
            name_threshold,
        )

        record_dict = {
            "evidence_id": ext.evidence_id,
            "provider": ext.provider,
            "query": ext.query,
            "name": ext.name,
            "address": ext.address,
            "phone": ext.phone,
        }

        if comparison["match_score"] >= name_threshold:
            record_dict["match_score"] = comparison["match_score"]
            record_dict["details"] = comparison
            matches.append(record_dict)
        elif comparison.get("has_conflict"):
            record_dict["conflict_detail"] = comparison
            conflicts.append(record_dict)
        else:
            record_dict["match_score"] = comparison["match_score"]
            unmatched.append(record_dict)

    # Overall confidence from matches
    if matches:
        avg_score = sum(m.get("match_score", 0) for m in matches) / len(matches)
        overall = min(avg_score * 0.8 + 0.15, 1.0)  # Scale down slightly
    elif conflicts:
        overall = 0.3  # Low confidence when external sources conflict
    else:
        overall = 0.0

    return CorroborationResult(
        evidence=external_records,
        matches=matches,
        conflicts=conflicts,
        unmatched=unmatched,
        overall_confidence=round(overall, 2),
    )


def _compare_external_to_canonical(
    ext: ExternalLocalEvidence,
    canonical_name: str,
    canonical_address: str,
    canonical_phone: str,
    name_threshold: float,
) -> dict[str, Any]:
    """Compare one external record to canonical values."""
    from .address import compare_addresses, normalize_address
    from .phone import compare_phones, normalize_phone

    result: dict[str, Any] = {"match_score": 0.0}
    has_conflict = False
    components = 0
    score_sum = 0.0

    # Name
    if ext.name and canonical_name:
        eq, status = names_equivalent(ext.name, canonical_name)
        if eq:
            score = 1.0 if status == "MATCH" else (0.85 if status == "EQUIVALENT_FORMAT" else 0.7)
        else:
            score = 0.0
            has_conflict = True
        result["name_status"] = status
        result["name_equivalent"] = eq
        components += 1
        score_sum += score

    # Address
    if ext.address and canonical_address:
        ext_addr = normalize_address(ext.address)
        can_addr = normalize_address(canonical_address)
        addr_status = compare_addresses(ext_addr, can_addr)
        if addr_status in ("MATCH", "EQUIVALENT_FORMAT", "PROBABLE_MATCH"):
            score = 1.0 if addr_status == "MATCH" else 0.7
        elif addr_status == "CONTRADICTION":
            score = 0.0
            has_conflict = True
        else:
            score = 0.3
        result["address_status"] = addr_status
        components += 1
        score_sum += score

    # Phone
    if ext.phone and canonical_phone:
        ext_phone = normalize_phone(ext.phone)
        can_phone = normalize_phone(canonical_phone)
        phone_status = compare_phones(ext_phone, can_phone)
        if phone_status in ("MATCH", "EQUIVALENT_FORMAT"):
            score = 1.0 if phone_status == "MATCH" else 0.8
        elif phone_status == "CONTRADICTION":
            score = 0.0
            has_conflict = True
        else:
            score = 0.3
        result["phone_status"] = phone_status
        components += 1
        score_sum += score

    result["match_score"] = score_sum / components if components > 0 else 0.0
    result["has_conflict"] = has_conflict

    return result


# ---------------------------------------------------------------------------
# Provenance guard
# ---------------------------------------------------------------------------


def validate_external_provenance(evidence: ExternalLocalEvidence) -> bool:
    """Verify that an external evidence record has sufficient provenance."""
    if not evidence.provider:
        return False
    if not evidence.evidence_id:
        return False
    if not evidence.raw_artifact_hash and not evidence.query:
        return False
    return True


def external_value_note(
    value: str,
    source_evidence: ExternalLocalEvidence,
) -> dict[str, str]:
    """Create a provenance note when considering an external value.

    External values should NEVER be copied into canonical without this note.
    """
    return {
        "value": value,
        "source": source_evidence.provider,
        "evidence_id": source_evidence.evidence_id,
        "retrieved_at": source_evidence.retrieved_at,
        "note": "External value — not copied to canonical without review",
    }

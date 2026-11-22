"""Business identity resolution and confidence calculation.

Uses first-party evidence as the primary signal. External data is corroboration
only and never overwrites canonical identity without authorization.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from .nap import normalize_name
from .schema import (
    LocalBusinessEntity,
    NamedValue,
)

# ---------------------------------------------------------------------------
# Identity confidence features
# ---------------------------------------------------------------------------


@dataclass
class IdentityFeatures:
    name_source_count: int = 0
    address_source_count: int = 0
    phone_source_count: int = 0
    schema_visibility_match: bool = False
    rendered_source_match: bool = False
    geo_match: bool = False
    branch_relationship_confidence: float = 0.0
    source_freshness: float = 1.0
    source_independence: float = 1.0
    contradiction_count: int = 0
    evidence_count: int = 0


# ---------------------------------------------------------------------------
# Identity builder
# ---------------------------------------------------------------------------


def build_identity(
    business_id: str,
    names: list[tuple[str, str]] | None = None,
    addresses: list[tuple[str, str]] | None = None,
    phones: list[tuple[str, str]] | None = None,
    emails: list[str] | None = None,
    domain: str = "",
    schema_entities: list[dict[str, Any]] | None = None,
) -> LocalBusinessEntity:
    """Build a LocalBusinessEntity from raw evidence tuples.

    Each name/address/phone tuple is (raw_value, source).
    """
    entity = LocalBusinessEntity(
        business_id=business_id,
        canonical_domain=domain,
        domains=[domain] if domain else [],
    )
    _add_names(entity, names)
    _add_addresses(entity, business_id, addresses)
    _add_phones(entity, phones)
    entity.emails = list(emails or [])
    entity.structured_data_entities = schema_entities or []

    # Compute initial confidence
    entity.confidence = _compute_confidence(entity)

    return entity


def _add_names(entity: LocalBusinessEntity, names: list[tuple[str, str]] | None) -> None:
    if not names:
        return
    entity.names.extend(NamedValue(value=raw, source=source) for raw, source in names)
    entity.canonical_name = max(names, key=lambda item: len(item[0]))[0]


def _add_addresses(
    entity: LocalBusinessEntity,
    business_id: str,
    addresses: list[tuple[str, str]] | None,
) -> None:
    for raw, source in addresses or []:
        location = _address_to_location(business_id, raw, source)
        if location:
            entity.locations.append(location)


def _add_phones(
    entity: LocalBusinessEntity,
    phones: list[tuple[str, str]] | None,
) -> None:
    if not phones:
        return
    from .phone import normalize_phone

    seen_e164: set[str] = set()
    seen_raw: set[str] = set()
    for raw, source in phones:
        parsed = normalize_phone(raw, source=source)
        if not parsed.valid:
            continue
        dedupe_key = parsed.e164 or "".join(ch for ch in parsed.raw if ch.isdigit())
        seen = seen_e164 if parsed.e164 else seen_raw
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        entity.phones.append(parsed)


def _address_to_location(
    business_id: str,
    raw_address: str,
    source: str,
) -> Any | None:
    """Convert a raw address observation into a BusinessLocation."""
    from .address import normalize_address

    addr = normalize_address(raw_address)
    if not addr.normalized and not addr.raw:
        return None

    from .schema import BusinessLocation

    loc_id = hashlib.sha256(
        f"{business_id}|{addr.normalized}".encode()
    ).hexdigest()[:16]

    return BusinessLocation(
        location_id=loc_id,
        business_id=business_id,
        address=addr,
        evidence_ids=[f"addr:{source}"],
    )


# ---------------------------------------------------------------------------
# Confidence computation
# ---------------------------------------------------------------------------


def _compute_confidence(entity: LocalBusinessEntity) -> float:
    """Calculate identity confidence from available evidence.

    Confidence increases with:
    - Multiple independent sources
    - Schema + visible agreement
    - Valid phone
    - Valid address
    """
    score = 0.0
    max_score = 0.0

    # Name evidence
    max_score += 0.2
    if entity.names:
        score += min(0.2, len(entity.names) * 0.05)

    # Address evidence
    max_score += 0.2
    if entity.locations:
        score += min(0.2, len(entity.locations) * 0.07)

    # Phone evidence
    max_score += 0.2
    valid_phones = [p for p in entity.phones if p.valid]
    if valid_phones:
        score += min(0.2, len(valid_phones) * 0.07)

    # Schema visibility
    max_score += 0.2
    if entity.structured_data_entities:
        score += 0.15
        # Bonus if schema has visible-page counterpart
        if _schema_name_matches_visible(entity):
            score += 0.05

    # Email evidence
    max_score += 0.2
    if entity.emails:
        score += min(0.2, len(entity.emails) * 0.07)

    if max_score == 0:
        return 0.0

    return round(score / max_score, 4)


def _schema_name_matches_visible(entity: LocalBusinessEntity) -> bool:
    schema_name = next(
        (name for name in entity.names if name.source.startswith("schema")),
        None,
    )
    visible_name = next(
        (name for name in entity.names if not name.source.startswith("schema")),
        None,
    )
    if not entity.structured_data_entities or not schema_name or not visible_name:
        return False

    from .nap import names_equivalent

    equivalent, _ = names_equivalent(schema_name.value, visible_name.value)
    return equivalent


# ---------------------------------------------------------------------------
# Entity merging (with branch protection)
# ---------------------------------------------------------------------------


def merge_entities(
    primary: LocalBusinessEntity,
    secondary: LocalBusinessEntity,
    branch_relationship: str = "",
) -> LocalBusinessEntity:
    """Merge two entities with branch-parent awareness.

    Never auto-merge when branch_relationship is set to "parent" or "child".
    """
    if branch_relationship in ("parent", "child"):
        # Keep separate; just link them
        secondary.branch_relationship = branch_relationship
        secondary.parent_entity_id = primary.business_id
        return primary  # Don't merge

    _merge_names(primary, secondary)
    _merge_unique_values(primary.locations, secondary.locations, lambda item: item.location_id)
    _merge_unique_values(primary.phones, secondary.phones, lambda item: item.e164, keep_empty=True)
    _merge_unique_values(primary.emails, secondary.emails, lambda item: item)
    _merge_unique_values(primary.domains, secondary.domains, lambda item: item)

    # Recalculate confidence
    primary.confidence = _compute_confidence(primary)

    return primary


def _merge_names(primary: LocalBusinessEntity, secondary: LocalBusinessEntity) -> None:
    existing_names = {normalize_name(name.value) for name in primary.names}
    for name in secondary.names:
        normalized = normalize_name(name.value)
        if normalized not in existing_names:
            primary.names.append(name)
            existing_names.add(normalized)


def _merge_unique_values(
    primary: list[Any],
    secondary: list[Any],
    key: Any,
    keep_empty: bool = False,
) -> None:
    existing = {key(item) for item in primary}
    for item in secondary:
        value = key(item)
        if (keep_empty and not value) or value not in existing:
            primary.append(item)
            existing.add(value)

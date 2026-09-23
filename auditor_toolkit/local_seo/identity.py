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

    # Names — pick canonical, store all variants
    if names:
        for raw, source in names:
            entity.names.append(NamedValue(value=raw, source=source))
        # Most frequent / longest name becomes canonical
        canonical = max(names, key=lambda x: len(x[0]))
        entity.canonical_name = canonical[0]

    # Addresses
    if addresses:
        for raw, source in addresses:
            loc = _address_to_location(business_id, raw, source)
            if loc:
                entity.locations.append(loc)

    # Phones
    if phones:
        from .phone import normalize_phone

        seen_e164: set[str] = set()
        seen_raw: set[str] = set()
        for raw, source in phones:
            parsed = normalize_phone(raw, source=source)
            if not parsed.valid:
                continue
            if parsed.e164:
                if parsed.e164 in seen_e164:
                    continue
                seen_e164.add(parsed.e164)
            else:
                normalized_raw = "".join(ch for ch in parsed.raw if ch.isdigit())
                if normalized_raw in seen_raw:
                    continue
                seen_raw.add(normalized_raw)
            entity.phones.append(parsed)

    # Emails
    if emails:
        entity.emails = list(emails)

    # Schema entities
    if schema_entities:
        entity.structured_data_entities = schema_entities

    # Compute initial confidence
    entity.confidence = _compute_confidence(entity)

    return entity


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
        if entity.names and any(
            n.source.startswith("schema") for n in entity.names
        ):
            schema_name = next(
                (n for n in entity.names if n.source.startswith("schema")),
                None,
            )
            visible_name = next(
                (n for n in entity.names if not n.source.startswith("schema")),
                None,
            )
            if schema_name and visible_name:
                from .nap import names_equivalent

                eq, _ = names_equivalent(schema_name.value, visible_name.value)
                if eq:
                    score += 0.05  # Match bonus

    # Email evidence
    max_score += 0.2
    if entity.emails:
        score += min(0.2, len(entity.emails) * 0.07)

    if max_score == 0:
        return 0.0

    return round(score / max_score, 4)


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

    # Merge names (deduplicate)
    existing_norms = {normalize_name(n.value) for n in primary.names}
    for name in secondary.names:
        norm = normalize_name(name.value)
        if norm not in existing_norms:
            primary.names.append(name)
            existing_norms.add(norm)

    # Merge locations
    existing_loc_ids = {loc.location_id for loc in primary.locations}
    for loc in secondary.locations:
        if loc.location_id not in existing_loc_ids:
            primary.locations.append(loc)
            existing_loc_ids.add(loc.location_id)

    # Merge phones (deduplicate by e164)
    existing_e164 = {p.e164 for p in primary.phones if p.e164}
    for phone in secondary.phones:
        if not phone.e164 or phone.e164 not in existing_e164:
            primary.phones.append(phone)
            if phone.e164:
                existing_e164.add(phone.e164)

    # Merge emails
    existing_emails = set(primary.emails)
    for email in secondary.emails:
        if email not in existing_emails:
            primary.emails.append(email)
            existing_emails.add(email)

    # Merge domains
    existing_domains = set(primary.domains)
    for domain in secondary.domains:
        if domain not in existing_domains:
            primary.domains.append(domain)
            existing_domains.add(domain)

    # Recalculate confidence
    primary.confidence = _compute_confidence(primary)

    return primary

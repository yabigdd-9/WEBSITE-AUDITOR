"""Local Business SEO + Entity/NAP Intelligence.

P2-002 / v38: audits whether a website presents a local business
consistently and correctly to users, search engines, and geographic systems.
"""

from .schema import (
    BusinessLocation,
    ExternalLocalEvidence,
    LocalBusinessEntity,
)

__all__ = [
    "BusinessLocation",
    "ExternalLocalEvidence",
    "LocalBusinessEntity",
]

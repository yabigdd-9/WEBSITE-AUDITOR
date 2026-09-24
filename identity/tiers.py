"""
Authoritative identity tiers implementation.
"""

from enum import Enum

class IdentityTier(Enum):
    T1 = "T1"  # authoritative identifier
    T2 = "T2"  # strong multi-signal
    T3 = "T3"  # corroborated
    T4 = "T4"  # fuzzy review only

def evaluate_tier(evidence: dict) -> IdentityTier:
    """
    Determine identity tier based on evidence.
    T1: authoritative identifier (NZBN, company number)
    T2: strong multi-signal (legal name, trading name, domain, address, phone)
    T3: corroborated (region, category, official social)
    T4: fuzzy review only
    """
    # Placeholder logic
    if evidence.get('nzbn') or evidence.get('company_number'):
        return IdentityTier.T1
    strong_signals = ['legal_name', 'trading_name', 'domain', 'address', 'phone']
    strong_count = sum(1 for s in strong_signals if evidence.get(s))
    if strong_count >= 3:
        return IdentityTier.T2
    corroborative = ['region', 'category', 'official_social']
    coro_count = sum(1 for c in corroborative if evidence.get(c))
    if coro_count >= 2:
        return IdentityTier.T3
    return IdentityTier.T4
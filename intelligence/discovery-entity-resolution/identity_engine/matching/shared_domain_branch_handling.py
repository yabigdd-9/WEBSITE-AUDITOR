# Shared-domain branch handling
# Identify branch relationships based on shared registrable domain.

from .domain_normalization import get_registrable_domain

def is_shared_domain_branch(domain1: str, domain2: str) -> bool:
    """Return True if two domains share the same registrable domain but have different subdomains.
    This indicates a potential parent/branch or subsidiary relationship.
    """
    if not domain1 or not domain2:
        return False

    reg1 = get_registrable_domain(domain1)
    reg2 = get_registrable_domain(domain2)

    # Must share the same registrable domain and not be the exact same domain
    if reg1 and reg2 and reg1 == reg2 and domain1 != domain2:
        return True
    return False
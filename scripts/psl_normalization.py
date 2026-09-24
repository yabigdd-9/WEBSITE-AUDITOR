"""
PSL (Public Suffix List) normalization for domain names.
"""

import publicsuffix2
from typing import Optional

def normalize_domain(domain: str) -> Optional[str]:
    """
    Return the registrable domain using the Public Suffix List.
    Returns None if domain is invalid or cannot be normalized.
    """
    try:
        # publicsuffix2 library loads PSL from built-in data or file
        psl = publicsuffix2.PublicSuffixList()
        registrable = psl.get_public_suffix(domain)
        if registrable:
            # The registrable domain is the domain part before the public suffix
            # Actually, we want the domain registrable: e.g., www.example.co.nz -> example.co.nz
            # publicsuffix2.get_public_suffix returns the suffix, so we need to subtract.
            # Let's use get_registrable_domain if available.
            # publicsuffix2 also has get_registrable_domain
            return publicsuffix2.PublicSuffixList().get_registrable_domain(domain)
        else:
            return None
    except Exception:
        return None

def is_registerable_domain(domain: str) -> bool:
    """Check if domain is a registrable domain (i.e., not a subdomain of a public suffix)."""
    try:
        psl = publicsuffix2.PublicSuffixList()
        return psl.is_public_suffix(domain) == False and psl.get_registrable_domain(domain) == domain
    except Exception:
        return False
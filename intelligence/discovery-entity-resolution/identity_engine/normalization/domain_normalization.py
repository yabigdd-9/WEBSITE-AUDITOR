# PSL-backed domain normalization
# Load public suffix list and provide registrable domain extraction.

import pandas as pd
from functools import lru_cache

# Path to the public suffix list Parquet file (placeholder)
PSL_PATH = "data/parquet/public_suffix_list/data.parquet"

@lru_cache(maxsize=1)
def load_psl():
    """Load the public suffix list from Parquet.
    Returns a set of suffixes.
    """
    try:
        df = pd.read_parquet(PSL_PATH)
        # Assuming the Parquet file has a column 'suffix' or similar.
        # Adjust based on actual structure.
        if 'suffix' in df.columns:
            return set(df['suffix'].astype(str).tolist())
        else:
            # Fallback: try first column
            return set(df.iloc[:, 0].astype(str).tolist())
    except Exception:
        # If file not found or error, return an empty set (will cause fallback to no normalization)
        return set()

def get_registrable_domain(hostname: str) -> str:
    """Extract registrable domain from hostname using PSL.
    Args:
        hostname: e.g., 'www.example.co.nz'
    Returns:
        Registrable domain: e.g., 'example.co.nz'
    """
    if not hostname:
        return ""
    hostname = hostname.lower().strip('.')
    parts = hostname.split('.')
    if len(parts) <= 1:
        return hostname
    psl = load_psl()
    # Iterate from the end to find the longest matching suffix
    for i in range(len(parts)):
        candidate = '.'.join(parts[i:])
        if candidate in psl:
            # Found a suffix, registrable domain is one level above if exists
            if i > 0:
                return '.'.join(parts[i-1:])
            else:
                # The hostname itself is a suffix (should not happen for normal domains)
                return candidate
    # No match found, return the hostname (fallback)
    return hostname
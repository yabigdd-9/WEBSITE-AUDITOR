"""Tier 1 external enrichment for the Website Auditor.

Keyless-first (W3C, SSL Labs read-only, local header grader), key-optional
(PageSpeed Insights, RankNibbler). stdlib + httpx only. Never touches the
deterministic auditors — it only *adds* an ``enrichment`` section.
"""

from integrations.tier1_enrichment.cache import EnrichmentCache
from integrations.tier1_enrichment.enrich import enrich_audit
from integrations.tier1_enrichment.graders import grade_security_headers
from integrations.tier1_enrichment.sources import (
    check_pagespeed,
    check_ranknibbler,
    check_ssllabs,
    check_urlscan_search,
    check_w3c,
)

__all__ = [
    "EnrichmentCache",
    "enrich_audit",
    "grade_security_headers",
    "check_pagespeed",
    "check_ranknibbler",
    "check_ssllabs",
    "check_urlscan_search",
    "check_w3c",
]

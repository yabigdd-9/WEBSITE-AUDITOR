"""Technology enrichment pipeline."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from .fingerprints import fingerprint
from .schema import TechEnrichmentResult, TechFingerprint, TechStack
from .versions import detect_version
from .vulns import check_vulnerabilities


def enrich_technology(
    html: str,
    url: str = "",
    headers: dict[str, str] | None = None,
    run_id: str = "",
) -> TechEnrichmentResult:
    """Run full technology enrichment pipeline on website content."""
    started = time.monotonic()
    started_at = datetime.now(UTC).isoformat()
    errors: list[str] = []

    try:
        fp = fingerprint(html, headers)
    except Exception as e:
        fp = TechFingerprint()
        errors.append(f"Fingerprint detection failed: {e}")

    versions = []
    for det in fp.all_detections:
        try:
            v = detect_version(det.name, html, headers)
            versions.append(v)
        except Exception as e:
            errors.append(f"Version detection failed for {det.name}: {e}")

    advisories = []
    try:
        stack = TechStack(fingerprint=fp, versions=versions)
        advisories = check_vulnerabilities(stack)
    except Exception as e:
        errors.append(f"Vulnerability check failed: {e}")

    return TechEnrichmentResult(
        url=url,
        fingerprint=fp,
        versions=versions,
        vulnerabilities=advisories,
        run_id=run_id,
        started_at=started_at,
        completed_at=datetime.now(UTC).isoformat(),
        duration_seconds=time.monotonic() - started,
        errors=errors,
    )

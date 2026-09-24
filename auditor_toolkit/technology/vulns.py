"""Vulnerability advisory generation from outdated components."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from .schema import TechStack, VulnerabilityAdvisory

_ADVISORY_DB: list[dict[str, str]] = [
    {"component": "WordPress", "cve_id": "CVE-2023-4774", "affected_below": "6.3.2", "severity": "high", "description": "Stored XSS in WordPress post editor.", "remediation": "Update to WordPress 6.3.2 or later."},
    {"component": "WordPress", "cve_id": "CVE-2023-3998", "affected_below": "6.3", "severity": "critical", "description": "Privilege escalation in WordPress core.", "remediation": "Update to WordPress 6.3 or later."},
    {"component": "jQuery", "cve_id": "CVE-2020-11023", "affected_below": "3.5.0", "severity": "medium", "description": "XSS vulnerability in jQuery.htmlPrefilter.", "remediation": "Update jQuery to 3.5.0 or later."},
]


def _vt(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)) if v else (0,)


def get_advisories(component: str, version: str) -> list[VulnerabilityAdvisory]:
    results = []
    for entry in _ADVISORY_DB:
        if entry["component"].lower() == component.lower() and _vt(version) < _vt(entry.get("affected_below", "")):
            results.append(VulnerabilityAdvisory(component=component, version=version, severity=entry["severity"], description=entry["description"], remediation=entry["remediation"], cve_id=entry.get("cve_id", ""), detected_at=datetime.now(UTC).isoformat()))
    return results


def check_vulnerabilities(stack: TechStack) -> list[VulnerabilityAdvisory]:
    advisories = []
    for v in stack.versions:
        if v.detected_version and v.is_outdated:
            advisories.extend(get_advisories(v.name, v.detected_version))
    return advisories

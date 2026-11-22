"""Version detection and outdated component checking."""

from __future__ import annotations

import re

from .schema import VersionInfo

_KNOWN_VERSIONS: dict[str, dict[str, str]] = {
    "WordPress": {"latest": "6.4"},
    "jQuery": {"latest": "3.7.1"},
    "React": {"latest": "18.2"},
    "Bootstrap": {"latest": "5.3"},
    "PHP": {"latest": "8.3"},
    "nginx": {"latest": "1.25"},
}

_VERSION_PATTERNS: dict[str, list[str]] = {
    "WordPress": [
        r'<meta\s+name="generator"\s+content="WordPress\s+([\d.]+)"',
        r'style\.min\.css\?ver=([\d.]+)',
    ],
    "jQuery": [
        r'jquery.*ver=([\d.]+)',
        r'jquery-([\d.]+)\.min\.js',
    ],
    "React": [r'react@([\d.]+)'],
    "Bootstrap": [r'bootstrap.*([\d.]+)\.min'],
}


def _version_tuple(v: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", v)
    return tuple(int(x) for x in parts) if parts else (0,)


def _is_outdated(detected: str, latest: str) -> bool:
    if not detected or not latest:
        return False
    return _version_tuple(detected) < _version_tuple(latest)


def _outdated_severity(detected: str, latest: str) -> str:
    try:
        d = _version_tuple(detected)
        lt = _version_tuple(latest)
        if d[0] < lt[0]:
            return "critical"
        if len(d) > 1 and len(lt) > 1 and d[1] < lt[1] - 1:
            return "high"
        return "medium"
    except (IndexError, ValueError):
        return "medium"


def _extract_version(tech_name: str, html: str = "", headers: dict[str, str] | None = None) -> str:
    source = html
    if headers:
        source += " " + " ".join(f"{k}: {v}" for k, v in headers.items())
    for p in _VERSION_PATTERNS.get(tech_name, []):
        m = re.search(p, source, re.IGNORECASE)
        if m:
            return m.group(1)
    return ""


def detect_version(
    tech_name: str,
    html: str = "",
    headers: dict[str, str] | None = None,
    known_version: str = "",
) -> VersionInfo:
    detected = known_version or _extract_version(tech_name, html, headers)
    latest = _KNOWN_VERSIONS.get(tech_name, {}).get("latest", "")
    is_outdated = _is_outdated(detected, latest)
    severity = _outdated_severity(detected, latest) if is_outdated else "low"
    return VersionInfo(
        name=tech_name,
        detected_version=detected,
        latest_version=latest,
        is_outdated=is_outdated,
        severity=severity,
    )


def check_outdated(versions: list[VersionInfo]) -> list[VersionInfo]:
    return [v for v in versions if v.is_outdated]

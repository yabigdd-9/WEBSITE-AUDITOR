"""Canonical domain + identity helpers (deterministic, offline-first).

canonical_domain() collapses a URL/host to its registered domain (eTLD+1), stripping
scheme, port, path, query and the ``www.`` prefix, and any subdomains. NZ multi-part
suffixes (``co.nz``, ``org.nz``, ``net.nz``, ...) are handled without a network fetch so
results are deterministic and reproducible offline.

Examples::

    canonical_domain("https://WWW.Example.CO.NZ/path?q=1") -> "example.co.nz"
    canonical_domain("http://sub.example.com:8080/x")      -> "example.com"
    canonical_domain("foo.co.nz")                          -> "foo.co.nz"
"""
from __future__ import annotations

import re as _re

# Multi-part public suffixes common in NZ/AU/UK & similar. Longest match wins.
_SECOND_LEVEL = {
    "co", "com", "net", "org", "gov", "govt", "ac", "edu", "mil", "gen", "biz",
    "info", "asn", "id", "school", "health", "iwi", "maori", "parliament", "cri",
}

_HOST_RE = _re.compile(r"^[a-z0-9]([a-z0-9\-\.]*[a-z0-9])?$")


def _strip_to_host(raw: str) -> str:
    u = raw.lower().strip()
    u = _re.sub(r"^[a-z][a-z0-9+.\-]*://", "", u)  # any scheme
    u = u.split("/")[0].split("?")[0].split("#")[0]
    u = u.split("@")[-1]  # strip userinfo
    u = u.split(":")[0]  # strip port
    return u.strip(" .")


def canonical_domain(raw: str) -> str:
    host = _strip_to_host(raw)
    if not host or not _HOST_RE.match(host):
        return host
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    suffix = labels[-1]
    # e.g. example.co.nz -> domain "example", suffix "co.nz"
    if len(labels) >= 3 and labels[-2] in _SECOND_LEVEL and len(suffix) == 2:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def registered_domain(raw: str) -> str:
    """Alias for canonical_domain (eTLD+1)."""
    return canonical_domain(raw)


def hostname(raw: str) -> str:
    """Full host with only scheme/port/path/query/userinfo stripped (subdomains kept)."""
    return _strip_to_host(raw)


def domain_group(raw: str) -> str:
    return canonical_domain(raw)


def same_entity(a: str, b: str) -> bool:
    return canonical_domain(a) == canonical_domain(b)

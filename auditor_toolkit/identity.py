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


IDENTITY_WEIGHTS = {
    "domain_name_match": 0.20,
    "website_brand_match": 0.18,
    "nzbn_match": 0.30,
    "email_domain_match": 0.14,
    "region_match": 0.08,
    "address_match": 0.05,
    "phone_match": 0.05,
}


def identity_confidence(signals: dict[str, bool | None]) -> dict:
    """Return a deterministic, inspectable identity confidence assessment.

    Unknown signals contribute no confidence. Explicit conflicts reduce confidence
    by half of that signal's weight. NZBN is the strongest signal, but no single
    weak string/domain match can produce outreach-grade identity confidence.
    """
    unknown = set(signals) - set(IDENTITY_WEIGHTS)
    if unknown:
        raise ValueError("Unknown identity signals: " + ", ".join(sorted(unknown)))

    positives = {}
    conflicts = {}
    score = 0.0
    observed_weight = 0.0
    for name, weight in IDENTITY_WEIGHTS.items():
        value = signals.get(name)
        if value is None:
            continue
        observed_weight += weight
        if value is True:
            positives[name] = weight
            score += weight
        elif value is False:
            conflicts[name] = weight
            score -= weight * 0.5
        else:
            raise ValueError(f"{name} must be true, false or null")

    score = max(0.0, min(1.0, score))
    critical_conflict = any(
        name in conflicts for name in ("nzbn_match", "domain_name_match", "website_brand_match")
    )
    if score >= 0.80 and not critical_conflict and len(positives) >= 3:
        status = "HIGH"
    elif score >= 0.60 and not critical_conflict and len(positives) >= 2:
        status = "MEDIUM"
    elif score >= 0.35:
        status = "REVIEW"
    else:
        status = "LOW"

    return {
        "version": "identity-v1",
        "confidence": round(score, 4),
        "status": status,
        "outreach_identity_eligible": status == "HIGH",
        "positive_signals": sorted(positives),
        "conflicts": sorted(conflicts),
        "unknown_signals": sorted(set(IDENTITY_WEIGHTS) - set(signals)),
        "observed_weight": round(observed_weight, 4),
        "weights": dict(IDENTITY_WEIGHTS),
    }


def assess_business_identity(
    *,
    business_name: str,
    website: str,
    legal_name: str | None = None,
    trading_name: str | None = None,
    nzbn_name: str | None = None,
    email: str | None = None,
    region_match: bool | None = None,
    address_match: bool | None = None,
    phone_match: bool | None = None,
    website_brand_match: bool | None = None,
) -> dict:
    """Build P7 identity signals from explicit evidence, then score them.

    Name/domain matching is deliberately conservative. Callers must pass location,
    address, phone and website-brand observations from captured evidence.
    """

    def norm(value: str | None) -> str:
        value = (value or "").casefold()
        value = _re.sub(r"\b(?:limited|ltd|company|co|the)\b", " ", value)
        return " ".join(_re.findall(r"[a-z0-9]+", value))

    expected_names = {norm(x) for x in (business_name, legal_name, trading_name) if norm(x)}
    nzbn_match = None if not nzbn_name else norm(nzbn_name) in expected_names

    domain = canonical_domain(website)
    stem = domain.split(".")[0] if domain else ""
    name_tokens = {token for name in expected_names for token in name.split()}
    domain_name_match = bool(stem and stem in name_tokens) if name_tokens else None

    email_domain_match = None
    if email:
        if "@" not in email:
            email_domain_match = False
        else:
            email_domain_match = canonical_domain(email.rsplit("@", 1)[1]) == domain

    signals = {
        "domain_name_match": domain_name_match,
        "website_brand_match": website_brand_match,
        "nzbn_match": nzbn_match,
        "email_domain_match": email_domain_match,
        "region_match": region_match,
        "address_match": address_match,
        "phone_match": phone_match,
    }
    result = identity_confidence(signals)
    result.update(
        {
            "business_name": business_name,
            "legal_name": legal_name,
            "trading_name": trading_name,
            "canonical_domain": domain,
            "signals": signals,
        }
    )
    return result

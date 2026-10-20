"""One passive signature interpreter, shared by canonical and legacy adapters."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any

from bs4 import BeautifulSoup

from .signatures import RULES

METHOD = "passive-technology-signatures-v2"
MAX_HTML_CHARACTERS = 8 * 1024 * 1024
MAX_CONTEXT_ELEMENTS = 10000
MAX_SIGNAL_RECORDS = 20000
COMPILED_RULES = tuple(
    (name, category, scope, re.compile(pattern, re.I), origin)
    for name, category, scope, pattern, origin in RULES
)


def _headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    if headers is None:
        return {}
    if not isinstance(headers, Mapping):
        raise ValueError("Technology headers must be a string mapping")
    values: dict[str, list[str]] = {}
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError("Technology header names and values must be strings")
        values.setdefault(key.lower(), []).append(value)
    return {key: "\n".join(sorted(set(parts))) for key, parts in sorted(values.items())}


def _legacy_weight(category: str, count: int) -> float:
    if category == "cms":
        return min(0.6 + count * 0.12, 0.99)
    if category == "framework":
        return min(0.5 + count * 0.15, 0.95)
    return {
        "analytics": 0.9,
        "server": 0.85,
        "cdn": 0.85,
        "ecommerce": 0.85,
        "payment": 0.85,
        "language": 0.8,
    }.get(category, 0.6)


def observe_technologies(
    html: str, headers: Mapping[str, str] | None = None, url: str = ""
) -> list[dict[str, Any]]:
    """Return linked signature clues, never active probes, installed-version proof or CVEs."""
    if not isinstance(html, str) or len(html) > MAX_HTML_CHARACTERS:
        raise ValueError("Technology analysis requires HTML within the declared character limit")
    normalized_headers = _headers(headers)
    header_text = "\n".join(f"{name}: {value}" for name, value in normalized_headers.items())
    soup = BeautifulSoup(html, "html.parser")
    generators = [
        tag.get("content")
        for tag in soup.find_all("meta")
        if isinstance(tag.get("name"), str)
        and tag.get("name").lower() == "generator"
        and isinstance(tag.get("content"), str)
    ]
    scripts = [tag.get("src") for tag in soup.find_all("script") if isinstance(tag.get("src"), str)]
    styles = [tag.get("href") for tag in soup.find_all("link") if isinstance(tag.get("href"), str)]
    if len(generators) + len(scripts) + len(styles) > MAX_CONTEXT_ELEMENTS:
        raise ValueError("Technology context element limit exceeded; coverage is incomplete")
    contexts = {
        "html": [("html", html)],
        "headers": [("headers", header_text)],
        "html_and_headers": [("html", html), ("headers", header_text)],
        "generator": [
            (f"meta:generator[{index}]", value) for index, value in enumerate(generators, 1)
        ],
        "script_src": [(f"script:src[{index}]", value) for index, value in enumerate(scripts, 1)],
        "stylesheet_href": [
            (f"link:href[{index}]", value) for index, value in enumerate(styles, 1)
        ],
    }
    groups: dict[tuple[str, str], list[dict[str, str]]] = {}
    signal_count = 0
    seen_signals = set()
    input_hashes = {}
    for name, category, scope, pattern, origin in COMPILED_RULES:
        if scope.startswith("header:"):
            key = scope.split(":", 1)[1]
            inputs = [(scope, normalized_headers[key])] if key in normalized_headers else []
        else:
            inputs = contexts[scope]
        for location, value in inputs:
            match = pattern.search(value)
            if not match:
                continue
            # Retain the matched clue, not entire cookies or unrelated header values.
            clue = (
                "nonempty header"
                if scope.startswith("header:") and pattern.pattern == ".+"
                else match.group(0)[:160]
            )
            if location == "headers":
                clue = "header signature matched; raw value withheld"
            signal_key = (name, category, location, pattern.pattern, origin)
            if signal_key in seen_signals:
                continue
            seen_signals.add(signal_key)
            signal_count += 1
            if signal_count > MAX_SIGNAL_RECORDS:
                raise ValueError("Technology signal limit exceeded; coverage is incomplete")
            if location not in input_hashes:
                input_hashes[location] = hashlib.sha256(value.encode()).hexdigest()
            signal = {
                "input": location,
                "pattern": pattern.pattern,
                "matched_clue": clue,
                "original_rule_source": origin,
                "source_url": url,
                "input_sha256": input_hashes[location],
            }
            signals = groups.setdefault((name, category), [])
            signals.append(signal)
    records = []
    html_hash = hashlib.sha256(html.encode()).hexdigest()
    for (name, category), signals in groups.items():
        weight = _legacy_weight(category, len({signal["pattern"] for signal in signals}))
        version_claims = []
        if name == "WordPress":
            for generator in generators:
                match = re.search(r"wordpress\s+([0-9]+(?:\.[0-9]+)*)", generator, re.I)
                if match and match.group(1) not in version_claims:
                    version_claims.append(match.group(1))
        version = version_claims[0] if len(version_claims) == 1 else None
        records.append(
            {
                "name": name,
                "category": category,
                "method": METHOD,
                "confidence": weight,
                "confidence_calibrated": False,
                "confidence_basis": "preserved signature weighting; not a probability",
                "version": version,
                "version_confidence": 0.9 if version else 0.0,
                "version_claims": version_claims,
                "version_status": "numeric_generator_token_unverified"
                if version
                else "unknown_or_ambiguous",
                "evidence": "; ".join(
                    f"{signal['input']}: {signal['matched_clue']}" for signal in signals[:3]
                ),
                "signals": signals,
                "html_sha256": html_hash,
                "source_url": url,
                "installation_confirmed": False,
                "vulnerability_assessed": False,
            }
        )
    return sorted(records, key=lambda row: (row["category"], row["name"].casefold()))

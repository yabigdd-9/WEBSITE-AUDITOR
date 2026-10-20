"""Offline trading-name proposals from hash-verified public page captures.

This command never verifies identity, edits CRM data, selects contacts or grants
outreach permission. Captures and metadata are untrusted input. Their checksums
bind local evidence; they do not authenticate a business or its website.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

import tldextract
from bs4 import BeautifulSoup

VERSION = "identity-name-proposals-v1"
MAX_CASES = 50
MAX_CASE_BYTES = 2_000_000
MAX_CAPTURE_BYTES = 3_000_000
PSL = tldextract.TLDExtract(
    suffix_list_urls=(), cache_dir=None, include_psl_private_domains=True
)
ORGANISATION_TYPES = {
    "Organization", "Corporation", "LocalBusiness", "ProfessionalService",
    "HomeAndConstructionBusiness", "HVACBusiness", "Electrician", "Plumber",
    "GeneralContractor", "RoofingContractor", "Store", "RealEstateAgent",
}


def _norm(value: str) -> str:
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", value).casefold()))


def _domain(url: str) -> tuple[str, str]:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().rstrip(".")
    if (
        parts.scheme not in {"http", "https"} or not host
        or parts.username or parts.password or parts.port not in {None, 80, 443}
        or any(ord(c) < 32 for c in url)
        or host == "localhost" or host.endswith((".local", ".internal", ".test", ".invalid"))
    ):
        raise ValueError("Public HTTP(S) URL without credentials required")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("IP-address website is not a business-domain input")
    parsed = PSL(host)
    if not parsed.suffix or not parsed.domain:
        raise ValueError("Registered website domain required")
    return host, parsed.top_domain_under_public_suffix


def _organisations(value, depth=0) -> set[str]:
    if depth > 32:
        return set()
    found = set()
    if isinstance(value, list):
        for item in value:
            found.update(_organisations(item, depth + 1))
    elif isinstance(value, dict):
        types = value.get("@type", [])
        if isinstance(types, str):
            types = [types]
        if isinstance(types, list):
            kinds = {t.rsplit("/", 1)[-1].rsplit("#", 1)[-1] for t in types if isinstance(t, str)}
            name = value.get("name")
            if kinds & ORGANISATION_TYPES and isinstance(name, str):
                name = " ".join(name.split())
                if 2 <= len(name) <= 250 and _norm(name):
                    found.add(name)
        for item in value.values():
            if isinstance(item, (dict, list)):
                found.update(_organisations(item, depth + 1))
    return found


def _bounded_bytes(path: Path, limit: int) -> bytes:
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Evidence file exceeds byte limit")
    return raw


def _page(root: Path, metadata: dict, domain: str) -> dict:
    if not isinstance(metadata, dict):
        raise ValueError("Page metadata must be an object")
    digest = metadata.get("sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("Capture SHA-256 required")
    capture_root = root / "cache/email-v2"
    path = (root / str(metadata.get("path", ""))).resolve()
    if not path.is_relative_to(capture_root) or path.name != digest + ".capture":
        raise ValueError("Capture must be a content-addressed file inside the capture directory")
    url = metadata.get("url")
    if not isinstance(url, str) or _domain(url)[1] != domain:
        raise ValueError("Capture URL does not match the recorded website domain")
    raw = _bounded_bytes(path, MAX_CAPTURE_BYTES)
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("Capture checksum mismatch")
    if not str(metadata.get("content_type", "")).lower().startswith("text/html"):
        raise ValueError("HTML page capture required for name proposals")
    soup = BeautifulSoup(raw, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    headings = [node.get_text(" ", strip=True) for node in soup.find_all("h1")]
    names = set()
    for node in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            names.update(_organisations(json.loads(node.get_text())))
        except (ValueError, RecursionError):
            continue
    return {
        "url": url, "sha256": digest, "captured_at": metadata.get("captured_at"),
        "title": title, "headings": headings, "organisation_names": sorted(names),
    }


def _case(root: Path, path: Path) -> dict:
    if not path.resolve().is_relative_to(root / "cases"):
        raise ValueError("Case file escapes the capture directory")
    raw = _bounded_bytes(path, MAX_CASE_BYTES)
    doc = json.loads(raw)
    business = doc.get("business") if isinstance(doc, dict) else None
    if not isinstance(business, dict):
        raise ValueError("Business metadata required")
    name = business.get("name")
    website = business.get("public_website")
    if not isinstance(name, str) or not isinstance(website, str):
        raise ValueError("Recorded business name and website required")
    host, domain = _domain(website)
    metadata = doc.get("pages")
    if not isinstance(metadata, list) or len(metadata) > 5:
        raise ValueError("At most five page records per case allowed")
    pages, errors = [], []
    for item in metadata:
        try:
            page = _page(root, item, domain)
            if not any(p["url"] == page["url"] or p["sha256"] == page["sha256"] for p in pages):
                pages.append(page)
        except (ValueError, OSError) as exc:
            errors.append(str(exc))
    normal_names = {}
    for page in pages:
        for candidate in page["organisation_names"]:
            normal_names.setdefault(_norm(candidate), candidate)
    matches = {}
    for normal, candidate in sorted(normal_names.items()):
        supports = [p for p in pages if any(_norm(n) == normal for n in p["organisation_names"])]
        prominent = [p for p in pages if any(
            " " + normal + " " in " " + _norm(text) + " "
            for text in [p["title"], *p["headings"]]
        )]
        if len(supports) >= 2 and prominent:
            matches[candidate] = supports
    stub = name.casefold().strip().removeprefix("www.").rstrip(".")
    is_domain_placeholder = stub in {host.removeprefix("www."), domain}
    status = "HUMAN_REVIEW_REQUIRED"
    proposed = None
    reasons = []
    if errors:
        reasons.append("One or more evidence records failed validation; proposal held")
    elif not is_domain_placeholder or business.get("trading_name"):
        reasons.append("A business or trading name is already supplied; no replacement proposed")
    elif len(normal_names) > 1:
        reasons.append("Multiple organisation names occur in the captured evidence")
    elif len(matches) != 1:
        reasons.append("A unique organisation name needs two distinct captures and a title/H1 match")
    else:
        proposed = next(iter(matches))
        status = "PROPOSAL_READY_FOR_REVIEW"
        reasons.append("One organisation name occurs in two distinct captures and a page title/H1")
    return {
        "case_id": business.get("id"), "case_file": path.name,
        "case_sha256": hashlib.sha256(raw).hexdigest(),
        "recorded_name": name, "website": website,
        "status": status, "proposed_trading_name": proposed,
        "observed_organisation_names": sorted(normal_names.values()),
        "evidence": pages, "evidence_errors": errors, "reasons": reasons,
        "human_confirmed": False, "identity_verified": False,
        "canonical_database_changed": False, "outreach_eligible": False,
    }


def build_identity_review(captures_root) -> dict:
    root = Path(captures_root).resolve()
    cases_dir = root / "cases"
    if not cases_dir.resolve().is_relative_to(root) or not cases_dir.is_dir():
        raise ValueError("Captures directory must contain a cases directory")
    paths = sorted(cases_dir.glob("*.json"))
    if not 1 <= len(paths) <= MAX_CASES:
        raise ValueError("Between one and fifty case files required")
    cases = []
    for path in paths:
        try:
            cases.append(_case(root, path))
        except (ValueError, OSError, RecursionError) as exc:
            cases.append({"case_file": path.name, "status": "INVALID_EVIDENCE", "reason": str(exc),
                          "human_confirmed": False, "identity_verified": False,
                          "canonical_database_changed": False, "outreach_eligible": False})
    return {
        "kind": "identity_name_review", "version": VERSION,
        "case_count": len(cases), "status_counts": dict(Counter(c["status"] for c in cases)),
        "cases": cases, "review_required": True, "production_applied": False,
        "human_confirmed": False, "external_sends": 0, "paid_ai_cost_usd": 0,
        "limitation": "Local checksums and first-party statements do not authenticate business identity or grant contact permission.",
    }

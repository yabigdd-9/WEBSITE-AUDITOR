"""Deterministic discovery-result quality classification for v45.

This module is intentionally stdlib-only and advisory to the discovery lane.
It rejects only high-confidence, deterministic junk classes. Ambiguous or novel
results are REVIEW, never silently discarded.

No network calls, model calls, database writes, outreach, or paid services occur
here.
"""
from __future__ import annotations

from pathlib import PurePosixPath
from urllib.parse import urlsplit
import re


BUSINESS_HOME = "BUSINESS_HOME"
BUSINESS_LOCATION = "BUSINESS_LOCATION"
BUSINESS_SERVICE_PAGE = "BUSINESS_SERVICE_PAGE"
DIRECTORY = "DIRECTORY"
AGGREGATOR = "AGGREGATOR"
SOCIAL_PROFILE = "SOCIAL_PROFILE"
MARKETPLACE = "MARKETPLACE"
NEWS = "NEWS"
BLOG = "BLOG"
GOVERNMENT = "GOVERNMENT"
REGISTRY = "REGISTRY"
JOB_BOARD = "JOB_BOARD"
DOCUMENT = "DOCUMENT"
IRRELEVANT = "IRRELEVANT"
UNKNOWN = "UNKNOWN"

ACCEPT = "ACCEPT"
REVIEW = "REVIEW"
REJECT = "REJECT"

BUSINESS_CLASSES = {BUSINESS_HOME, BUSINESS_LOCATION, BUSINESS_SERVICE_PAGE}
JUNK_CLASSES = {
    DIRECTORY,
    AGGREGATOR,
    SOCIAL_PROFILE,
    MARKETPLACE,
    NEWS,
    GOVERNMENT,
    REGISTRY,
    JOB_BOARD,
    DOCUMENT,
    IRRELEVANT,
}

# Order matters: specific government registries must beat the generic
# *.govt.nz rule.
_DOMAIN_CLASSES = (
    (REGISTRY, (
        "companiesoffice.govt.nz",
        "companies-register.companiesoffice.govt.nz",
        "nzbn.govt.nz",
    )),
    (SOCIAL_PROFILE, (
        "facebook.com",
        "instagram.com",
        "linkedin.com",
        "tiktok.com",
        "twitter.com",
        "x.com",
        "youtube.com",
    )),
    (DIRECTORY, (
        "yellow.co.nz",
        "finda.co.nz",
        "nzs.com",
        "zenbu.co.nz",
    )),
    (MARKETPLACE, (
        "trademe.co.nz",
        "facebookmarketplace.com",
    )),
    (JOB_BOARD, (
        "seek.co.nz",
        "seek.com",
        "indeed.com",
        "indeed.co.nz",
    )),
    (NEWS, (
        "stuff.co.nz",
        "nzherald.co.nz",
        "rnz.co.nz",
        "newsroom.co.nz",
        "1news.co.nz",
    )),
)

_DOCUMENT_SUFFIXES = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".rtf",
}
_DIRECTORY_PATH_MARKERS = {
    "directory", "business-directory", "businesses", "listings", "listing",
    "suppliers", "providers",
}
_SERVICE_PATH_MARKERS = {
    "service", "services", "what-we-do", "solutions", "repairs", "installation",
    "maintenance", "plumbing", "electrical", "building", "roofing", "landscaping",
}
_LOCATION_PATH_MARKERS = {
    "location", "locations", "branch", "branches", "contact", "find-us",
}
_IRRELEVANT_PATH_MARKERS = {
    "privacy", "privacy-policy", "terms", "terms-of-use", "cookies",
}

_BUSINESS_HINTS = re.compile(
    r"\b(service|services|book|booking|quote|quotes|contact|call|"
    r"plumb|electric|builder|roof|landscap|dent|mechanic|repair|install)\w*\b",
    re.I,
)
_DIRECTORY_HINTS = re.compile(
    r"\b(directory|find\s+(?:a|an)|listings?|businesses\s+near|compare\s+providers)\b",
    re.I,
)
_NEWS_HINTS = re.compile(r"\b(news|breaking|article|reporter|opinion)\b", re.I)
_JOB_HINTS = re.compile(r"\b(jobs?|careers?|vacanc(?:y|ies)|hiring)\b", re.I)


def _host_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def _safe_text(value, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _region_tokens(region: str) -> set[str]:
    return {
        token.casefold()
        for token in re.findall(r"[A-Za-z]{3,}", str(region or ""))
        if len(token) >= 3
    }


def classify_candidate(candidate: dict, region: str = "") -> dict:
    """Classify one discovery candidate using deterministic evidence only.

    The returned mapping is deliberately verbose so the decision is
    reconstructable later. Unknown/ambiguous inputs return REVIEW.
    """
    if not isinstance(candidate, dict):
        raise ValueError("candidate must be an object")

    raw_url = (
        candidate.get("source_url")
        or candidate.get("url")
        or candidate.get("public_website")
        or candidate.get("website")
        or ""
    )
    title = _safe_text(candidate.get("title") or candidate.get("name"), 250)
    snippet = _safe_text(
        candidate.get("content") or candidate.get("snippet") or candidate.get("description"),
        500,
    )
    effective_region = _safe_text(candidate.get("region") or region, 160)

    parsed = urlsplit(str(raw_url or "").strip())
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    path = parsed.path or "/"
    path_cf = path.casefold()
    segments = {
        segment.casefold()
        for segment in PurePosixPath(path_cf).parts
        if segment not in {"/", ""}
    }

    supporting: list[str] = []
    contradicting: list[str] = []
    missing: list[str] = []
    classification = UNKNOWN
    confidence = 0.30

    if not host:
        missing.append("host")
        return _result(
            classification, confidence, supporting, contradicting, missing,
            raw_url, host, path, title, snippet, effective_region,
        )

    suffix = PurePosixPath(path_cf).suffix
    if suffix in _DOCUMENT_SUFFIXES:
        classification = DOCUMENT
        confidence = 0.99
        supporting.append(f"document_suffix:{suffix}")
        return _result(
            classification, confidence, supporting, contradicting, missing,
            raw_url, host, path, title, snippet, effective_region,
        )

    for cls, domains in _DOMAIN_CLASSES:
        if any(_host_matches(host, domain) for domain in domains):
            classification = cls
            confidence = 0.99
            supporting.append(f"known_{cls.lower()}_domain:{host}")
            return _result(
                classification, confidence, supporting, contradicting, missing,
                raw_url, host, path, title, snippet, effective_region,
            )

    if host.endswith(".govt.nz") or host.endswith(".gov.nz"):
        classification = GOVERNMENT
        confidence = 0.99
        supporting.append(f"government_domain:{host}")
        return _result(
            classification, confidence, supporting, contradicting, missing,
            raw_url, host, path, title, snippet, effective_region,
        )

    text = f"{title} {snippet}".strip()

    if _DIRECTORY_HINTS.search(text):
        classification = AGGREGATOR
        confidence = 0.92
        supporting.append("directory_language")
    elif _JOB_HINTS.search(text):
        classification = JOB_BOARD
        confidence = 0.92
        supporting.append("job_language")
    elif _NEWS_HINTS.search(text):
        classification = NEWS
        confidence = 0.90
        supporting.append("news_language")
    elif segments & _DIRECTORY_PATH_MARKERS:
        classification = AGGREGATOR
        confidence = 0.88
        supporting.append(
            "directory_path:" + sorted(segments & _DIRECTORY_PATH_MARKERS)[0]
        )
    elif segments & _SERVICE_PATH_MARKERS:
        classification = BUSINESS_SERVICE_PAGE
        confidence = 0.82
        supporting.append(
            "service_path:" + sorted(segments & _SERVICE_PATH_MARKERS)[0]
        )
    elif segments & _LOCATION_PATH_MARKERS:
        classification = BUSINESS_LOCATION
        confidence = 0.76
        supporting.append(
            "location_path:" + sorted(segments & _LOCATION_PATH_MARKERS)[0]
        )
    elif segments & _IRRELEVANT_PATH_MARKERS:
        classification = IRRELEVANT
        confidence = 0.82
        supporting.append(
            "irrelevant_path:" + sorted(segments & _IRRELEVANT_PATH_MARKERS)[0]
        )
    elif path in {"", "/"}:
        # Root first-party-looking sites are plausible business homepages, but
        # still below "identity proven" confidence. Later stages remain
        # authoritative.
        classification = BUSINESS_HOME
        confidence = 0.68
        supporting.append("root_page")
        if host.endswith(".nz") or host.endswith(".co.nz"):
            confidence = 0.74
            supporting.append("nz_domain")
    elif _BUSINESS_HINTS.search(text):
        classification = BUSINESS_SERVICE_PAGE
        confidence = 0.72
        supporting.append("business_language")
    else:
        classification = UNKNOWN
        confidence = 0.35
        missing.append("decisive_page_type_signal")

    region_tokens = _region_tokens(effective_region)
    if region_tokens and any(token in path_cf or token in text.casefold() for token in region_tokens):
        supporting.append("region_signal")

    if classification in BUSINESS_CLASSES and not title and not snippet:
        missing.append("title_or_snippet")
    if classification in JUNK_CLASSES and _BUSINESS_HINTS.search(text):
        contradicting.append("business_language_present")

    return _result(
        classification, confidence, supporting, contradicting, missing,
        raw_url, host, path, title, snippet, effective_region,
    )


def _result(
    classification: str,
    confidence: float,
    supporting: list[str],
    contradicting: list[str],
    missing: list[str],
    raw_url: str,
    host: str,
    path: str,
    title: str,
    snippet: str,
    region: str,
) -> dict:
    if classification in BUSINESS_CLASSES and confidence >= 0.60:
        disposition = ACCEPT
    elif classification in JUNK_CLASSES and confidence >= 0.90:
        disposition = REJECT
    else:
        disposition = REVIEW

    return {
        "classification": classification,
        "confidence": round(float(confidence), 4),
        "disposition": disposition,
        "supporting_signals": list(supporting),
        "contradicting_signals": list(contradicting),
        "missing_signals": list(missing),
        "raw_inputs": {
            "url": _safe_text(raw_url, 500),
            "host": _safe_text(host, 253),
            "path": _safe_text(path, 500),
            "title": _safe_text(title, 250),
            "snippet": _safe_text(snippet, 500),
            "region": _safe_text(region, 160),
        },
        "rule_version": "discovery-quality-v1",
    }


def filter_candidates(candidates, region: str = "") -> dict:
    """Filter only high-confidence deterministic junk.

    REVIEW candidates remain in the accepted stream so novelty or missing
    evidence cannot become an accidental terminal rejection.
    """
    accepted = []
    rejected = []
    review = []

    for index, candidate in enumerate(candidates or (), 1):
        if not isinstance(candidate, dict):
            rejected.append({
                "row": index,
                "classification": IRRELEVANT,
                "disposition": REJECT,
                "confidence": 1.0,
                "reason": "candidate_not_object",
            })
            continue

        quality = classify_candidate(candidate, region)
        enriched = dict(candidate)
        enriched["discovery_quality"] = quality

        if quality["disposition"] == REJECT:
            rejected.append({
                "row": index,
                "url": quality["raw_inputs"]["url"],
                "classification": quality["classification"],
                "disposition": quality["disposition"],
                "confidence": quality["confidence"],
                "supporting_signals": quality["supporting_signals"],
                "rule_version": quality["rule_version"],
            })
            continue

        accepted.append(enriched)
        if quality["disposition"] == REVIEW:
            review.append({
                "row": index,
                "url": quality["raw_inputs"]["url"],
                "classification": quality["classification"],
                "confidence": quality["confidence"],
                "missing_signals": quality["missing_signals"],
                "rule_version": quality["rule_version"],
            })

    return {
        "accepted": accepted,
        "rejected": rejected,
        "review": review,
        "counts": {
            "accepted": len(accepted),
            "rejected": len(rejected),
            "review": len(review),
        },
        "external_sends": 0,
        "paid_calls": 0,
    }

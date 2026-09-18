#!/usr/bin/env python3
"""Hunter.io enrichment adapter — external corroboration source.

Hunter.io results are treated as an independent third-party source. They can:
- Seed new email candidates for a business
- Provide independent corroboration (boosts 'independent_source' weight)
- NEVER reach VERIFIED_HIGH on their own — first-party observation is still required

API: https://hunter.io/api-documentation/v2

Design rules:
- All API calls are bounded and cached
- Results are stored append-only in hunter_enrichment table
- Hunter confidence is mapped to the existing label system
- No paid inference, no model calls — pure HTTP + deterministic processing
"""
import datetime as dt
import hashlib
import http.client
import ipaddress
import json
import os
import socket
import sqlite3
import ssl
import time
from pathlib import Path
from urllib.parse import urlencode

UTC = dt.timezone.utc

HUNTER_API_HOST = "api.hunter.io"
HUNTER_API_VERSION = "v2"

# Rate limits (free plan: 50/month, paid: more — we stay conservative)
MAX_REQUESTS_PER_DOMAIN = 3
CACHE_HOURS = 24
REQUEST_TIMEOUT = 12


def utcnow():
    return dt.datetime.now(UTC).isoformat()


def sha256(data):
    return hashlib.sha256(
        data if isinstance(data, bytes) else data.encode()
    ).hexdigest()


def age_days(stamp, at=None):
    try:
        t = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=UTC)
        return ((at or dt.datetime.now(UTC)) - t).total_seconds() / 86400
    except (ValueError, TypeError, AttributeError):
        return float("inf")


def get_api_key():
    """Resolve HUNTER_API_KEY from environment. Never log or persist it."""
    key = os.environ.get("HUNTER_API_KEY")
    if not key:
        raise ValueError(
            "HUNTER_API_KEY not set. Add it to .env (gitignored): "
            'HUNTER_API_KEY="your-key-here"'
        )
    return key


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2))
    temp.replace(path)


def _safe_getaddr(hostname):
    """Validate hostname resolves to a public IP. DNS rebinding protection."""
    addresses = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    if not addresses:
        raise ValueError(f"No DNS resolution for {hostname}")
    for a in addresses:
        ip = ipaddress.ip_address(a[4][0])
        if not ip.is_global:
            raise ValueError(f"Non-public IP for {hostname}: {ip}")
    return addresses[0][4][0]


def _api_request(path, params=None):
    """Make a bounded GET request to Hunter.io API with safety checks."""
    if params is None:
        params = {}

    # Validate host resolves to public IP
    ip = _safe_getaddr(HUNTER_API_HOST)

    api_key = get_api_key()
    params["api_key"] = api_key

    url_path = f"/v2/{path}"
    if params:
        url_path += "?" + urlencode(params)

    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection(
        HUNTER_API_HOST, timeout=REQUEST_TIMEOUT, context=ctx
    )

    try:
        conn.request("GET", url_path, headers={
            "User-Agent": "MoneyMachine-HunterEnrichment/1.0",
            "Accept": "application/json",
        })
        response = conn.getresponse()
        body = response.read().decode("utf-8")

        if response.status == 401:
            raise ValueError("Hunter.io API: invalid API key (401)")
        if response.status == 429:
            raise ValueError("Hunter.io API: rate limit exceeded (429)")
        if response.status == 404:
            return None  # No data found
        if response.status != 200:
            raise ValueError(
                f"Hunter.io API: HTTP {response.status}: {body[:200]}"
            )

        return json.loads(body)
    finally:
        conn.close()


def domain_search(domain, limit=10, offset=0, cache_dir=None):
    """Hunter.io Domain Search — find email addresses associated with a domain.

    Returns dict with 'emails' list or None if not found.
    Results are cached to avoid redundant API calls.
    """
    domain = domain.lower().strip()
    if not domain:
        return None

    cache_key = sha256(f"domain_search:{domain}:{limit}:{offset}")
    cache_path = None
    if cache_dir:
        cache_path = Path(cache_dir) / "hunter" / f"{cache_key}.json"
        if cache_path.exists():
            cached = json.loads(cache_path.read_text())
            if 0 <= age_days(cached.get("cached_at", ""), None) <= (CACHE_HOURS / 24):
                cached["from_cache"] = True
                return cached

    result = _api_request("domain-search", {
        "domain": domain,
        "limit": min(limit, 100),
        "offset": offset,
    })

    if result is None:
        return None

    # Normalize response
    emails = []
    for entry in result.get("data", {}).get("emails", []):
        emails.append({
            "value": entry.get("value", ""),
            "type": entry.get("type", "unknown"),
            "confidence": entry.get("confidence", 0),
            "sources": [s.get("uri", "") for s in entry.get("sources", [])],
            "first_name": entry.get("first_name"),
            "last_name": entry.get("last_name"),
            "position": entry.get("position"),
            "department": entry.get("department"),
            "linkedin": entry.get("linkedin"),
            "twitter": entry.get("twitter"),
            "phone_number": entry.get("phone_number"),
            "verification": entry.get("verification", {}),
        })

    output = {
        "domain": domain,
        "emails": emails,
        "total": result.get("data", {}).get("total", 0),
        "limit": limit,
        "offset": offset,
        "cached_at": utcnow(),
        "from_cache": False,
    }

    if cache_path:
        atomic_json(cache_path, output)

    return output


def email_verifier(email, cache_dir=None):
    """Hunter.io Email Verifier — check if an email is deliverable.

    Returns dict with verification result or None.
    """
    email = email.lower().strip()
    if not email:
        return None

    cache_key = sha256(f"email_verifier:{email}")
    cache_path = None
    if cache_dir:
        cache_path = Path(cache_dir) / "hunter" / f"{cache_key}.json"
        if cache_path.exists():
            cached = json.loads(cache_path.read_text())
            if 0 <= age_days(cached.get("cached_at", ""), None) <= (CACHE_HOURS / 24):
                cached["from_cache"] = True
                return cached

    result = _api_request("email-verifier", {"email": email})

    if result is None:
        return None

    data = result.get("data", {})
    output = {
        "email": email,
        "result": data.get("result", "unknown"),  # deliverable, undeliverable, risky, unknown
        "score": data.get("score", 0),
        "regexp": data.get("regexp", False),
        "gibberish": data.get("gibberish", False),
        "disposable": data.get("disposable", False),
        "webmail": data.get("webmail", False),
        "mx_records": data.get("mx_records", False),
        "smtp_server": data.get("smtp_server", False),
        "smtp_check": data.get("smtp_check", False),
        "accept_all": data.get("accept_all", False),
        "block": data.get("block", False),
        "sources": [s.get("uri", "") for s in data.get("sources", [])],
        "cached_at": utcnow(),
        "from_cache": False,
    }

    if cache_path:
        atomic_json(cache_path, output)

    return output


def hunter_to_candidate(hunter_email, business_id, domain):
    """Convert a Hunter.io email entry to an email_candidates row dict.

    Hunter candidates start as OBSERVED (external source) — they need
    first-party verification to reach VERIFIED_HIGH.
    """
    email = hunter_email.get("value", "").lower().strip()
    if not email or "@" not in email:
        return None

    confidence = hunter_email.get("confidence", 0)

    # Map Hunter confidence to our label system
    # Hunter confidence is 0-100; we treat it as external corroboration
    if confidence >= 80:
        label = "OBSERVED"  # External high confidence — still needs first-party
    elif confidence >= 50:
        label = "CANDIDATE"  # External medium confidence
    else:
        label = "UNVERIFIED"  # External low confidence

    return {
        "email": email,
        "normalized_email": email,
        "source_type": "hunter_enrichment",
        "source_url": hunter_email.get("sources", [None])[0] if hunter_email.get("sources") else None,
        "source_excerpt": json.dumps({
            "hunter_confidence": confidence,
            "hunter_type": hunter_email.get("type"),
            "hunter_position": hunter_email.get("position"),
            "hunter_department": hunter_email.get("department"),
        }),
        "observed_at": utcnow(),
        "candidate_method": "hunter_domain_search",
        "status": label,
        "hunter_confidence": confidence,
        "hunter_sources": hunter_email.get("sources", []),
        "hunter_first_name": hunter_email.get("first_name"),
        "hunter_last_name": hunter_email.get("last_name"),
        "hunter_position": hunter_email.get("position"),
        "hunter_department": hunter_email.get("department"),
    }


def enrich_business(d, business_id, domain, cache_dir=None, limit=10):
    """Enrich a business with Hunter.io data.

    1. Run domain search on the business's canonical domain
    2. Store results in hunter_enrichment table
    3. Return candidate rows for email_candidates insertion

    Returns dict with candidates list and metadata.
    """
    if not domain:
        return {"candidates": [], "error": "No domain provided", "total": 0}

    result = domain_search(domain, limit=limit, cache_dir=cache_dir)
    if result is None:
        return {"candidates": [], "error": "No Hunter.io data found", "total": 0}

    candidates = []
    for hunter_email in result.get("emails", []):
        candidate = hunter_to_candidate(hunter_email, business_id, domain)
        if candidate:
            candidate["business_id"] = business_id
            candidates.append(candidate)

    return {
        "candidates": candidates,
        "total": result.get("total", 0),
        "domain": domain,
        "hunter_cached": result.get("from_cache", False),
    }


def store_enrichment(d, business_id, enrichment_result):
    """Store Hunter enrichment results in the database.

    INSERT OR IGNORE — enrichment is idempotent per business/domain.
    """
    if not enrichment_result or not enrichment_result.get("candidates"):
        return

    for candidate in enrichment_result["candidates"]:
        try:
            d.execute(
                """INSERT OR IGNORE INTO hunter_enrichment (
                    business_id, email, normalized_email, source_type, source_url,
                    source_excerpt, observed_at, candidate_method, status,
                    hunter_confidence, hunter_sources, hunter_first_name,
                    hunter_last_name, hunter_position, hunter_department,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    business_id,
                    candidate["email"],
                    candidate["normalized_email"],
                    candidate["source_type"],
                    candidate["source_url"],
                    candidate["source_excerpt"],
                    candidate["observed_at"],
                    candidate["candidate_method"],
                    candidate["status"],
                    candidate.get("hunter_confidence", 0),
                    json.dumps(candidate.get("hunter_sources", [])),
                    candidate.get("hunter_first_name"),
                    candidate.get("hunter_last_name"),
                    candidate.get("hunter_position"),
                    candidate.get("hunter_department"),
                    utcnow(),
                ),
            )
        except sqlite3.IntegrityError:
            pass  # Already exists — skip


def get_hunter_independent_sources(d, business_id, email):
    """Count independent Hunter.io sources for an email address.

    Used as 'independent_source' corroboration in scoring.
    Returns count of distinct Hunter sources (URIs) for this email.
    """
    rows = d.execute(
        """SELECT source_url, hunter_sources FROM hunter_enrichment
           WHERE business_id = ? AND normalized_email = ?""",
        (business_id, email.lower().strip()),
    ).fetchall()

    sources = set()
    for row in rows:
        if row["source_url"]:
            sources.add(row["source_url"])
        try:
            for s in json.loads(row["hunter_sources"] or "[]"):
                if s:
                    sources.add(s)
        except (json.JSONDecodeError, TypeError):
            pass

    return len(sources)

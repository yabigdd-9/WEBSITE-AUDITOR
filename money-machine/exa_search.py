#!/usr/bin/env python3
"""Exa search adapter — web search, content extraction, and Q&A.

Wraps exa_py with caching and bounded requests.
API: https://docs.exa.ai/reference/search-api-guide-for-coding-agents
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path

import exa_py

UTC = dt.timezone.utc

MAX_RESULTS_DEFAULT = 5
CACHE_HOURS = 24


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
    """Resolve EXA_API_KEY from environment."""
    key = os.environ.get("EXA_API_KEY")
    if not key:
        raise ValueError("EXA_API_KEY not set.")
    return key


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2))
    temp.replace(path)


def get_client():
    """Get authenticated Exa client."""
    return exa_py.Exa(api_key=get_api_key())


def search(query, num_results=MAX_RESULTS_DEFAULT, type="auto",
            contents_highlights=True, system_prompt=None, output_schema=None,
            cache_dir=None, max_age_hours=None):
    """Exa neural search.
    
    Returns dict with 'results' list and metadata.
    """
    num_results = max(1, min(10, num_results))
    
    # Build cache key
    cache_key = sha256(f"search:{query}:{num_results}:{type}:{system_prompt}:{output_schema}")
    cache_path = None
    if cache_dir:
        cache_path = Path(cache_dir) / "exa" / f"{cache_key}.json"
        if cache_path.exists():
            cached = json.loads(cache_path.read_text())
            cache_age = age_days(cached.get("cached_at", ""), None)
            if max_age_hours is not None:
                if 0 <= cache_age <= (max_age_hours / 24):
                    cached["from_cache"] = True
                    return cached
            elif 0 <= cache_age <= (CACHE_HOURS / 24):
                cached["from_cache"] = True
                return cached
    
    client = get_client()
    
    contents = None
    if contents_highlights:
        contents = {"highlights": True}
    
    result = client.search(
        query,
        type=type,
        num_results=num_results,
        contents=contents,
        system_prompt=system_prompt,
        output_schema=output_schema,
    )
    
    output = {
        "query": query,
        "type": type,
        "results": [r.model_dump() if hasattr(r, 'model_dump') else r for r in result.results],
        "cached_at": utcnow(),
        "from_cache": False,
    }
    
    if hasattr(result, 'output') and result.output:
        output["output"] = result.output
    
    if cache_path:
        atomic_json(cache_path, output)
    
    return output


def extract(urls, mode="highlights", max_characters=20000, cache_dir=None):
    """Exa content extraction for known URLs."""
    if not urls:
        return {"results": [], "cached_at": utcnow(), "from_cache": False}
    
    # Deduplicate
    seen = set()
    unique_urls = []
    for url in urls:
        normalized = url.split("#")[0]
        if normalized not in seen:
            seen.add(normalized)
            unique_urls.append(url)
    
    cache_key = sha256(f"extract:{sorted(unique_urls)}:{mode}:{max_characters}")
    cache_path = None
    if cache_dir:
        cache_path = Path(cache_dir) / "exa" / f"{cache_key}.json"
        if cache_path.exists():
            cached = json.loads(cache_path.read_text())
            if 0 <= age_days(cached.get("cached_at", ""), None) <= (CACHE_HOURS / 24):
                cached["from_cache"] = True
                return cached
    
    client = get_client()
    
    contents = None
    if mode == "highlights":
        contents = {"highlights": True}
    elif mode == "text":
        contents = {"text": {"maxCharacters": max_characters, "verbosity": "compact"}}
    elif mode == "summary":
        contents = {"summary": True}
    
    result = client.get_contents(unique_urls, contents=contents)
    
    output = {
        "urls": unique_urls,
        "mode": mode,
        "results": [r.model_dump() if hasattr(r, 'model_dump') else r for r in result.results],
        "cached_at": utcnow(),
        "from_cache": False,
    }
    
    if cache_path:
        atomic_json(cache_path, output)
    
    return output


def get_answer(query, num_results=3, cache_dir=None):
    """Exa answer endpoint — grounded answer with citations."""
    cache_key = sha256(f"answer:{query}:{num_results}")
    cache_path = None
    if cache_dir:
        cache_path = Path(cache_dir) / "exa" / f"{cache_key}.json"
        if cache_path.exists():
            cached = json.loads(cache_path.read_text())
            if 0 <= age_days(cached.get("cached_at", ""), None) <= (CACHE_HOURS / 24):
                cached["from_cache"] = True
                return cached
    
    client = get_client()
    result = client.answer(query, num_results=num_results)
    
    output = {
        "query": query,
        "answer": result.get("answer", "") if isinstance(result, dict) else getattr(result, "answer", ""),
        "sources": result.get("sources", []) if isinstance(result, dict) else getattr(result, "sources", []),
        "cached_at": utcnow(),
        "from_cache": False,
    }
    
    if cache_path:
        atomic_json(cache_path, output)
    
    return output


def search_business_info(business_name, domain=None, cache_dir=None):
    """Search for business contact info."""
    query = f"{business_name}"
    if domain:
        query += f" site:{domain}"
    else:
        query += " contact email phone"
    
    return search(query, num_results=5, type="auto",
                   contents_highlights=True, cache_dir=cache_dir)

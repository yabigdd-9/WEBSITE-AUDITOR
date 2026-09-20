#!/usr/bin/env python3
"""Website Rescue Auditor v2 — NZ small business website defect detection.

from __future__ import annotations

Async, cached, 25+ checks, batch-capable, HTML reports.

Usage:
    python3 website_auditor.py <url> [--format md|json|html] [--output file]
    python3 website_auditor.py --batch prospects.csv [--concurrency 8]
    python3 website_auditor.py --all               # full pipeline
    python3 website_auditor.py --emails <url>       # email discovery only
    python3 website_auditor.py --scout prospects.csv # cross-reference queue

All checks use public data only. No login, no API keys required.
"""
import argparse, asyncio, html as html_lib, json, re, subprocess, sys, time, urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx, bs4, trafilatura, pyphen

from auditor_core import (
    build_page_evidence,
    category_scores,
    detect_site_type,
    normalize_defects,
    resolve_profile,
)
from auditor_core.network import NetworkSafetyError, SafeFetcher, ensure_public_url, robots_policy
from auditor_core.registry import get_registry

# ── config ──────────────────────────────────────────────────────────
CACHE_DIR = Path("outputs/.cache")
CACHE_TTL = 3600
CONCURRENCY = 8
TIMEOUT = 15
USER_AGENT = "Mozilla/5.0 (NZ) WebsiteRescueAuditor/2.0"

CACHE_DIR.mkdir(parents=True, exist_ok=True)
HEADERS = {"User-Agent": USER_AGENT}

# ── cache ───────────────────────────────────────────────────────────
def _cache_path(key: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", key)[:80]
    return CACHE_DIR / f"{safe}.json"

def cache_get(key: str, ttl: int = CACHE_TTL) -> Any | None:
    p = _cache_path(key)
    if not p.exists(): return None
    try:
        d = json.loads(p.read_text())
        if time.time() - d.get("_ts", 0) < ttl: return d["_data"]
    except Exception: pass
    return None

def cache_set(key: str, data: Any, ttl: int = CACHE_TTL) -> None:
    p = _cache_path(key)
    p.write_text(json.dumps({"_ts": time.time(), "_data": data}, default=str))

# ── async HTTP ──────────────────────────────────────────────────────
async def fetch_page(session: httpx.AsyncClient, url: str) -> dict:
    """Fetch a bounded public HTTP(S) page with redirect re-validation."""
    try:
        validated_url = await ensure_public_url(url)
    except NetworkSafetyError as exc:
        return {"error": str(exc), "text": "", "headers": {}, "status": None}
    key = f"safe-page-v2:{validated_url}"
    cached = cache_get(key)
    if isinstance(cached, dict) and "text" in cached:
        return cached

    fetcher = SafeFetcher(
        session,
        timeout=TIMEOUT,
        max_redirects=5,
        max_body_bytes=5_000_000,
        per_domain_concurrency=2,
        delay_seconds=0.25,
    )
    try:
        result = await fetcher.get_text(validated_url)
    except (httpx.HTTPError, NetworkSafetyError) as exc:
        return {"error": str(exc), "text": "", "headers": {}, "status": None}

    payload = result.to_dict()
    cache_set(key, payload, ttl=3600)
    return payload


async def fetch_html(session: httpx.AsyncClient, url: str) -> str:
    """Backward-compatible HTML helper using the safe fetcher."""
    return str((await fetch_page(session, url)).get("text") or "")


async def fetch_head(session: httpx.AsyncClient, url: str) -> dict:
    """Backward-compatible header helper using the safe fetcher."""
    try:
        validated_url = await ensure_public_url(url)
    except NetworkSafetyError:
        return {}
    key = f"safe-head-v2:{validated_url}"
    cached = cache_get(key, ttl=1800)
    if isinstance(cached, dict):
        return cached

    fetcher = SafeFetcher(
        session,
        timeout=TIMEOUT,
        max_redirects=5,
        max_body_bytes=64_000,
        per_domain_concurrency=2,
        delay_seconds=0.25,
    )
    try:
        result = await fetcher.head_status(validated_url)
    except (httpx.HTTPError, NetworkSafetyError):
        return {}
    headers = dict(result.headers)
    headers["status"] = result.status
    headers["final_url"] = result.final_url
    headers["redirect_chain"] = result.redirect_chain
    cache_set(key, headers, ttl=1800)
    return headers

def _rendered_evidence_sync(url: str) -> dict:
    """Run the existing Playwright/Lighthouse/axe evidence engine when installed."""
    script = Path("audit/evidence-audit.mjs")
    node_modules = Path("audit/node_modules")
    if not script.exists():
        return {"status": "skipped", "reason": "audit/evidence-audit.mjs is missing"}
    if not node_modules.exists():
        return {
            "status": "skipped",
            "reason": "browser tooling not installed; run 'cd audit && npm install && npx playwright install chromium'",
        }

    safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", urllib.parse.urlparse(url).netloc or "site")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path("outputs/evidence") / safe / stamp
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            ["node", str(script), url, str(output_dir)],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except FileNotFoundError:
        return {"status": "skipped", "reason": "node executable not found"}
    except subprocess.TimeoutExpired:
        return {"status": "error", "reason": "rendered evidence timed out after 180 seconds"}

    if proc.returncode != 0:
        return {
            "status": "error",
            "reason": (proc.stderr or proc.stdout or "rendered evidence failed")[-2000:],
            "output_dir": str(output_dir),
        }
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {"ok": True, "output_dir": str(output_dir)}
    return {
        "status": "ok",
        "output_dir": payload.get("output_dir", str(output_dir)),
        "audit": payload.get("audit", {}),
    }


async def collect_rendered_evidence(url: str) -> dict:
    return await asyncio.to_thread(_rendered_evidence_sync, url)

# ── readability ─────────────────────────────────────────────────────
_HYPHENATOR = pyphen.Pyphen(lang="en_US")

def readability_scores(text: str) -> tuple[float | None, float | None]:
    """Return Flesch reading ease and Flesch-Kincaid grade without NLTK."""
    words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", text or "")
    if not words:
        return None, None
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    sentence_count = max(1, len(sentences))
    syllables = 0
    for word in words:
        parts = _HYPHENATOR.inserted(word.lower()).split("-")
        syllables += max(1, len([p for p in parts if p]))
    word_count = len(words)
    words_per_sentence = word_count / sentence_count
    syllables_per_word = syllables / word_count
    flesch = 206.835 - (1.015 * words_per_sentence) - (84.6 * syllables_per_word)
    grade = (0.39 * words_per_sentence) + (11.8 * syllables_per_word) - 15.59
    return flesch, grade

# ── defect checks ───────────────────────────────────────────────────
def check_ssl(domain: str) -> dict:
    """Inspect TLS while pinning the connection to a resolved public IP."""
    import ipaddress
    import socket
    import ssl

    issues = {}
    try:
        records = socket.getaddrinfo(domain, 443, type=socket.SOCK_STREAM)
        public_addresses = []
        for record in records:
            address = record[4][0].split("%", 1)[0]
            try:
                if ipaddress.ip_address(address).is_global and address not in public_addresses:
                    public_addresses.append(address)
            except ValueError:
                continue
        if not public_addresses:
            return {"ssl_error": True, "error": "no public TLS address"}

        context = ssl.create_default_context()
        last_error = None
        cert = None
        for address in public_addresses:
            family = socket.AF_INET6 if ":" in address else socket.AF_INET
            sock = socket.socket(family, socket.SOCK_STREAM)
            sock.settimeout(10)
            try:
                target = (address, 443, 0, 0) if family == socket.AF_INET6 else (address, 443)
                sock.connect(target)
                with context.wrap_socket(sock, server_hostname=domain) as tls:
                    cert = tls.getpeercert()
                break
            except (ssl.SSLError, socket.timeout, ConnectionError, OSError) as exc:
                last_error = exc
                try:
                    sock.close()
                except OSError:
                    pass
        if cert is None:
            if isinstance(last_error, ssl.SSLCertVerificationError):
                return {"ssl_error": True, "error": "certificate verification failed"}
            return {"ssl_error": True, "error": "TLS connection failed"}

        not_after = cert.get("notAfter")
        if not_after:
            expiry_ts = ssl.cert_time_to_seconds(not_after)
            expiry = datetime.fromtimestamp(expiry_ts, timezone.utc)
            days = (expiry - datetime.now(timezone.utc)).days
            issues["expiry_date"] = expiry.isoformat()
            issues["days_remaining"] = days
            if days < 0:
                issues["expired"] = True
            elif days < 30:
                issues["expiring_soon"] = True
        return issues
    except (socket.gaierror, OSError):
        return {"ssl_error": True, "error": "TLS resolution failed"}

def check_security_headers(headers: dict) -> list:
    defects = []
    for h, name in [("strict-transport-security","HSTS"),("content-security-policy","CSP"),
                    ("x-frame-options","X-Frame-Options"),("x-content-type-options","X-Content-Type"),
                    ("referrer-policy","Referrer-Policy"),("permissions-policy","Permissions-Policy")]:
        if h not in {k.lower() for k in headers}:
            defects.append({"defect": f"Missing {name}", "impact": f"Missing {name} — reduces XSS/clickjacking protection"})
    return defects

def check_html_structure(soup: bs4.BeautifulSoup, body_text: str) -> list:
    defects = []
    if not soup.find("h1"):
        defects.append({"defect": "Missing H1 tag", "impact": "No clear page hierarchy for SEO/screen readers"})
    h1s = soup.find_all("h1")
    if len(h1s) > 1:
        defects.append({"defect": f"Multiple H1 tags ({len(h1s)})", "impact": "Dilutes page topic signal"})
    imgs = soup.find_all("img")
    missing_alt = sum(1 for img in imgs if not img.get("alt", "").strip())
    if imgs and missing_alt > len(imgs) * 0.5:
        defects.append({"defect": f"{missing_alt}/{len(imgs)} images missing alt text", "impact": "Accessibility fail; SEO penalty"})
    if not soup.find("title"):
        defects.append({"defect": "Missing <title> tag", "impact": "Blank search results; no context"})
    desc_tag = soup.find("meta", attrs={"name": "description"})
    desc_content = ""
    if desc_tag:
        desc_content = desc_tag.get("content", "").strip()
        if not desc_content:
            m = re.search(r'content=["\']([^"\']*)["\']', str(desc_tag))
            desc_content = m.group(1) if m else ""
    if not desc_content:
        defects.append({"defect": "Missing meta description", "impact": "Lower CTR from search"})
    robots = soup.find("meta", attrs={"name": "robots"})
    if robots and "noindex" in robots.get("content", "").lower():
        defects.append({"defect": "Meta robots noindex", "impact": "Pages blocked from search index"})
    canonical = soup.find("link", attrs={"rel": "canonical"})
    if not canonical:
        defects.append({"defect": "Missing canonical URL", "impact": "Duplicate content risk"})
    og_tags = soup.find_all("meta", attrs={"property": re.compile(r"^og:")})
    if not og_tags:
        defects.append({"defect": "Missing Open Graph tags", "impact": "Poor social share previews"})
    if not body_text or len(body_text.strip()) < 200:
        defects.append({"defect": "Thin content (<200 words)", "impact": "Low SEO value; thin page"})
    return defects

def check_schema_org(soup: bs4.BeautifulSoup) -> dict:
    scripts = soup.find_all("script", type="application/ld+json")
    schemas = []
    for s in scripts:
        try:
            data = json.loads(s.string)
            schemas.append(data.get("@type", "Unknown"))
        except Exception: pass
    return {"count": len(schemas), "types": schemas}

def extract_emails(html: str) -> list:
    pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = set(re.findall(pattern, html))
    junk = {"info@domain.com","admin@domain.com","contact@domain.com",
            "hello@domain.com","support@domain.com","webmaster@domain.com"}
    return sorted(e for e in emails if e not in junk and not re.match(r'^[0-9a-f]{16,}@', e))

def score_defects(defects: list) -> int:
    score = 0
    for d in defects:
        msg = d.get("defect", d.get("header", ""))
        if any(w in msg.lower() for w in ["expired","ssl_error","noindex","thin content"]):
            score += 20
        elif any(w in msg.lower() for w in ["missing h1","no contact form","missing title",
                                              "broken","mobile-responsive","missing alt"]):
            score += 12
        elif any(w in msg.lower() for w in ["missing meta","missing og","missing canonical",
                                              "multiple h1","stale copyright"]):
            score += 8
        elif any(w in msg.lower() for w in ["missing header","no hsts","no csp"]):
            score += 5
        elif "w3c" in msg.lower() or "markup" in msg.lower():
            score += min(int(re.search(r'(\d+)', msg).group(1)) * 0.2, 15) if re.search(r'(\d+)', msg) else 5
        else:
            score += 5
    return min(score, 100)

def finalize_audit_result(
    result: dict,
    *,
    html: str,
    headers: dict,
    profile: str,
    mode: str,
    schema_types: list[str] | None = None,
) -> dict:
    """Attach stable IDs, evidence, transparent scores and profile metadata."""
    detection = detect_site_type(html, schema_types or [])
    profile_name, profile_config = resolve_profile(profile, detection["site_type"])
    findings = normalize_defects(result.get("defects", []), url=result["url"])

    evidence = result.setdefault("evidence", {})
    evidence["raw_page"] = build_page_evidence(result["url"], html, headers, source="static")
    result["findings"] = findings
    result["category_scores"] = category_scores(findings)
    result["taxonomy"] = {
        "version": get_registry().taxonomy_version,
        "stable_check_ids": True,
    }
    result["site_type"] = detection
    result["audit_profile"] = {
        "name": profile_name,
        "config": profile_config,
    }
    result["audit_mode"] = {
        "requested": mode,
        "static_completed": True,
        "rendered_status": "not_requested",
    }
    result["score_semantics"] = {
        "score": "legacy opportunity/defect score; 100 means more defects/opportunity",
        "category_scores": "health scores; 100 means healthier",
    }
    return result

# ── main audit ──────────────────────────────────────────────────────
async def audit_one(
    session: httpx.AsyncClient,
    url: str,
    *,
    profile: str = "auto",
    mode: str = "static",
) -> dict:
    url = url.strip().rstrip("/")
    if not url.startswith("http"):
        url = "https://" + url
    domain_match = re.match(r"https?://([^/:]+)", url)
    domain = domain_match.group(1) if domain_match else url
    print(f"  🔍 {domain}")

    try:
        robots = await robots_policy(session, url, user_agent=USER_AGENT, timeout=10)
    except NetworkSafetyError as exc:
        robots = {
            "allowed": False,
            "robots_url": None,
            "reason": f"target blocked by network safety policy: {exc}",
            "crawl_delay": None,
        }

    if not robots.get("allowed", True):
        result = {
            "url": url,
            "domain": domain,
            "defects": [],
            "defect_count": 0,
            "score": 0,
            "evidence": {"robots": robots},
            "meta": {},
            "social": [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "audit_state": "skipped",
            "skip_reason": robots.get("reason", "robots.txt disallowed audit"),
        }
        return finalize_audit_result(
            result,
            html="",
            headers={},
            profile=profile,
            mode=mode,
            schema_types=[],
        )

    crawl_delay = robots.get("crawl_delay")
    if isinstance(crawl_delay, (int, float)) and crawl_delay > 0:
        await asyncio.sleep(min(float(crawl_delay), 30.0))

    page = await fetch_page(session, url)
    html = str(page.get("text") or "")
    headers = dict(page.get("headers") or {})
    if page.get("status") is not None:
        headers["status"] = page.get("status")

    if not html:
        reason = str(page.get("error") or "Cannot audit")
        result = {
            "url": url,
            "domain": domain,
            "defects": [{"defect": "Site unreachable", "impact": reason}],
            "defect_count": 1,
            "score": 100,
            "evidence": {
                "robots": robots,
                "network": {
                    "error": page.get("error"),
                    "redirect_chain": page.get("redirect_chain", []),
                },
            },
            "meta": {},
            "social": [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return finalize_audit_result(
            result,
            html="",
            headers=headers,
            profile=profile,
            mode=mode,
            schema_types=[],
        )

    soup = bs4.BeautifulSoup(html, "lxml")
    body_text = trafilatura.extract(html, include_links=False, include_images=False) or ""

    defects = []
    evidence = {
        "robots": robots,
        "network": {
            "requested_url": page.get("requested_url", url),
            "final_url": page.get("final_url", url),
            "status": page.get("status"),
            "bytes_read": page.get("bytes_read", 0),
            "redirect_chain": page.get("redirect_chain", []),
        },
    }

    # SSL
    ssl_info = check_ssl(domain)
    if ssl_info.get("expired"):
        days = ssl_info.get("days_remaining", 0)
        defects.append({"defect": f"Expired SSL ({days}d ago)", "impact": "Browser warnings; trust destroyed"})
    elif ssl_info.get("expiring_soon"):
        defects.append({"defect": f"SSL expiring in {ssl_info.get('days_remaining')}d", "impact": "Imminent outage"})
    elif ssl_info.get("ssl_error"):
        defects.append({"defect": "SSL verification failed", "impact": "Insecure connection"})

    # Security headers
    defects.extend(check_security_headers(headers))

    # HTML structure
    defects.extend(check_html_structure(soup, body_text))

    # Schema.org
    schema = check_schema_org(soup)
    evidence["schema_org"] = schema
    if schema["count"] == 0:
        defects.append({"defect": "No structured data (Schema.org)", "impact": "Rich results unavailable in search"})

    # Social links
    social = {}
    for platform, pattern in [("facebook", r"facebook\.com/[^\"'\s]+"), ("instagram", r"instagram\.com/[^\"'\s]+"),
                               ("twitter", r"twitter\.com/[^\"'\s]+"), ("linkedin", r"linkedin\.com/[^\"'\s]+"),
                               ("youtube", r"youtube\.com/[^\"'\s]+")]:
        m = re.findall(pattern, html, re.IGNORECASE)
        if m: social[platform] = list(set(m))[:3]
    evidence["social_links"] = list(social.keys())

    # Emails
    emails = extract_emails(html)
    evidence["emails"] = emails

    # Readability
    try:
        flesch, fk = readability_scores(body_text)
        evidence["readability"] = {
            "flesch": round(flesch, 1) if flesch is not None else None,
            "grade": round(fk, 1) if fk is not None else None,
        }
        if flesch is not None and flesch < 40:
            defects.append({"defect": f"Low readability (Flesch {flesch:.0f})", "impact": "Content too complex for general audience"})
    except Exception:
        evidence["readability"] = {"flesch": None, "grade": None}

    # Word count
    wc = len(body_text.split()) if body_text else 0
    evidence["word_count"] = wc

    # W3C markup (sampled)
    try:
        nu_url = f"https://validator.w3.org/nu/?doc={url}&out=json"
        r = await session.get(nu_url, timeout=20)
        if r.status_code == 200:
            data = r.json()
            errs = [m for m in data.get("messages", []) if m.get("type") == "error"]
            if errs:
                err_count = len(errs)
                defects.append({"defect": f"{err_count} HTML errors", "impact": "Rendering inconsistencies; SEO"})
                evidence["w3c_errors"] = err_count
    except Exception:
        pass

    # Broken links (internal, sampled) — safe fetcher re-validates redirects.
    hrefs = re.findall(r'href=["\'](/[^"\']*|https?://[^"\']*)["\']', html, re.IGNORECASE)
    final_base = str(page.get("final_url") or url)
    parsed_base = urllib.parse.urlsplit(final_base)
    base_domain = urllib.parse.urlunsplit((parsed_base.scheme, parsed_base.netloc, "", "", ""))
    internal = [h for h in hrefs if h.startswith("/") and len(h) > 1][:10]
    broken = []
    link_fetcher = SafeFetcher(
        session,
        timeout=8,
        max_redirects=5,
        max_body_bytes=64_000,
        per_domain_concurrency=2,
        delay_seconds=max(0.25, float(robots.get("crawl_delay") or 0)),
    )

    async def check_link(href):
        full = urllib.parse.urljoin(base_domain + "/", href)
        try:
            link_robots = await robots_policy(session, full, user_agent=USER_AGENT, timeout=8)
            if not link_robots.get("allowed", True):
                return
            response = await link_fetcher.head_status(full)
            if response.status >= 400:
                broken.append({"url": full, "status": response.status})
        except (httpx.HTTPError, NetworkSafetyError):
            return

    await asyncio.gather(*(check_link(h) for h in internal))
    if broken:
        defects.append({"defect": f"{len(broken)} broken link(s)", "impact": "Frustrates visitors; wastes crawl budget"})
        evidence["broken_links"] = broken

    score = score_defects(defects)

    # Extract meta description properly
    desc_tag = soup.find("meta", attrs={"name": "description"})
    desc_content = ""
    if desc_tag:
        desc_content = desc_tag.get("content", "").strip()
        if not desc_content:
            m = re.search(r'content=["\']([^"\']*)["\']', str(desc_tag))
            desc_content = m.group(1) if m else ""

    result = {
        "url": url, "domain": domain, "defects": defects, "defect_count": len(defects),
        "score": score, "evidence": evidence,
        "meta": {"title": soup.title.string.strip() if soup.title and soup.title.string else None,
                 "meta_description": desc_content if desc_content else None},
        "social": list(social.keys()), "emails": emails,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    result = finalize_audit_result(
        result,
        html=html,
        headers=headers,
        profile=profile,
        mode=mode,
        schema_types=schema.get("types", []),
    )
    if mode == "rendered":
        rendered = await collect_rendered_evidence(url)
        result["rendered_evidence"] = rendered
        result["audit_mode"]["rendered_status"] = rendered.get("status", "error")
    return result

async def audit_batch(
    urls: list,
    concurrency: int = CONCURRENCY,
    *,
    profile: str = "auto",
    mode: str = "static",
) -> list:
    sem = asyncio.Semaphore(concurrency)
    async def limited(url):
        async with sem:
            return await audit_one(client, url, profile=profile, mode=mode)
    async with httpx.AsyncClient(headers=HEADERS) as session:
        global client
        client = session
        results = await asyncio.gather(*(limited(u) for u in urls))
    return results

def generate_html_report(audit: dict) -> str:
    score = audit["score"]
    tier = "HOT" if score >= 80 else "WARM" if score >= 60 else "NURTURE" if score >= 40 else "COLD"
    color = "#FF1A1A" if score < 40 else "#FF8A00" if score < 60 else "#EFFF00" if score < 80 else "#00D4A3"
    rows = "".join(
        "<tr><td>"
        + html_lib.escape(str(d.get("defect", "")))
        + "</td><td>"
        + html_lib.escape(str(d.get("impact", "")))
        + "</td></tr>"
        for d in audit.get("defects", [])
    )
    domain = html_lib.escape(str(audit.get("domain", "")))
    timestamp = html_lib.escape(str(audit.get("timestamp", "")))
    return f"""<html><head>
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; object-src 'none'">
    <style>body{{font-family:sans-serif;margin:2em;background:#1a1a2e;color:#eee}}
    .score{{font-size:3em;color:{color};text-align:center}}
    table{{width:100%;border-collapse:collapse}} th,td{{padding:8px;text-align:left;border-bottom:1px solid #333}}
    </style></head><body><h1>{domain}</h1>
    <div class="score">{score}/100 — {tier}</div>
    <table><tr><th>Defect</th><th>Impact</th></tr>{rows}</table>
    <p><em>Generated {timestamp}</em></p></body></html>"""

# ── CLI ─────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(description="Website Rescue Auditor v2")
    p.add_argument("url", nargs="?", help="URL to audit")
    p.add_argument("--batch", metavar="CSV", help="Batch file (one URL per line)")
    p.add_argument("--concurrency", type=int, default=CONCURRENCY)
    p.add_argument("--format", choices=["md","json","html"], default="md")
    p.add_argument("--output", "-o", help="Output file")
    p.add_argument("--all", action="store_true", help="Full pipeline (audit + emails + report)")
    p.add_argument("--emails", action="store_true", help="Email discovery only")
    p.add_argument("--scout", metavar="FILE", help="Cross-reference prospects vs audits")
    p.add_argument("--cache-ttl", type=int, default=CACHE_TTL)
    p.add_argument("--mode", choices=["static", "rendered"], default="static",
                   help="Static HTTP/HTML audit or deep rendered Playwright/Lighthouse/axe audit")
    p.add_argument("--profile",
                   choices=["auto", "quick", "standard", "deep", "ecommerce", "leadgen", "nz_small_business"],
                   default="auto", help="Audit profile; auto uses deterministic site-type detection")
    p.add_argument("--enrich", action="store_true",
                   help="Add Tier 1 external enrichment (W3C/SSL Labs/urlscan/local "
                        "header grade keyless; PageSpeed/RankNibbler when keys set). "
                        "Additive only — existing checks untouched.")
    args = p.parse_args()

    async def _run():
        if args.scout:
            print(f"📋 Scouting: {args.scout}")
            return
        if args.batch:
            urls = Path(args.batch).read_text().splitlines()
            urls = [u.strip() for u in urls if u.strip()]
            print(f"🚀 Auditing {len(urls)} sites (concurrency={args.concurrency})...")
            results = await audit_batch(
                urls, args.concurrency, profile=args.profile, mode=args.mode
            )
            for r in results:
                print(f"  {r['domain']}: {r['score']}/100 ({r['defect_count']} defects)")
                safe = re.sub(r'[^\w.-]', '_', r['domain'])
                Path("audits").mkdir(exist_ok=True)
                Path(f"audits/{safe}.json").write_text(json.dumps(r, indent=2, default=str))
            return results
        if args.url:
            async with httpx.AsyncClient(headers=HEADERS) as session:
                global client
                client = session
                result = await audit_one(
                    session, args.url, profile=args.profile, mode=args.mode
                )
                if args.enrich:
                    from integrations.tier1_enrichment import enrich_audit
                    import os
                    include = ("headers", "w3c", "ssllabs", "urlscan")
                    if os.environ.get("PAGESPEED_API_KEY", "").strip():
                        include += ("pagespeed",)
                    if os.environ.get("RANKNIBBLER_API_KEY", "").strip():
                        include += ("ranknibbler",)
                    enrich_audit(result, await fetch_head(session, args.url), include=include)
            if args.format == "html":
                output = generate_html_report(result)
            elif args.format == "json":
                output = json.dumps(result, indent=2, default=str)
            else:
                output = json.dumps(result, indent=2, default=str)
            if args.output:
                Path(args.output).write_text(output)
                print(f"✅ Saved to {args.output}")
            else:
                print(output)
            return result
        p.print_help()

    asyncio.run(_run())

if __name__ == "__main__":
    main()
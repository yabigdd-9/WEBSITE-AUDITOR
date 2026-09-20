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
import argparse, asyncio, json, re, subprocess, sys, time, urllib.parse
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
async def fetch_html(session: httpx.AsyncClient, url: str) -> str:
    key = f"html:{url}"
    cached = cache_get(key)
    if cached: return cached
    try:
        r = await session.get(url, timeout=TIMEOUT, follow_redirects=True)
        html = r.text
        cache_set(key, html, ttl=3600)
        return html
    except Exception:
        return ""

async def fetch_head(session: httpx.AsyncClient, url: str) -> dict:
    key = f"head:{url}"
    cached = cache_get(key, ttl=1800)
    if cached: return cached
    try:
        r = await session.head(url, timeout=TIMEOUT, follow_redirects=True)
        result = dict(r.headers)
        result["status"] = r.status_code
        cache_set(key, result, ttl=1800)
        return result
    except Exception:
        return {}

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
    """Inspect a site's TLS certificate without invoking a shell."""
    import socket
    import ssl

    issues = {}
    try:
        context = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=10) as raw:
            with context.wrap_socket(raw, server_hostname=domain) as tls:
                cert = tls.getpeercert()
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
    except ssl.SSLCertVerificationError:
        return {"ssl_error": True, "error": "certificate verification failed"}
    except (socket.timeout, socket.gaierror, ConnectionError, OSError):
        return {"ssl_error": True, "error": "TLS connection failed"}

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

    html, headers = await asyncio.gather(
        fetch_html(session, url),
        fetch_head(session, url),
    )
    if not html:
        result = {
            "url": url,
            "domain": domain,
            "defects": [{"defect": "Site unreachable", "impact": "Cannot audit"}],
            "defect_count": 1,
            "score": 100,
            "evidence": {},
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
    evidence = {}

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

    # Broken links (internal, sampled)
    hrefs = re.findall(r'href=["\'](/[^"\']*|https?://[^"\']*)["\']', html, re.IGNORECASE)
    internal = [h for h in hrefs if h.startswith("/") and len(h) > 1][:10]
    base_m = re.match(r"(https?://[^/]+)", url)
    base_domain = base_m.group(1) if base_m else ""
    broken = []
    if base_domain:
        sem = asyncio.Semaphore(5)
        async def check_link(href):
            async with sem:
                full = base_domain + href
                try:
                    r = await session.head(full, timeout=8, follow_redirects=True)
                    if r.status_code >= 400: broken.append({"url": full, "status": r.status_code})
                except Exception:
                    try:
                        r = await session.get(full, timeout=8, follow_redirects=True)
                        if r.status_code >= 400: broken.append({"url": full, "status": r.status_code})
                    except Exception: pass
        await asyncio.gather(*(check_link(h) for h in internal))
    if broken:
        defects.append({"defect": f"{len(broken)} broken link(s)", "impact": "Frustrates visitors; wastes crawl budget"})
        evidence["broken_links"] = len(broken)

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
    rows = "".join(f"<tr><td>{d['defect']}</td><td>{d.get('impact','')}</td></tr>" for d in audit.get("defects", []))
    return f"""<html><head><style>body{{font-family:sans-serif;margin:2em;background:#1a1a2e;color:#eee}}
    .score{{font-size:3em;color:{color};text-align:center}}
    table{{width:100%;border-collapse:collapse}} th,td{{padding:8px;text-align:left;border-bottom:1px solid #333}}
    </style></head><body><h1>{audit['domain']}</h1>
    <div class="score">{score}/100 — {tier}</div>
    <table><tr><th>Defect</th><th>Impact</th></tr>{rows}</table>
    <p><em>Generated {audit['timestamp']}</em></p></body></html>"""

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
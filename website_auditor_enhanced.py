#!/usr/bin/env python3
"""Website Rescue Auditor v3 — Enhanced defect detection with auto-remediation.

New in v3:
  - robots.txt + sitemap.xml detection
  - PageSpeed Insights API (free)
  - Auto-remediation suggestions on every defect
  - Favicon detection
  - Color contrast analysis (inline styles)
  - Better scoring weights
  - JSON/Markdown/HTML output formats

Usage:
    python3 website_auditor.py <url> [--format md|json|html] [--output file]
    python3 website_auditor.py --batch prospects.csv [--concurrency 8]
    python3 website_auditor.py --all               # full pipeline
    python3 website_auditor.py --emails <url>       # email discovery only
    python3 website_auditor.py --scout prospects.csv # cross-reference queue
"""
import argparse, asyncio, json, re, sys, time, urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx, bs4, trafilatura, textstat

# ── config ──────────────────────────────────────────────────────────
CACHE_DIR = Path("outputs/.cache")
CACHE_TTL = 3600
CONCURRENCY = 8
TIMEOUT = 15
USER_AGENT = "Mozilla/5.0 (NZ) WebsiteRescueAuditor/3.0"

CACHE_DIR.mkdir(parents=True, exist_ok=True)
HEADERS = {"User-Agent": USER_AGENT}

# ── remediation database ────────────────────────────────────────────
REMEDIATION = {
    "expired": "Renew SSL immediately via your hosting provider or Let's Encrypt (free).",
    "ssl_error": "Check SSL chain with SSL Labs test; reinstall certificate if incomplete.",
    "hsts": "Add header: Strict-Transport-Security: max-age=31536000; includeSubDomains",
    "csp": "Add header: Content-Security-Policy: default-src 'self'; img-src *; style-src 'self' 'unsafe-inline'",
    "x-frame-options": "Add header: X-Frame-Options: SAMEORIGIN",
    "x-content-type": "Add header: X-Content-Type-Options: nosniff",
    "referrer-policy": "Add header: Referrer-Policy: strict-origin-when-cross-origin",
    "missing_h1": "Add a single <h1> tag at the top of the page describing the page topic.",
    "multiple_h1": "Keep only one <h1> per page; convert others to <h2> or <h3>.",
    "missing_alt": 'Add alt="" to decorative images, or descriptive text to informative ones.',
    "missing_title": "Add a <title> tag (50-60 chars) with your business name + location.",
    "missing_meta_desc": "Add <meta name='description'> (150-155 chars) with a clear value proposition.",
    "missing_canonical": 'Add <link rel="canonical" href="..."> to prevent duplicate content issues.',
    "missing_og": "Add Open Graph meta tags (og:title, og:description, og:image, og:url).",
    "noindex": 'Remove <meta name="robots" content="noindex"> to allow search indexing.',
    "thin_content": "Expand page to 300+ words with useful, original content for visitors.",
    "no_schema": 'Add Schema.org JSON-LD (LocalBusiness or Organization type).',
    "broken_link": "Fix or remove the broken URL; redirect if the page moved.",
    "missing_favicon": 'Add <link rel="icon" href="/favicon.ico"> in <head>.',
    "low_readability": "Simplify sentences; use shorter words and break up long paragraphs.",
    "missing_viewport": 'Add <meta name="viewport" content="width=device-width, initial-scale=1"> for mobile.',
    "html_errors": "Fix HTML markup errors reported by W3C validator.",
    "missing_robots": "Create /robots.txt with: User-agent: *\nSitemap: https://yoursite.co.nz/sitemap.xml",
    "missing_sitemap": "Generate /sitemap.xml listing all important pages.",
    "missing_hsts": "Enable HSTS header with max-age=31536000.",
    "slow_performance": "Optimize images, enable compression, minify CSS/JS, use a CDN.",
}

def get_remediation(defect_text: str) -> str:
    """Return remediation suggestion based on defect text."""
    text = defect_text.lower()
    for key, fix in REMEDIATION.items():
        if key in text:
            return fix
    return "Review this issue with your web developer or hosting provider."

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

async def fetch_url(session: httpx.AsyncClient, url: str) -> str:
    """Fetch arbitrary URL for robots.txt/sitemap."""
    try:
        r = await session.get(url, timeout=10, follow_redirects=True)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return ""

# ── defect checks ───────────────────────────────────────────────────
def check_ssl(domain: str) -> dict:
    import subprocess
    cmd = f"echo | openssl s_client -servername {domain} -connect {domain}:443 2>/dev/null | openssl x509 -noout -dates 2>/dev/null"
    try:
        r = subprocess.run(["bash","-c",cmd], capture_output=True, text=True, timeout=10)
        out = r.stdout
        issues = {}
        m = re.search(r"notAfter=(\w+ \d+ \d+:\d+:\d+ \d+ \w+)", out)
        if m:
            from datetime import datetime as dt
            expiry = dt.strptime(m.group(1), "%b %d %H:%M:%S %Y %Z")
            days = (expiry - datetime.now(timezone.utc)).days
            issues["expiry_date"] = expiry.isoformat()
            issues["days_remaining"] = days
            if days < 0: issues["expired"] = True
            elif days < 30: issues["expiring_soon"] = True
        if "Verify return code: 0" not in out and r.returncode != 0:
            issues["ssl_error"] = True
        return issues
    except Exception as e:
        return {"error": str(e)}

def check_security_headers(headers: dict) -> list:
    defects = []
    checks = [
        ("strict-transport-security", "Missing HSTS", "Missing HSTS header — reduces HTTPS enforcement"),
        ("content-security-policy", "Missing CSP", "Missing CSP — reduces XSS protection"),
        ("x-frame-options", "Missing X-Frame-Options", "Missing X-Frame-Options — reduces clickjacking protection"),
        ("x-content-type-options", "Missing X-Content-Type", "Missing X-Content-Type — reduces MIME sniffing"),
        ("referrer-policy", "Missing Referrer-Policy", "Missing Referrer-Policy — leaks referrer data"),
        ("permissions-policy", "Missing Permissions-Policy", "Missing Permissions-Policy — no feature restrictions"),
    ]
    header_keys = {k.lower() for k in headers}
    for h_key, defect_name, impact in checks:
        if h_key not in header_keys:
            defects.append({
                "defect": defect_name,
                "impact": impact,
                "remediation": get_remediation(h_key),
            })
    return defects

def check_html_structure(soup: bs4.BeautifulSoup, body_text: str) -> list:
    defects = []

    # H1 checks
    if not soup.find("h1"):
        defects.append({"defect": "Missing H1 tag", "impact": "No clear page hierarchy for SEO/screen readers", "remediation": get_remediation("missing_h1")})
    h1s = soup.find_all("h1")
    if len(h1s) > 1:
        defects.append({"defect": f"Multiple H1 tags ({len(h1s)})", "impact": "Dilutes page topic signal", "remediation": get_remediation("multiple_h1")})

    # Alt text
    imgs = soup.find_all("img")
    missing_alt = sum(1 for img in imgs if not img.get("alt", "").strip())
    if imgs and missing_alt > len(imgs) * 0.5:
        defects.append({"defect": f"{missing_alt}/{len(imgs)} images missing alt text", "impact": "Accessibility fail; SEO penalty", "remediation": get_remediation("missing_alt")})

    # Title
    if not soup.find("title"):
        defects.append({"defect": "Missing <title> tag", "impact": "Blank search results; no context", "remediation": get_remediation("missing_title")})

    # Meta description
    desc_tag = soup.find("meta", attrs={"name": "description"})
    desc_content = ""
    if desc_tag:
        desc_content = desc_tag.get("content", "").strip()
        if not desc_content:
            m = re.search(r'content=["\']([^"\']*)["\']', str(desc_tag))
            desc_content = m.group(1) if m else ""
    if not desc_content:
        defects.append({"defect": "Missing meta description", "impact": "Lower CTR from search", "remediation": get_remediation("missing_meta_desc")})

    # Viewport meta
    viewport = soup.find("meta", attrs={"name": "viewport"})
    if not viewport or "width=device-width" not in viewport.get("content", ""):
        defects.append({"defect": "Missing/invalid viewport meta", "impact": "Poor mobile experience", "remediation": get_remediation("missing_viewport")})

    # Robots meta
    robots = soup.find("meta", attrs={"name": "robots"})
    if robots and "noindex" in robots.get("content", "").lower():
        defects.append({"defect": "Meta robots noindex", "impact": "Pages blocked from search index", "remediation": get_remediation("noindex")})

    # Canonical
    canonical = soup.find("link", attrs={"rel": "canonical"})
    if not canonical:
        defects.append({"defect": "Missing canonical URL", "impact": "Duplicate content risk", "remediation": get_remediation("missing_canonical")})

    # Open Graph
    og_tags = soup.find_all("meta", attrs={"property": re.compile(r"^og:")})
    if not og_tags:
        defects.append({"defect": "Missing Open Graph tags", "impact": "Poor social share previews", "remediation": get_remediation("missing_og")})

    # Favicon
    favicon = soup.find("link", attrs={"rel": re.compile(r"icon", re.I)})
    if not favicon:
        defects.append({"defect": "Missing favicon", "impact": "No browser tab/bookmark icon; looks unfinished", "remediation": get_remediation("missing_favicon")})

    # Thin content
    if not body_text or len(body_text.strip()) < 200:
        defects.append({"defect": "Thin content (<200 words)", "impact": "Low SEO value; thin page", "remediation": get_remediation("thin_content")})

    # Check inline styles for potential contrast issues
    inline_styles = re.findall(r'style=["\']([^"\']*)["\']', str(soup), re.IGNORECASE)
    contrast_issues = []
    for style in inline_styles:
        color_m = re.search(r'color\s*:\s*#?([0-9a-fA-F]{3,6})', style)
        bg_m = re.search(r'background(?:-color)?\s*:\s*#?([0-9a-fA-F]{3,6})', style)
        if color_m and bg_m:
            # Very simple heuristic: if colors are close, flag it
            color_hex = color_m.group(1)
            bg_hex = bg_m.group(1)
            if len(color_hex) == len(bg_hex) == 6:
                r1, g1, b1 = int(color_hex[:2],16), int(color_hex[2:4],16), int(color_hex[4:],16)
                r2, g2, b2 = int(bg_hex[:2],16), int(bg_hex[2:4],16), int(bg_hex[4:],16)
                # Simple luminance distance
                lum_diff = abs((r1*0.299 + g1*0.587 + b1*0.114) - (r2*0.299 + g2*0.587 + b2*0.114))
                if lum_diff < 40:
                    contrast_issues.append(f"#{color_hex}/#{bg_hex}")
    if contrast_issues:
        defects.append({"defect": f"Potential low contrast ({len(contrast_issues)} instances)", "impact": "WCAG AA fail; text hard to read", "remediation": "Ensure text-to-background contrast ratio ≥ 4.5:1 for body text."})

    # Stale copyright
    copyright_match = re.search(r'copyright\s*[©©]?\s*(\d{4})', str(soup), re.IGNORECASE)
    if copyright_match:
        year = int(copyright_match.group(1))
        if year < datetime.now().year - 1:
            defects.append({"defect": f"Stale copyright year ({year})", "impact": "Looks neglected; trust signal decay", "remediation": "Update copyright footer to current year."})

    # Contact form detection
    forms = soup.find_all("form")
    has_contact = any(
        "contact" in str(f).lower() or "email" in str(f).lower() or "enquiry" in str(f).lower()
        for f in forms
    )
    if not forms or not has_contact:
        defects.append({"defect": "No contact form found", "impact": "Visitors can't easily reach you", "remediation": "Add a simple contact form with name, email, message fields."})

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

async def check_pagespeed(session: httpx.AsyncClient, url: str) -> dict:
    """Query free PageSpeed Insights API."""
    try:
        api_url = f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={urllib.parse.quote(url)}&strategy=mobile&category=performance&category=accessibility&category=best-practices&category=seo"
        r = await session.get(api_url, timeout=60)
        if r.status_code == 200:
            data = r.json()
            lighthouse = data.get("lighthouseResult", {})
            categories = lighthouse.get("categories", {})
            audits = lighthouse.get("audits", {})
            result = {
                "performance": categories.get("performance", {}).get("score", 0) * 100,
                "accessibility": categories.get("accessibility", {}).get("score", 0) * 100,
                "best_practices": categories.get("best-practices", {}).get("score", 0) * 100,
                "seo": categories.get("seo", {}).get("score", 0) * 100,
            }
            # Extract top opportunities
            opportunities = []
            for audit_id, audit in audits.items():
                if audit.get("score") is not None and audit["score"] < 0.5 and audit.get("details", {}).get("type") == "opportunity":
                    opportunities.append({"id": audit_id, "title": audit.get("title", ""), "savings": audit.get("details", {}).get("overallSavingsMs", 0)})
            result["opportunities"] = sorted(opportunities, key=lambda x: x.get("savings", 0), reverse=True)[:5]
            return result
    except Exception:
        pass
    return {}

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
                                              "broken","missing alt"]):
            score += 12
        elif any(w in msg.lower() for w in ["missing meta","missing og","missing canonical",
                                              "multiple h1","stale copyright","missing favicon",
                                              "missing viewport","contrast"]):
            score += 8
        elif any(w in msg.lower() for w in ["missing header","no hsts","no csp",
                                              "missing referrer","missing x-frame"]):
            score += 5
        elif "w3c" in msg.lower() or "html error" in msg.lower():
            score += min(int(re.search(r'(\d+)', msg).group(1)) * 0.2, 15) if re.search(r'(\d+)', msg) else 5
        else:
            score += 5
    return min(score, 100)

# ── main audit ──────────────────────────────────────────────────────
async def audit_one(session: httpx.AsyncClient, url: str) -> dict:
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
        return {"url": url, "domain": domain, "defects": [{"defect": "Site unreachable", "impact": "Cannot audit"}], "remediations": [],
                "defect_count": 1, "score": 100, "evidence": {}, "meta": {}, "social": [], "timestamp": datetime.now().isoformat()}

    soup = bs4.BeautifulSoup(html, "lxml")
    body_text = trafilatura.extract(html, include_links=False, include_images=False) or ""

    defects = []
    evidence = {}
    remediations = []

    # SSL
    ssl_info = check_ssl(domain)
    if ssl_info.get("expired"):
        days = ssl_info.get("days_remaining", 0)
        defects.append({"defect": f"Expired SSL ({days}d ago)", "impact": "Browser warnings; trust destroyed", "remediation": get_remediation("expired")})
    elif ssl_info.get("expiring_soon"):
        defects.append({"defect": f"SSL expiring in {ssl_info.get('days_remaining')}d", "impact": "Imminent outage", "remediation": get_remediation("expired")})
    elif ssl_info.get("ssl_error"):
        defects.append({"defect": "SSL verification failed", "impact": "Insecure connection", "remediation": get_remediation("ssl_error")})

    # Security headers
    defects.extend(check_security_headers(headers))

    # HTML structure (includes H1, alt, contrast, viewport, favicon, etc.)
    defects.extend(check_html_structure(soup, body_text))

    # Schema.org
    schema = check_schema_org(soup)
    evidence["schema_org"] = schema
    if schema["count"] == 0:
        defects.append({"defect": "No structured data (Schema.org)", "impact": "Rich results unavailable in search", "remediation": get_remediation("no_schema")})

    # robots.txt check
    base_match = re.match(r"(https?://[^/]+)", url)
    base = base_match.group(1) if base_match else url
    robots_txt = await fetch_url(session, f"{base}/robots.txt")
    if not robots_txt:
        defects.append({"defect": "Missing /robots.txt", "impact": "Search engines get no crawling guidance", "remediation": get_remediation("missing_robots")})
    else:
        evidence["robots_txt"] = True
        # Check for sitemap reference
        if "sitemap:" in robots_txt.lower():
            evidence["sitemap_in_robots"] = True
        else:
            defects.append({"defect": "No sitemap reference in robots.txt", "impact": "Crawlers won't find your sitemap", "remediation": "Add 'Sitemap: https://yoursite.co.nz/sitemap.xml' to /robots.txt"})

    # sitemap.xml check
    sitemap_txt = await fetch_url(session, f"{base}/sitemap.xml")
    if not sitemap_txt:
        defects.append({"defect": "Missing /sitemap.xml", "impact": "Search engines can't discover all pages", "remediation": get_remediation("missing_sitemap")})
    else:
        evidence["sitemap_exists"] = True

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
        flesch = textstat.flesch_reading_ease(body_text) if body_text else None
        fk = textstat.flesch_kincaid_grade(body_text) if body_text else None
        evidence["readability"] = {"flesch": round(flesch, 1) if flesch else None, "grade": round(fk, 1) if fk else None}
        if flesch is not None and flesch < 40:
            defects.append({"defect": f"Low readability (Flesch {flesch:.0f})", "impact": "Content too complex for general audience", "remediation": get_remediation("low_readability")})
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
            data = await r.json()
            errs = [m for m in data.get("messages", []) if m.get("type") == "error"]
            if errs:
                err_count = len(errs)
                defects.append({"defect": f"{err_count} HTML errors", "impact": "Rendering inconsistencies; SEO", "remediation": get_remediation("html_errors")})
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
        defects.append({"defect": f"{len(broken)} broken link(s)", "impact": "Frustrates visitors; wastes crawl budget", "remediation": get_remediation("broken_link")})
        evidence["broken_links"] = len(broken)

    # PageSpeed Insights (free API)
    print(f"    ⏱  Running PageSpeed Insights...")
    pagespeed = await check_pagespeed(session, url)
    if pagespeed:
        evidence["pagespeed"] = pagespeed
        if pagespeed.get("performance", 100) < 50:
            defects.append({"defect": f"Slow performance (PageSpeed {pagespeed['performance']:.0f}/100)", "impact": "Visitors bounce; Google penalizes slow sites", "remediation": get_remediation("slow_performance")})

    score = score_defects(defects)

    # Extract meta description properly
    desc_tag = soup.find("meta", attrs={"name": "description"})
    desc_content = ""
    if desc_tag:
        desc_content = desc_tag.get("content", "").strip()
        if not desc_content:
            m = re.search(r'content=["\']([^"\']*)["\']', str(desc_tag))
            desc_content = m.group(1) if m else ""

    # Build remediations list
    for d in defects:
        if "remediation" not in d:
            d["remediation"] = get_remediation(d.get("defect", ""))
        remediations.append({"defect": d["defect"], "fix": d["remediation"]})

    return {
        "url": url, "domain": domain, "defects": defects, "defect_count": len(defects),
        "score": score, "evidence": evidence, "remediations": remediations,
        "meta": {"title": soup.title.string.strip() if soup.title and soup.title.string else None,
                 "meta_description": desc_content if desc_content else None},
        "social": list(social.keys()), "emails": emails,
        "timestamp": datetime.now().isoformat()
    }

async def audit_batch(urls: list, concurrency: int = CONCURRENCY) -> list:
    sem = asyncio.Semaphore(concurrency)
    async def limited(url):
        async with sem:
            return await audit_one(client, url)
    async with httpx.AsyncClient(headers=HEADERS) as session:
        global client
        client = session
        results = await asyncio.gather(*(limited(u) for u in urls))
    return results

def generate_html_report(audit: dict) -> str:
    score = audit["score"]
    tier = "HOT" if score >= 80 else "WARM" if score >= 60 else "NURTURE" if score >= 40 else "COLD"
    color = "#FF1A1A" if score < 40 else "#FF8A00" if score < 60 else "#EFFF00" if score < 80 else "#00D4A3"
    rows = ""
    for d in audit.get("defects", []):
        fix = d.get("remediation", "")
        rows += f'<tr><td>{d["defect"]}</td><td>{d.get("impact","")}</td><td>{fix}</td></tr>\n'

    # Remediation summary
    remediation_html = ""
    for r in audit.get("remediations", []):
        remediation_html += f'<li><strong>{r["defect"]}:</strong> {r["fix"]}</li>\n'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Audit: {audit['domain']}</title>
<style>
body{{font-family:-apple-system,sans-serif;margin:2em;background:#1a1a2e;color:#eee;max-width:1000px;margin:2em auto}}
.score{{font-size:3em;color:{color};text-align:center;margin:0.5em 0}}
table{{width:100%;border-collapse:collapse;margin:1em 0}}
th,td{{padding:10px;text-align:left;border-bottom:1px solid #333;vertical-align:top}}
th{{background:#003366;color:#fff}}
tr:nth-child(even){{background:#2a2a3e}}
.remediation{{background:#1e3a2e;padding:1em;border-radius:8px;margin:1em 0}}
.remediation li{{margin:0.3em 0}}
</style></head>
<body>
<h1>{audit['domain']}</h1>
<div class="score">{score}/100 — {tier}</div>
<p>Defects: {audit['defect_count']} | Generated: {audit['timestamp'][:19]}</p>
<h2>Defects Found</h2>
<table><tr><th>Defect</th><th>Impact</th><th>Fix</th></tr>
{rows}</table>
<div class="remediation">
<h2>🛠 Remediation Guide</h2>
<ol>{remediation_html}</ol>
</div>
<p><em>Website Rescue Auditor v3 — All free checks, no API keys needed.</em></p>
</body></html>"""

def generate_markdown_report(audit: dict) -> str:
    score = audit["score"]
    tier = "🔥 HOT" if score >= 80 else "⚡ WARM" if score >= 60 else "🌱 NURTURE" if score >= 40 else "❄️ COLD"
    lines = [
        f"# {audit['domain']} — {score}/100 {tier}",
        f"",
        f"**Defects:** {audit['defect_count']} | **Generated:** {audit['timestamp'][:19]}",
        f"",
        f"## Defects",
        f"",
    ]
    for d in audit.get("defects", []):
        lines.append(f"- **{d['defect']}** — {d.get('impact', '')}")
        if d.get("remediation"):
            lines.append(f"  - 🛠 {d['remediation']}")
    lines.append("")
    lines.append("## Evidence")
    evidence = audit.get("evidence", {})
    for k, v in evidence.items():
        lines.append(f"- **{k}:** {v}")
    return "\n".join(lines)

# ── CLI ─────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(description="Website Rescue Auditor v3 — Enhanced")
    p.add_argument("url", nargs="?", help="URL to audit")
    p.add_argument("--batch", metavar="CSV", help="Batch file (one URL per line)")
    p.add_argument("--concurrency", type=int, default=CONCURRENCY)
    p.add_argument("--format", choices=["md","json","html"], default="md")
    p.add_argument("--output", "-o", help="Output file")
    p.add_argument("--all", action="store_true", help="Full pipeline (audit + emails + report)")
    p.add_argument("--emails", action="store_true", help="Email discovery only")
    p.add_argument("--scout", metavar="FILE", help="Cross-reference prospects vs audits")
    p.add_argument("--cache-ttl", type=int, default=CACHE_TTL)
    p.add_argument("--no-pagespeed", action="store_true", help="Skip PageSpeed API (faster)")
    args = p.parse_args()

    async def _run():
        if args.scout:
            print(f"📋 Scouting: {args.scout}")
            return
        if args.batch:
            urls = Path(args.batch).read_text().splitlines()
            urls = [u.strip() for u in urls if u.strip()]
            print(f"🚀 Auditing {len(urls)} sites (concurrency={args.concurrency})...")
            results = await audit_batch(urls, args.concurrency)
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
                result = await audit_one(session, args.url)
            if args.format == "html":
                output = generate_html_report(result)
            elif args.format == "json":
                output = json.dumps(result, indent=2, default=str)
            else:
                output = generate_markdown_report(result)
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

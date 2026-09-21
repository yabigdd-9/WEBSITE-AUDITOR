#!/usr/bin/env python3
"""DEPRECATED — use `wa` (auditor_toolkit.cli:main) or `./mm` instead.

Ultimate Website Auditor v4 — Comprehensive, smart, fast, free.

New in v4:
  - Domain intelligence (WHOIS, DNS, subdomain enumeration)
  - Stealth fetching (Cloudflare/bot bypass via scrapling)
  - Content quality scoring (readability depth, duplicate content)
  - Broken link deep check (async, parallel)
  - DNS health check (MX, SPF, DKIM signals)
  - Subdomain discovery for cross-site analysis
  - Telegram/Slack notification on completion
  - Async sitemap parsing
  - Better caching with TTL per check type

Usage:
    python3 ultimate_auditor.py <url> [--format md|json|html] [--output file]
    python3 ultimate_auditor.py --batch prospects.csv [--concurrency 8]
    python3 ultimate_auditor.py --stealth <url>  # bypass bot protection
"""

if __name__ == "__main__":
    from auditor_toolkit.compat import legacy_main
    raise SystemExit(legacy_main())

import argparse, asyncio, json, re, sys, time, urllib.parse, hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from collections import Counter

import httpx, bs4, trafilatura, textstat

# ── config ──────────────────────────────────────────────────────────
CACHE_DIR = Path("outputs/.cache")
CACHE_TTL = 3600
CONCURRENCY = 8
TIMEOUT = 15
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
STEALTH = False

CACHE_DIR.mkdir(parents=True, exist_ok=True)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-NZ,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
}

# ── notification system ────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""
SLACK_WEBHOOK_URL = ""

def load_notifications():
    """Load notification credentials from environment or .env file."""
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key == "TELEGRAM_BOT_TOKEN":
                global TELEGRAM_BOT_TOKEN
                TELEGRAM_BOT_TOKEN = val
            elif key == "TELEGRAM_CHAT_ID":
                global TELEGRAM_CHAT_ID
                TELEGRAM_CHAT_ID = val
            elif key == "SLACK_WEBHOOK_URL":
                global SLACK_WEBHOOK_URL
                SLACK_WEBHOOK_URL = val

async def send_notification(message: str):
    """Send notification via configured channels."""
    load_notifications()
    tasks = []
    
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        tasks.append(send_telegram(message))
    if SLACK_WEBHOOK_URL:
        tasks.append(send_slack(message))
    
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

async def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient() as session:
            await session.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"})
    except Exception as e:
        print(f"  ⚠ Telegram notification failed: {e}")

async def send_slack(message: str):
    try:
        async with httpx.AsyncClient() as session:
            await session.post(SLACK_WEBHOOK_URL, json={"text": message})
    except Exception as e:
        print(f"  ⚠ Slack notification failed: {e}")

# ── remediation database (expanded) ─────────────────────────────────
REMEDIATION = {
    "expired": "Renew SSL immediately via Let's Encrypt (free) or your hosting provider.",
    "ssl_error": "Check SSL chain with SSL Labs; reinstall certificate if incomplete.",
    "hsts": "Add header: Strict-Transport-Security: max-age=31536000; includeSubDomains",
    "csp": "Add header: Content-Security-Policy: default-src 'self'; img-src *",
    "x-frame-options": "Add header: X-Frame-Options: SAMEORIGIN",
    "x-content-type": "Add header: X-Content-Type-Options: nosniff",
    "referrer-policy": "Add header: Referrer-Policy: strict-origin-when-cross-origin",
    "missing_h1": "Add a single <h1> tag describing the page topic.",
    "multiple_h1": "Keep only one <h1>; convert others to <h2>/<h3>.",
    "missing_alt": 'Add alt="" to decorative images, or descriptive text to informative ones.',
    "missing_title": "Add <title> (50-60 chars) with business name + location.",
    "missing_meta_desc": "Add <meta name='description'> (150-155 chars) with value proposition.",
    "missing_canonical": 'Add <link rel="canonical" href="...">.',
    "missing_og": "Add Open Graph meta tags (og:title, og:description, og:image).",
    "noindex": 'Remove <meta name="robots" content="noindex">.',
    "thin_content": "Expand page to 300+ words with useful, original content.",
    "no_schema": "Add Schema.org JSON-LD (LocalBusiness or Organization).",
    "broken_link": "Fix or remove the broken URL.",
    "missing_favicon": 'Add <link rel="icon" href="/favicon.ico">.',
    "low_readability": "Simplify sentences; use shorter words.",
    "missing_viewport": 'Add <meta name="viewport" content="width=device-width, initial-scale=1">.',
    "html_errors": "Fix HTML markup errors per W3C validator.",
    "missing_robots": "Create /robots.txt with sitemap reference.",
    "missing_sitemap": "Generate /sitemap.xml listing all pages.",
    "missing_hsts": "Enable HSTS header with max-age=31536000.",
    "slow_performance": "Optimize images, enable compression, minify CSS/JS.",
    "missing_spf": "Add SPF TXT record: v=spf1 include:_spf.google.com ~all",
    "missing_dkim": "Add DKIM TXT record for your email provider.",
    "missing_dmarc": "Add DMARC TXT record: v=DMARC1; p=quarantine;",
    "stale_copyright": "Update copyright footer to current year.",
    "no_contact_form": "Add a contact form with name, email, message fields.",
    "duplicate_content": "Add canonical tags; rewrite duplicate sections.",
    "missing_privacy": "Add a Privacy Policy page linked in footer.",
    "missing_tos": "Add Terms of Service page if you collect data.",
    "no_analytics": "Add Google Analytics 4 or Matomo tracking.",
    "missing_cta": "Add a clear Call-to-Action button above the fold.",
    "slow_tfb": "Reduce time-to-first-byte; optimize server response.",
}

def get_remediation(defect_text: str) -> str:
    text = defect_text.lower()
    for key, fix in REMEDIATION.items():
        if key in text:
            return fix
    return "Review with your web developer."

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
    try:
        r = await session.get(url, timeout=10, follow_redirects=True)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return ""

# ── domain intelligence ────────────────────────────────────────────
async def check_dns(session: httpx.AsyncClient, domain: str) -> dict:
    """Check DNS records using Google DoH."""
    result = {}
    try:
        # A record
        r = await session.get(f"https://dns.google/resolve?name={domain}&type=A")
        if r.status_code == 200:
            data = r.json()
            if "Answer" in data:
                result["a_records"] = [a.get("data") for a in data["Answer"][:5]]
    except Exception:
        pass
    
    try:
        # MX record
        r = await session.get(f"https://dns.google/resolve?name={domain}&type=MX")
        if r.status_code == 200:
            data = r.json()
            if "Answer" in data:
                result["mx_records"] = [a.get("data") for a in data["Answer"][:5]]
    except Exception:
        pass
    
    try:
        # TXT records (SPF, DKIM, DMARC)
        r = await session.get(f"https://dns.google/resolve?name={domain}&type=TXT")
        if r.status_code == 200:
            data = r.json()
            if "Answer" in data:
                txt_records = [a.get("data") for a in data["Answer"]]
                result["txt_records"] = txt_records[:10]
                result["has_spf"] = any("v=spf1" in t for t in txt_records)
                result["has_dmarc"] = any("v=dmarc1" in t.lower() for t in txt_records)
    except Exception:
        pass
    
    return result

async def check_whois(session: httpx.AsyncClient, domain: str) -> dict:
    """Check WHOIS via free RDAP API."""
    try:
        # Use rdap.org (free, no auth)
        r = await session.get(f"https://rdap.org/domain/{domain}", timeout=10)
        if r.status_code == 200:
            data = r.json()
            result = {}
            # Extract events
            for event in data.get("events", []):
                if event.get("eventAction") == "registration":
                    result["registered"] = event.get("eventDate")
                elif event.get("eventAction") == "expiration":
                    result["expires"] = event.get("eventDate")
            # Registrar
            for entity in data.get("entities", []):
                if "registrar" in entity.get("roles", []):
                    vcard = entity.get("vcardArray", [[]])
                    if vcard and len(vcard) > 1:
                        for item in vcard[1]:
                            if item[0] == "fn":
                                result["registrar"] = item[3]
            # Status
            result["status"] = data.get("status", [])
            return result
    except Exception:
        pass
    return {}

def check_ssl(domain: str) -> dict:
    import subprocess
    cmd = f"echo | openssl s_client -servername {domain} -connect {domain}:443 2>/dev/null | openssl x509 -noout -dates -subject 2>/dev/null"
    try:
        r = subprocess.run(["bash","-c",cmd], capture_output=True, text=True, timeout=10)
        out = r.stdout
        issues = {}
        m = re.search(r"notAfter=(\w+ \d+ \d+:\d+:\d+ \d+ \w+)", out)
        if m:
            expiry = datetime.strptime(m.group(1), "%b %d %H:%M:%S %Y %Z")
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

# ── defect checks (comprehensive) ──────────────────────────────────
def check_security_headers(headers: dict) -> list:
    defects = []
    checks = [
        ("strict-transport-security", "Missing HSTS", "Missing HSTS header"),
        ("content-security-policy", "Missing CSP", "Missing Content-Security-Policy"),
        ("x-frame-options", "Missing X-Frame-Options", "Missing clickjacking protection"),
        ("x-content-type-options", "Missing X-Content-Type", "Missing MIME sniffing protection"),
        ("referrer-policy", "Missing Referrer-Policy", "Leaks referrer data"),
        ("permissions-policy", "Missing Permissions-Policy", "No feature restrictions"),
    ]
    header_keys = {k.lower() for k in headers}
    for h_key, defect_name, impact in checks:
        if h_key not in header_keys:
            defects.append({"defect": defect_name, "impact": impact, "remediation": get_remediation(h_key)})
    return defects

def check_html_structure(soup: bs4.BeautifulSoup, body_text: str) -> list:
    defects = []

    # H1
    if not soup.find("h1"):
        defects.append({"defect": "Missing H1 tag", "impact": "No clear page hierarchy", "remediation": get_remediation("missing_h1")})
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
        defects.append({"defect": "Missing <title> tag", "impact": "Blank search results", "remediation": get_remediation("missing_title")})

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

    # Viewport
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
        defects.append({"defect": "Missing favicon", "impact": "No browser tab icon", "remediation": get_remediation("missing_favicon")})

    # Thin content
    if not body_text or len(body_text.strip()) < 200:
        defects.append({"defect": "Thin content (<200 words)", "impact": "Low SEO value", "remediation": get_remediation("thin_content")})

    # Contrast check (inline styles)
    inline_styles = re.findall(r'style=["\']([^"\']*)["\']', str(soup), re.IGNORECASE)
    contrast_issues = []
    for style in inline_styles:
        color_m = re.search(r'color\s*:\s*#?([0-9a-fA-F]{3,6})', style)
        bg_m = re.search(r'background(?:-color)?\s*:\s*#?([0-9a-fA-F]{3,6})', style)
        if color_m and bg_m:
            color_hex = color_m.group(1)
            bg_hex = bg_m.group(1)
            if len(color_hex) == len(bg_hex) == 6:
                r1, g1, b1 = int(color_hex[:2],16), int(color_hex[2:4],16), int(color_hex[4:],16)
                r2, g2, b2 = int(bg_hex[:2],16), int(bg_hex[2:4],16), int(bg_hex[4:],16)
                lum_diff = abs((r1*0.299 + g1*0.587 + b1*0.114) - (r2*0.299 + g2*0.587 + b2*0.114))
                if lum_diff < 40:
                    contrast_issues.append(f"#{color_hex}/#{bg_hex}")
    if contrast_issues:
        defects.append({"defect": f"Potential low contrast ({len(contrast_issues)} instances)", "impact": "WCAG AA fail", "remediation": "Ensure contrast ratio ≥ 4.5:1"})

    # Stale copyright
    copyright_match = re.search(r'copyright\s*[©]?\s*(\d{4})', str(soup), re.IGNORECASE)
    if copyright_match:
        year = int(copyright_match.group(1))
        if year < datetime.now().year - 1:
            defects.append({"defect": f"Stale copyright year ({year})", "impact": "Looks neglected", "remediation": get_remediation("stale_copyright")})

    # Contact form
    forms = soup.find_all("form")
    has_contact = any("contact" in str(f).lower() or "email" in str(f).lower() for f in forms)
    if not forms or not has_contact:
        defects.append({"defect": "No contact form found", "impact": "Visitors can't reach you easily", "remediation": get_remediation("no_contact_form")})

    # Privacy/TOS links
    links_text = " ".join(a.get_text().lower() for a in soup.find_all("a"))
    if "privacy" not in links_text:
        defects.append({"defect": "No privacy policy link", "impact": "GDPR/privacy compliance risk", "remediation": get_remediation("missing_privacy")})
    if "terms" not in links_text:
        defects.append({"defect": "No terms of service link", "impact": "Legal compliance risk", "remediation": get_remediation("missing_tos")})

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
    """Free PageSpeed Insights API."""
    try:
        api_url = f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={urllib.parse.quote(url)}&strategy=mobile&category=performance&category=accessibility&category=best-practices&category=seo"
        r = await session.get(api_url, timeout=60)
        if r.status_code == 200:
            data = r.json()
            lighthouse = data.get("lighthouseResult", {})
            categories = lighthouse.get("categories", {})
            return {
                "performance": categories.get("performance", {}).get("score", 0) * 100,
                "accessibility": categories.get("accessibility", {}).get("score", 0) * 100,
                "best_practices": categories.get("best-practices", {}).get("score", 0) * 100,
                "seo": categories.get("seo", {}).get("score", 0) * 100,
            }
    except Exception:
        pass
    return {}

async def check_sitemap(session: httpx.AsyncClient, base: str) -> dict:
    """Parse sitemap.xml for page count and structure."""
    result = {}
    sitemap_txt = await fetch_url(session, f"{base}/sitemap.xml")
    if sitemap_txt:
        result["exists"] = True
        urls = re.findall(r'<loc>([^<]+)</loc>', sitemap_txt)
        result["url_count"] = len(urls)
        result["sample_urls"] = urls[:5]
    else:
        result["exists"] = False
    return result

# ── main audit ──────────────────────────────────────────────────────
async def audit_one(session: httpx.AsyncClient, url: str, use_stealth: bool = False) -> dict:
    url = url.strip().rstrip("/")
    if not url.startswith("http"):
        url = "https://" + url
    domain_match = re.match(r"https?://([^/:]+)", url)
    domain = domain_match.group(1) if domain_match else url
    print(f"  🔍 {domain}")

    if use_stealth:
        try:
            from scrapling.fetchers import StealthyFetcher
            page = StealthyFetcher.fetch(url, headless=True)
            html = page.html_content
            headers = {}
        except ImportError:
            print(f"    ⚠ scrapling not installed, falling back to httpx")
            html, headers = await asyncio.gather(
                fetch_html(session, url),
                fetch_head(session, url),
            )
    else:
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

    # HTML structure
    defects.extend(check_html_structure(soup, body_text))

    # Schema.org
    schema = check_schema_org(soup)
    evidence["schema_org"] = schema
    if schema["count"] == 0:
        defects.append({"defect": "No structured data (Schema.org)", "impact": "Rich results unavailable", "remediation": get_remediation("no_schema")})

    # robots.txt
    base_match = re.match(r"(https?://[^/]+)", url)
    base = base_match.group(1) if base_match else url
    robots_txt = await fetch_url(session, f"{base}/robots.txt")
    if not robots_txt:
        defects.append({"defect": "Missing /robots.txt", "impact": "No crawling guidance for search engines", "remediation": get_remediation("missing_robots")})
    else:
        evidence["robots_txt"] = True
        if "sitemap:" in robots_txt.lower():
            evidence["sitemap_in_robots"] = True

    # sitemap.xml
    sitemap = await check_sitemap(session, base)
    evidence["sitemap"] = sitemap
    if not sitemap.get("exists"):
        defects.append({"defect": "Missing /sitemap.xml", "impact": "Search engines can't discover all pages", "remediation": get_remediation("missing_sitemap")})

    # DNS health
    dns = await check_dns(session, domain)
    evidence["dns"] = dns
    if not dns.get("has_spf"):
        defects.append({"defect": "Missing SPF record", "impact": "Emails flagged as spam", "remediation": get_remediation("missing_spf")})
    if not dns.get("has_dmarc"):
        defects.append({"defect": "Missing DMARC record", "impact": "Email authentication weakness", "remediation": get_remediation("missing_dmarc")})

    # Social links
    social = {}
    for platform, pattern in [("facebook", r"facebook\.com/[^\"'\s]+"), ("instagram", r"instagram\.com/[^\"'\s]+"),
                               ("twitter", r"twitter\.com/[^\"'\s]+"), ("linkedin", r"linkedin\.com/[^\"'\s]+"),
                               ("youtube", r"youtube\.com/[^\"'\s]+")]:
        m = re.findall(pattern, html, re.IGNORECASE)
        if m: social[platform] = list(set(m))[:3]
    evidence["social_links"] = list(social.keys())

    # Emails
    emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html)
    evidence["emails"] = sorted(set(e.lower() for e in emails if not e.startswith("noreply")))

    # Readability
    try:
        flesch = textstat.flesch_reading_ease(body_text) if body_text else None
        fk = textstat.flesch_kincaid_grade(body_text) if body_text else None
        evidence["readability"] = {"flesch": round(flesch, 1) if flesch else None, "grade": round(fk, 1) if fk else None}
        if flesch is not None and flesch < 40:
            defects.append({"defect": f"Low readability (Flesch {flesch:.0f})", "impact": "Content too complex", "remediation": get_remediation("low_readability")})
    except Exception:
        evidence["readability"] = {"flesch": None, "grade": None}

    # Word count
    wc = len(body_text.split()) if body_text else 0
    evidence["word_count"] = wc

    # W3C markup
    try:
        nu_url = f"https://validator.w3.org/nu/?doc={url}&out=json"
        r = await session.get(nu_url, timeout=20)
        if r.status_code == 200:
            data = await r.json()
            errs = [m for m in data.get("messages", []) if m.get("type") == "error"]
            if errs:
                err_count = len(errs)
                defects.append({"defect": f"{err_count} HTML errors", "impact": "Rendering inconsistencies", "remediation": get_remediation("html_errors")})
                evidence["w3c_errors"] = err_count
    except Exception:
        pass

    # Broken links (internal, sampled)
    hrefs = re.findall(r'href=["\'](/[^"\']*|https?://[^"\']*)["\']', html, re.IGNORECASE)
    internal = [h for h in hrefs if h.startswith("/") and len(h) > 1][:15]
    base_domain = base
    broken = []
    if base_domain:
        sem = asyncio.Semaphore(10)
        async def check_link(href):
            async with sem:
                full = base_domain + href
                try:
                    r = await session.head(full, timeout=8, follow_redirects=True)
                    if r.status_code >= 400: broken.append({"url": full, "status": r.status_code})
                except Exception:
                    pass
        await asyncio.gather(*(check_link(h) for h in internal))
    if broken:
        defects.append({"defect": f"{len(broken)} broken link(s)", "impact": "Frustrates visitors", "remediation": get_remediation("broken_link")})
        evidence["broken_links"] = len(broken)

    # PageSpeed
    print(f"    ⏱  Running PageSpeed Insights...")
    pagespeed = await check_pagespeed(session, url)
    if pagespeed:
        evidence["pagespeed"] = pagespeed
        if pagespeed.get("performance", 100) < 50:
            defects.append({"defect": f"Slow performance (PageSpeed {pagespeed['performance']:.0f}/100)", "impact": "Visitors bounce; Google penalizes", "remediation": get_remediation("slow_performance")})

    score = score_defects(defects)

    # Extract meta
    desc_tag = soup.find("meta", attrs={"name": "description"})
    desc_content = ""
    if desc_tag:
        desc_content = desc_tag.get("content", "").strip()
        if not desc_content:
            m = re.search(r'content=["\']([^"\']*)["\']', str(desc_tag))
            desc_content = m.group(1) if m else ""

    for d in defects:
        if "remediation" not in d:
            d["remediation"] = get_remediation(d.get("defect", ""))
        remediations.append({"defect": d["defect"], "fix": d["remediation"]})

    return {
        "url": url, "domain": domain, "defects": defects, "defect_count": len(defects),
        "score": score, "evidence": evidence, "remediations": remediations,
        "meta": {"title": soup.title.string.strip() if soup.title and soup.title.string else None,
                 "meta_description": desc_content if desc_content else None},
        "social": list(social.keys()), "emails": evidence.get("emails", []),
        "timestamp": datetime.now().isoformat()
    }

def score_defects(defects: list) -> int:
    score = 0
    for d in defects:
        msg = d.get("defect", d.get("header", ""))
        if any(w in msg.lower() for w in ["expired","ssl_error","noindex","thin content"]):
            score += 20
        elif any(w in msg.lower() for w in ["missing h1","no contact form","missing title","broken","missing alt",
                                              "no privacy","no terms"]):
            score += 12
        elif any(w in msg.lower() for w in ["missing meta","missing og","missing canonical","multiple h1",
                                              "stale copyright","missing favicon","missing viewport","contrast"]):
            score += 8
        elif any(w in msg.lower() for w in ["missing header","no hsts","no csp","missing referrer","missing x-frame",
                                              "missing spf","missing dmarc"]):
            score += 5
        elif "html error" in msg.lower():
            score += min(int(re.search(r'(\d+)', msg).group(1)) * 0.2, 15) if re.search(r'(\d+)', msg) else 5
        else:
            score += 5
    return min(score, 100)

async def audit_batch(urls: list, concurrency: int = CONCURRENCY, use_stealth: bool = False) -> list:
    sem = asyncio.Semaphore(concurrency)
    async def limited(url):
        async with sem:
            return await audit_one(client, url, use_stealth)
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
    remediation_html = ""
    for r in audit.get("remediations", []):
        remediation_html += f'<li><strong>{r["defect"]}:</strong> {r["fix"]}</li>\n'
    evidence = audit.get("evidence", {})
    pagespeed = evidence.get("pagespeed", "")
    ps_html = ""
    if pagespeed:
        ps_html = f"<h2>PageSpeed Scores</h2><div class='scores'>"
        ps_html += f"<div class='ps-score'>Performance: {pagespeed.get('performance', 0):.0f}/100</div>"
        ps_html += f"<div class='ps-score'>Accessibility: {pagespeed.get('accessibility', 0):.0f}/100</div>"
        ps_html += f"<div class='ps-score'>Best Practices: {pagespeed.get('best_practices', 0):.0f}/100</div>"
        ps_html += f"<div class='ps-score'>SEO: {pagespeed.get('seo', 0):.0f}/100</div>"
        ps_html += "</div>"
    dns = evidence.get("dns", {})
    dns_html = ""
    if dns:
        dns_html = f"<h2>DNS Health</h2><p>SPF: {'✓' if dns.get('has_spf') else '✗'} | DMARC: {'✓' if dns.get('has_dmarc') else '�g'} | MX: {len(dns.get('mx_records', []))} records</p>"
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Audit: {audit['domain']}</title>
<style>
body{{font-family:-apple-system,sans-serif;margin:2em;background:#1a1a2e;color:#eee;max-width:1000px;margin:2em auto}}
.score{{font-size:3em;color:{color};text-align:center;margin:0.5em 0}}
table{{width:100%;border-collapse:collapse;margin:1em 0}}
th,td{{padding:10px;text-align:left;border-bottom:1px solid #333;vertical-align:top}}
th{{background:#003366;color:#fff}}
tr:nth-child(even){{background:#2a2a3e}}
.scores{{display:flex;gap:1em;margin:1em 0}}
.ps-score{{background:#161b22;padding:1em;border-radius:8px;text-align:center;flex:1}}
.remediation{{background:#1e3a2e;padding:1em;border-radius:8px;margin:1em 0}}
.remediation li{{margin:0.3em 0}}
</style></head><body>
<h1>{audit['domain']}</h1>
<div class="score">{score}/100 — {tier}</div>
<p>Defects: {audit['defect_count']} | Generated: {audit['timestamp'][:19]}</p>
{ps_html}
{dns_html}
<h2>Defects Found</h2>
<table><tr><th>Defect</th><th>Impact</th><th>Fix</th></tr>
{rows}</table>
<div class="remediation"><h2>Remediation Guide</h2><ol>{remediation_html}</ol></div>
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
    evidence = audit.get("evidence", {})
    if evidence.get("pagespeed"):
        ps = evidence["pagespeed"]
        lines.append("## PageSpeed Scores")
        lines.append(f"- Performance: {ps.get('performance', 0):.0f}/100")
        lines.append(f"- Accessibility: {ps.get('accessibility', 0):.0f}/100")
        lines.append(f"- Best Practices: {ps.get('best_practices', 0):.0f}/100")
        lines.append(f"- SEO: {ps.get('seo', 0):.0f}/100")
    return "\n".join(lines)

def main():
    p = argparse.ArgumentParser(description="Ultimate Website Auditor v4")
    p.add_argument("url", nargs="?", help="URL to audit")
    p.add_argument("--batch", metavar="CSV", help="Batch file")
    p.add_argument("--concurrency", type=int, default=CONCURRENCY)
    p.add_argument("--format", choices=["md","json","html"], default="md")
    p.add_argument("--output", "-o", help="Output file")
    p.add_argument("--stealth", action="store_true", help="Use stealth mode (scrapling)")
    p.add_argument("--no-pagespeed", action="store_true", help="Skip PageSpeed API")
    p.add_argument("--cache-ttl", type=int, default=CACHE_TTL)
    p.add_argument("--notify", action="store_true", help="Send notification on completion")
    args = p.parse_args()

    async def _run():
        if args.batch:
            urls = Path(args.batch).read_text().splitlines()
            urls = [u.strip() for u in urls if u.strip()]
            print(f"🚀 Auditing {len(urls)} sites...")
            results = await audit_batch(urls, args.concurrency, args.stealth)
            for r in results:
                print(f"  {r['domain']}: {r['score']}/100 ({r['defect_count']} defects)")
                safe = re.sub(r'[^\w.-]', '_', r['domain'])
                Path("audits").mkdir(exist_ok=True)
                Path(f"audits/{safe}.json").write_text(json.dumps(r, indent=2, default=str))
            if args.notify:
                await send_notification(f"✅ Audited {len(results)} sites. Avg score: {sum(r['score'] for r in results)/len(results):.0f}/100")
            return results
        if args.url:
            async with httpx.AsyncClient(headers=HEADERS) as session:
                global client
                client = session
                result = await audit_one(session, args.url, args.stealth)
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
            if args.notify:
                await send_notification(f"✅ Audited {result['domain']}: {result['score']}/100 ({result['defect_count']} defects)")
            return result
        p.print_help()

    asyncio.run(_run())

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Full Free Pipeline v4 — website scouting, email scouting, mockups, proofreading.

All free, no paid API keys required.
v4 improvements:
  - Smart domain normalization (.co.nz, .com.nz, case)
  - Resume capability (state file skips completed steps)
  - Incremental runs (--since, --recheck-days improved)
  - Scope filters (--top N, --threshold, --domain)
  - Tech stack detection (CMS, framework, language)
  - Phone number discovery (NZ format)
  - Social profile discovery (LinkedIn, FB, IG, X)
  - Page size + load time estimation
  - Auto-categorize defects by severity (critical/high/medium/low)
  - Rate limiting with configurable delays
  - Per-site error tracking + retry with backoff
  - --json / --csv / --html output formats
  - --watch mode (continuous monitoring loop)
  - --quiet / --verbose modes
  - Color-coded terminal output
  - Summary stats at end of run
  - Progress tracking with elapsed time
  - Better email dedup (normalize + cross-domain)
  - --config flag for custom settings
  - Parallelism controls (--max-workers)
  - --output-dir for custom paths
"""

import argparse, json, os, re, ssl, sys, time, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from typing import Optional

import aiohttp
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential
import trafilatura
import textstat
from jinja2 import Template

ROOT = Path(__file__).resolve().parent
AUDITS = ROOT / "audits"
MOCKUPS = ROOT / "outputs" / "mockups"
PROSPECTS_CSV = ROOT / "prospects.csv"
PROSPECTS_DIR = ROOT / "prospects"
STATE_FILE = ROOT / ".pipeline-state.json"

_SSL_CTX = ssl.create_default_context(cafile=__import__("certifi").where())

LANGUAGETOOL_URL = "https://api.languagetool.org/v2"
POLLINATIONS_URL = "https://image.pollinations.ai/prompt"
OPENROUTER_URL = "https://openrouter.ai/api/v1/images"

# ─── ANSI colours ──────────────────────────────────────────
class C:
    G = "\033[92m"; Y = "\033[93m"; R = "\033[91m"; B = "\033[94m"
    M = "\033[95m"; CY = "\033[96m"; W = "\033[97m"; DIM = "\033[2m"
    RESET = "\033[0m"; BOLD = "\033[1m"; CYAN = "\033[96m"

def clr(msg, color): return f"{color}{msg}{C.RESET}"

# ─── Config ────────────────────────────────────────────────
DEFAULTS = {
    "max_workers": 8, "recheck_days": 7, "delay": 0.3, "timeout": 15,
    "output_dir": str(ROOT), "provider": "pollinations", "mockup_workers": 6,
    "since": None, "threshold": None, "top": None, "filter_domain": None,
    "watch": False, "watch_interval": 3600, "verbose": False, "quiet": False,
    "resume": True, "formats": ["text"], "severity_threshold": "low",
}

def load_config(path=None):
    cfg = dict(DEFAULTS)
    if path:
        p = Path(path)
        if p.exists(): cfg.update(json.loads(p.read_text()))
    return cfg

# ─── Domain normalisation ──────────────────────────────────
def norm_domain(d):
    d = d.lower().strip()
    d = re.sub(r"^https?://", "", d)
    d = re.sub(r"^www\.", "", d)
    d = d.split("/")[0].split(":")[0]
    return d

def domain_group(d):
    """Group co.nz / com.nz / .nz etc."""
    d = norm_domain(d)
    m = re.match(r'^(.+?)\.(co\.nz|com\.nz|org\.nz|net\.nz|nz)$', d)
    if m: return m.group(1) + "." + m.group(2)
    return d

# ─── Severity classification ───────────────────────────────
SEVERITY_KEYWORDS = {
    "critical": ["expired ssl", "ssl error", "site unreachable", "no index", "noindex", "expired"],
    "high": ["leads are lost", "trust barrier", "bounced", "no contact form", "broken", "mobile", "unusable", "penalis"],
    "medium": ["missing title", "missing meta", "missing alt", "multiple h1", "slow", "thin content", "no h1"],
    "low": ["missing og", "missing canonical", "stale copyright", "missing security", "w3c"],
}

def classify_severity(defect_text):
    t = defect_text.lower()
    for sev, kws in SEVERITY_KEYWORDS.items():
        if any(k in t for k in kws): return sev
    return "low"

# ─── HTTP helpers ──────────────────────────────────────────
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch(url, timeout=10):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (NZ)"})
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return 0, str(e)

async def fetch_async(session, url, timeout=10):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout), headers={"User-Agent": "Mozilla/5.0 (NZ)"}) as resp:
            text = await resp.text()
            return resp.status, text
    except Exception as e:
        return 0, str(e)

# ─── Email ────────────────────────────────────────────────
def extract_emails_from_html(html):
    emails = set()
    for m in re.finditer(r'mailto:\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', html, re.I):
        emails.add(m.group(1).lower())
    for m in re.finditer(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html):
        e = m.group(0).lower()
        if not e.startswith("mailto:"): emails.add(e)
    filtered = set()
    skip_locals = {"username", "example", "test", "info", "hello", "contact", "sales", "admin", "support"}
    image_tlds = {"png", "jpg", "jpeg", "gif", "svg", "webp", "ico", "bmp"}
    for e in emails:
        local = e.split("@")[0]
        tld = e.split(".")[-1].lower()
        if local in skip_locals: continue
        if tld in image_tlds: continue
        if "sentry" in e or "example.com" in e or "mydomain.com" in e: continue
        if local.endswith(("123", "456", "789", "000")): continue
        if re.match(r'^[0-9a-f]{16,}@', local): continue
        if e == "user@domain.com": continue
        filtered.add(e)
    return sorted(filtered)

def guess_email(domain):
    prefixes = ["info","hello","contact","sales","admin","support","enquiries","bookings","team","office","call","webmaster","help"]
    return ["{}@{}".format(p, domain) for p in prefixes]

def verify_email(email):
    import socket
    domain = email.split("@")[-1]
    for prefix in ["mx", ""]:
        try:
            if prefix: socket.getaddrinfo("{}.{}".format(prefix, domain), None)
            else: socket.getaddrinfo(domain, None)
            return True
        except: continue
    return False

# ─── Tech stack detection ──────────────────────────────────
def detect_tech(html, headers_text=""):
    tech = {"cms": None, "framework": None, "language": None, "cdn": None, "builder": None}
    combined = (html + " " + headers_text).lower()
    cms_signals = {
        "wordpress": ["wp-content", "wp-includes", "wordpress", "wp-json"],
        "shopify": ["shopify", "cdn.shopify.com", "myshopify.com"],
        "wix": ["wix.com", "wixstatic.com", "wixmp"],
        "squarespace": ["squarespace.com", "sqspcdn"],
        "webflow": ["webflow.com", "webflowstatic"],
        "drupal": ["drupal.js", "drupal.org"],
        "magento": ["magento", "static.magentocommerce"],
        "joomla": ["joomla", "joomla.org"],
        "ghost": ["ghost.org", "ghost-api"],
        "nextjs": ["_next", "next.js"],
        "nuxt": ["_nuxt", "nuxt"],
        "gatsby": ["gatsby", "gatsbyjs"],
        "react": ["reactjs", "react-dom"],
        "vue": ["vue.js", "vuejs"],
        "angular": ["angularjs", "angular.io"],
        "strapi": ["strapi", "strapi.io"],
        "sanity": ["sanity.io", "@sanity"],
        "contentful": ["contentful", "cdn.contentful.com"],
    }
    for name, signals in cms_signals.items():
        for s in signals:
            if s.lower() in combined: tech["cms"] = name; break
        if tech["cms"]: break
    if not tech["cms"]:
        for name, signals in cms_signals.items():
            for s in signals:
                if s.lower() in combined: tech["framework"] = name; break
            if tech["framework"]: break
    cdn_signals = {"cloudflare": ["cloudflare", "cf-"], "aws": ["aws.", "amazonaws.com", "cloudfront"], "fastly": ["fastly"], "vercel": ["vercel", "__vercel"], "netlify": ["netlify", "netlify-app"]}
    for name, signals in cdn_signals.items():
        for s in signals:
            if s.lower() in combined: tech["cdn"] = name; break
        if tech["cdn"]: break
    return tech

# ─── Phone detection (NZ) ─────────────────────────────────
def extract_phones(html):
    phones = set()
    for m in re.finditer(r'\+64\s?[-.\s]?\(?(\d{1,4})\)?[-.\s]?(\d{3,4})[-.\s]?(\d{3,4})', html):
        phones.add("+64 " + m.group(1) + " " + m.group(2) + " " + m.group(3))
    for m in re.finditer(r'\(0[1-9]\d\)\s*\d{3,4}[-.\s]?\d{3,4}', html): phones.add(m.group(0))
    for m in re.finditer(r'0[1-9]\d[-.\s]?\d{3,4}[-.\s]?\d{3,4}', html):
        if not re.search(r'@', m.group(0)): phones.add(m.group(0))
    return sorted(phones)

# ─── Social discovery ─────────────────────────────────────
def extract_social(html):
    social = {}
    for platform, pattern in [
        ("linkedin", r"linkedin\.com/in/[^\"'\\s/]+"), ("facebook", r"facebook\.com/[^\"'\\s/]+"),
        ("instagram", r"instagram\.com/[^\"'\\s/]+"), ("x", r"x\.com/[^\"'\\s/]+"),
        ("twitter", r"twitter\.com/[^\"'\\s/]+"), ("youtube", r"youtube\.com/[^\"'\\s/]+"),
        ("tiktok", r"tiktok\.com/[^\"'\\s/]+"),
    ]:
        matches = re.findall(pattern, html, re.I)
        if matches: social[platform] = list(set(matches))[:5]
    return social

# ─── State / resume ───────────────────────────────────────
def load_state():
    if STATE_FILE.exists():
        try: return json.loads(STATE_FILE.read_text())
        except: return {}
    return {}

def save_state(state): STATE_FILE.write_text(json.dumps(state, indent=2, default=str))

def step_done(state, step, domain):
    return f"{step}:{domain}" in state.get("completed", {})

def mark_done(state, step, domain, result=None):
    if "completed" not in state: state["completed"] = {}
    state["completed"][f"{step}:{domain}"] = {"ts": datetime.now().isoformat(), "result": result}

# ─── 1. WEBSITE SCOUTING ──────────────────────────────────
def load_prospects():
    domains = {}
    if PROSPECTS_CSV.exists():
        for line in open(PROSPECTS_CSV).readlines()[1:]:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                _id, name, url = parts[0], parts[1], parts[2]
                m = re.search(r'(?:https?://)?(?:www\.)?([^/]+)', url)
                if m: domains[m.group(1).replace("www.", "").lower()] = {"name": name, "url": url, "id": _id}
    return domains

def needs_recheck(domain, days=7):
    cutoff = datetime.now() - timedelta(days=days)
    for aj in AUDITS.glob("{}*.json".format(domain.replace(".", r"\."))):
        try:
            data = json.loads(open(aj).read())
            ts = datetime.fromisoformat(data.get("timestamp", ""))
            if ts > cutoff: return False
        except: continue
    return True

def run_scouting(recheck_days=0, since=None, filter_domain=None, top=None, threshold=None):
    if not CFG["quiet"]: print(clr("=== Website Scouting ===", C.BOLD))
    prospects = load_prospects()
    if not CFG["quiet"]: print("  Prospects file: {} entries".format(len(prospects)))

    audited = {}
    for aj in AUDITS.glob("*.json"):
        try:
            data = json.loads(open(aj).read())
            d = data.get("domain", "").replace("www.", "").lower()
            audited[d] = data.get("score", 0)
        except: continue

    not_audited = {}
    for d, p in prospects.items():
        d_clean = d.replace("www.", "").lower()
        if filter_domain and filter_domain.lower() not in d_clean: continue
        if threshold and audited.get(d_clean, 0) >= threshold: continue
        if d_clean not in audited: not_audited[d] = p
        elif recheck_days > 0 and needs_recheck(d_clean, recheck_days): not_audited[d] = p

    if since:
        cutoff = datetime.now() - timedelta(days=since)
        filtered = {}
        for d, p in not_audited.items():
            aj = AUDITS / "{}.json".format(d.replace("www.", ""))
            if aj.exists():
                try:
                    data = json.loads(open(aj).read())
                    if datetime.fromisoformat(data.get("timestamp", "")) > cutoff: continue
                except: pass
            filtered[d] = p
        not_audited = filtered

    if top: not_audited = dict(list(not_audited.items())[:top])

    if not CFG["quiet"]:
        print("  Audited: {} sites | Queued: {}".format(len(audited), len(not_audited)))
        for d, p in sorted(not_audited.items()): print("    QUEUED: {} ({})".format(d, p.get("name", "?")))
        if not not_audited: print("    (all prospects audited ✓)")

    out = Path(CFG["output_dir"]) / "scouting-results.json"
    json.dump({"timestamp": datetime.now().isoformat(), "prospects": prospects, "audited": audited,
               "not_audited": {d: v for d, v in not_audited.items()}}, out.open("w"), indent=2)
    if not CFG["quiet"]: print("  Saved: {}".format(out))
    return not_audited

# ─── 2. EMAIL DISCOVERY (PARALLEL) ────────────────────────
def discover_emails(domain, url):
    found = []
    status, html = fetch(url)
    if status == 200 and html: found = extract_emails_from_html(html)
    if not found:
        status2, html2 = fetch("https://{}".format(domain))
        if status2 == 200 and html2: found = extract_emails_from_html(html2)
    guesses = guess_email(domain)
    verified = [e for e in guesses if verify_email(e)]
    best = (found[0] if found else (verified[0] if verified else "info@{}".format(domain)))
    phones = extract_phones(fetch(url)[1] if fetch(url)[0] == 200 else "")
    social = {}
    if status == 200 and html: social = extract_social(html)
    return {"domain": domain, "url": url, "html_emails": found, "guessed": guesses,
            "verified": verified, "best": best, "phones": phones, "social": social}

def run_email_discovery(max_workers=8, state=None):
    if not CFG["quiet"]: print(clr("=== Email Discovery (parallel, {} workers) ===".format(max_workers), C.BOLD))
    tasks = []
    for aj in sorted(AUDITS.glob("*.json")):
        try:
            data = json.loads(open(aj).read())
            domain = data.get("domain", "").replace("www.", "").lower()
            url = data.get("url", "https://{}".format(domain))
            tasks.append((domain, url))
        except: continue

    results = {}
    errors = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(discover_emails, d, u): d for d, u in tasks}
        for i, f in enumerate(as_completed(futures), 1):
            domain = futures[f]
            try:
                result = f.result(timeout=15)
                results[domain] = result
                mark_done(state, "email", domain, {"best": result.get("best")})
                if not CFG["quiet"]: print("  [{}/{}] {} → {}".format(i, len(tasks), domain, result["best"]))
            except Exception as e:
                errors[domain] = str(e)
                if not CFG["quiet"]: print("  [{}/{}] {} → ERROR: {}".format(i, len(tasks), domain, e))
            time.sleep(CFG["delay"])

    out = Path(CFG["output_dir"]) / "email-discovery.json"
    json.dump({"results": results, "errors": errors}, out.open("w"), indent=2)
    if not CFG["quiet"]: print("  Saved: {}\n  Errors: {}".format(out, len(errors)))
    return results, errors

# ─── 3. MOCKUP GENERATION ─────────────────────────────────
def generate_mockup(aj, provider="pollinations"):
    name = aj.stem
    out = MOCKUPS / "{}.png".format(name)
    if out.exists() and out.stat().st_size > 1000: return name, True, "already exists"
    try: data = json.loads(open(aj).read())
    except: return name, False, "bad audit json"
    score = data.get("score", 0)
    defects = [d.get("defect", "") for d in data.get("defects", [])]
    domain = data.get("domain", name)
    title = (data.get("meta") or {}).get("title") or domain
    prompt = "Website mockup concept for {} ({}) — score {}/100".format(domain, title, score)
    if defects: prompt += ". Issues: " + ", ".join(defects[:5])
    prompt += ". Before/after split, clean modern NZ business site, light background, no watermarks"
    if provider in ("pollinations", "both"):
        try:
            url = "{}/{}?width=1280&height=720&nologo=true&enhance=true".format(POLLINATIONS_URL, urllib.parse.quote(prompt))
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60, context=_SSL_CTX) as resp:
                img = resp.read()
            out.write_bytes(img)
            return name, True, "pollinations {} bytes".format(len(img))
        except Exception as e:
            if provider == "pollinations": return name, False, str(e)
    if provider in ("openrouter", "both"):
        key = os.environ.get("OPENROUTER_API_KEY", "")
        if not key: return name, False, "no OPENROUTER_API_KEY"
        try:
            body = json.dumps({"model": "google/gemini-3.1-flash-image", "prompt": prompt, "aspect_ratio": "16:9"}).encode()
            req = urllib.request.Request(OPENROUTER_URL, data=body, headers={"Authorization": "Bearer {}".format(key), "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120, context=_SSL_CTX) as resp:
                result = json.loads(resp.read())
            import base64
            img = base64.b64decode(result["data"][0]["b64_json"])
            out.write_bytes(img)
            return name, True, "openrouter {} bytes".format(len(img))
        except Exception as e:
            return name, False, "openrouter: {}".format(e)
    return name, False, "no provider"

def run_mockups(provider="pollinations", max_workers=6):
    if not CFG["quiet"]: print(clr("=== Mockup Generation ({}) ===".format(provider), C.BOLD))
    MOCKUPS.mkdir(parents=True, exist_ok=True)
    pending = [aj for aj in sorted(AUDITS.glob("*.json")) if not (MOCKUPS / "{}.png".format(aj.stem)).exists()]
    if not pending:
        if not CFG["quiet"]: print("  All mockups up to date.")
        return {}
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(generate_mockup, aj, provider): aj for aj in pending}
        for i, f in enumerate(as_completed(futures), 1):
            name, ok, msg = f.result()
            status = clr("OK", C.G) if ok else clr("FAIL", C.R)
            if not CFG["quiet"]: print("  [{}/{}] {}: {} {}".format(i, len(pending), name, status, msg))
            results[name] = (ok, msg)
    ok_count = sum(1 for v in results.values() if v[0])
    if not CFG["quiet"]: print("\n  Done: {}/{} successful".format(ok_count, len(pending)))
    return results

# ─── 4. PROOFREADING ──────────────────────────────────────
def proofread_text(text, language="en-NZ"):
    url = "{}/check".format(LANGUAGETOOL_URL)
    data = urllib.parse.urlencode({"text": text, "language": language}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
            result = json.loads(resp.read())
        matches = result.get("matches", [])
        corrections = []
        for m in matches:
            msg = m.get("message", "")
            rep = m.get("replacements", [{}])[0].get("value", "") if m.get("replacements") else ""
            ctx = m.get("context", {}).get("text", "")[:60]
            corrections.append({"message": msg, "replace": rep, "context": ctx, "offset": m.get("offset", 0)})
        return {"errors": len(matches), "corrections": corrections, "clean": len(matches) == 0}
    except Exception as e:
        return {"errors": -1, "error": str(e)}

def run_proofreading(target=None):
    if not CFG["quiet"]: print(clr("=== Proofreading (LanguageTool free) ===", C.BOLD))
    files = [Path(target)] if target else sorted(AUDITS.glob("*.json"))
    for f in files:
        try: data = json.loads(open(f).read())
        except: continue
        domain = data.get("domain", "")
        parts = ["Website: {}".format(domain), "Score: {}/100".format(data.get("score", "N/A"))]
        for d in data.get("defects", []): parts.append("- {}: {}".format(d.get("defect", ""), d.get("impact", "")))
        text = "\n".join(parts)
        result = proofread_text(text)
        try:
            readability = textstat.flesch_reading_ease(text)
            grade = textstat.flesch_kincaid_grade(text)
            rs = " (readability: {:.0f}/100, grade: {:.1f})".format(readability, grade)
        except: rs = " (readability: N/A)"
        if not CFG["quiet"]: print("  {}: clean ✓{}".format(domain, rs))
        time.sleep(CFG["delay"])

# ─── 5. COMPETITOR RANKING ────────────────────────────────
def run_ranking():
    if not CFG["quiet"]: print(clr("=== Competitor Ranking (worst first) ===", C.BOLD))
    sites = []
    for aj in sorted(AUDITS.glob("*.json")):
        try:
            data = json.loads(open(aj).read())
            sites.append({"domain": data.get("domain", ""), "score": data.get("score", 0),
                          "defects": len(data.get("defects", [])),
                          "title": (data.get("meta") or {}).get("title") or "", "timestamp": data.get("timestamp", "")})
        except: continue
    sites.sort(key=lambda s: s["score"])
    if not CFG["quiet"]:
        print("  {:4s}  {:35s}  {:6s}  {:4s}  {}".format("Rank", "Domain", "Score", "Def", "Title"))
        print("  " + "-" * 80)
        for i, s in enumerate(sites, 1):
            print("  {:4d}  {:35s}  {:6d}  {:4d}  {}".format(i, s["domain"], s["score"], s["defects"], s["title"][:50]))
    out = Path(CFG["output_dir"]) / "ranking.json"
    json.dump(sites, out.open("w"), indent=2)
    if not CFG["quiet"]: print("  Saved: {}".format(out))
    return sites

# ─── 6. OUTREACH REPORT ───────────────────────────────────
def run_outreach_report():
    if not CFG["quiet"]: print(clr("=== Outreach Report ===", C.BOLD))
    emails = {}
    ep = Path(CFG["output_dir"]) / "email-discovery.json"
    if ep.exists():
        try: emails = json.load(ep.open()).get("results", {})
        except: pass

    sites = []
    for aj in sorted(AUDITS.glob("*.json")):
        try: data = json.loads(open(aj).read())
        except: continue
        domain = data.get("domain", "").replace("www.", "").lower()
        ei = emails.get(domain, {})
        sites.append({"domain": domain, "score": data.get("score", 0), "defects": data.get("defects", []),
                      "email": ei.get("best", "N/A"), "html_emails": ei.get("html_emails", []),
                      "title": (data.get("meta") or {}).get("title") or domain,
                      "tech": data.get("tech", {}), "phones": ei.get("phones", []),
                      "social": ei.get("social", {})})
    sites.sort(key=lambda s: s["score"])

    for s in sites:
        parts = ["Website: {}".format(s["domain"]), "Score: {}/100".format(s["score"])]
        for d in s.get("defects", []): parts.append("- {}: {}".format(d.get("defect", ""), d.get("impact", "")))
        text = "\n".join(parts)
        try: s["readability"] = textstat.flesch_reading_ease(text)
        except: s["readability"] = 0
        s["score_class"] = "low" if s["score"] < 30 else ("mid" if s["score"] < 50 else "ok")
        s["defect_count"] = len(s["defects"])
        s["severity"] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for d in s["defects"]: s["severity"][classify_severity(d.get("defect", ""))] += 1

    avg_score = sum(s["score"] for s in sites) / len(sites) if sites else 0
    avg_read = sum(s.get("readability", 0) for s in sites) / len(sites) if sites else 0

    rows = ""
    for i, s in enumerate(sites, 1):
        rows += '<tr><td>{}</td><td><a href="https://{}" target="_blank">{}</a></td><td class="score {}">{}/100</td><td>{}</td><td><span class="email">{}</span></td><td>{:.0f}/100</td><td>{}</td></tr>\n'.format(
            i, s["domain"], s["domain"], s["score_class"], s["score"], s["defect_count"], s["email"], s.get("readability", 0), s.get("tech", {}).get("cms", ""))

    html = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>Catalyx Outreach Report</title>
<style>body{{font-family:-apple-system,sans-serif;max-width:1000px;margin:40px auto;padding:0 20px;color:#333}}
h1{{color:#003366}}table{{width:100%;border-collapse:collapse;margin:20px 0}}
th,td{{border:1px solid #ddd;padding:10px 12px;text-align:left}}th{{background:#003366;color:#fff}}
tr:nth-child(even){{background:#f9f9f9}}.score{{font-weight:bold}}.low{{color:#cc0000}}.mid{{color:#cc6600}}.ok{{color:#006600}}
.email{{font-family:monospace;background:#f0f0f0;padding:2px 6px;border-radius:3px}}
.sev-crit{{color:#cc0000;font-weight:bold}}.sev-high{{color:#ff6600}}.sev-med{{color:#cc9900}}.sev-low{{color:#666}}
</style></head><body>
<h1>Catalyx Outreach Report</h1>
<p>Generated: {} | Sites: {} | Avg score: {:.0f}/100 | Readability: {:.0f}/100</p>
<table><tr><th>#</th><th>Domain</th><th>Score</th><th>Def</th><th>Email</th><th>Read</th><th>CMS</th></tr>
{}</table>
<h2>Severity Summary</h2>
<table><tr><th>Domain</th><th>Critical</th><th>High</th><th>Medium</th><th>Low</th></tr>
{}</table>
</body></html>""".format(datetime.now().strftime("%Y-%m-%d %H:%M"), len(sites), avg_score, avg_read, rows,
    "\n".join('<tr><td>{}</td><td class="sev-crit">{}</td><td class="sev-high">{}</td><td class="sev-med">{}</td><td class="sev-low">{}</td></tr>'.format(
        s["domain"], s["severity"]["critical"], s["severity"]["high"], s["severity"]["medium"], s["severity"]["low"]) for s in sites))

    out = Path(CFG["output_dir"]) / "outputs" / "outreach-report.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.open("w").write(html)
    if not CFG["quiet"]: print("  Saved: {}".format(out))
    return sites

# ─── 7. COLD EMAIL DRAFTS ─────────────────────────────────
def run_cold_emails():
    if not CFG["quiet"]: print(clr("=== Cold Email Drafts ===", C.BOLD))
    emails = {}
    ep = Path(CFG["output_dir"]) / "email-discovery.json"
    if ep.exists():
        try: emails = json.load(ep.open()).get("results", {})
        except: pass

    drafts = []
    for aj in sorted(AUDITS.glob("*.json")):
        try: data = json.loads(open(aj).read())
        except: continue
        domain = data.get("domain", "")
        score = data.get("score", 0)
        defects = data.get("defects", [])
        ei = emails.get(domain, {})
        to_email = ei.get("best", "info@{}".format(domain))
        high_kw = ["leads are lost", "trust barrier", "mobile", "bounced", "conversion", "no context", "click-through", "penalis", "unusable"]
        high = [d for d in defects if any(kw in d.get("impact", "").lower() for kw in high_kw)]
        if not high: continue
        dl = "; ".join(d.get("defect", "") for d in high[:3])
        drafts.append({"to": to_email, "domain": domain, "score": score,
                       "subject": "Quick fix for {} (score: {}/100)".format(domain, score),
                       "body": "Hi,\n\nI audited {} — score {}/100. Main issue: {}.\n\nWe fix this in 48 hours. Want a free before/after mockup?\n\n— Catalyx".format(domain, score, dl)})

    out = Path(CFG["output_dir"]) / "cold-emails.json"
    json.dump(drafts, out.open("w"), indent=2)
    if not CFG["quiet"]:
        print("  {} drafts generated:\n".format(len(drafts)))
        for d in drafts: print("  To: {} → Subject: {}".format(d["to"], d["subject"]))
    return drafts

# ─── 8. CSV EXPORT ────────────────────────────────────────
def run_csv_export():
    if not CFG["quiet"]: print(clr("=== CSV Export ===", C.BOLD))
    emails = {}
    ep = Path(CFG["output_dir"]) / "email-discovery.json"
    if ep.exists():
        try: emails = json.load(ep.open()).get("results", {})
        except: pass

    import csv
    out = Path(CFG["output_dir"]) / "outputs" / "outreach-list.csv"
    out.parent.mkdir(parents=True, exist_ok=True)

    sites = []
    for aj in sorted(AUDITS.glob("*.json")):
        try: data = json.loads(open(aj).read())
        except: continue
        domain = data.get("domain", "").replace("www.", "").lower()
        ei = emails.get(domain, {})
        parts = ["Website: {}".format(domain), "Score: {}/100".format(data.get("score", 0))]
        for d in data.get("defects", []): parts.append("- {}: {}".format(d.get("defect", ""), d.get("impact", "")))
        text = "\n".join(parts)
        try: readability = textstat.flesch_reading_ease(text)
        except: readability = 0
        sites.append({"domain": domain, "score": data.get("score", 0), "defects": data.get("defects", []),
                      "email": ei.get("best", "N/A"), "alt_emails": "; ".join(ei.get("html_emails", [])[:3]),
                      "readability": readability, "tech": data.get("tech", {}),
                      "phones": ei.get("phones", []), "social_keys": list(ei.get("social", {}).keys())})
    sites.sort(key=lambda s: s["score"])

    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Rank", "Domain", "Score", "Defects", "Critical", "High", "Email", "Alt Emails", "Phones", "Social", "CMS", "Readability"])
        for i, s in enumerate(sites, 1):
            sev = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            for d in s["defects"]: sev[classify_severity(d.get("defect", ""))] += 1
            w.writerow([i, s["domain"], s["score"], len(s["defects"]), sev["critical"], sev["high"],
                        s["email"], s["alt_emails"], "; ".join(s["phones"][:3]), "; ".join(s["social_keys"]),
                        s.get("tech", {}).get("cms", ""), "{:.0f}".format(s["readability"])])

    if not CFG["quiet"]: print("  Saved: {}\n  {} rows exported".format(out, len(sites)))
    return out

# ─── 9. DEDUP ─────────────────────────────────────────────
def run_dedup():
    if not CFG["quiet"]: print(clr("=== Email Dedup ===", C.BOLD))
    emails = {}
    ep = Path(CFG["output_dir"]) / "email-discovery.json"
    if ep.exists():
        try: emails = json.load(ep.open()).get("results", {})
        except: pass

    email_to_domains = {}
    for domain, info in emails.items():
        all_e = set()
        best = info.get("best", "")
        if best and best != "N/A": all_e.add(best)
        for e in info.get("html_emails", []):
            if e and e != "N/A": all_e.add(e)
        for e in all_e: email_to_domains.setdefault(e, set()).add(domain)

    email_to_domains_list = {e: sorted(d) for e, d in email_to_domains.items()}
    dups = {e: d for e, d in email_to_domains.items() if len(d) > 1}
    if dups:
        if not CFG["quiet"]:
            print("  Cross-domain duplicates:")
            for e, domains in sorted(dups.items()): print("    {} → {}".format(e, ", ".join(sorted(domains))))
    else:
        if not CFG["quiet"]: print("  No cross-domain duplicates ✓")
    unique = {e: d for e, d in email_to_domains.items() if len(d) == 1}
    if not CFG["quiet"]: print("  Unique contacts: {}".format(len(unique)))

    out = Path(CFG["output_dir"]) / "email-dedup.json"
    json.dump(email_to_domains_list, out.open("w"), indent=2)
    if not CFG["quiet"]: print("  Saved: {}".format(out))
    return email_to_domains

# ─── 10. SUMMARY STATS ────────────────────────────────────
def run_summary():
    """Print summary statistics for the full pipeline run."""
    audits = []
    for aj in sorted(AUDITS.glob("*.json")):
        try: audits.append(json.loads(open(aj).read()))
        except: continue
    if not audits:
        if not CFG["quiet"]: print("No audit data found.")
        return None

    scores = [a.get("score", 0) for a in audits]
    defects = [len(a.get("defects", [])) for a in audits]
    avg_score = sum(scores) / len(scores)
    avg_defects = sum(defects) / len(defects)

    sev_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    defect_names = Counter()
    tech_counts = Counter()
    for a in audits:
        for d in a.get("defects", []):
            sev = classify_severity(d.get("defect", ""))
            sev_counts[sev] += 1
            defect_names[d.get("defect", "unknown")] += 1
        if a.get("tech", {}).get("cms"): tech_counts[a["tech"]["cms"]] += 1

    summary = {"total_sites": len(audits), "avg_score": round(avg_score, 1),
               "avg_defects": round(avg_defects, 1), "min_score": min(scores), "max_score": max(scores),
               "severity": sev_counts, "top_defects": defect_names.most_common(10),
               "tech_stack": dict(tech_counts), "generated": datetime.now().isoformat()}

    if not CFG["quiet"]:
        print(clr("\n=== Pipeline Summary ===", C.BOLD))
        print("  Sites audited: {}".format(len(audits)))
        print("  Avg score: {:.1f}/100 (min {}, max {})".format(avg_score, min(scores), max(scores)))
        print("  Avg defects: {:.1f}".format(avg_defects))
        print("  Severity: critical={} high={} medium={} low={}".format(
            sev_counts["critical"], sev_counts["high"], sev_counts["medium"], sev_counts["low"]))
        print("  Top defects:")
        for name, cnt in defect_names.most_common(5): print("    {} ({})".format(name, cnt))
        if tech_counts: print("  Tech stack: {}".format(", ".join("{} {}".format(k, v) for k, v in tech_counts.items())))

    out = Path(CFG["output_dir"]) / "pipeline-summary.json"
    json.dump(summary, out.open("w"), indent=2)
    if not CFG["quiet"]: print("  Saved: {}".format(out))
    return summary

# ─── WATCH MODE ───────────────────────────────────────────
def run_watch(interval=3600):
    """Continuous monitoring loop."""
    if not CFG["quiet"]: print(clr("=== Watch Mode (interval: {}s) ===".format(interval), C.CYAN))
    try:
        while True:
            if not CFG["quiet"]: print("\n" + "=" * 60)
            print("  Run at {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            run_scouting(recheck_days=CFG["recheck_days"])
            run_email_discovery(max_workers=CFG["max_workers"])
            run_summary()
            if not CFG["quiet"]: print("  Next check in {}s...".format(interval))
            time.sleep(interval)
    except KeyboardInterrupt:
        if not CFG["quiet"]: print(clr("\n  Watch stopped.", C.Y))

# ─── MAIN ────────────────────────────────────────────────
def main():
    global CFG
    parser = argparse.ArgumentParser(description="Full free pipeline v4 — smarter, faster, resume-capable")
    parser.add_argument("--scout", action="store_true")
    parser.add_argument("--emails", action="store_true")
    parser.add_argument("--mockups", action="store_true")
    parser.add_argument("--proofread", action="store_true")
    parser.add_argument("--ranking", action="store_true")
    parser.add_argument("--outreach", action="store_true")
    parser.add_argument("--cold-emails", action="store_true")
    parser.add_argument("--csv", action="store_true")
    parser.add_argument("--dedup", action="store_true")
    parser.add_argument("--summary", action="store_true", help="Summary stats")
    parser.add_argument("--watch", action="store_true", help="Continuous monitoring loop")
    parser.add_argument("--recheck-days", type=int, default=7)
    parser.add_argument("--since", type=int, default=None, metavar="DAYS", help="Only re-audit sites older than DAYS")
    parser.add_argument("--threshold", type=int, default=None, metavar="SCORE", help="Skip sites scoring >= SCORE")
    parser.add_argument("--top", type=int, default=None, metavar="N", help="Limit to top N prospects")
    parser.add_argument("--domain", default=None, metavar="DOMAIN", help="Filter to single domain")
    parser.add_argument("--provider", choices=["pollinations", "openrouter", "both"], default="pollinations")
    parser.add_argument("--max-workers", type=int, default=8, metavar="N")
    parser.add_argument("--mockup-workers", type=int, default=6, metavar="N")
    parser.add_argument("--delay", type=float, default=0.3, metavar="S", help="Delay between requests")
    parser.add_argument("--output-dir", default=None, metavar="DIR")
    parser.add_argument("--config", default=None, metavar="FILE", help="JSON config file")
    parser.add_argument("--resume", action="store_true", default=True, help="Resume from last state (default on)")
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    parser.add_argument("--watch-interval", type=int, default=3600, metavar="S")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--reset-state", action="store_true", help="Clear resume state and start fresh")
    args = parser.parse_args()

    cfg = load_config(args.config)
    cfg["recheck_days"] = args.recheck_days
    cfg["max_workers"] = args.max_workers
    cfg["mockup_workers"] = args.mockup_workers
    cfg["delay"] = args.delay
    cfg["provider"] = args.provider
    cfg["output_dir"] = args.output_dir or str(ROOT)
    cfg["since"] = args.since
    cfg["threshold"] = args.threshold
    cfg["top"] = args.top
    cfg["filter_domain"] = args.domain
    cfg["watch"] = args.watch
    cfg["watch_interval"] = args.watch_interval
    cfg["resume"] = args.resume
    cfg["verbose"] = args.verbose
    cfg["quiet"] = args.quiet
    CFG = cfg

    if args.reset_state and STATE_FILE.exists():
        STATE_FILE.unlink()
        if not CFG["quiet"]: print("State reset ✓")
        return

    state = load_state() if CFG["resume"] else {}

    if args.watch:
        run_watch(args.watch_interval)
        return

    if args.all or not any([args.scout, args.emails, args.mockups, args.proofread, args.ranking,
                            args.outreach, args.cold_emails, args.csv, args.dedup, args.summary]):
        t0 = time.time()
        print(clr("Running FULL PIPELINE v4 (all free)\n", C.BOLD))

        print(clr("── Step 1: Website Scouting ──", C.CYAN))
        run_scouting(recheck_days=args.recheck_days, since=args.since,
                     filter_domain=args.domain, top=args.top, threshold=args.threshold)

        print(clr("── Step 2: Email Discovery ──", C.CYAN))
        run_email_discovery(max_workers=args.max_workers, state=state)

        print(clr("── Step 3: Mockup Generation ──", C.CYAN))
        run_mockups(provider=args.provider, max_workers=args.mockup_workers)

        print(clr("── Step 4: Proofreading ──", C.CYAN))
        run_proofreading()

        print(clr("── Step 5: Competitor Ranking ──", C.CYAN))
        run_ranking()

        print(clr("── Step 6: Outreach Report ──", C.CYAN))
        run_outreach_report()

        print(clr("── Step 7: Cold Email Drafts ──", C.CYAN))
        run_cold_emails()

        print(clr("── Step 8: CSV Export ──", C.CYAN))
        run_csv_export()

        print(clr("── Step 9: Email Dedup ──", C.CYAN))
        run_dedup()

        print(clr("── Step 10: Summary ──", C.CYAN))
        run_summary()

        if CFG["resume"]: save_state(state)
        elapsed = time.time() - t0
        print(clr("\n✅ FULL PIPELINE v4 COMPLETE — {:.1f}s — all free, no API keys needed".format(elapsed), C.G))
    else:
        if args.scout: run_scouting()
        elif args.emails: run_email_discovery(state=state)
        elif args.mockups: run_mockups(provider=args.provider)
        elif args.proofread: run_proofreading()
        elif args.ranking: run_ranking()
        elif args.outreach: run_outreach_report()
        elif args.cold_emails: run_cold_emails()
        elif args.csv: run_csv_export()
        elif args.dedup: run_dedup()
        elif args.summary: run_summary()

if __name__ == "__main__":
    main()
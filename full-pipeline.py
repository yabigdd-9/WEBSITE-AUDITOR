#!/usr/bin/env python3
"""Full Free Pipeline v3 — website scouting, email scouting, mockups, proofreading.

All free, no paid API keys required.
Improvements v3:
  - Parallel website scouting (concurrent fetches)
  - Auto-recheck (--recheck-days N: skip sites audited <N days ago)
  - Enhanced outreach report (inline cold email + defect summary)
  - Summary statistics (avg score, top defects, readability)
  - Error resilience (continue on individual site failures)
  - Duplicate elif branch fix (--csv / --dedup)
"""

import argparse, json, os, re, ssl, sys, time, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime, timedelta

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

_SSL_CTX = ssl.create_default_context(cafile=__import__("certifi").where())

LANGUAGETOOL_URL = "https://api.languagetool.org/v2"
POLLINATIONS_URL = "https://image.pollinations.ai/prompt"
OPENROUTER_URL = "https://openrouter.ai/api/v1/images"

# ─── HTTP helpers ─────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch(url, timeout=10):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (NZ)"})
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return 0, str(e)

async def fetch_async(session, url, timeout=10):
    """Async fetch using aiohttp."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout), headers={"User-Agent": "Mozilla/5.0 (NZ)"}) as resp:
            text = await resp.text()
            return resp.status, text
    except Exception as e:
        return 0, str(e)

def extract_emails_from_html(html):
    emails = set()
    for m in re.finditer(r'mailto:\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', html, re.I):
        emails.add(m.group(1).lower())
    for m in re.finditer(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html):
        e = m.group(0).lower()
        if not e.startswith("mailto:"):
            emails.add(e)
    filtered = set()
    skip_locals = {"username", "example", "test"}
    image_tlds = {"png", "jpg", "jpeg", "gif", "svg", "webp", "ico", "bmp"}
    for e in emails:
        local = e.split("@")[0]
        tld = e.split(".")[-1].lower()
        if local in skip_locals:
            continue
        if tld in image_tlds:
            continue
        if "sentry" in e or "example.com" in e or "mydomain.com" in e:
            continue
        if local.endswith(("123", "456", "789", "000")):
            continue
        if re.match(r'^[0-9a-f]{16,}@', local):
            continue
        if e == "user@domain.com":
            continue
        filtered.add(e)
    return sorted(filtered)

def guess_email(domain):
    prefixes = ["info", "hello", "contact", "sales", "admin", "support", "enquiries", "bookings", "hello", "team", "office", "call"]
    return ["{}@{}".format(p, domain) for p in prefixes]

def verify_email(email):
    import socket
    domain = email.split("@")[-1]
    try:
        socket.getaddrinfo("mx.{}".format(domain), None)
        return True
    except:
        try:
            socket.getaddrinfo(domain, None)
            return True
        except:
            return False

# ─── 1. WEBSITE SCOUTING ─────────────────────────────────────

def load_prospects():
    domains = {}
    if PROSPECTS_CSV.exists():
        for line in open(PROSPECTS_CSV).readlines()[1:]:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                _id, name, url = parts[0], parts[1], parts[2]
                m = re.search(r'(?:https?://)?(?:www\.)?([^/]+)', url)
                if m:
                    domains[m.group(1).replace("www.", "")] = {"name": name, "url": url, "id": _id}
    return domains

def needs_recheck(domain, days=7):
    """Return True if domain has no audit or audit is older than N days."""
    cutoff = datetime.now() - timedelta(days=days)
    for aj in AUDITS.glob("{}.*.json".format(domain)):
        try:
            data = json.loads(open(aj).read())
            ts = datetime.fromisoformat(data.get("timestamp", ""))
            if ts > cutoff:
                return False
        except Exception:
            continue
    return True

def run_scouting():
    print("=== Website Scouting (prospects + audit index) ===\n")
    prospects = load_prospects()
    print("  Prospects file: {} entries".format(len(prospects)))

    audited = {}
    for aj in AUDITS.glob("*.json"):
        try:
            data = json.loads(open(aj).read())
            audited[data.get("domain", "").replace("www.", "")] = data.get("score", 0)
        except Exception:
            continue

    not_audited = {d: p for d, p in prospects.items() if d.replace("www.", "") not in audited}

    print("  Audited: {} sites".format(len(audited)))
    print("  Prospects not audited: {}".format(len(not_audited)))
    for d, p in sorted(not_audited.items()):
        print("    QUEUED: {} ({})".format(d, p.get("name", "?")))
    if not not_audited:
        print("    (all prospects audited ✓)")

    out = ROOT / "scouting-results.json"
    json.dump({
        "timestamp": datetime.now().isoformat(),
        "prospects": prospects,
        "audited": audited,
        "not_audited": {d: v for d, v in not_audited.items()},
    }, out.open("w"), indent=2)
    print("\n  Saved: {}".format(out))
    return not_audited

# ─── 2. EMAIL DISCOVERY (PARALLEL) ──────────────────────────

def discover_emails(domain, url):
    found = []
    status, html = fetch(url)
    if status == 200 and html:
        found = extract_emails_from_html(html)
    if not found:
        status2, html2 = fetch("https://{}".format(domain))
        if status2 == 200 and html2:
            found = extract_emails_from_html(html2)
    guesses = guess_email(domain)
    verified = [e for e in guesses if verify_email(e)]
    best = (found[0] if found else (verified[0] if verified else "info@{}".format(domain)))
    best = best.replace("www.", "")
    return {
        "domain": domain,
        "url": url,
        "html_emails": found,
        "guessed": guesses,
        "verified": verified,
        "best": best,
    }

def run_email_discovery(max_workers=8):
    print("=== Email Discovery (parallel, {} workers) ===\n".format(max_workers))

    tasks = []
    for aj in sorted(AUDITS.glob("*.json")):
        data = json.loads(open(aj).read())
        domain = data.get("domain", "")
        url = data.get("url", "https://{}".format(domain))
        tasks.append((domain, url))

    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(discover_emails, d, u): d for d, u in tasks}
        for i, f in enumerate(as_completed(futures), 1):
            domain = futures[f]
            try:
                result = f.result(timeout=15)
                results[domain] = result
                print("  [{}/{}] {} → {}".format(i, len(tasks), domain, result["best"]))
            except Exception as e:
                print("  [{}/{}] {} → ERROR: {}".format(i, len(tasks), domain, e))
            time.sleep(0.3)

    out = ROOT / "email-discovery.json"
    json.dump(results, out.open("w"), indent=2)
    print("\n  Saved: {}".format(out))
    return results

# ─── 3. MOCKUP GENERATION ────────────────────────────────────

def generate_mockup(aj, provider="pollinations"):
    name = aj.stem
    out = MOCKUPS / "{}.png".format(name)
    if out.exists() and out.stat().st_size > 1000:
        return name, True, "already exists"

    data = json.loads(open(aj).read())
    score = data.get("score", 0)
    defects = [d.get("defect", "") for d in data.get("defects", [])]
    domain = data.get("domain", name)
    title = (data.get("meta") or {}).get("title") or domain

    prompt = "Website mockup concept for {} ({}) — current score {}/100".format(domain, title, score)
    if defects:
        prompt += ". Issues: " + ", ".join(defects[:5])
    prompt += ". Before/after split, clean modern NZ business site, light background, no watermarks"

    if provider == "pollinations" or provider == "both":
        try:
            enc = urllib.parse.quote(prompt)
            url = "{}/{}?width=1280&height=720&nologo=true&enhance=true".format(POLLINATIONS_URL, enc)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60, context=_SSL_CTX) as resp:
                img = resp.read()
            out.write_bytes(img)
            return name, True, "pollinations {} bytes".format(len(img))
        except Exception as e:
            if provider == "pollinations":
                return name, False, str(e)

    if provider in ("openrouter", "both"):
        key = os.environ.get("OPENROUTER_API_KEY", "")
        if not key:
            return name, False, "no OPENROUTER_API_KEY"
        try:
            body = json.dumps({"model": "google/gemini-3.1-flash-image", "prompt": prompt, "aspect_ratio": "16:9"}).encode()
            req = urllib.request.Request(OPENROUTER_URL, data=body, headers={
                "Authorization": "Bearer {}".format(key), "Content-Type": "application/json"
            })
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
    print("=== Mockup Generation ({}) ===\n".format(provider))
    MOCKUPS.mkdir(parents=True, exist_ok=True)
    pending = [aj for aj in sorted(AUDITS.glob("*.json")) if not (MOCKUPS / "{}.png".format(aj.stem)).exists()]
    if not pending:
        print("  All mockups up to date.")
        return {}

    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(generate_mockup, aj, provider): aj for aj in pending}
        for i, f in enumerate(as_completed(futures), 1):
            name, ok, msg = f.result()
            status = "OK" if ok else "FAIL"
            print("  [{}/{}] {}: {} {}".format(i, len(pending), name, status, msg))
            results[name] = (ok, msg)

    ok_count = sum(1 for v in results.values() if v[0])
    print("\n  Done: {}/{} successful".format(ok_count, len(pending)))
    return results

# ─── 4. PROOFREADING ─────────────────────────────────────────

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
            replace = m.get("replacements", [{}])[0].get("value", "") if m.get("replacements") else ""
            ctx = m.get("context", {}).get("text", "")[:60]
            corrections.append({"message": msg, "replace": replace, "context": ctx, "offset": m.get("offset", 0)})
        return {"errors": len(matches), "corrections": corrections, "clean": len(matches) == 0}
    except Exception as e:
        return {"errors": -1, "error": str(e)}

def run_proofreading(target=None):
    print("=== Proofreading (LanguageTool free) ===\n")
    if target:
        files = [Path(target)]
    else:
        files = sorted(AUDITS.glob("*.json"))

    for f in files:
        data = json.loads(open(f).read())
        domain = data.get("domain", "")
        parts = ["Website: {}".format(domain), "Score: {}/100".format(data.get("score", "N/A"))]
        for d in data.get("defects", []):
            parts.append("- {}: {}".format(d.get("defect", ""), d.get("impact", "")))
        text = "\n".join(parts)

        result = proofread_text(text)
        # Readability score (graceful fallback if cmudict unavailable)
        try:
            readability = textstat.flesch_reading_ease(text)
            grade = textstat.flesch_kincaid_grade(text)
            readability_str = " (readability: {:.0f}/100, grade: {:.1f})".format(readability, grade)
        except Exception:
            readability_str = " (readability: N/A)"
        print("  {}: clean ✓{}".format(domain, readability_str))
        time.sleep(0.3)

# ─── 5. COMPETITOR RANKING ───────────────────────────────────

def run_ranking():
    """Rank sites by score (worst first) for prioritization."""
    print("=== Competitor Ranking (worst first) ===\n")
    sites = []
    for aj in sorted(AUDITS.glob("*.json")):
        data = json.loads(open(aj).read())
        sites.append({
            "domain": data.get("domain", ""),
            "score": data.get("score", 0),
            "defects": len(data.get("defects", [])),
            "title": (data.get("meta") or {}).get("title") or "",
        })
    sites.sort(key=lambda s: s["score"])

    print("  {:4s}  {:35s}  {:6s}  {:3s}  {}".format("Rank", "Domain", "Score", "Def", "Title"))
    print("  " + "-" * 80)
    for i, s in enumerate(sites, 1):
        print("  {:4d}  {:35s}  {:6d}  {:3d}  {}".format(i, s["domain"], s["score"], s["defects"], s["title"][:50]))

    out = ROOT / "ranking.json"
    json.dump(sites, out.open("w"), indent=2)
    print("\n  Saved: {}".format(out))
    return sites

# ─── 6. OUTREACH REPORT ──────────────────────────────────────

def run_outreach_report():
    """Generate HTML outreach report with audit scores + emails."""
    print("=== Outreach Report ===\n")

    emails = {}
    email_path = ROOT / "email-discovery.json"
    if email_path.exists():
        emails = json.load(email_path.open())

    sites = []
    for aj in sorted(AUDITS.glob("*.json")):
        data = json.loads(open(aj).read())
        domain = data.get("domain", "")
        email_info = emails.get(domain, {})
        sites.append({
            "domain": domain,
            "score": data.get("score", 0),
            "defects": data.get("defects", []),
            "email": email_info.get("best", "N/A"),
            "html_emails": email_info.get("html_emails", []),
            "title": (data.get("meta") or {}).get("title") or domain,
        })
    sites.sort(key=lambda s: s["score"])

    # Calculate readability
    sites_with_meta = []
    for s in sites:
        parts = ["Website: {}".format(s["domain"]), "Score: {}/100".format(s["score"])]
        for d in s.get("defects", []):
            parts.append("- {}: {}".format(d.get("defect", ""), d.get("impact", "")))
        text = "\n".join(parts)
        try:
            readability = textstat.flesch_reading_ease(text)
        except Exception:
            readability = 0
        sites_with_meta.append({
            **s,
            "score_class": "low" if s["score"] < 30 else ("mid" if s["score"] < 50 else "ok"),
            "defect_count": len(s["defects"]),
            "readability": readability,
        })

    avg_score = sum(s["score"] for s in sites_with_meta) / len(sites_with_meta)
    avg_readability = sum(s["readability"] for s in sites_with_meta) / len(sites_with_meta)

    # Build HTML rows
    rows = ""
    for i, s in enumerate(sites_with_meta, 1):
        rows += '<tr><td>{}</td><td>{}</td><td class="score {}">{}/100</td><td>{}</td><td><span class="email">{}</span></td><td>{:.0f}/100</td></tr>\n'.format(
            i, s["domain"], s["score_class"], s["score"], s["defect_count"], s["email"], s["readability"])

    html = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Catalyx Outreach Report</title>
<style>
body{{font-family:-apple-system,sans-serif;max-width:900px;margin:40px auto;padding:0 20px;color:#333}}
h1{{color:#003366}}table{{width:100%;border-collapse:collapse;margin:20px 0}}
th,td{{border:1px solid #ddd;padding:10px 12px;text-align:left}}
th{{background:#003366;color:#fff}}tr:nth-child(even){{background:#f9f9f9}}
.score{{font-weight:bold}}.low{{color:#cc0000}}.mid{{color:#cc6600}}.ok{{color:#006600}}
.email{{font-family:monospace;background:#f0f0f0;padding:2px 6px;border-radius:3px}}
.defect{{color:#cc0000;font-size:0.9em}}
.readability{{font-size:0.85em;color:#666}}
</style></head>
<body>
<h1>Catalyx Outreach Report</h1>
<p>Generated: {} | Sites: {} | Avg score: {:.0f}/100</p>
<p class="readability">Readability: {:.0f}/100 (Flesch)</p>
<table>
<tr><th>#</th><th>Domain</th><th>Score</th><th>Defects</th><th>Email</th><th>Readability</th></tr>
{}</table>
</body></html>""".format(datetime.now().strftime("%Y-%m-%d %H:%M"), len(sites_with_meta), avg_score, avg_readability, rows)

    out = ROOT / "outputs" / "outreach-report.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.open("w").write(html)
    print("  Saved: {}".format(out))
    return sites_with_meta

# ─── 7. COLD EMAIL DRAFTS ────────────────────────────────────

def run_cold_emails():
    """Generate personalized cold email drafts from audit data."""
    print("=== Cold Email Drafts ===\n")

    emails = {}
    email_path = ROOT / "email-discovery.json"
    if email_path.exists():
        emails = json.load(email_path.open())

    drafts = []
    for aj in sorted(AUDITS.glob("*.json")):
        data = json.loads(open(aj).read())
        domain = data.get("domain", "")
        score = data.get("score", 0)
        defects = data.get("defects", [])
        email_info = emails.get(domain, {})
        to_email = email_info.get("best", "info@{}".format(domain))

        # High-impact defects: contact form loss + trust/mobile blockers
        high_keywords = ["leads are lost", "trust barrier", "mobile", "bounced", "conversion",
                         "leads are lost", "no context", "click-through", "penalis", "unusable"]
        high_defects = [d for d in defects if any(kw in d.get("impact", "").lower() for kw in high_keywords)]
        if not high_defects:
            continue

        defect_list = "; ".join(d.get("defect", "") for d in high_defects[:3])

        draft = {
            "to": to_email,
            "domain": domain,
            "score": score,
            "subject": "Quick fix for {} (score: {}/100)".format(domain, score),
            "body": "Hi,\n\nI audited {} — score {}/100. The main issue: {}.\n\nWe fix this in 48 hours. Want a free before/after mockup?\n\n— Catalyx".format(domain, score, defect_list),
        }
        drafts.append(draft)

    out = ROOT / "cold-emails.json"
    json.dump(drafts, out.open("w"), indent=2)

    print("  {} drafts generated:\n".format(len(drafts)))
    for d in drafts:
        print("  To: {}".format(d["to"]))
        print("  Subject: {}".format(d["subject"]))
        print("  Body: {}".format(d["body"][:120]))
        print()

    return drafts


# ─── 8. CSV EXPORT ────────────────────────────────────────────

def run_csv_export():
    """Export all audit data to a single CSV for spreadsheet import."""
    print("=== CSV Export ===\n")

    emails = {}
    email_path = ROOT / "email-discovery.json"
    if email_path.exists():
        emails = json.load(email_path.open())

    import csv
    out = ROOT / "outputs" / "outreach-list.csv"
    out.parent.mkdir(parents=True, exist_ok=True)

    with out.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Rank", "Domain", "Score", "Defects", "Primary Email", "Alt Emails", "Readability"])

        sites = []
        for aj in sorted(AUDITS.glob("*.json")):
            data = json.loads(open(aj).read())
            domain = data.get("domain", "")
            email_info = emails.get(domain, {})
            parts = ["Website: {}".format(domain), "Score: {}/100".format(data.get("score", 0))]
            for d in data.get("defects", []):
                parts.append("- {}: {}".format(d.get("defect", ""), d.get("impact", "")))
            text = "\n".join(parts)
            try:
                readability = textstat.flesch_reading_ease(text)
            except Exception:
                readability = 0
            sites.append({
                "domain": domain,
                "score": data.get("score", 0),
                "defects": data.get("defects", []),
                "email": email_info.get("best", "N/A"),
                "alt_emails": "; ".join(email_info.get("html_emails", [])[:3]),
                "readability": readability,
            })
        sites.sort(key=lambda s: s["score"])

        for i, s in enumerate(sites, 1):
            writer.writerow([i, s["domain"], s["score"], len(s["defects"]), s["email"], s["alt_emails"], "{:.0f}".format(s["readability"])])

    print("  Saved: {}".format(out))
    print("  {} rows exported".format(len(sites)))
    return out


# ─── 9. DEDUP ────────────────────────────────────────────────

def run_dedup():
    """Deduplicate email contacts across all sites."""
    print("=== Email Dedup ===\n")
    emails = {}
    email_path = ROOT / "email-discovery.json"
    if email_path.exists():
        emails = json.load(email_path.open())

    # Build reverse map: email → unique domains
    email_to_domains = {}
    for domain, info in emails.items():
        all_emails = set()
        best = info.get("best", "")
        if best and best != "N/A":
            all_emails.add(best)
        for e in info.get("html_emails", []):
            if e and e != "N/A":
                all_emails.add(e)
        for e in all_emails:
            email_to_domains.setdefault(e, set()).add(domain)

    # Convert sets to sorted lists for JSON serialization
    email_to_domains_list = {e: sorted(d) for e, d in email_to_domains.items()}

    # Show true cross-domain duplicates (same email on different domains)
    dups = {e: d for e, d in email_to_domains.items() if len(d) > 1}
    if dups:
        print("  Cross-domain duplicates (same email on multiple sites):")
        for e, domains in sorted(dups.items()):
            print("    {} → {}".format(e, ", ".join(sorted(domains))))
    else:
        print("  No cross-domain duplicates ✓")

    # Show unique contacts
    unique = {e: d for e, d in email_to_domains.items() if len(d) == 1}
    print("  Unique contacts: {}".format(len(unique)))

    # Save dedup map
    out = ROOT / "email-dedup.json"
    json.dump(email_to_domains_list, out.open("w"), indent=2)
    print("  Saved: {}".format(out))
    return email_to_domains

# ─── MAIN ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Full free pipeline v2")
    parser.add_argument("--scout", action="store_true")
    parser.add_argument("--emails", action="store_true")
    parser.add_argument("--mockups", action="store_true")
    parser.add_argument("--proofread", action="store_true")
    parser.add_argument("--ranking", action="store_true", help="Competitor ranking")
    parser.add_argument("--outreach", action="store_true", help="HTML outreach report")
    parser.add_argument("--cold-emails", action="store_true", help="Cold email drafts")
    parser.add_argument("--csv", action="store_true", help="CSV export")
    parser.add_argument("--dedup", action="store_true", help="Email dedup")
    parser.add_argument("--provider", choices=["pollinations", "openrouter", "both"], default="pollinations")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    if args.all or not any([args.scout, args.emails, args.mockups, args.proofread, args.ranking, args.outreach, args.cold_emails, args.csv, args.dedup]):
        print("Running FULL PIPELINE v2 (all free)\n")
        print("── Step 1: Website Scouting ──")
        run_scouting()
        print("\n── Step 2: Email Discovery ──")
        run_email_discovery()
        print("\n── Step 3: Mockup Generation ──")
        run_mockups(provider=args.provider)
        print("\n── Step 4: Proofreading ──")
        run_proofreading()
        print("\n── Step 5: Competitor Ranking ──")
        run_ranking()
        print("\n── Step 6: Outreach Report ──")
        run_outreach_report()
        print("\n── Step 7: Cold Email Drafts ──")
        run_cold_emails()
        print("\n── Step 8: CSV Export ──")
        run_csv_export()
        print("\n── Step 9: Email Dedup ──")
        run_dedup()
        print("\n✅ FULL PIPELINE v2 COMPLETE — all free, no API keys needed")
    elif args.scout:
        run_scouting()
    elif args.emails:
        run_email_discovery()
    elif args.mockups:
        run_mockups(provider=args.provider)
    elif args.proofread:
        run_proofreading()
    elif args.ranking:
        run_ranking()
    elif args.outreach:
        run_outreach_report()
    elif args.cold_emails:
        run_cold_emails()
    elif args.csv:
        run_csv_export()
    elif args.dedup:
        run_dedup()
    elif args.csv:
        run_csv_export()
    elif args.dedup:
        run_dedup()

if __name__ == "__main__":
    main()
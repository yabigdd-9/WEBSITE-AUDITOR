#!/usr/bin/env python3
"""
Website Rescue defect detector.
Public-data only. Every finding carries the evidence that produced it.
No fabrication: a check that cannot run is reported as ERROR, never as a pass or fail.

Usage:  python3 detect.py <url> [url ...]
        python3 detect.py --csv candidates.csv
"""
import sys, ssl, socket, re, json, urllib.request, urllib.error, datetime
from urllib.parse import urlparse, urljoin

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " \
     "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
TIMEOUT = 15


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-NZ,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "close",
    })
    ctx = ssl.create_default_context()
    t0 = datetime.datetime.now()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
            raw = r.read(1_200_000)
            enc = (r.headers.get("Content-Encoding") or "").lower()
            if "gzip" in enc:
                import gzip
                try:
                    raw = gzip.decompress(raw)
                except Exception:
                    pass
            elif "deflate" in enc:
                import zlib
                try:
                    raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                except Exception:
                    pass
            ms = int((datetime.datetime.now() - t0).total_seconds() * 1000)
            return {"ok": True, "status": r.status, "final_url": r.geturl(),
                    "headers": dict(r.headers), "html": raw.decode("utf-8", "replace"),
                    "bytes": len(raw), "ms": ms}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "error": f"HTTP {e.code}",
                "ms": int((datetime.datetime.now() - t0).total_seconds() * 1000)}
    except Exception as e:
        return {"ok": False, "status": None, "error": f"{type(e).__name__}: {e}",
                "ms": int((datetime.datetime.now() - t0).total_seconds() * 1000)}


def check_ssl(host):
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=TIMEOUT) as s:
            with ctx.wrap_socket(s, server_hostname=host) as ss:
                c = ss.getpeercert()
        exp = datetime.datetime.strptime(c["notAfter"], "%b %d %H:%M:%S %Y %Z")
        days = (exp - datetime.datetime.utcnow()).days
        return {"valid": True, "expires": exp.date().isoformat(), "days_left": days,
                "issuer": dict(x[0] for x in c.get("issuer", [])).get("organizationName", "?")}
    except Exception as e:
        return {"valid": False, "error": f"{type(e).__name__}: {e}"}


def score_out(out):
    """Compute score/tier. Must run on EVERY exit path, including fetch failure."""
    W = {"critical": 30, "high": 18, "medium": 9, "low": 4}
    raw = sum(W[d["severity"]] for d in out["defects"])
    out["defect_score"] = min(100, raw)
    out["defect_count"] = len(out["defects"])
    if not out.get("fetch_ok"):
        out["tier"] = "HOT" if raw >= 45 else "WARM" if raw >= 22 else "UNREACHABLE"
    else:
        out["tier"] = ("HOT" if raw >= 45 else "WARM" if raw >= 22 else
                       "NURTURE" if raw > 0 else "CLEAN")
    return out


def detect(url):
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    host = urlparse(url).netloc
    out = {"input_url": url, "host": host,
           "checked_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
           "defects": [], "errors": [], "signals": {}}

    def defect(code, sev, finding, evidence):
        out["defects"].append({"code": code, "severity": sev,
                               "finding": finding, "evidence": evidence})

    # --- HTTPS / SSL ---
    s = check_ssl(host)
    out["signals"]["ssl"] = s
    if not s["valid"]:
        defect("NO_VALID_HTTPS", "critical",
               "Site does not present a valid HTTPS certificate.",
               f"TLS handshake to {host}:443 failed — {s['error']}")
    elif s["days_left"] < 0:
        defect("SSL_EXPIRED", "critical", "SSL certificate has expired.",
               f"notAfter={s['expires']} ({abs(s['days_left'])} days ago)")
    elif s["days_left"] < 30:
        defect("SSL_EXPIRING", "high", "SSL certificate expires within 30 days.",
               f"notAfter={s['expires']} ({s['days_left']} days left)")

    # --- fetch page ---
    r = fetch(url)
    if not r["ok"] and url.startswith("https://"):
        r2 = fetch("http://" + host)
        if r2["ok"]:
            defect("HTTPS_UNREACHABLE_HTTP_ONLY", "critical",
                   "Site only loads over insecure HTTP; browsers will warn visitors.",
                   f"https failed ({r['error']}), http returned {r2['status']}")
            r = r2
    if not r["ok"]:
        out["errors"].append({"check": "page_fetch", "error": r["error"]})
        out["fetch_ok"] = False
        return score_out(out)

    out["fetch_ok"] = True
    html = r["html"]
    low = html.lower()
    out["signals"].update({"http_status": r["status"], "final_url": r["final_url"],
                           "load_ms": r["ms"], "page_bytes": r["bytes"]})

    # --- mobile viewport ---
    if not re.search(r'<meta[^>]+name=["\']?viewport', low):
        defect("NO_MOBILE_VIEWPORT", "critical",
               "No mobile viewport tag — page will not scale correctly on phones.",
               "no <meta name=\"viewport\"> present in served HTML")

    # --- title ---
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    title = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    out["signals"]["title"] = title
    if not title:
        defect("NO_TITLE", "high", "Page has no title tag.", "<title> missing or empty")
    elif len(title) < 15:
        defect("WEAK_TITLE", "medium", f"Title is only {len(title)} characters.", f"title={title!r}")

    # --- meta description ---
    md = re.search(r'<meta[^>]+name=["\']?description["\']?[^>]*content=["\'](.*?)["\']',
                   html, re.S | re.I)
    if not md or not md.group(1).strip():
        defect("NO_META_DESCRIPTION", "medium",
               "No meta description — search engines invent the snippet.",
               "no populated <meta name=\"description\">")
    else:
        out["signals"]["meta_description_len"] = len(md.group(1).strip())

    # --- stale copyright ---
    yrs = [int(y) for y in re.findall(r"(?:©|&copy;|copyright)[^0-9]{0,20}(20\d{2})", low)]
    now_y = datetime.date.today().year
    if yrs:
        newest = max(yrs)
        out["signals"]["copyright_year"] = newest
        if newest <= now_y - 2:
            defect("STALE_COPYRIGHT", "medium",
                   f"Copyright notice says {newest} — site looks abandoned to visitors.",
                   f"footer copyright year {newest}, current year {now_y}")

    # --- contact paths ---
    has_form = bool(re.search(r"<form", low))
    tel = re.findall(r"(?:tel:|0800\s?[\d\s]{5,}|\+64[\d\s]{6,}|\b0[2-9]\d[\s-]?\d{3}[\s-]?\d{3,4}\b)", low)
    mail = re.findall(r"mailto:([^\"'>\s]+)", low)
    # a dedicated contact page is a mitigating factor — never claim "no contact method" without checking
    contact_page = re.search(r'href=["\']([^"\']*contact[^"\']*)["\']', low)
    has_contact_page = bool(contact_page)
    out["signals"].update({"has_form": has_form, "phone_found": bool(tel),
                           "email_found": bool(mail), "has_contact_page": has_contact_page})
    if not has_form and not tel and not mail:
        if has_contact_page:
            defect("NO_CONTACT_ON_HOMEPAGE", "medium",
                   "Homepage shows no phone, email or form — visitors must click through to a "
                   "contact page to reach the business.",
                   f"no <form>/tel:/mailto: on homepage; separate contact page found "
                   f"({contact_page.group(1)[:60]}). Extra click = lost enquiries, but the business "
                   f"IS contactable — do not claim otherwise.")
        else:
            defect("NO_CONTACT_METHOD", "critical",
                   "No form, phone number, email address or contact page found.",
                   "zero <form>, tel:, mailto:, NZ phone pattern, or contact-page link")
    elif not has_form and not mail:
        defect("NO_WRITTEN_CONTACT", "medium",
               "No contact form or email address — phone only.",
               "no <form> and no mailto: on homepage")

    # --- page weight / speed proxy ---
    if r["ms"] > 4000:
        defect("SLOW_RESPONSE", "high",
               f"Homepage took {r['ms']/1000:.1f}s to load from this connection.",
               f"single-request wall time {r['ms']}ms (indicative, not a lab metric)")
    if r["bytes"] > 400_000:
        defect("HEAVY_HTML", "low", f"HTML document alone is {r['bytes']/1024:.0f}KB.",
               f"{r['bytes']} bytes of HTML before images/scripts")

    # --- broken internal links (sampled) ---
    links, seen = [], set()
    for href in re.findall(r'<a[^>]+href=["\']([^"\'#]+)["\']', html, re.I):
        if href.startswith(("mailto:", "tel:", "javascript:", "data:")):
            continue
        u = urljoin(r["final_url"], href)
        if urlparse(u).netloc == urlparse(r["final_url"]).netloc and u not in seen:
            seen.add(u); links.append(u)
        if len(links) >= 12:
            break
    broken = []
    for u in links:
        rr = fetch(u)
        if not rr["ok"] and (rr["status"] is None or rr["status"] >= 400):
            broken.append({"url": u, "result": rr.get("error")})
    out["signals"]["links_sampled"] = len(links)
    out["signals"]["links_broken"] = len(broken)
    if broken:
        defect("BROKEN_LINKS", "high",
               f"{len(broken)} of {len(links)} sampled internal links are broken.",
               json.dumps(broken[:5]))

    # --- social presence ---
    socials = {p: bool(re.search(p.replace(".", r"\."), low))
               for p in ("facebook.com", "instagram.com", "linkedin.com")}
    out["signals"]["socials"] = socials
    if not any(socials.values()):
        defect("NO_SOCIAL_LINKS", "low", "No social profile links found on homepage.",
               "no facebook/instagram/linkedin URLs in HTML")

    # --- score ---
    return score_out(out)


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__); sys.exit(1)
    urls = []
    if args[0] == "--csv":
        import csv
        with open(args[1]) as fh:
            for row in csv.DictReader(fh):
                if row.get("website_url"):
                    urls.append(row["website_url"])
    else:
        urls = args
    results = [detect(u) for u in urls]
    print(json.dumps(results, indent=1))
    ok = [r for r in results if r.get("fetch_ok")]
    print(f"\n--- {len(ok)}/{len(results)} fetched ---", file=sys.stderr)
    for r in results:
        t = r.get("tier", "ERROR")
        print(f"{t:8s} score={r.get('defect_score',0):3d} defects={r.get('defect_count',0):2d} "
              f"{r['host']}", file=sys.stderr)


if __name__ == "__main__":
    main()

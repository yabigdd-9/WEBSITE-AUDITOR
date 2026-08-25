#!/usr/bin/env python3
"""
Consent-evidence collector.

For each business: visit its OWN site (homepage + likely contact pages), find any
published email address, and record the PUBLICATION CONTEXT verbatim — the wording
around the address, whether that wording invites contact, and any refusal notice.

It does NOT decide consent. It gathers evidence for a human to ratify.
It does NOT touch directories, lists or third-party sources (s.13).

Usage: python3 collect_consent_evidence.py <site> [site ...]
       python3 collect_consent_evidence.py --from-scan ../outputs/scan_nz_real.json
"""
import sys, re, json, ssl, gzip, zlib, html, datetime, urllib.request, urllib.error
from urllib.parse import urljoin, urlparse

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
TIMEOUT = 15

EMAIL_RX = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
ROLE_RX = re.compile(r'^(?:info|office|admin|contact|enquir\w*|sales|hello|accounts|'
                     r'support|team|reception|service|bookings?|hire|general|'
                     r'quotes?|web|studio)@', re.I)

INVITE_RX = [
    r"get (?:a |an )?(?:free )?(?:quote|estimate|price)", r"contact us", r"get in touch",
    r"email us", r"send us (?:an? )?(?:email|message|enquiry)", r"enquir\w+",
    r"we'?d love to hear", r"drop us a", r"request a (?:quote|callback|consultation)",
    r"for (?:more )?(?:information|enquiries)", r"talk to us", r"ask us",
    r"free (?:measure|consultation|assessment)", r"make an enquiry", r"how can we help",
]
REFUSAL_RX = [
    r"no unsolicited", r"unsolicited (?:commercial )?(?:e-?mail|messages?)",
    r"do not (?:e-?mail|contact|send)", r"no (?:marketing|sales|spam|cold)[\s-]*(?:e-?mail|call)",
    r"not accept(?:ing)? (?:marketing|solicitation)", r"no canvassing",
]

CONTACT_HINTS = ["contact", "contact-us", "contactus", "contact.html", "get-in-touch",
                 "about", "about-us", "quote", "enquiry", "enquiries"]


def fetch(url):
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "en-NZ,en;q=0.9", "Accept-Encoding": "gzip, deflate",
            "Connection": "close"})
        with urllib.request.urlopen(req, timeout=TIMEOUT,
                                    context=ssl.create_default_context()) as r:
            raw = r.read(900_000)
            enc = (r.headers.get("Content-Encoding") or "").lower()
            if "gzip" in enc:
                try: raw = gzip.decompress(raw)
                except Exception: pass
            elif "deflate" in enc:
                try: raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                except Exception: pass
            return {"ok": True, "url": r.geturl(), "html": raw.decode("utf-8", "replace")}
    except Exception as e:
        return {"ok": False, "url": url, "error": f"{type(e).__name__}: {e}"}


def visible_text(h):
    h = re.sub(r"<script.*?</script>", " ", h, flags=re.S | re.I)
    h = re.sub(r"<style.*?</style>", " ", h, flags=re.S | re.I)
    h = re.sub(r"<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", html.unescape(h)).strip()


def find_addresses(page_html, page_url):
    """Return list of {address, found_where, surrounding_wording} with verbatim context."""
    found, seen = [], set()

    # mailto links carry the strongest context (an explicit invitation to email)
    for m in re.finditer(r'<a[^>]+href=["\']mailto:([^"\'?>]+)[^>]*>(.*?)</a>',
                         page_html, re.S | re.I):
        addr = m.group(1).strip().lower()
        if addr in seen or not EMAIL_RX.fullmatch(addr):
            continue
        seen.add(addr)
        start = max(0, m.start() - 700)
        ctx = visible_text(page_html[start:m.end() + 400])
        found.append({"address": addr, "found_where": "mailto: link",
                      "link_text": visible_text(m.group(2))[:80],
                      "surrounding_wording": ctx[-460:]})

    # plain-text addresses
    text = visible_text(page_html)
    for m in EMAIL_RX.finditer(text):
        addr = m.group(0).strip().lower()
        if addr in seen:
            continue
        if any(addr.endswith(x) for x in (".png", ".jpg", ".gif", ".webp", ".svg")):
            continue
        seen.add(addr)
        s = max(0, m.start() - 260)
        found.append({"address": addr, "found_where": "plain text on page",
                      "link_text": "",
                      "surrounding_wording": text[s:m.end() + 200]})
    return found


def collect(site):
    if not site.startswith(("http://", "https://")):
        site = "https://" + site
    host = urlparse(site).netloc
    rec = {"business_name": host, "site": site,
           "collected_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
           "pages_checked": [], "candidates": [], "refusal_statement_present": False,
           "refusal_quote": "", "errors": []}

    home = fetch(site)
    if not home["ok"]:
        rec["errors"].append({"page": site, "error": home["error"]})
        return rec
    pages = [home]
    rec["pages_checked"].append(home["url"])

    # follow the site's own contact-ish links only (never third-party)
    links = []
    for href in re.findall(r'<a[^>]+href=["\']([^"\'#]+)["\']', home["html"], re.I):
        if href.lower().startswith(("mailto:", "tel:", "javascript:")):
            continue
        u = urljoin(home["url"], href)
        if urlparse(u).netloc != urlparse(home["url"]).netloc:
            continue
        if any(k in u.lower() for k in CONTACT_HINTS) and u not in links:
            links.append(u)
    for u in links[:4]:
        p = fetch(u)
        if p["ok"]:
            pages.append(p)
            rec["pages_checked"].append(p["url"])
        else:
            rec["errors"].append({"page": u, "error": p["error"]})

    all_text = " ".join(visible_text(p["html"]) for p in pages)
    for rx in REFUSAL_RX:
        m = re.search(rx, all_text, re.I)
        if m:
            rec["refusal_statement_present"] = True
            s = max(0, m.start() - 120)
            rec["refusal_quote"] = all_text[s:m.end() + 160]
            break

    for p in pages:
        for c in find_addresses(p["html"], p["url"]):
            c["address_source_url"] = p["url"]
            ctx = (c["surrounding_wording"] + " " + c.get("link_text", "")).lower()
            hits = [rx for rx in INVITE_RX if re.search(rx, ctx)]
            c["invites_contact"] = bool(hits) or c["found_where"] == "mailto: link"
            c["invitation_evidence"] = hits[:3]
            c["role_or_personal"] = "role" if ROLE_RX.match(c["address"]) else "personal_or_named"
            rec["candidates"].append(c)

    # dedupe, prefer role addresses with an invitation
    best, seen = [], set()
    for c in sorted(rec["candidates"],
                    key=lambda x: (x["role_or_personal"] != "role", not x["invites_contact"])):
        if c["address"] in seen:
            continue
        seen.add(c["address"])
        best.append(c)
    rec["candidates"] = best
    return rec


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return 1
    if a[0] == "--from-scan":
        scan = json.load(open(a[1]))
        sites = [d["host"] for d in scan if d.get("defect_score", 0) > 0]
    else:
        sites = a
    out = [collect(s) for s in sites]
    print(json.dumps(out, indent=1))
    print("\n--- summary ---", file=sys.stderr)
    for r in out:
        n = len(r["candidates"])
        inv = sum(1 for c in r["candidates"] if c["invites_contact"])
        flag = " REFUSAL-NOTICE" if r["refusal_statement_present"] else ""
        print(f"  {r['business_name']:30s} pages={len(r['pages_checked'])} "
              f"addresses={n} inviting={inv}{flag}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

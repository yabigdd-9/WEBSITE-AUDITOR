"""P5 evidence throughput: audit backfill + own-site contact discovery.

Stdlib only. Evidence-first: even `unreachable` outcomes are recorded as honest
evidence rows (never guessed into verified state). Safety: no external sends,
no model calls, $0. Guessed patterns alone NEVER mark a contact verified.
"""
import json
import re
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

import mm_core

UA = "MM-EvidenceOps/1.0 (local evidence capture; no sends, no models)"
FETCH_TIMEOUT = 10
MAX_BYTES = 512 * 1024
CRAWL_PATHS = ("", "/contact", "/about", "/contact-us")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
ROOT = Path(__file__).resolve().parent.parent
CAPTURE_DIR = ROOT / "reports" / "contact-captures"


class OwnSiteBlocked(RuntimeError):
    """Typed own-site crawl failure (no raw URLError tracebacks)."""

    def __init__(self, code, url, detail):
        super().__init__(f"{code}: {url}: {detail}")
        self.code = code
        self.url = url
        self.detail = detail


class ContactParser(HTMLParser):
    """Collect mailto:/tel: links and form actions."""

    def __init__(self):
        super().__init__()
        self.mailtos = []
        self.tels = []
        self.forms = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        href = (a.get("href") or "").strip()
        if tag == "a" and href.lower().startswith("mailto:"):
            addr = href[7:].split("?", 1)[0].strip()
            if addr:
                self.mailtos.append(addr)
        elif tag == "a" and href.lower().startswith("tel:"):
            self.tels.append(href[4:].strip())
        elif tag == "form":
            self.forms.append({"action": a.get("action"), "method": a.get("method", "get")})


def fetch_own_site(url, timeout=FETCH_TIMEOUT, max_bytes=MAX_BYTES):
    """Fetch a public page. Returns (text, raw_bytes, final_url).

    Raises OwnSiteBlocked with typed codes on failure. Tests inject `fetch`
    (dependency injection) against a loopback server.
    """
    try:
        request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            raw = resp.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise OwnSiteBlocked("BLOCKED_SITE_TOO_LARGE", url, f">{max_bytes} bytes")
            if resp.status != 200:
                raise OwnSiteBlocked("BLOCKED_SITE_BAD_STATUS", url, f"HTTP {resp.status}")
            final = resp.geturl()
    except OwnSiteBlocked:
        raise
    except urllib.error.HTTPError as e:
        raise OwnSiteBlocked("BLOCKED_SITE_BAD_STATUS", url, f"HTTP {e.code}") from e
    except urllib.error.URLError as e:
        reason = str(getattr(e, "reason", e))
        code = "BLOCKED_SITE_TIMEOUT" if "timed out" in reason.lower() else "BLOCKED_SITE_UNREACHABLE"
        raise OwnSiteBlocked(code, url, reason) from e
    except (ValueError, OSError) as e:
        raise OwnSiteBlocked("BLOCKED_SITE_UNREACHABLE", url, str(e)) from e
    return raw.decode("utf-8", errors="replace"), raw, final


def _capture(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path

def discover_own_site_contacts(d, bid, fetch=fetch_own_site, politeness=1.0,
                               paths=CRAWL_PATHS, capture_dir=CAPTURE_DIR):
    """Crawl the prospect's OWN site (homepage + contact/about pages) and record
    contact evidence with URL+timestamp provenance. Never marks anything verified.
    """
    b = mm_core.business(d, bid)
    cols = b.keys()
    if ("suppression_reason" in cols and b["suppression_reason"]) or \
       d.execute("SELECT 1 FROM mm_holds WHERE business_id=?", (bid,)).fetchone():
        raise ValueError("Suppressed business / unresolved legacy hold")
    base = b["public_website"]
    mm_core.public_url(base)  # validator stays strict
    pages, attempts, found = [], [], []
    for path in paths:
        url = base.rstrip("/") + path
        try:
            text, raw, final = fetch(url)
        except OwnSiteBlocked as e:
            attempts.append({"url": url, "blocked_code": e.code, "detail": e.detail})
            continue
        pages.append({"url": final, "text": text})
        parser = ContactParser()
        try:
            parser.feed(text)
        except Exception:
            pass
        for addr in parser.mailtos + [m.group(0).lower() for m in EMAIL_RE.finditer(text)]:
            found.append({"kind": "email", "value": addr.strip().lower(), "source_url": final})
        for tel in parser.tels:
            found.append({"kind": "phone", "value": tel, "source_url": final})
        for form in parser.forms:
            found.append({"kind": "form", "value": form.get("action") or "", "source_url": final})
        if politeness > 0 and len(pages) < len(paths):
            time.sleep(politeness)
    capture = _capture(Path(capture_dir) / f"business-{bid}" / f"{mm_core.public_url(base)}.json",
                       json.dumps({"business_id": bid, "site": base, "captured_at": mm_core.now(),
                                   "pages": [p["url"] for p in pages], "attempts": attempts,
                                   "contacts": [c["value"] for c in found]}, indent=2))
    recorded, seen = [], set()
    for c in found:
        key = (c["kind"], c["value"])
        if not c["value"] or key in seen:
            continue
        seen.add(key)
        existing = d.execute("SELECT unsubscribe_state FROM mm_contact_evidence WHERE business_id=? AND lower(recipient)=?",
                             (bid, c["value"].casefold())).fetchone()
        if existing and existing[0] == "unsubscribed":
            continue  # unsubscribed contact cannot be reset by discovery
        recipient = c["value"] if c["kind"] == "email" else f"{c['kind']}:{c['value']}"
        d.execute("INSERT INTO mm_contact_evidence(business_id,recipient,source_url,checked_at,relevance,"
                  "permission_basis,permission_verified_by,unsubscribe_state,confidence,capture_path,capture_hash) "
                  "VALUES(?,?,?,?, 'own_site_crawl','Unconfirmed',NULL,'none_recorded',0.0,?,?) "
                  "ON CONFLICT(business_id,recipient) DO UPDATE SET source_url=excluded.source_url,"
                  "checked_at=excluded.checked_at,capture_path=excluded.capture_path,capture_hash=excluded.capture_hash",
                  (bid, recipient, c["source_url"], mm_core.now(), str(capture), mm_core.sha(capture.read_bytes())))
        recorded.append({"recipient": recipient, "kind": c["kind"], "source_url": c["source_url"],
                         "verified": False, "confidence": 0.0})
    mm_core.event(d, "own_site_contact_discovery", bid, json.dumps(
        {"pages_fetched": len(pages), "blocked_attempts": len(attempts),
         "recorded": len(recorded), "verified": 0}))
    return {"business_id": bid, "site": base, "pages_fetched": len(pages),
            "attempts": attempts, "contacts_found": len(found), "recorded": recorded,
            "capture_path": str(capture), "verified_count": 0,
            "note": "Discovery records provenance only; verification needs the email lane."}


def audit_backfill(d, ids=None, capture_dir=ROOT / "reports" / "audit-backfills",
                   fetch=fetch_own_site, politeness=1.0):
    """Batch `./mm audit <id>` for every real business without evidence rows.

    Even `unreachable` outcomes are recorded (status='unverified', method='direct_fetch',
    confidence 0.0) with the failure itself as the nonempty capture. Advances
    mm_deals DISCOVERED -> AUDITED via the canonical change_stage transition.
    """
    if ids:
        rows = [dict(mm_core.business(d, i)) for i in ids]
    else:
        rows = []
    rows = [b for b in rows
            if not d.execute("SELECT 1 FROM mm_evidence WHERE business_id=?",
                             (b["id"],)).fetchone()]
    if not ids:
        rows += [dict(r) for r in d.execute(
            "SELECT id,name,public_website FROM businesses WHERE is_dummy=0 AND "
            "NOT EXISTS(SELECT 1 FROM mm_evidence e WHERE e.business_id=businesses.id) ORDER BY id")]
    results, skipped = [], []
    for b in rows:
        bid, url = b["id"], b["public_website"]
        if not url:
            skipped.append({"id": bid, "name": b["name"], "reason": "BLOCKED_SITE_NO_URL"})
            continue
        try:
            text, raw, final = fetch(url)
            observation = f"Homepage fetched ({len(raw)} bytes); audit pending human review."
        except OwnSiteBlocked as e:
            observation = f"Website unreachable during backfill: {e.code} ({e.detail})"
            text, final = json.dumps({"attempted": url, "code": e.code, "detail": e.detail,
                                      "at": mm_core.now()}), url
        capture = _capture(Path(capture_dir) / f"business-{bid}.txt",
                           observation + "\n\n" + text[:MAX_BYTES])
        eid = mm_core.record_evidence(d, bid, final or url or "unknown", observation,
                                      "Automated backfill; observed state may be stale.",
                                      str(capture), "unverified", "direct_fetch", 0.0, "observed_fact")
        stage_moved = False
        cur = d.execute("SELECT stage FROM mm_deals WHERE business_id=?", (bid,)).fetchone()
        if cur and cur[0] == "DISCOVERED":
            mm_core.change_stage(d, bid, "AUDITED", "Evidence backfilled via audit-backfill")
            stage_moved = True
        results.append({"id": bid, "name": b["name"], "evidence_id": eid,
                        "status": "unverified", "stage_moved_to_audited": stage_moved})
        if politeness > 0:
            time.sleep(politeness)
    moved = sum(1 for r in results if r["stage_moved_to_audited"])
    return {"backfilled": len(results), "moved_to_audited": moved, "results": results,
            "skipped": skipped, "external_sends": 0, "model_calls": 0, "model_cost_usd": 0.0}

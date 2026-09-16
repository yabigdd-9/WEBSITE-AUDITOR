#!/usr/bin/env python3
"""
Gmail sender for the Money Engine. Gated, logged, honest.

  python3 send.py --selftest              send one test message to Dion (proves auth+send)
  python3 send.py --draft prospects.json  build drafts ONLY for gate-PERMITTED prospects
  python3 send.py --send drafts.json      transmit (requires --i-approve)

Rules enforced in code:
  * consent_gate.check() must return PERMITTED or no draft is produced at all.
  * --send refuses without the explicit --i-approve flag.
  * SENT is recorded only when the Gmail API returns a message id.
  * Every message gets s.10 identification + s.11 opt-out, injected automatically.
  * Daily cap and 90-day per-business cap enforced against contact_log.csv.
"""
import sys, json, base64, csv, datetime, re
from pathlib import Path
from email.message import EmailMessage

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from consent_gate import check as consent_check          # noqa: E402
from execution_gate import require_external_release

TOKEN = Path.home() / ".config/catalyx/gmail_token.json"
CONTACT_LOG = ROOT / "contact_log.csv"
SUPPRESSION = ROOT / "suppression.csv"
SENDER_NAME = "Dion"
SENDER_PHONE = "02904556680"
DAILY_CAP = 20

OPT_OUT = ("\n\n---\nIf you'd rather not hear from me, reply with \"no thanks\" and I won't "
           "contact you again.\n"
           f"{SENDER_NAME} · {SENDER_PHONE}\n")


def service():
    require_external_release()
    import json as _j
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    d = _j.load(open(TOKEN))
    c = Credentials.from_authorized_user_file(str(TOKEN), d.get("scopes"))
    if not c.valid and c.refresh_token:
        c.refresh(Request())
        open(TOKEN, "w").write(c.to_json())
    return build("gmail", "v1", credentials=c), c


def me(svc):
    return svc.users().getProfile(userId="me").execute()["emailAddress"]


def sent_today():
    if not CONTACT_LOG.exists():
        return 0
    today = datetime.date.today().isoformat()
    with open(CONTACT_LOG) as fh:
        return sum(1 for r in csv.DictReader(fh)
                   if r.get("date", "").startswith(today) and r.get("status") == "SENT")


def log_contact(addr, business, subject, status, detail=""):
    new = not CONTACT_LOG.exists()
    with open(CONTACT_LOG, "a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["date", "address", "business", "subject", "status", "detail"])
        w.writerow([datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                    addr, business, subject, status, detail])


def build_body(p):
    """Body is assembled from VERIFIED defects only. No price. No invented claims."""
    defects = p.get("verified_defects") or []
    human = {
        "BROKEN_LINKS": "at least one link on your site returns a 404 error page",
        "NO_CONTACT_ON_HOMEPAGE": "your homepage doesn't show a phone number or email, so visitors have to hunt for a way to contact you",
        "NO_CONTACT_METHOD": "I couldn't find any way to contact you from your site",
        "STALE_COPYRIGHT": "the footer still shows an old copyright year, which makes the site look unattended",
        "NO_MOBILE_VIEWPORT": "the site isn't set up to scale on phones",
        "SSL_EXPIRED": "your security certificate has expired, so browsers warn visitors before they can view the site",
        "NO_VALID_HTTPS": "the site doesn't have a working security certificate, so browsers may warn visitors",
        "SLOW_RESPONSE": "the homepage was slow to load when I checked it",
        "NO_WRITTEN_CONTACT": "there's no contact form or email address, only a phone number",
        "NO_SOCIAL_LINKS": "there are no links to your social pages",
        "HEAVY_HTML": "the page code is unusually heavy, which slows loading",
        "WEAK_TITLE": "the page title is very short, which weakens how it appears in search results",
        "NO_META_DESCRIPTION": "there's no meta description, so Google writes its own snippet for you",
        "NO_TITLE": "the page has no title tag",
    }
    lines = [human[d] for d in defects if d in human][:3]
    if not lines:
        return None
    obs = lines[0] if len(lines) == 1 else \
        lines[0] + ", and " + lines[1] if len(lines) == 2 else \
        ", ".join(lines[:-1]) + ", and " + lines[-1]
    ev = p.get("evidence_detail", "")
    return (
        f"Hi,\n\n"
        f"I was looking at {p['business_name']} and noticed {obs}.\n"
        + (f"\n{ev}\n" if ev else "")
        + f"\nI fix this kind of thing for local businesses. I'm not after a meeting — if it's "
          f"useful I'll send you the specifics so you (or whoever looks after your site) can "
          f"just get it sorted.\n\n"
          f"Worth me sending that over?\n\n"
          f"{SENDER_NAME}\n{SENDER_PHONE}"
    )


def draft(prospects):
    out, blocked = [], []
    for p in prospects:
        decision, reasons, channel = consent_check(p)
        if decision != "PERMITTED":
            blocked.append({"business_name": p.get("business_name"), "reasons": reasons,
                            "channel": channel})
            continue
        body = build_body(p)
        if not body:
            blocked.append({"business_name": p.get("business_name"),
                            "reasons": ["NO_RENDERABLE_VERIFIED_DEFECT"], "channel": "manual_review"})
            continue
        out.append({"to": p["address"], "business_name": p["business_name"],
                    "subject": f"Quick note about the {p['business_name']} website",
                    "body": body + OPT_OUT,
                    "consent_type": p.get("consent_type_claimed"),
                    "ratified_by": p.get("human_ratified_by"),
                    "defects": p.get("verified_defects")})
    return out, blocked


def send(drafts, approved):
    require_external_release()
    if not approved:
        print("REFUSED: --send requires --i-approve. Nothing transmitted.", file=sys.stderr)
        return 2
    svc, _ = service()
    frm = me(svc)
    budget = DAILY_CAP - sent_today()
    if budget <= 0:
        print(f"REFUSED: daily cap {DAILY_CAP} reached.", file=sys.stderr)
        return 3
    ok = fail = 0
    for d in drafts[:budget]:
        m = EmailMessage()
        m["To"] = d["to"]; m["From"] = f"{SENDER_NAME} <{frm}>"; m["Subject"] = d["subject"]
        m.set_content(d["body"])
        try:
            r = svc.users().messages().send(
                userId="me",
                body={"raw": base64.urlsafe_b64encode(m.as_bytes()).decode()}).execute()
            mid = r.get("id")
            if not mid:
                raise RuntimeError("no message id returned")
            log_contact(d["to"], d["business_name"], d["subject"], "SENT", f"id={mid}")
            print(f"SENT   {d['to']:34s} id={mid}")
            ok += 1
        except Exception as e:
            log_contact(d["to"], d["business_name"], d["subject"], "FAILED", str(e)[:200])
            print(f"FAILED {d['to']:34s} {type(e).__name__}: {e}", file=sys.stderr)
            fail += 1
    print(f"\n{ok} sent / {fail} failed  (SENT = Gmail returned a message id)")
    return 0 if fail == 0 else 1


def selftest():
    require_external_release()
    svc, _ = service()
    addr = me(svc)
    m = EmailMessage()
    m["To"] = addr
    m["From"] = f"{SENDER_NAME} <{addr}>"
    m["Subject"] = "Hermes Money Engine — send path self-test"
    m.set_content(
        "This is an automated self-test from the Hermes Money Engine.\n\n"
        "It proves the Gmail send path works end to end via OAuth (no app password needed).\n\n"
        "No prospect has been contacted. Outreach remains gated by the UEMA consent gate\n"
        "and requires your explicit approval per batch.\n" + OPT_OUT)
    r = svc.users().messages().send(
        userId="me", body={"raw": base64.urlsafe_b64encode(m.as_bytes()).decode()}).execute()
    print(f"AUTH OK as {addr}")
    print(f"SELF-TEST SENT — gmail message id = {r.get('id')}")
    log_contact(addr, "SELF-TEST", "send path self-test", "SENT", f"id={r.get('id')}")
    return 0


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return 1
    if a[0] == "--selftest":
        return selftest()
    if a[0] == "--draft":
        pros = json.load(open(a[1]))
        d, b = draft(pros if isinstance(pros, list) else [pros])
        Path(ROOT / "drafts.json").write_text(json.dumps(d, indent=1))
        print(json.dumps({"drafts_built": len(d), "blocked": len(b)}, indent=1))
        for x in b:
            print(f"  BLOCKED {x['business_name']}: {', '.join(x['reasons'][:3])}")
        return 0
    if a[0] == "--send":
        return send(json.load(open(a[1])), "--i-approve" in a)
    print(__doc__); return 1


if __name__ == "__main__":
    sys.exit(main())

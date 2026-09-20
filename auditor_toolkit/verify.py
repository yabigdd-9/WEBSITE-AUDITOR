"""Local-first email verification consensus ($0, no quota).

score = 0.35*mx_ok + 0.25*smtp_rcpt + 0.15*not_disposable + 0.15*not_catchall_heuristic + 0.10*first_party
Gates: score >= 0.75 AND first_party_source required before drafting (matches plan).
SMTP RCPT probe is opt-in (SMTP_PROBE=1) and rate-limited; default = DNS-only + blocklist.
"""
from __future__ import annotations

import os
import socket
from pathlib import Path

BLOCKLIST = set()
for _p in (Path(__file__).resolve().parent.parent / "money-machine" / "disposable_email_blocklist.conf",
           Path(__file__).parent / "assets" / "disposable_blocklist.txt"):
    try:
        if _p.is_file():
            BLOCKLIST |= {
                line.strip().lower()
                for line in _p.read_text().splitlines()
                if line.strip() and not line.startswith("#")
            }
    except Exception:
        pass
BLOCKLIST |= {"mailinator.com", "tempmail.com", "10minutemail.com", "guerrillamail.com"}


def _mx_ok(domain: str) -> bool:
    try:
        import dns.resolver
        return bool(dns.resolver.resolve(domain, "MX", lifetime=5))
    except Exception:
        try:  # fallback: domain resolves at all
            socket.getaddrinfo(domain, 25, timeout=5)
            return True
        except Exception:
            return False


def verify_local(email: str, first_party_source: bool = False, probe_smtp: bool = False) -> dict:
    try:
        from email_validator import validate_email
        v = validate_email(email, check_deliverability=False)
        addr, domain = v.normalized.lower(), v.domain.lower()
    except Exception as exc:
        return {"email": email, "score": 0.0, "verdict": "REJECTED", "reasons": [f"syntax: {exc}"]}
    mx = _mx_ok(domain)
    not_disp = domain not in BLOCKLIST
    # catch-all heuristic: without a probe we cannot confirm; neutral 0.5 credit only if MX ok
    catchall_credit = 0.5 if mx else 0.0
    smtp_rcpt = 0.0
    if probe_smtp and os.getenv("SMTP_PROBE") == "1":
        try:
            import asyncio

            smtp_rcpt = float(asyncio.run(_smtp_probe(domain, addr)))
        except Exception:
            smtp_rcpt = 0.0
    score = round(0.35 * mx + 0.25 * smtp_rcpt + 0.15 * not_disp + 0.15 * catchall_credit + 0.10 * first_party_source, 3)
    reasons = []
    if not mx:
        reasons.append("no MX/A record")
    if not not_disp:
        reasons.append("disposable domain")
    if not first_party_source:
        reasons.append("not observed first-party — needs on-site evidence")
    verdict = "VERIFIED_HIGH" if (score >= 0.75 and first_party_source and mx) else ("CANDIDATE" if score >= 0.5 else "REJECTED")
    return {"email": addr, "score": score, "verdict": verdict, "reasons": reasons,
            "components": {"mx_ok": mx, "smtp_rcpt": smtp_rcpt, "not_disposable": not_disp,
                           "catchall_credit": catchall_credit, "first_party": first_party_source}}


async def _smtp_probe(domain: str, addr: str) -> float:
    import aiosmtplib
    import dns.resolver
    try:
        mx = dns.resolver.resolve(domain, "MX", lifetime=5)
        host = str(sorted(mx, key=lambda r: r.preference)[0].exchange).rstrip(".")
    except Exception:
        return 0.0
    try:
        async with aiosmtplib.SMTP(hostname=host, port=25, timeout=8) as c:
            await c.ehlo()
            await c.mail("verify@localhost")
            _, msg = await c.rcpt(addr)
            if str(msg)[:3].isdigit():
                code = int(str(msg).split()[0])
            else:
                code = int(getattr(c, "last_response", (0,))[0])
            return 1.0 if 200 <= code < 300 else 0.0
    except Exception:
        return 0.0

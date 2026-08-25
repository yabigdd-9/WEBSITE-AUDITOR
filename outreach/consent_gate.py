#!/usr/bin/env python3
"""
UEMA 2007 consent gate — REQUIRED before any electronic outreach artifact is produced.

Design rules:
  * Defaults to DENY. Absence of evidence is never treated as consent.
  * "Address published on the site" is NOT a consent basis by itself.
  * Hermes cannot self-ratify an inference; a human must, and it is recorded.
  * There is no override parameter. Blocked is blocked.
  * A blocked prospect keeps its research and is routed to a lawful channel.

Usage:
    python3 consent_gate.py --check prospects.json
    python3 consent_gate.py --selftest
"""
import json, re, sys, csv, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SUPPRESSION = ROOT / "suppression.csv"
CONTACT_LOG = ROOT / "contact_log.csv"

REQUIRED_FIELDS = [
    "business_name", "address", "address_source_url", "address_found_where",
    "surrounding_wording", "invites_contact", "refusal_statement_present",
    "role_or_personal", "relevance_to_role", "prior_relationship",
    "consent_type_claimed", "why_consent_believed", "verified_defects",
]

VALID_CONSENT = {"EXPRESS", "PRIOR_RELATIONSHIP", "INFERRED", "NONE"}

REFUSAL_PATTERNS = [
    r"no unsolicited", r"unsolicited (?:commercial )?(?:e-?mail|messages?)",
    r"do not (?:e-?mail|contact|send)", r"no (?:marketing|sales|spam|cold)",
    r"not accept(?:ing)? (?:marketing|solicitation)", r"no canvassing",
    r"opt[- ]out", r"we do not welcome",
]

PERSONAL_HINTS = [r"^[a-z]+\.[a-z]+@", r"^[a-z]{1,12}@(?:gmail|hotmail|outlook|yahoo|icloud)\."]
ROLE_HINTS = [r"^(?:info|office|admin|contact|enquir\w*|sales|hello|accounts|support|team)@"]


def load_suppression():
    if not SUPPRESSION.exists():
        return set()
    with open(SUPPRESSION) as fh:
        return {r["address"].strip().lower() for r in csv.DictReader(fh) if r.get("address")}


def recently_contacted(address, days=90):
    if not CONTACT_LOG.exists():
        return False
    cutoff = datetime.date.today() - datetime.timedelta(days=days)
    with open(CONTACT_LOG) as fh:
        for r in csv.DictReader(fh):
            if r.get("address", "").strip().lower() == address.strip().lower():
                try:
                    if datetime.date.fromisoformat(r["date"][:10]) >= cutoff:
                        return True
                except Exception:
                    return True          # unparseable date => treat as contacted (fail closed)
    return False


def check(p):
    """Return (decision, reasons, channel). decision in PERMITTED / BLOCKED."""
    reasons, addr = [], (p.get("address") or "").strip().lower()

    # 1. completeness — missing evidence is never consent
    for f in REQUIRED_FIELDS:
        if p.get(f) in (None, "", []):
            reasons.append(f"MISSING_FIELD:{f}")

    # 2. explicit refusal anywhere in the published context
    ctx = " ".join(str(p.get(k, "")) for k in
                   ("surrounding_wording", "refusal_statement_present", "page_text")).lower()
    if str(p.get("refusal_statement_present")).strip().lower() in ("true", "yes", "1"):
        reasons.append("REFUSAL_STATEMENT_PRESENT")
    for rx in REFUSAL_PATTERNS:
        if re.search(rx, ctx):
            reasons.append(f"REFUSAL_WORDING_MATCHED:{rx}")
            break

    # 3. provenance — harvested/purchased sources are barred (s.13)
    src = (p.get("address_source_url") or "").lower()
    prov = (p.get("address_provenance") or "own_website").lower()
    if prov not in ("own_website", "prior_relationship", "express_optin"):
        reasons.append(f"DISALLOWED_PROVENANCE:{prov}")
    if src and not re.match(r"^https?://", src):
        reasons.append("SOURCE_URL_NOT_A_URL")
    if any(k in src for k in ("yellow", "directory", "list", "database", "leads")):
        reasons.append("SOURCE_LOOKS_LIKE_DIRECTORY_OR_LIST")

    # 4. consent claim validity
    claim = (p.get("consent_type_claimed") or "").upper()
    if claim not in VALID_CONSENT:
        reasons.append(f"INVALID_CONSENT_TYPE:{claim or 'EMPTY'}")
    if claim == "NONE":
        reasons.append("NO_CONSENT_CLAIMED")
    if claim == "INFERRED":
        # publication alone is explicitly insufficient
        invites = str(p.get("invites_contact")).strip().lower() in ("true", "yes", "1")
        if not invites:
            reasons.append("INFERENCE_UNSUPPORTED:published_address_does_not_invite_contact")
        if not str(p.get("relevance_to_role", "")).strip():
            reasons.append("INFERENCE_UNSUPPORTED:no_relevance_to_role")
        if len(str(p.get("why_consent_believed", "")).strip()) < 40:
            reasons.append("INFERENCE_UNSUPPORTED:rationale_too_thin")
        if not p.get("human_ratified_by"):
            reasons.append("INFERENCE_NOT_HUMAN_RATIFIED")
    if claim == "EXPRESS" and not p.get("express_consent_evidence"):
        reasons.append("EXPRESS_CLAIMED_WITHOUT_EVIDENCE")
    if claim == "PRIOR_RELATIONSHIP" and not str(p.get("prior_relationship", "")).strip():
        reasons.append("PRIOR_RELATIONSHIP_CLAIMED_WITHOUT_DETAIL")

    # 5. address shape
    if addr:
        if any(re.search(r, addr) for r in PERSONAL_HINTS) and \
           not any(re.search(r, addr) for r in ROLE_HINTS):
            if not str(p.get("relevance_to_role", "")).strip():
                reasons.append("PERSONAL_ADDRESS_WITHOUT_ROLE_RELEVANCE")
    else:
        reasons.append("NO_ADDRESS")

    # 6. suppression + frequency
    if addr in load_suppression():
        reasons.append("ON_SUPPRESSION_LIST")
    if addr and recently_contacted(addr):
        reasons.append("CONTACTED_WITHIN_90_DAYS")

    # 7. relevance substance — generic pitch also destroys the rationale
    if not p.get("verified_defects"):
        reasons.append("NO_VERIFIED_DEFECT_FOR_THIS_BUSINESS")

    decision = "PERMITTED" if not reasons else "BLOCKED"
    channel = "email_queued_for_dion" if decision == "PERMITTED" else \
              "manual_review_then_phone_or_post"
    return decision, sorted(set(reasons)), channel


def selftest():
    cases = []

    # A: the exact error being corrected — published address, nothing else
    cases.append(("published address only, no invitation, no ratification", {
        "business_name": "Example Painters", "address": "info@example.co.nz",
        "address_source_url": "https://example.co.nz/contact",
        "address_found_where": "footer", "surrounding_wording": "info@example.co.nz",
        "invites_contact": False, "refusal_statement_present": False,
        "role_or_personal": "role", "relevance_to_role": "",
        "prior_relationship": "none", "consent_type_claimed": "INFERRED",
        "why_consent_believed": "it was on the website",
        "verified_defects": ["BROKEN_LINKS"]}, "BLOCKED"))

    # B: refusal notice present
    cases.append(("explicit no-marketing notice", {
        "business_name": "B Ltd", "address": "office@b.co.nz",
        "address_source_url": "https://b.co.nz/contact", "address_found_where": "contact page",
        "surrounding_wording": "Contact us for a quote. We do not accept marketing emails.",
        "invites_contact": True, "refusal_statement_present": True,
        "role_or_personal": "role", "relevance_to_role": "website enquiries",
        "prior_relationship": "none", "consent_type_claimed": "INFERRED",
        "why_consent_believed": "quote invitation implies openness to relevant business contact",
        "human_ratified_by": "Dion", "verified_defects": ["SSL_EXPIRED"]}, "BLOCKED"))

    # C: directory-sourced
    cases.append(("directory-sourced address", {
        "business_name": "C Ltd", "address": "info@c.co.nz",
        "address_source_url": "https://yellow.co.nz/listing/c-ltd",
        "address_provenance": "directory", "address_found_where": "listing",
        "surrounding_wording": "Email this business", "invites_contact": True,
        "refusal_statement_present": False, "role_or_personal": "role",
        "relevance_to_role": "general enquiries", "prior_relationship": "none",
        "consent_type_claimed": "INFERRED",
        "why_consent_believed": "listing invites contact from the public generally",
        "human_ratified_by": "Dion", "verified_defects": ["NO_MOBILE_VIEWPORT"]}, "BLOCKED"))

    # D: fully evidenced + human ratified
    cases.append(("invitation + relevance + ratified", {
        "business_name": "D Decorators", "address": "office@d.co.nz",
        "address_source_url": "https://d.co.nz/contact-us",
        "address_provenance": "own_website", "address_found_where": "contact page 'Get a quote' block",
        "surrounding_wording": "Get a quote — email our office and we'll come back to you.",
        "invites_contact": True, "refusal_statement_present": False,
        "role_or_personal": "role",
        "relevance_to_role": "office address handles inbound work enquiries; message concerns their own site's broken enquiry path",
        "prior_relationship": "none", "consent_type_claimed": "INFERRED",
        "why_consent_believed": ("Address is published in a block expressly inviting emailed enquiries "
                                "about work, and the message concerns a defect in that same enquiry path "
                                "which is directly relevant to the address's business function."),
        "human_ratified_by": "Dion", "ratified_at": "2026-08-18",
        "verified_defects": ["BROKEN_LINKS", "NO_CONTACT_ON_HOMEPAGE"]}, "PERMITTED"))

    # E: no verified defect => generic pitch
    e = dict(cases[3][1]); e["verified_defects"] = []
    cases.append(("no verified defect", e, "BLOCKED"))

    # F: no consent claimed
    f = dict(cases[3][1]); f["consent_type_claimed"] = "NONE"
    cases.append(("consent NONE", f, "BLOCKED"))

    print("UEMA CONSENT GATE — SELF TEST\n" + "=" * 66)
    passed = 0
    for label, payload, expect in cases:
        got, reasons, channel = check(payload)
        ok = got == expect
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {label}\n       expected={expect} got={got} -> {channel}")
        for r in reasons[:4]:
            print(f"         · {r}")
    print("=" * 66)
    print(f"{passed}/{len(cases)} passed")
    return 0 if passed == len(cases) else 1


def main():
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if "--check" in sys.argv:
        path = sys.argv[sys.argv.index("--check") + 1]
        data = json.load(open(path))
        data = data if isinstance(data, list) else [data]
        out = []
        for p in data:
            d, r, c = check(p)
            out.append({"business_name": p.get("business_name"), "decision": d,
                        "reasons": r, "channel": c})
        print(json.dumps(out, indent=1))
        blocked = sum(1 for o in out if o["decision"] == "BLOCKED")
        print(f"\n{len(out)-blocked} permitted / {blocked} blocked", file=sys.stderr)
        sys.exit(0)
    print(__doc__)


if __name__ == "__main__":
    main()

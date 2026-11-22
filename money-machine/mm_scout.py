"""Local, review-only research commands."""
import json
from pathlib import Path

import mm_core as core


def register(subcommands):
    for name in ("contact", "offers", "evidence", "outreach", "preflight"):
        command = subcommands.add_parser("scout-" + name)
        command.add_argument("--id", required=True, type=int)
        if name == "contact":
            command.add_argument("--refresh", action="store_true")
        if name in ("offers", "outreach", "preflight"):
            command.add_argument("--report", type=Path, required=True)
            command.add_argument("--ideas", type=Path, help="JSON array of proposed features")
        if name in ("outreach", "preflight"):
            command.add_argument("--recipient", required=True)
            command.add_argument("--draft", type=Path, required=True)
            command.add_argument("--mockup", action="append", default=[], metavar="ID=FILE")

    sent = subcommands.add_parser("scout-record-send")
    sent.add_argument("--id", required=True, type=int)
    sent.add_argument("--recipient", required=True)
    sent.add_argument("--gmail-id", required=True)
    optout = subcommands.add_parser("scout-record-optout")
    optout.add_argument("--recipient", required=True)


def record(db, args):
    from email_validator import validate_email

    recipient = validate_email(args.recipient, check_deliverability=False).normalized.casefold()
    if args.cmd == "scout-record-optout":
        db.execute(
            "INSERT OR IGNORE INTO mm_suppression(address, reason, created_at) VALUES(?,?,?)",
            (recipient, "Recipient opted out", core.now()),
        )
        return {"recipient": recipient, "suppressed": True}

    core.business(db, args.id)
    gmail_id = args.gmail_id.strip()
    if not gmail_id:
        raise ValueError("Provide the Gmail message ID from Sent")
    db.execute("BEGIN IMMEDIATE")
    existing = db.execute(
        "SELECT business_id, json_extract(detail,'$.recipient') FROM messages "
        "WHERE action='gmail_outreach_sent' AND json_extract(detail,'$.gmail_id')=?",
        (gmail_id,),
    ).fetchone()
    if existing and tuple(existing) != (args.id, recipient):
        raise ValueError("Gmail message ID is already logged for a different recipient or business")
    if not existing:
        db.execute(
            "INSERT INTO messages(event_at,action,business_id,detail) VALUES(?,?,?,?)",
            (core.now(), "gmail_outreach_sent", args.id,
             json.dumps({"recipient": recipient, "gmail_id": gmail_id})),
        )
    return {"recipient": recipient, "gmail_id": gmail_id, "recorded": True}


def run(db, args):
    business = dict(core.business(db, args.id))
    website = business["public_website"]
    host = core.public_url(website)
    result = {"business_id": args.id, "business": business["name"], "website": website}
    if args.cmd == "scout-contact":
        from mm_email_network import Crawler

        pages, errors = Crawler(core.root()).crawl(website, refresh=args.refresh)
        observations = dict.fromkeys(
            (hit["email"], page["url"], hit["method"])
            for page in pages if core.public_url(page["url"]) == host
            for hit in page["observations"]
        )
        result.update(
            contacts=[{"email": email, "reference": url, "method": method}
                      for email, url, method in observations],
            crawl_errors=errors,
        )
        return result
    if args.cmd == "scout-evidence":
        rows = db.execute(
            "SELECT to_state, reason, evidence, event_at FROM pipeline_events "
            "WHERE business_id=? ORDER BY id", (args.id,),
        )
        result["events"] = [dict(row) for row in rows]
        return result

    report = json.loads(args.report.read_text())
    if core.public_url(report["url"]) != host:
        raise ValueError("Report website does not match the prospect")
    offers = [
        {"id": str(index), "title": finding["defect"], "severity": finding["severity"],
         "reference": finding["source_url"], "observed": finding["observed"],
         "proposal": finding["remediation_action"]}
        for index, finding in enumerate(report.get("findings", []), 1)
        if finding.get("observed") and finding.get("remediation_action")
        and finding.get("source_url") and finding.get("confidence") != "heuristic"
        and core.public_url(finding["source_url"]) == host
    ]
    priorities = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    offers.sort(key=lambda offer: priorities.get(offer["severity"], 4))
    if args.ideas:
        for index, idea in enumerate(json.loads(args.ideas.read_text()), 1):
            if core.public_url(idea["reference"]) != host:
                raise ValueError("Feature reference does not match the prospect")
            offers.append({"id": f"idea-{index}", "title": idea["title"],
                           "reference": idea["reference"], "proposal": idea["proposal"],
                           "kind": "proposed_feature"})
    result["offers"] = offers
    if args.cmd in ("scout-outreach", "scout-preflight"):
        mockups = dict(value.split("=", 1) for value in args.mockup)
        if not offers or set(mockups) != {offer["id"] for offer in offers}:
            raise ValueError("Provide one --mockup ID=FILE for each offer from scout-offers")
        paths = [Path(mockups[offer["id"]]).resolve(strict=True) for offer in offers]
        if len(set(paths)) != len(paths) or any(not path.is_file() for path in paths):
            raise ValueError("Each offer requires a separate mockup file")
        draft = args.draft.read_text().strip()
        if not draft:
            raise ValueError("Provide a non-empty draft")
        for offer, path in zip(offers, paths):
            offer["mockup"] = str(path)
        result.update(status="REVIEW_REQUIRED", recipient=args.recipient, draft=draft)
    if args.cmd == "scout-preflight":
        result["preflight"] = preflight(db, business, args.recipient)
        result["status"] = "REVIEW_REQUIRED" if not result["preflight"]["blocked"] else "BLOCKED"
    return result


def preflight(db, business, recipient):
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    blocked = []
    if business.get("suppression_reason"):
        blocked.append("Business is suppressed")
    if "mm_holds" not in tables or "mm_suppression" not in tables:
        blocked.append("Suppression and hold records are unavailable")
    else:
        if db.execute("SELECT 1 FROM mm_holds WHERE business_id=?", (business["id"],)).fetchone():
            blocked.append("Business has a hold")
        if db.execute("SELECT 1 FROM mm_suppression WHERE lower(trim(address))=?",
                      (recipient.strip().casefold(),)).fetchone():
            blocked.append("Recipient is suppressed")
    if "mm_messages" not in tables:
        blocked.append("Prior sends in the outreach database cannot be checked")
    elif db.execute(
        "SELECT 1 FROM mm_messages WHERE sent_at IS NOT NULL "
        "AND (business_id=? OR lower(trim(recipient))=?)",
        (business["id"], recipient.strip().casefold()),
    ).fetchone():
        blocked.append("A prior send exists for this business or recipient")
    if "messages" in tables and db.execute(
        "SELECT 1 FROM messages WHERE action='gmail_outreach_sent' "
        "AND (business_id=? OR json_extract(detail,'$.recipient')=?)",
        (business["id"], recipient.strip().casefold()),
    ).fetchone():
        blocked.append("A prior Gmail send is logged for this business or recipient")
    return {"blocked": blocked, "reference_check": "prospect website matched",
            "mockup_check": "separate local files present",
            "remaining_review": ["Open each reference and mockup as the recipient",
                                 "Check the sending account for previous outreach"]}

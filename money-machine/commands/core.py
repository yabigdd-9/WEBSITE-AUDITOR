"""Core operator commands for mm_operator."""

from __future__ import annotations

import argparse
import contextlib
import json
from pathlib import Path

from .exceptions import OperatorError, ValidationError
from .compat import *

# Re-export for backward compatibility
CLAIM_TYPES = CLAIM_TYPES
STAGES = STAGES
REPLY_ACTIONS = REPLY_ACTIONS
OFFERS = OFFERS
ONTOLOGY = ONTOLOGY

mm_now = mm_now


def register(subparsers: argparse._SubParsersAction):
    """Register core commands."""
    # Daily operations
    for cmd in ("daily", "run-day", "status", "money", "learn"):
        subparsers.add_parser(cmd, help=f"{cmd.replace('-', ' ').title()} operations")

    # System commands
    for cmd in ("backup", "init", "doctor", "experiment"):
        subparsers.add_parser(cmd, help=f"{cmd.replace('-', ' ').title()} operations")

    # Business operations
    intake = subparsers.add_parser("intake")
    intake.add_argument("--name", required=True)
    intake.add_argument("--url", required=True)
    intake.add_argument("--region", required=True)
    intake.add_argument("--source", required=True)

    audit = subparsers.add_parser("audit")
    audit.add_argument("id", type=int)
    audit.add_argument("--url", required=True)
    audit.add_argument("--observation", required=True)
    audit.add_argument("--limitation", required=True)
    audit.add_argument("--capture", required=True)
    audit.add_argument("--status", choices=["verified", "partial", "refuted", "unverified"], required=True)
    audit.add_argument("--method", required=True)
    audit.add_argument("--confidence", type=float, required=True)
    audit.add_argument("--claim-type", choices=CLAIM_TYPES, default="observed_fact")

    contact = subparsers.add_parser("contact")
    contact.add_argument("id", type=int)
    contact.add_argument("--recipient", required=True)
    contact.add_argument("--url", required=True)
    contact.add_argument("--capture", required=True)
    contact.add_argument("--relevance", required=True)

    draft = subparsers.add_parser("draft")
    draft.add_argument("id", type=int)
    draft.add_argument("--recipient", required=True)
    draft.add_argument("--body-file", required=True)
    draft.add_argument("--parent", type=int)

    draft_review = subparsers.add_parser("draft-review")
    draft_review.add_argument("id", type=int)

    draft_approve = subparsers.add_parser("draft-approve")
    draft_approve.add_argument("id", type=int)
    draft_approve.add_argument("--actor", required=True)
    draft_approve.add_argument("--approval-receipt", type=int, required=True)

    review = subparsers.add_parser("review")
    review.add_argument("id", type=int)
    review.add_argument("--body-file", required=True)
    review.add_argument("--human", required=True)
    review.add_argument("--approval-receipt", type=int, required=True)
    review.add_argument("--proposal", action="store_true")

    record_sent = subparsers.add_parser("record-sent")
    record_sent.add_argument("id", type=int)
    record_sent.add_argument("--receipt", type=int, required=True)
    record_sent.add_argument("--proposal", action="store_true")

    receipt_import = subparsers.add_parser("receipt-import")
    receipt_import.add_argument("--envelope", required=True)

    for cmd in ("cash", "refund"):
        p = subparsers.add_parser(cmd)
        p.add_argument("id", type=int)
        p.add_argument("--cents", type=int, required=True)
        p.add_argument("--receipt", type=int, required=True)

    reply = subparsers.add_parser("reply")
    reply.add_argument("id", type=int)
    reply.add_argument("--classification", choices=list(REPLY_ACTIONS), required=True)
    reply.add_argument("--receipt", type=int, required=True)

    suppress = subparsers.add_parser("suppress")
    suppress.add_argument("--address", required=True)
    suppress.add_argument("--reason", required=True)

    stage = subparsers.add_parser("stage")
    stage.add_argument("id", type=int)
    stage.add_argument("--stage", choices=STAGES, required=True)
    stage.add_argument("--next-action", required=True)
    stage.add_argument("--due")

    quote = subparsers.add_parser("quote")
    quote.add_argument("id", type=int)
    quote.add_argument("--recipient", required=True)
    quote.add_argument("--body-file", required=True)
    quote.add_argument("--price-nzd", type=int, required=True)

    score = subparsers.add_parser("score")
    score.add_argument("id", type=int)
    score.add_argument("--inputs", required=True)

    demo_qa = subparsers.add_parser("demo-qa")
    demo_qa.add_argument("id", type=int)
    demo_qa.add_argument("--path", required=True)

    model_request_cmd = subparsers.add_parser("model-request")
    model_request_cmd.add_argument("--model", required=True)
    model_request_cmd.add_argument("--provider", required=True)
    model_request_cmd.add_argument("--purpose", required=True)

    run_job = subparsers.add_parser("run-job")
    run_job.add_argument("--key", required=True)
    run_job.add_argument("--kind", choices=["status", "learn"], required=True)


def handle(a: argparse.Namespace) -> dict | str:
    """Handle core commands."""
    validate_environment()

    with contextlib.closing(connect()) as d, d:
        if a.cmd in ("daily", "run-day", "status"):
            result = run_day(d, write=a.cmd != "status")
        elif a.cmd == "money":
            result = run_day(d, False)["next_revenue_action"]
        elif a.cmd == "learn":
            result = learn(d)
        elif a.cmd == "doctor":
            result = doctor(d, a.profile)
        elif a.cmd == "experiment":
            result = assign_experiment(d, a.id, a.industry, a.problem, a.offer, a.price_band, a.style, a.demo_type)
        elif a.cmd == "intake":
            host = public_url(a.url)
            public_url(a.source)
            for b in d.execute("SELECT id, name, public_website FROM businesses WHERE is_dummy=0"):
                if b["name"].strip().casefold() == a.name.strip().casefold():
                    raise ValidationError("Duplicate prospect " + str(b["id"]))
                try:
                    existing_host = public_url(b["public_website"]) if b["public_website"] else None
                except ValueError:
                    existing_host = None
                if existing_host == host:
                    raise ValidationError("Duplicate prospect " + str(b["id"]))
            c = d.execute(
                "INSERT INTO businesses(name, region, public_website, source, discovered_at, current_status, is_dummy) VALUES(?,?,?,?,?,'discovered',0)",
                (a.name.strip(), a.region, a.url, a.source, mm_now()),
            )
            bid = c.lastrowid
            d.execute("INSERT INTO mm_deals(business_id, stage, updated_at) VALUES(?,'DISCOVERED',?)", (bid, mm_now()))
            event(d, "intake", bid, a.source)
            result = {"business_id": bid}
        elif a.cmd == "audit":
            result = {"evidence_id": record_evidence(d, a.id, a.url, a.observation, a.limitation, a.capture, a.status, a.method, a.confidence, a.claim_type)}
        elif a.cmd == "contact":
            record_contact(d, a.id, a.recipient, a.url, a.capture, a.relevance)
            result = {"contact_source": "captured", "permission": "Human review required"}
        elif a.cmd == "draft":
            result = {"draft_id": create_draft(d, a.id, a.recipient, Path(a.body_file).read_text(), a.parent)}
        elif a.cmd == "draft-review":
            import mm_drafts
            result = mm_drafts.review_draft(d, a.id)
        elif a.cmd == "draft-approve":
            import mm_drafts
            with contextlib.closing(connect()) as _dd, _dd:
                result = mm_drafts.approve_draft(_dd, a.id, a.actor, a.approval_receipt)
        elif a.cmd == "review":
            approve(d, a.id, Path(a.body_file).read_text(), a.human, a.approval_receipt, a.proposal)
            result = {"approval": "Recorded from evidence"}
        elif a.cmd == "record-sent":
            record_sent(d, a.id, a.receipt, a.proposal)
            result = {"recorded": True, "sent_by_this_command": False}
        elif a.cmd == "receipt-import":
            result = {"receipt_id": import_receipt(d, a.envelope), "verification": "Human attestation; no live provider query"}
        elif a.cmd == "cash":
            cash(d, a.id, a.cents, a.receipt)
            result = metrics(d)
        elif a.cmd == "refund":
            refund(d, a.id, a.cents, a.receipt)
            result = metrics(d)
        elif a.cmd == "reply":
            record_reply(d, a.id, a.classification, a.receipt)
            result = {"action": REPLY_ACTIONS[a.classification]}
        elif a.cmd == "suppress":
            d.execute("INSERT OR IGNORE INTO mm_suppression(address, reason, created_at) VALUES(?,?,?)", (a.address.strip().lower(), a.reason, mm_now()))
            event(d, "suppress", None, a.address.strip().lower())
            result = {"suppressed": True}
        elif a.cmd == "stage":
            change_stage(d, a.id, a.stage, a.next_action, a.due)
            result = {"stage": a.stage}
        elif a.cmd == "quote":
            result = {"proposal_id": create_proposal(d, a.id, a.recipient, Path(a.body_file).read_text(), a.price_nzd * 100)}
        elif a.cmd == "score":
            result = save_score(d, a.id, latest_evidence(d, a.id), **json.loads(Path(a.inputs).read_text()))
        elif a.cmd == "demo-qa":
            result = demo_qa(d, a.id, a.path)
        elif a.cmd == "model-request":
            result = model_request(d, a.model, a.provider, a.purpose)
        elif a.cmd == "run-job":
            d.execute("BEGIN IMMEDIATE")
            j = claim_job(d, a.key, a.kind)
            d.commit()
            if j["state"] == "completed":
                result = {"cached_checkpoint": json.loads(j["checkpoint"])}
            else:
                try:
                    result = run_day(d, False) if a.kind == "status" else learn(d)
                    finish_job(d, a.key, result)
                except Exception as ex:
                    finish_job(d, a.key, {}, str(ex))
                    d.commit()
                    raise
        elif a.cmd == "price":
            if (a.hours_low is None) != (a.hours_high is None):
                raise ValidationError("Both hour bounds required")
            result = pricing(a.problem, [a.hours_low, a.hours_high] if a.hours_low is not None else None)
        elif a.cmd == "backup":
            result = backup()
        elif a.cmd == "init":
            b = backup()
            migrate(d, b)
            result = "Migration checked; backup " + str(b)
        else:
            raise OperatorError(f"Unknown core command: {a.cmd}")

    return result


def metrics(d):
    """Calculate and return business metrics."""
    get = lambda sql: d.execute(sql).fetchone()[0]
    proven = []
    # Limit to recent verified sends to avoid loading all messages (N+1 fix)
    for m in d.execute("SELECT * FROM mm_messages WHERE sent_at IS NOT NULL AND send_receipt IS NOT NULL ORDER BY sent_at DESC LIMIT 1000"):
        try:
            receipt(d, m["send_receipt"], "send", m["business_id"], m["id"], digest(m["recipient"], m["body"]))
            proven.append(m)
        except ValueError:
            pass
    revenue = 0
    refunds = 0
    # Limit to recent cash records to avoid loading all (N+1 fix)
    for c in d.execute("SELECT * FROM mm_cash ORDER BY received_at DESC LIMIT 1000"):
        try:
            r = receipt(d, c["receipt"], "payment", c["business_id"])
            if r["amount_cents"] != c["amount_cents"] or r["currency"] != "NZD":
                continue
            revenue += c["amount_cents"]
        except ValueError:
            continue
    refunds = get("SELECT coalesce(sum(amount_cents),0) FROM mm_refunds")
    verified = 0
    fresh_legacy = 0
    for row in d.execute("SELECT DISTINCT business_id FROM mm_evidence"):
        bid = row[0]
        eid = latest_evidence(d, bid)
        checked = d.execute("SELECT checked_at FROM mm_evidence WHERE id=?", (eid,)).fetchone()[0]
        fresh_legacy += fresh(checked)
        try:
            evidence(d, eid, bid)
            verified += 1
        except ValueError:
            pass

    return {
        "real_prospects": get("SELECT count(*) FROM businesses WHERE is_dummy=0"),
        "fresh_legacy_observation_prospects": fresh_legacy,
        "independently_verified_current_claims": verified,
        "prospects_without_any_evidence": get("SELECT count(*) FROM businesses b WHERE is_dummy=0 AND NOT EXISTS(SELECT 1 FROM mm_evidence e WHERE e.business_id=b.id)"),
        "verified_sends": len(proven),
        "verified_replies": sum(human_reply_verified(d, m["id"], m["business_id"], m["reply"]) for m in proven),
        "legacy_claimed_sends_unverified": get("SELECT count(*) FROM outreach WHERE sent_at IS NOT NULL"),
        "suppressed_businesses": get("SELECT count(*) FROM mm_deals WHERE stage='SUPPRESSED'"),
        "suppressed_addresses": get("SELECT count(*) FROM mm_suppression"),
        "active_drafts": get("SELECT count(*) FROM mm_messages WHERE sent_at IS NULL AND invalidated_reason IS NULL"),
        "invalidated_drafts": get("SELECT count(*) FROM mm_messages WHERE invalidated_reason IS NOT NULL"),
        "proposal_drafts": get("SELECT count(*) FROM mm_proposals WHERE sent_at IS NULL AND invalidated_reason IS NULL"),
        "gross_received_nzd": round(revenue / 100, 2),
        "refunded_nzd": round(refunds / 100, 2),
        "net_received_nzd": round(max(0, revenue - refunds) / 100, 2),
        "model_calls_this_workflow": 0,
        "model_cost_this_workflow_usd": 0,
        "models_enabled": False,
        "historical_billing_status": "Not reconciled against provider statements; zero ledger values are not proof of historical zero spend",
    }
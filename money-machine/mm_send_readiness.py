"""Read-only preparation for exact-message email transport review. Never sends."""

from __future__ import annotations

import mm_approval
import mm_core as core
import mm_email_store
import mm_transport


def inspect_message(db, message_id, *, own_claim=None, canonical=False):
    """Recheck existing gates without approving, migrating or creating intents."""
    result = {
        "message_id": message_id,
        "mode": "TRANSPORT_REVIEW_ONLY",
        "ready_to_send": False,
        "message_ready_for_transport_review": False,
        "external_messages_sent": 0,
        "database_writes": 0,
        "network_calls": 0,
        "checks": {},
    }
    checks = result["checks"]
    try:
        result["transport"] = mm_transport.status()
        row = db.execute(
            "SELECT id,business_id,recipient,body,approved_hash,sent_at,invalidated_reason "
            "FROM mm_messages WHERE id=?",
            (message_id,),
        ).fetchone()
        if row is None:
            checks["message_exists"] = False
            result["holds"] = ["message_exists", "live_transport_not_approved"]
            return result
        message = dict(row)
        checks["message_exists"] = True
        checks["not_already_sent"] = message["sent_at"] is None
        checks["draft_valid"] = message["invalidated_reason"] is None
        digest = core.digest(message["recipient"], message["body"])
        result.update(business_id=message["business_id"], content_hash=digest)
        checks["exact_message_approval"] = message["approved_hash"] == digest
        approval = db.execute(
            "SELECT status,content_hash FROM approval_records WHERE business_id=? "
            "ORDER BY id DESC LIMIT 1",
            (message["business_id"],),
        ).fetchone()
        checks["latest_approval_matches"] = bool(
            approval and approval["status"] == "APPROVED" and approval["content_hash"] == digest
        )
        try:
            mm_email_store.require_email(db, message["business_id"], message["recipient"])
            checks["current_verified_recipient"] = True
        except (ValueError, LookupError):
            checks["current_verified_recipient"] = False
        gates = mm_approval.evaluate(db, message["business_id"])
        if own_claim and "no_duplicate_send" in gates["gates"]:
            reserved = db.execute(
                "SELECT 1 FROM smtp_candidate_submissions s JOIN outreach_send_ledger l "
                "ON l.idempotency_key=s.submission_key WHERE s.message_id=? "
                "AND s.submission_key=? AND s.content_hash=? AND s.status='RESERVED' "
                "AND l.business_id=? AND l.content_hash=? AND l.status='planned'",
                (message_id, own_claim, digest, message["business_id"], digest),
            ).fetchone()
            others = db.execute(
                "SELECT count(*) FROM outreach_send_ledger WHERE business_id=? "
                "AND status IN ('planned','sent') AND idempotency_key<>?",
                (message["business_id"], own_claim),
            ).fetchone()[0]
            if reserved and not others:
                gates["gates"]["no_duplicate_send"] = {
                    "passed": True,
                    "evidence": {"own_durable_reservation": True},
                }
                gates["all_passed"] = all(
                    value.get("passed") is True for value in gates["gates"].values()
                )
        checks["current_approval_gates"] = gates["all_passed"] is True
        result["approval_gates"] = gates["gates"]
        result["message_ready_for_transport_review"] = all(checks.values())
    except Exception as exc:
        # Unknown schema/policy/read errors must remain a visible hold.
        checks["inspection_available"] = False
        result["error_type"] = type(exc).__name__
    result["holds"] = [name for name, passed in checks.items() if not passed]
    transport = result.get("transport", {})
    live = transport.get("enabled") is True and transport.get("external_send_allowed") is True
    if not live:
        result["holds"].append("live_transport_not_approved")
    if canonical and live and result["message_ready_for_transport_review"]:
        try:
            import mm_smtp_live

            envelope = mm_smtp_live.engine.prepare(
                message_id, message["recipient"], message["body"]
            )
            mm_smtp_live._strict_approval(db, message_id, envelope)
            checks["canonical_approval_artifact_copy_and_evidence"] = True
        except Exception:
            checks["canonical_approval_artifact_copy_and_evidence"] = False
            result["message_ready_for_transport_review"] = False
            result["holds"].append("canonical_approval_artifact_copy_and_evidence")
    result["ready_to_send"] = live and result["message_ready_for_transport_review"]
    if (
        message_id
        and db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='smtp_candidate_submissions'"
        ).fetchone()
    ):
        claim = db.execute(
            "SELECT status FROM smtp_candidate_submissions WHERE message_id=?", (message_id,)
        ).fetchone()
        if claim and own_claim is None:
            result["ready_to_send"] = False
            result["holds"].append("prior_submission_requires_reconciliation")
    return result

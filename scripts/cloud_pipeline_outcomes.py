"""Owner-attested business outcomes; no network, delivery, charging or inference."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

KIND = "website_auditor_business_outcomes_v1"
MAX_IMPORT = 100
MAX_HISTORY = 10000
STATES = {
    "approval": {"approved", "revoked"},
    "send": {"queued", "attempted", "provider_accepted", "delivered", "bounced"},
    "response": {"received"},
    "quote": {"issued", "accepted", "declined"},
    "invoice": {"issued", "voided"},
    "payment": {"confirmed", "refunded"},
    "cost": {"confirmed"},
    "suppression": {"opted_out"},
}
ID = re.compile(r"[A-Za-z0-9_-]{1,100}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
FIELDS = {
    "event_id",
    "entity_id",
    "action",
    "status",
    "timestamp_utc",
    "evidence_sha256",
    "record_id",
    "amount_minor",
    "currency",
    "owner_verified",
}
BASE = {
    "event_id",
    "entity_id",
    "action",
    "status",
    "timestamp_utc",
    "evidence_sha256",
    "record_id",
    "owner_verified",
}


def validate(item, now):
    if not isinstance(item, dict) or set(item) - FIELDS or not BASE <= set(item):
        raise ValueError("Invalid outcome fields; no free text or contact data permitted")
    if not all(
        isinstance(item[k], str) and ID.fullmatch(item[k]) for k in ("event_id", "record_id")
    ):
        raise ValueError("Invalid outcome identity")
    if not all(
        isinstance(item[k], str) and DIGEST.fullmatch(item[k])
        for k in ("entity_id", "evidence_sha256")
    ):
        raise ValueError("Hashed entity and evidence required")
    if item["action"] not in STATES or item["status"] not in STATES[item["action"]]:
        raise ValueError("Invalid outcome transition")
    if item["owner_verified"] is not True:
        raise ValueError("Owner evidence verification required")
    try:
        date = datetime.fromisoformat(item["timestamp_utc"].replace("Z", "+00:00"))
        if date.tzinfo is None or date.timestamp() > now + 300:
            raise ValueError("Timezone or chronology invalid")
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("Invalid outcome timestamp") from exc
    monetary = item["action"] in {"payment", "cost"}
    if monetary:
        if (
            type(item.get("amount_minor")) is not int
            or not 0 < item["amount_minor"] <= 100_000_000
            or item.get("currency") != "NZD"
        ):
            raise ValueError("Positive bounded NZD minor units required")
    elif "amount_minor" in item or "currency" in item:
        raise ValueError("Money only belongs on verified payment/cost records")
    return {**item, "timestamp_utc": date.astimezone(timezone.utc).isoformat()}


def _require(prior, action, status, record=None):
    return any(
        x["action"] == action
        and x["status"] == status
        and (record is None or x["record_id"] == record)
        for x in prior
    )


def _check_sequence(item, prior):
    action, status, record = item["action"], item["status"], item["record_id"]
    if action == "send":
        if any(x["action"] == "suppression" for x in prior) and status in {
            "queued",
            "attempted",
            "provider_accepted",
        }:
            raise ValueError("Suppressed prospect cannot be queued or sent")
        if status in {"queued", "attempted", "provider_accepted"}:
            approvals = [x for x in prior if x["action"] == "approval"]
            if not approvals or approvals[-1]["status"] != "approved":
                raise ValueError("Active owner approval required")
        prerequisite = {
            "attempted": "queued",
            "provider_accepted": "attempted",
            "delivered": "provider_accepted",
            "bounced": "provider_accepted",
        }
        if status in prerequisite and not _require(prior, "send", prerequisite[status], record):
            raise ValueError("Missing send prerequisite")
    if action == "quote" and status in {"accepted", "declined"}:
        if not _require(prior, "quote", "issued", record):
            raise ValueError("Quote must exist before a response")
        if any(
            x["action"] == "quote"
            and x["record_id"] == record
            and x["status"] in {"accepted", "declined"}
            for x in prior
        ):
            raise ValueError("Quote already finalized")
    if (
        action == "invoice"
        and status == "voided"
        and not _require(prior, "invoice", "issued", record)
    ):
        raise ValueError("Invoice must exist before voiding")
    if action == "payment":
        if not _require(prior, "invoice", "issued", record):
            raise ValueError("Payment must reference an issued invoice")
        if _require(prior, "invoice", "voided", record):
            raise ValueError("Cannot confirm payment for voided invoice")
        if status == "refunded":
            paid = sum(
                x["amount_minor"] * (1 if x["status"] == "confirmed" else -1)
                for x in prior
                if x["action"] == "payment" and x["record_id"] == record
            )
            if item["amount_minor"] > paid:
                raise ValueError("Refund exceeds confirmed payments")


def import_outcomes(state, document, *, now, run_id, actor):
    """Validate on a copy: failed imports never partially mutate checkpoint state."""
    if (
        not isinstance(document, dict)
        or set(document) != {"kind", "events"}
        or document["kind"] != KIND
        or not isinstance(document["events"], list)
        or len(document["events"]) > MAX_IMPORT
    ):
        raise ValueError("Invalid outcome bundle")
    if not ID.fullmatch(run_id) or not actor:
        raise ValueError("Authenticated run and owner identity required")
    working = copy.deepcopy(state)
    events = working.setdefault("business_events", [])
    imported = 0
    for raw in document["events"]:
        item = validate(raw, now)
        if item["entity_id"] not in working["prospects"]:
            raise ValueError("Outcome must refer to a known prospect")
        duplicate = next((x for x in events if x["event_id"] == item["event_id"]), None)
        if duplicate:
            if any(duplicate[k] != v for k, v in item.items()):
                raise ValueError("Conflicting event ID")
            continue
        if len(events) >= MAX_HISTORY:
            raise ValueError("Outcome history full; owner archival required")
        if any(
            x["action"] == item["action"]
            and x["evidence_sha256"] == item["evidence_sha256"]
            and x["status"] == item["status"]
            for x in events
        ):
            raise ValueError("Duplicate source evidence under a different event ID")
        prior = [x for x in events if x["entity_id"] == item["entity_id"]]
        if prior and item["timestamp_utc"] < prior[-1]["timestamp_utc"]:
            raise ValueError("Outcomes must be imported chronologically per prospect")
        if any(
            x["action"] == item["action"]
            and x["status"] == item["status"]
            and x["record_id"] == item["record_id"]
            for x in prior
        ) and item["action"] not in {"payment", "cost", "approval"}:
            raise ValueError("Duplicate business transition")
        if item["action"] == "approval" and item["status"] == "approved":
            draft = working["prospects"][item["entity_id"]].get("draft")
            if not draft or hashlib.sha256(draft.encode()).hexdigest() != item["evidence_sha256"]:
                raise ValueError("Approval must identify the current exact draft")
        _check_sequence(item, prior)
        events.append(
            {
                **item,
                "run_id": run_id,
                "actor_sha256": hashlib.sha256(actor.encode()).hexdigest(),
                "sanitized_error": "none",
                "source": "owner_verified_import",
            }
        )
        if item["action"] == "suppression":
            prospect = working["prospects"][item["entity_id"]]
            prospect["status"] = "suppressed"
            prospect["draft"] = None
        imported += 1
    state.clear()
    state.update(working)
    return imported


def outcome_metrics(state):
    events = state.get("business_events", [])

    def count(action, status):
        return sum(x["action"] == action and x["status"] == status for x in events)

    paid = sum(
        x["amount_minor"] * (1 if x["status"] == "confirmed" else -1)
        for x in events
        if x["action"] == "payment"
    )
    costs = sum(x["amount_minor"] for x in events if x["action"] == "cost")
    return {
        "contacts_sent": count("send", "provider_accepted"),
        "provider_accepted": count("send", "provider_accepted"),
        "delivered": count("send", "delivered"),
        "bounced": count("send", "bounced"),
        "contacts_queued": count("send", "queued"),
        "replies": count("response", "received"),
        "accepted_quotes": count("quote", "accepted"),
        "invoices_issued": count("invoice", "issued"),
        "confirmed_revenue": paid / 100,
        "confirmed_revenue_minor": paid,
        "confirmed_cost_minor": costs,
        "currency": "NZD",
        "revenue_status": "owner-verified receipt imports; external totals unreconciled"
        if paid
        else "zero verified; external totals unreconciled",
    }


def private_import_path(path, suffix):
    root = Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())).resolve()
    path = Path(path).absolute()
    if (
        path.suffix != suffix
        or ".." in path.parts
        or path.is_symlink()
        or not path.parent.is_dir()
        or path.parent.resolve() != path.parent
        or not path.resolve().is_relative_to(root)
    ):
        raise ValueError("Imports must use regular files in a private temporary directory")
    return path


def main():
    parser = argparse.ArgumentParser(
        description="Seal owner-verified outcomes locally; never sends"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        from cryptography.fernet import Fernet

        incoming = private_import_path(args.input, ".json")
        outgoing = private_import_path(args.output, ".enc")
        if incoming.stat().st_size > 100_000:
            raise ValueError("Oversized input")
        doc = json.loads(incoming.read_text())
        if doc.get("kind") != KIND or not isinstance(doc.get("events"), list):
            raise ValueError("Invalid outcome document")
        now = int(datetime.now(timezone.utc).timestamp())
        for item in doc["events"]:
            validate(item, now)
        token = Fernet(os.environ["WA_PIPELINE_STATE_KEY"].encode()).encrypt(
            json.dumps(doc).encode()
        )
        if len(token) > 50_000:
            raise ValueError("Input exceeds workflow dispatch limit")
        from scripts.report_vault import _write_new_file

        _write_new_file(outgoing, token)
        print("Encrypted outcome import prepared; no external operation performed.")
        return 0
    except Exception:
        print("Outcome preparation blocked; review the schema privately.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

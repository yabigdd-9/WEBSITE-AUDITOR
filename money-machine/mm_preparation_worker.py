"""Loop C: deterministic remediation, local concept demo, and QA.

This worker is deliberately incapable of deployment or outreach. It consumes
only canonical auditor_toolkit reports already recorded by the audit worker,
writes local preview artifacts under outputs/, and advances one declared
pipeline edge at a time.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from mm_pipeline import PermanentError, RetryableError

REPO = Path(__file__).resolve().parents[1]
TOOLKIT_ROOT = REPO / "outputs" / "toolkit"
PACKAGE_ROOT = REPO / "outputs" / "prospect-packages"


def _event_evidence(d, business_id, to_state):
    row = d.execute(
        "SELECT evidence FROM pipeline_events "
        "WHERE business_id=? AND to_state=? AND evidence IS NOT NULL "
        "ORDER BY id DESC LIMIT 1",
        (business_id, to_state),
    ).fetchone()
    if not row:
        return {}
    try:
        value = json.loads(row["evidence"])
    except (KeyError, TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _canonical_report(d, business_id):
    audit = _event_evidence(d, business_id, "AUDITED")
    run_id = str(audit.get("run_id") or "").strip()
    if not run_id:
        raise PermanentError(
            "canonical audit run_id missing; human may requeue this item to AUDIT_PENDING"
        )

    from auditor_toolkit.storage import History

    history = History(TOOLKIT_ROOT)
    try:
        report = history.get(run_id)
    except KeyError as exc:
        raise RetryableError(
            "canonical audit history entry unavailable: " + run_id
        ) from exc

    if report.get("status") != "complete":
        raise RetryableError("canonical audit is not complete: " + run_id)
    if report.get("run_id") != run_id:
        raise PermanentError("canonical audit identity mismatch")
    return report


def _workspace(business_id, run_id):
    # run_id originates from canonical toolkit history, but keep path construction
    # defensive so no event value can escape the local output tree.
    safe_run = "".join(
        ch for ch in str(run_id) if ch.isalnum() or ch in ("-", "_")
    )
    if not safe_run or safe_run != str(run_id):
        raise PermanentError("unsafe canonical audit run_id")
    root = (PACKAGE_ROOT / ("business-" + str(int(business_id))) / safe_run).resolve()
    package_root = PACKAGE_ROOT.resolve()
    if not root.is_relative_to(package_root):
        raise PermanentError("prospect package path escaped output root")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _build_remediation(report, workspace):
    from auditor_toolkit.remediation import build_remediation

    try:
        return build_remediation(report, workspace / "remediation")
    except (OSError, ValueError) as exc:
        raise RetryableError("remediation preview failed: " + str(exc)[:240]) from exc


def _build_demo(report, remediation, workspace):
    from auditor_toolkit.demo import build_demo

    report_path = (report.get("artifacts") or {}).get("json")
    try:
        return build_demo(
            report,
            remediation,
            workspace / "demo",
            render=False,
            report_path=report_path,
        )
    except (OSError, ValueError) as exc:
        raise RetryableError("local concept demo failed: " + str(exc)[:240]) from exc


def _verified_contact(d, business_id):
    """Return only the authoritative current VERIFIED_HIGH local contact."""
    view = d.execute(
        "SELECT 1 FROM sqlite_master WHERE type='view' AND name='email_current_high'"
    ).fetchone()
    if not view:
        return None
    row = d.execute(
        "SELECT normalized_email,verification_id FROM email_current_high "
        "WHERE prospect_id=? ORDER BY verification_id DESC LIMIT 1",
        (business_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "email": row["normalized_email"],
        "verification": "VERIFIED_HIGH",
        "verification_id": row["verification_id"],
    }


def _load_manifest(path, kind, run_id):
    path = Path(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise RetryableError("missing/unreadable " + kind + " manifest") from exc
    if not isinstance(value, dict) or value.get("source_run_id") != run_id:
        raise PermanentError(kind + " manifest does not match canonical audit run")
    return value


def _write_review_packet(d, business_id, report, workspace, qa):
    """Write an idempotent local review packet, optionally with deterministic price.

    Pricing is never invented. A commercial quote/draft exists only when the
    operator explicitly provides MM_HOURLY_RATE_NZD in the local process
    environment. No packet is inserted into mm_messages and nothing is sent.
    """
    from auditor_toolkit.common import atomic_write_json, atomic_write_text

    run_id = report["run_id"]
    remediation = _load_manifest(
        workspace / "remediation" / "remediation.json", "remediation", run_id
    )
    demo = _load_manifest(workspace / "demo" / "demo.json", "demo", run_id)
    contact = _verified_contact(d, business_id)

    rate = str(os.environ.get("MM_HOURLY_RATE_NZD") or "").strip()
    quote = None
    commercial_packet = None
    commercial_packet_path = None
    quote_status = "OPERATOR_RATE_REQUIRED"
    draft_status = "NOT_GENERATED_RATE_REQUIRED"

    if rate:
        from auditor_toolkit.packet import build_packet
        from auditor_toolkit.quote import calculate_quote

        try:
            quote = calculate_quote(report, rate)
        except ValueError as exc:
            raise PermanentError(
                "invalid MM_HOURLY_RATE_NZD; operator correction required: "
                + str(exc)[:200]
            ) from exc

        rate_ref = hashlib.sha256(rate.encode("utf-8")).hexdigest()[:12]
        commercial_dir = workspace / ("commercial-packet-" + rate_ref)
        commercial_packet_path = commercial_dir / "packet.json"
        if commercial_packet_path.is_file():
            commercial_packet = _load_manifest(
                commercial_packet_path, "commercial packet", run_id
            )
        else:
            if commercial_dir.exists() and any(commercial_dir.iterdir()):
                raise RetryableError(
                    "partial commercial packet exists; human review required: "
                    + str(commercial_dir)
                )
            commercial_packet = build_packet(
                report,
                remediation,
                demo,
                quote,
                commercial_dir,
                contact=contact,
            )
        atomic_write_json(workspace / "quote.json", quote)
        quote_status = "DETERMINISTIC_QUOTE_READY"
        draft_status = "LOCAL_DRAFT_READY"

    review_dir = workspace / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    packet = {
        "schema_version": 1,
        "kind": "money_machine_review_packet",
        "business_id": int(business_id),
        "source_run_id": run_id,
        "website": report.get("url"),
        "audit": {
            "health_score": report.get("health_score"),
            "defect_score": report.get("severity_score", report.get("defect_score", report.get("score"))),
            "defect_count": len(report.get("defects") or []),
            "report_path": (report.get("artifacts") or {}).get("json"),
        },
        "remediation": {
            "manifest": str(workspace / "remediation" / "remediation.json"),
            "preview_items": len(remediation.get("items") or []),
            "production_changes": remediation.get("production_changes", 0),
        },
        "demo": {
            "manifest": str(workspace / "demo" / "demo.json"),
            "html": demo.get("demo_html"),
            "status": demo.get("status"),
            "live_site_changed": demo.get("live_site_changed"),
            "external_deploy": demo.get("external_deploy"),
        },
        "qa": {
            "score": qa.get("score"),
            "passed": bool(qa.get("passed")),
        },
        "contact": contact,
        "quote_status": quote_status,
        "quote": quote,
        "draft_status": draft_status,
        "commercial_packet": (
            str(commercial_packet_path)
            if commercial_packet is not None else None
        ),
        "human_review_required": True,
        "approval_status": "HUMAN_APPROVAL_REQUIRED",
        "send_enabled": False,
        "external_send_allowed": False,
        "external_sends": 0,
        "model_calls": 0,
        "paid_ai_cost_usd": 0,
    }
    packet_path = review_dir / "packet.json"
    atomic_write_json(packet_path, packet)

    summary = (
        "# Money Machine review packet\n\n"
        + "Audit run: " + str(run_id) + "\n\n"
        + "Website: " + str(report.get("url") or "") + "\n\n"
        + "Demo QA: " + ("PASS" if qa.get("passed") else "FAIL")
        + " (" + str(qa.get("score")) + ")\n\n"
        + "Quote status: **" + quote_status + "**\n\n"
        + "Draft status: **" + draft_status + "**\n\n"
        + "Human review is required. Nothing was sent, no live site was changed, "
        + "and no paid AI call was made.\n"
    )
    atomic_write_text(review_dir / "REVIEW_PACKET.md", summary)
    return packet_path, packet


def preparation_worker_handler(d, item_row, worker):
    """Advance deterministic preparation exactly one declared edge at a time."""
    state = item_row["state"]
    bid = item_row["business_id"]

    if state == "VERIFIED":
        return (
            "REMEDIATION_PENDING",
            "verified prospect ready for deterministic remediation preview",
            {"model_calls": 0, "paid_ai_cost_usd": 0, "external_sends": 0},
        )

    if state == "REMEDIATION_PENDING":
        report = _canonical_report(d, bid)
        workspace = _workspace(bid, report["run_id"])
        remediation = _build_remediation(report, workspace)
        return (
            "DEMO_PENDING",
            "deterministic remediation preview prepared",
            {
                "run_id": report["run_id"],
                "remediation_path": str(workspace / "remediation" / "remediation.json"),
                "preview_items": len(remediation.get("items") or []),
                "production_changes": remediation.get("production_changes", 0),
                "external_dispatch": remediation.get("external_dispatch", False),
                "model_calls": 0,
                "paid_ai_cost_usd": 0,
                "external_sends": 0,
            },
        )

    if state == "DEMO_PENDING":
        report = _canonical_report(d, bid)
        workspace = _workspace(bid, report["run_id"])
        remediation = _build_remediation(report, workspace)
        demo = _build_demo(report, remediation, workspace)
        return (
            "DEMO_READY",
            "local concept demo prepared",
            {
                "run_id": report["run_id"],
                "demo_path": demo["demo_html"],
                "demo_manifest": str(workspace / "demo" / "demo.json"),
                "status": demo.get("status"),
                "local_concept": demo.get("local_concept"),
                "live_site_changed": demo.get("live_site_changed"),
                "external_deploy": demo.get("external_deploy"),
                "model_calls": 0,
                "paid_ai_cost_usd": 0,
                "external_sends": 0,
            },
        )

    if state == "DEMO_READY":
        report = _canonical_report(d, bid)
        workspace = _workspace(bid, report["run_id"])
        demo_path = (workspace / "demo" / "index.html").resolve()
        if not demo_path.is_relative_to(workspace.resolve()):
            raise PermanentError("demo path escaped prospect workspace")
        if not demo_path.is_file() or not demo_path.stat().st_size:
            raise RetryableError("local concept demo artifact missing")

        from mm_operator import demo_qa

        try:
            qa = demo_qa(d, bid, demo_path)
        except (OSError, ValueError) as exc:
            raise RetryableError("demo QA could not complete: " + str(exc)[:240]) from exc

        return (
            "QA_PENDING",
            "deterministic demo QA recorded",
            {
                "run_id": report["run_id"],
                "demo_path": str(demo_path),
                "score": qa.get("score"),
                "passed": qa.get("passed"),
                "model_calls": 0,
                "paid_ai_cost_usd": 0,
                "external_sends": 0,
            },
        )

    if state == "QA_PENDING":
        from mm_workers import qa_handler

        nxt, reason, evidence = qa_handler(d, item_row, worker)
        if nxt != "OUTREACH_PENDING":
            return nxt, reason, evidence

        report = _canonical_report(d, bid)
        workspace = _workspace(bid, report["run_id"])
        qa_row = d.execute(
            "SELECT score,passed FROM mm_demo_qa WHERE business_id=?",
            (bid,),
        ).fetchone()
        qa = {
            "score": qa_row["score"] if qa_row else None,
            "passed": bool(qa_row["passed"]) if qa_row else False,
        }
        packet_path, packet = _write_review_packet(
            d, bid, report, workspace, qa
        )
        enriched = dict(evidence or {})
        enriched.update({
            "review_packet": str(packet_path),
            "quote_status": packet["quote_status"],
            "draft_status": packet["draft_status"],
            "human_review_required": True,
            "external_sends": 0,
            "model_calls": 0,
            "paid_ai_cost_usd": 0,
        })
        return (
            "OUTREACH_PENDING",
            "demo QA passed; local review packet prepared",
            enriched,
        )

    raise PermanentError("unsupported preparation state: " + state)

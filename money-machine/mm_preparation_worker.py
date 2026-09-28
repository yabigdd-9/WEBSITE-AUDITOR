"""Loop C: deterministic remediation, local concept demo, and QA.

This worker is deliberately incapable of deployment or outreach. It consumes
only canonical auditor_toolkit reports already recorded by the audit worker,
writes local preview artifacts under outputs/, and advances one declared
pipeline edge at a time.
"""
from __future__ import annotations

import json
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
        return qa_handler(d, item_row, worker)

    raise PermanentError("unsupported preparation state: " + state)

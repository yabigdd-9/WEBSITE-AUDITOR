#!/usr/bin/env python3
"""
HERMES_ZERO_TOKEN Daily Report Generator
Produces DAILY_REPORT_YYYY-MM-DD.md and daily_metrics.json in
state/hermes_zero_token/reports/ with zero-token attestation.

This reuses existing mm_core/mm_runtime_guards for DB reads and accounting
(snapshots), but produces the plan's required report format locally.
No network calls to hosted services.
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

STATE_DIR = PROJECT_ROOT / "state" / "hermes_zero_token"
REPORTS_DIR = PROJECT_ROOT / "state" / "hermes_zero_token" / "reports"
DB_PATH = PROJECT_ROOT / "database" / "money_machine.db"


# Zero-token env enforcement
os.environ["HERMES_ZERO_TOKEN_MODE"] = "ZERO_LLM"
os.environ["HERMES_ALLOW_HOSTED_LLM"] = "0"
os.environ["HERMES_ALLOW_PAID_FALLBACK"] = "0"
os.environ["WEBSITE_AUDITOR_OUTREACH_SEND"] = "0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def db_query(sql: str, params=tuple()) -> list:
    """Run a read-only query against the production database."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _safe_int(query: str, params=tuple()) -> int | None:
    """Unavailable accounting remains unknown rather than becoming zero."""
    try:
        rows = db_query(query, params)
        return int(rows[0][0]) if rows else 0
    except (sqlite3.Error, ValueError, TypeError):
        return None


def collect_metrics() -> dict[str, Any]:
    """Collect all zero-token attestation metrics from the DB."""
    metrics: dict[str, Any] = {
        "run_mode": "ZERO_LLM",
        "generated_at": _now(),
        "host": os.uname().nodename,
    }

    # --- Business discovery metrics ---
    metrics["discovered_total"] = _safe_int("SELECT count(*) AS c FROM businesses")

    metrics["eligible_unique_new"] = _safe_int(
        "SELECT count(*) AS c FROM businesses "
        "WHERE current_status IN ('audited','scored','qualified') AND is_dummy=0"
    )

    # --- Audit metrics ---
    metrics["audited_total"] = _safe_int("SELECT count(*) AS c FROM audits")
    metrics["evidenced_finding_count"] = _safe_int("SELECT count(*) AS c FROM mm_evidence")

    # --- Scoring / qualification ---
    metrics["qualified_ready_count"] = _safe_int(
        "SELECT count(*) AS c FROM pipeline_items "
        "WHERE state IN ('CONTACT_PENDING','QUALIFIED','REMEDIATION_PENDING',"
        "'DEMO_PENDING','OUTREACH_PENDING','APPROVAL_PENDING')"
    )
    metrics["uncertain_review_count"] = _safe_int(
        "SELECT count(*) AS c FROM pipeline_items WHERE state='NEEDS_REVIEW'"
    )
    metrics["duplicate_candidates_count"] = _safe_int(
        "SELECT count(*) AS c FROM pipeline_items WHERE state='REJECTED'"
    )

    # --- Screenshots ---
    metrics["screenshots_saved"] = _safe_int("SELECT count(*) AS c FROM mm_artifacts")

    # --- Audit log / scripts ---
    audit_log = STATE_DIR / "audit.jsonl"
    scripts_succeeded = 0
    scripts_failed = 0
    if audit_log.exists():
        for line in audit_log.read_text().splitlines():
            try:
                rec = json.loads(line)
                if rec.get("event") == "complete":
                    if rec.get("status") == "completed":
                        scripts_succeeded += 1
                    elif rec.get("status") in ("failed", "error", "timeout", "blocked"):
                        scripts_failed += 1
            except json.JSONDecodeError:
                pass
    metrics["script_counts_scope"] = "cumulative retained audit log"
    metrics["test_counts_scope"] = "worker runs, not individual pytest cases"
    metrics["scripts_succeeded"] = scripts_succeeded
    metrics["scripts_failed"] = scripts_failed

    # --- Tests (from last audit log test_worker runs) ---
    metrics["test_passed"] = 0
    metrics["test_failed"] = 0
    if audit_log.exists():
        for line in reversed(audit_log.read_text().splitlines()):
            try:
                rec = json.loads(line)
                if rec.get("worker_id") in {"testing", "testing_worker"} and rec.get("event") == "complete":
                    if rec.get("status") == "completed":
                        metrics["test_passed"] = metrics.get("test_passed", 0) + 1
                    elif rec.get("status") in ("failed", "error", "timeout", "blocked"):
                        metrics["test_failed"] = metrics.get("test_failed", 0) + 1
            except json.JSONDecodeError:
                pass

    # --- Zero-token attestation (MUST BE ZERO) ---
    metrics["host_model_calls"] = _safe_int(
        "SELECT COALESCE(SUM(model_calls),0) FROM mm_model_invocations"
    )

    metrics["paid_model_calls"] = _safe_int(
        "SELECT count(*) FROM mm_model_invocations WHERE cost_usd > 0 OR provider IS NOT NULL"
    )

    # DB has CHECK(cost_usd=0), so this is provably zero
    metrics["estimated_paid_cost_nzd"] = (0.0 if metrics["paid_model_calls"] == 0 else None)

    metrics["outbound_messages_sent"] = _safe_int(
        "SELECT count(*) FROM mm_messages WHERE sent_at IS NOT NULL OR send_receipt IS NOT NULL"
    )

    metrics["attestation_complete"] = all(metrics[key] is not None for key in (
        "host_model_calls", "paid_model_calls", "outbound_messages_sent"))
    return metrics


def write_daily_report(metrics: dict[str, Any]) -> Path:
    """Write DAILY_REPORT_YYYY-MM-DD.md to state/hermes_zero_token/reports/."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = _now_date()
    report_path = REPORTS_DIR / f"DAILY_REPORT_{date_str}.md"
    metrics_path = REPORTS_DIR / "daily_metrics.json"

    # Write metrics JSON (atomic write: write temp, rename)
    tmp_metrics = metrics_path.with_suffix(".json.tmp")
    tmp_metrics.write_text(json.dumps(metrics, indent=2, default=str))
    os.replace(tmp_metrics, metrics_path)

    # Write human-readable markdown report
    attestation_ok = (
        metrics.get("attestation_complete", False)
        and metrics["host_model_calls"] == 0
        and metrics["paid_model_calls"] == 0
        and metrics["outbound_messages_sent"] == 0
    )
    attestation_str = "✅ PASS — all zero-token counts are zero" if attestation_ok else "❌ FAIL — non-zero or unavailable accounting"

    lines = [
        f"# Daily Report — {date_str}",
        "",
        f"**Generated at:** {metrics['generated_at']}",
        f"**Run mode:** {metrics['run_mode']}",
        f"**Host:** {metrics['host']}",
        "",
        "## Zero-Token Attestation",
        "",
        f"- `host_model_calls` = {metrics['host_model_calls']}",
        f"- `paid_model_calls` = {metrics['paid_model_calls']}",
        f"- `estimated_paid_cost_nzd` = {metrics['estimated_paid_cost_nzd']}",
        f"- `outbound_messages_sent` = {metrics['outbound_messages_sent']}",
        "",
        f"{attestation_str}",
        "",
        "## Discovery and Auditing",
        "",
        f"- `discovered_total` = {metrics['discovered_total']}",
        f"- `eligible_unique_new` = {metrics['eligible_unique_new']}",
        f"- `audited_total` = {metrics['audited_total']}",
        f"- `evidenced_finding_count` = {metrics['evidenced_finding_count']}",
        f"- `screenshots_saved` = {metrics['screenshots_saved']}",
        "",
        "## Scoring and Review",
        "",
        f"- `qualified_ready_count` = {metrics['qualified_ready_count']}",
        f"- `uncertain_review_count` = {metrics['uncertain_review_count']}",
        f"- `duplicate_candidates_count` = {metrics['duplicate_candidates_count']}",
        "",
        "## Worker/Script Health",
        "Counts cover the retained cumulative audit log; tests count worker runs, not pytest cases.",
        "",
        f"- `scripts_succeeded` = {metrics['scripts_succeeded']}",
        f"- `scripts_failed` = {metrics['scripts_failed']}",
        f"- `test_passed` = {metrics['test_passed']}",
        f"- `test_failed` = {metrics['test_failed']}",
        "",
        "## Next Operator Decisions",
        "",
        "1. Review any `scripts_failed > 0` in the audit log (`state/hermes_zero_token/audit.jsonl`).",
        "2. Review `uncertain_review_count` pipeline items.",
        "3. Inspect daily cron runs in `hermes cron history`.",
        "",
    ]
    report_path.write_text("\n".join(lines))
    return report_path


def main() -> int:
    metrics = collect_metrics()
    report_path = write_daily_report(metrics)
    print(json.dumps(metrics, indent=2, default=str))
    print(f"\nReport written to: {report_path}")
    print(f"Metrics written to: {REPORTS_DIR / 'daily_metrics.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

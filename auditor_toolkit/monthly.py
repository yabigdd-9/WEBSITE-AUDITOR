"""Monthly evidence snapshots and RFC 822 email drafts; never sends or schedules."""

from __future__ import annotations

import hashlib
import html
import json
import re
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from email.policy import SMTP
from pathlib import Path
from zoneinfo import ZoneInfo

from .agency_config import get_client, validate_config
from .browser import export_pdf
from .common import atomic_write_json, atomic_write_text
from .comparison import (
    build_comparison,
    build_trend,
    compare_finding_history,
    render_history_svg,
    utc_timestamp,
    verification_evidence,
)
from .revenue import calculate_revenue, roi_csv
from .storage import History

TEMPLATE_VERSION = 3
HISTORY_LIMIT = 1000


def instant(text):
    result = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result


def month_bounds(month, zone):
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise ValueError("Month must be YYYY-MM")
    start = datetime.strptime(month, "%Y-%m").replace(tzinfo=ZoneInfo(zone))
    end = (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )
    previous = (
        start.replace(year=start.year - 1, month=12)
        if start.month == 1
        else start.replace(month=start.month - 1)
    )
    return previous, start, end


def previous_month(zone="Pacific/Auckland", now=None):
    now = now or datetime.now(ZoneInfo(zone))
    previous, _, _ = month_bounds(now.astimezone(ZoneInfo(zone)).strftime("%Y-%m"), zone)
    return previous.strftime("%Y-%m")


def _defects(run):
    records = run.get("defects") if run else None
    return [item for item in records if isinstance(item, dict)] if isinstance(records, list) else []


def _event_time(value):
    # SQLite CURRENT_TIMESTAMP is UTC without an offset. Only this documented
    # event format gets that interpretation; audit timestamps must have offsets.
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d{1,6})?", value):
        value += "+00:00"
    normalized = utc_timestamp(value)
    return instant(normalized) if normalized else None


def _event_utc(value):
    when = _event_time(value)
    return utc_timestamp(when.isoformat()) if when else None


def _reported_score(run):
    value = run.get("health_score") if run and run.get("status") == "complete" else None
    return value if type(value) in {int, float} and 0 <= value <= 100 else None


def _hold_message(reasons):
    labels = {
        "audit_incomplete": "Audit checks are incomplete",
        "health_unavailable_or_invalid": "Reported health is unavailable or invalid",
        "timestamp_unavailable_or_invalid": "The saved observation time is unavailable or invalid",
        "check_provenance_missing": "Checker versions or coverage were not recorded",
        "check_provenance_invalid": "Recorded checker evidence is inconsistent",
        "check_coverage_incomplete": "Required audit coverage is incomplete",
        "coverage_provenance_invalid": "Recorded coverage is inconsistent",
        "measurement_contract_missing_or_invalid": "Audit settings or source evidence are missing or invalid",
        "scoring_provenance_missing": "Scoring rules were not fully recorded",
        "profile_or_schema_missing": "The audit profile or report format is unrecorded",
        "scope_source_or_scoring_mismatch": "Audit scope, source or scoring changed",
        "target_comparison_held": "The earlier audit cannot support a comparison",
        "audit_history_limit_exceeded": "Audit history exceeds the review limit",
        "invalid_saved_observation": "A saved audit observation is inconsistent or invalid",
        "current_or_prior_month_observation_missing": "One of the two months has no audit observation",
        "invalid_comparison_observation": "Saved observations cannot establish a score comparison",
        "invalid_trend_observation": "Saved observations cannot establish a chart",
        "outside_chart_window": "Outside the displayed chart window",
        "history_unavailable": "Valid chart history is unavailable",
    }
    return "; ".join(dict.fromkeys(labels.get(reason, "Measurement evidence is unavailable") for reason in reasons))


def collect_month(history, client, month, zone):
    previous_start, start, end = month_bounds(month, zone)
    # Exact URL/profile selection: a slash variant is not silently equivalent.
    selector = (
        "url=? AND (CASE WHEN json_valid(report) THEN json_extract(report, '$.profile') END=? "
        "OR NOT json_valid(report)) "
        "AND (audit_instant_utc(timestamp)<? OR audit_instant_utc(timestamp) IS NULL)"
    )
    params = (client["url"], client["profile"], utc_timestamp(end.isoformat()))
    event_selector = (
        "kind='remediation' AND CASE WHEN json_valid(payload) "
        "THEN json_extract(payload, '$.verification_run') END IN "
        "(SELECT id FROM runs WHERE url=? AND CASE WHEN json_valid(report) "
        "THEN json_extract(report, '$.profile') END=?) "
        "AND (monthly_event_instant(timestamp) IS NULL OR "
        "(monthly_event_instant(timestamp)>=? AND monthly_event_instant(timestamp)<?))"
    )
    with history.connect() as db:
        db.create_function(
            "monthly_event_instant", 1,
            _event_utc,
            deterministic=True,
        )
        run_count = db.execute("SELECT COUNT(*) FROM runs WHERE " + selector, params).fetchone()[0]
        raw = db.execute(
            "SELECT id,url,timestamp,report FROM runs WHERE " + selector
            + " ORDER BY audit_instant_utc(timestamp) DESC, id DESC LIMIT ?",
            (*params, HISTORY_LIMIT),
        ).fetchall()
        event_params = (client["url"], client["profile"], utc_timestamp(start.isoformat()), utc_timestamp(end.isoformat()))
        event_count = db.execute(
            "SELECT COUNT(*) FROM events WHERE " + event_selector, event_params
        ).fetchone()[0]
        events = db.execute(
            "SELECT id,timestamp,payload FROM events WHERE " + event_selector
            + " ORDER BY id DESC LIMIT ?", (*event_params, HISTORY_LIMIT),
        ).fetchall()
    source_reasons = ["audit_history_limit_exceeded"] if run_count > HISTORY_LIMIT else []
    runs = []
    held_observations = []
    for identity, url, timestamp, payload in raw:
        try:
            run = json.loads(payload)
            when = utc_timestamp(run.get("timestamp")) if isinstance(run, dict) else None
            if (not isinstance(run, dict) or not isinstance(identity, str) or not identity
                    or run.get("run_id") != identity or run.get("url") != url
                    or run.get("profile") != client["profile"] or when is None
                    or when != utc_timestamp(timestamp) or instant(when) >= end):
                raise ValueError("Invalid saved monthly observation")
            runs.append(run)
        except (ValueError, TypeError):
            source_reasons.append("invalid_saved_observation")
            held_observations.append({"run_id": identity, "reason": "invalid_saved_observation"})
    source_reasons = sorted(set(source_reasons))
    runs.sort(key=lambda r: (instant(r["timestamp"]), r["run_id"]))
    current_runs = [r for r in runs if start <= instant(r["timestamp"]) < end]
    prior_runs = [r for r in runs if previous_start <= instant(r["timestamp"]) < start]
    current = current_runs[-1] if current_runs else None
    prior = prior_runs[-1] if prior_runs else None
    by_id = {r["run_id"]: r for r in runs}
    completed = {}
    held_events = []
    for event_id, timestamp, payload in sorted(events):
        when = _event_time(timestamp)
        record = json.loads(payload)
        if not isinstance(record, dict) or record.get("state") != "verified":
            continue
        if when is None:
            held_events.append({"event_id": event_id, "reason": "event_timestamp_invalid"})
            continue
        if not start <= when < end:
            continue
        identity = record.get("id")
        try:
            if not isinstance(identity, str) or not identity:
                raise ValueError("finding_identity_missing")
            verified_run = by_id.get(record.get("verification_run"))
            detection = by_id.get(record.get("detection_run"))
            if not verified_run or not detection:
                raise ValueError("bound_detection_or_verification_unavailable")
            if instant(verified_run["timestamp"]) > when:
                raise ValueError("verification_after_recorded_event")
            binding = verification_evidence(verified_run, [detection], identity)
            if any(record.get(key) != value for key, value in binding.items()):
                raise ValueError("verification_basis_binding_missing_or_mismatched")
            if source_reasons or event_count > HISTORY_LIMIT:
                raise ValueError("source_history_incomplete_or_truncated")
            finding = next(d for d in _defects(detection) if d.get("finding_id") == identity)
            recurrence = compare_finding_history(current, [detection]) if current else None
            completed[identity] = {
                "finding_id": identity,
                "defect": finding.get("defect", "Recorded finding"),
                "verified_at": timestamp,
                "verification_run": record["verification_run"],
                **binding,
                "event_id": event_id,
                "present_again_at_month_end": (
                    identity in recurrence["observed_current"]
                    if recurrence and recurrence["comparison_assessed"] else None
                ),
            }
        except (ValueError, TypeError, KeyError, StopIteration):
            held_events.append({"event_id": event_id, "reason": "verification_evidence_not_established"})
    comparison = {"status": "held", "held_reasons": list(source_reasons), "health_delta": None}
    if current and prior and not source_reasons:
        try:
            pair = build_comparison([prior, current])
            comparison.update(
                status=pair["status"], health_delta=pair["rows"][1]["health_delta_from_target"],
                held_reasons=sorted({reason for row in pair["rows"] for reason in row["held_reasons"]}),
                prior_run_id=prior["run_id"], current_run_id=current["run_id"],
                basis_sha256=pair["rows"][0]["basis_sha256"] if pair["status"] == "comparable" else None,
            )
        except (ValueError, TypeError, KeyError):
            comparison["held_reasons"].append("invalid_comparison_observation")
    elif not current or not prior:
        comparison["held_reasons"].append("current_or_prior_month_observation_missing")
    period_runs = sorted(current_runs + prior_runs, key=lambda r: (instant(r["timestamp"]), r["run_id"]))
    trend_document = None
    if period_runs and not source_reasons:
        try:
            window = period_runs[-100:]
            trend_document = build_trend(window[-1], window[:-1])
            trend_document["monthly_window"] = {"total_observations": len(period_runs), "displayed_observations": len(window)}
        except (ValueError, TypeError, KeyError):
            comparison["held_reasons"].append("invalid_trend_observation")
    points = {row["run_id"]: row for row in trend_document["points"]} if trend_document else {}
    trend = [{
        "run_id": run["run_id"], "timestamp": run["timestamp"], "status": run.get("status"),
        "health_score": points.get(run["run_id"], {}).get("plotted_health"),
        "reported_health": _reported_score(run),
        "held_reasons": points.get(run["run_id"], {}).get("held_reasons", ["outside_chart_window" if trend_document else "history_unavailable"]),
    } for run in period_runs]
    recommendations = (
        sorted(
            _defects(current),
            key=lambda d: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(
                d.get("severity"), 4
            ),
        )
        if current and not source_reasons
        else []
    )
    return {
        "month": month,
        "timezone": zone,
        "client": client,
        "current": current,
        "prior": prior,
        "trend": trend,
        "health_delta": comparison["health_delta"],
        "comparison": comparison,
        "trend_document": trend_document,
        "fixes_verified": list(completed.values()),
        "verification_review": {
            "held_events": held_events, "candidate_events": event_count,
            "truncated": event_count > HISTORY_LIMIT,
            "count_complete": not source_reasons and event_count <= HISTORY_LIMIT and not held_events,
        },
        "history_review": {"selected_rows": run_count, "loaded_rows": len(raw), "limit": HISTORY_LIMIT, "held_reasons": source_reasons, "held_observations": held_observations},
        "recommendations": recommendations,
        "data_status": "invalid_history" if source_reasons else "no_audit" if current is None else current.get("status", "unknown"),
        "source_run_ids": sorted(
            {r["run_id"] for r in current_runs + prior_runs}
            | {d["verification_run"] for d in completed.values()}
            | {d["detection_run"] for d in completed.values()}
        ),
    }


def _display(value):
    if value is None:
        return "Not quantified"
    if isinstance(value, dict) and set(value) == {"low", "high"}:
        return f"{value['low'] or 'N/A'} to {value['high'] or 'N/A'}"
    return str(value)


def render_monthly(data, config, revenue, pdf_status="pending"):
    def e(value):
        return html.escape(str(value), quote=True)

    agency, contact = config["agency"], config["contact"]
    current = data["current"]
    history_held = bool(data["history_review"]["held_reasons"])
    score = _reported_score(current) if not history_held else None
    name = data["client"]["name"]
    summary = (
        f"{name}: {len(_defects(current))} finding records in the latest {data['month']} audit. "
        f"Audit status: {current.get('status', 'unknown')}. {len(data['fixes_verified'])} remediation verifications have matching evidence this month."
        if current
        else f"No audit for {name} in {data['month']}. No current health or financial conclusion is available."
    )
    if history_held:
        summary = "Saved audit history is invalid or exceeds the review limit. Current findings and monthly conclusions require review."
    risk = revenue["revenue_at_risk_nzd_monthly"]
    risk_label = f"NZD {risk['low']}–{risk['high']}/month" if risk else "Not quantified"
    logo = (
        f'<img class="logo" alt="{e(agency["name"])} logo" src="{agency["logo_data"]}">'
        if agency.get("logo_data")
        else ""
    )
    trend_rows = "".join(
        f"<tr><td>{e(r['timestamp'])}</td><td>{e(r['status'])}</td><td>{e(_display(r['reported_health']))}</td><td>{e(_hold_message(r['held_reasons']) or 'Matching recorded basis')}</td></tr>"
        for r in data["trend"]
    )
    fixes = "".join(
        f"<li>{e(d['defect'])} — verified {e(d['verified_at'])}; evidence {e(d['verification_run'])}"
        + ("; observed again by month end" if d["present_again_at_month_end"] is True
           else "; month-end recurrence not assessed" if d["present_again_at_month_end"] is None else "")
        + "</li>"
        for d in data["fixes_verified"]
    )
    recommendations = "".join(
        f"<tr><td>{e(d.get('severity', 'review'))}</td><td>{e(d.get('defect', 'Recorded finding'))}</td><td>{e(d.get('remediation_action') or 'Review evidence, prepare a local fix preview, then re-audit.')}</td></tr>"
        for d in data["recommendations"]
    )
    financial_rows = "".join(
        "<tr><td>"
        + e(row["defect"])
        + "</td><td>"
        + e(_display(row["risk_nzd_monthly"]))
        + "</td><td>"
        + e(_display(row["fix_cost_nzd"]))
        + "</td></tr>"
        for row in revenue["rows"]
    )
    checks = current.get("checks", {}) if current and not history_held else {}
    checks = checks if isinstance(checks, dict) else {}
    compliance = [
        {"check": key, **checks[key]}
        for key in ("axe", "accessibility_static", "ux", "headers", "tls")
        if isinstance(checks.get(key), dict)
    ]
    assumption_labels = {
        "monthly_visitors": "Monthly visitors",
        "baseline_conversion_rate": "Baseline conversion rate (without modeled defects)",
        "value_per_conversion_nzd": "Expected value per conversion (NZD)",
        "contribution_margin": "Contribution margin",
        "hourly_rate_nzd": "Hourly rate (NZD)",
        "horizon_months": "Planning horizon (months)",
    }
    inputs_html = "".join(
        "<tr><td>"
        + e(label)
        + "</td><td>"
        + e(_display(revenue["assumptions"].get(key)))
        + "</td></tr>"
        for key, label in assumption_labels.items()
    )
    sources_html = "".join(
        "<li><strong>"
        + e(row["defect"])
        + "</strong>: relative conversion loss "
        + e(_display(row["assumptions"]["relative_conversion_loss"]))
        + "; recovery fraction "
        + e(_display(row["assumptions"].get("recovery_fraction", {"low": 0, "high": 1})))
        + ". Source: "
        + e(row["assumptions"]["source"])
        + ". Rationale: "
        + e(row["assumptions"]["rationale"])
        + ". Reviewed by "
        + e(row["assumptions"]["reviewed_by"])
        + ".</li>"
        for row in revenue["rows"]
        if row["status"] == "scenario"
    )
    chart = render_history_svg(data["trend_document"]) if data["trend_document"] else ""
    comparison_note = (
        _hold_message(data["comparison"]["held_reasons"])
        if data["comparison"]["status"] == "held" else "Matching recorded measurement basis"
    )
    window = data["trend_document"]["monthly_window"] if data["trend_document"] else None
    chart_note = (
        f"Chart shows the latest {window['displayed_observations']} of {window['total_observations']} observations in these two months."
        if window else "No chart with established measurement provenance is available."
    )
    held_count = len(data["verification_review"]["held_events"])
    verification_note = f"{held_count} recorded verification events have held evidence and are excluded from verified counts."
    if data["verification_review"]["truncated"]:
        verification_note += " Event history exceeds the review limit; all verification counts are held."
    compliance_html = "".join(
        "<li>"
        + e(c["check"])
        + ": "
        + e(c.get("status", "unknown"))
        + " - "
        + e(c.get("reason", "Review the detailed audit evidence."))
        + "</li>"
        for c in compliance
    )
    payback = revenue["payback_months"]
    payback_text = (
        (
            "Low-benefit scenario: "
            + _display(payback["low"])
            + "; high-benefit scenario: "
            + _display(payback["high"])
        )
        if payback
        else "Not quantified"
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(name)} — {e(data["month"])} monthly report</title><style>
@page {{ size:A4; margin:16mm; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,Arial,sans-serif; color:#183040; line-height:1.55; max-width:960px; margin:30px auto; padding:0 20px; }}
header {{ padding:25px; background:{agency["secondary_color"]}; color:white; border-top:8px solid {agency["primary_color"]}; }}
h1 {{ font-size:28px; }} h2 {{ color:{agency["primary_color"]}; margin-top:30px; }}
.kpi {{ display:inline-block; padding:16px; margin:14px 12px 0 0; background:#edf5f4; }}
table {{ width:100%; border-collapse:collapse; }} th,td {{ border-bottom:1px solid #cbd5df; text-align:left; padding:8px; vertical-align:top; overflow-wrap:anywhere; }}
svg {{ width:100%; height:auto; }}
tr,li {{ break-inside:avoid; }} thead {{ display:table-header-group; }} pre {{ white-space:pre-wrap; overflow-wrap:anywhere; font-size:11px; }}
.logo {{ max-width:180px; max-height:70px; }} footer {{ border-top:1px solid #cbd5df; margin-top:24px; font-size:12px; }}
@media print {{ body {{ margin:0; padding:0; }} .new-page {{ break-before:page; }} }}
</style></head><body><header>{logo}<p>{e(agency["name"])}</p><h1>Monthly website report</h1><p>{e(name)} · {e(data["month"])} · {e(data["timezone"])}</p><p>{e(data["client"]["url"])}</p></header>
<h2>Executive summary</h2><p>{e(summary)}</p><div class="kpi">Reported health: {e(_display(score))}</div><div class="kpi">Scenario revenue at risk: {e(risk_label)}</div>
<p>Month-over-month reported health change: {e(_display(data["health_delta"]))}. {e(comparison_note)}.</p>
<p>Comparisons require complete checks and matching recorded URL, profile, source, scope and scoring. Matching records do not establish identical lab or field conditions.</p>
<h2>Score trend</h2><p>{e(chart_note)} Held observations break the line.</p>{chart}<table><thead><tr><th>Observation</th><th>Audit status</th><th>Reported health</th><th>Comparison evidence</th></tr></thead><tbody>{trend_rows or '<tr><td colspan="4">No audits in these months.</td></tr>'}</tbody></table>
<h2 class="new-page">Revenue at risk — scenario, not measurement</h2><p>{e(revenue["disclaimer"])}</p><p>{e(revenue["aggregation"])}</p>
<table><thead><tr><th>Defect</th><th>Modeled NZD/month range</th><th>Modeled fix cost range</th></tr></thead><tbody>{financial_rows or '<tr><td colspan="3">No quantified defects.</td></tr>'}</tbody></table>
<p>Potential monthly recovery: {e(_display(revenue["potential_recovery_nzd_monthly"]))}. Fix costs for modeled items: {e(_display(revenue["fix_cost_nzd"]))}.</p>
<p>Profit-based ROI over {e(revenue["horizon_months"])} months: {e(_display(revenue["profit_roi_percent"]))}%. Payback months by low/high benefit scenario: {e(payback_text)}.</p>
<h3>Inputs and provenance</h3><table><tbody>{inputs_html}</tbody></table><ul>{sources_html}</ul>
<p>Unquantified defect types: {e(", ".join(revenue["unquantified_defect_keys"]) or "None")}. Coverage: {e(revenue["coverage"].replace("_", " "))}.</p>
<h2 class="new-page">Recorded fix verifications this month</h2><p>Only recorded verification events with a matching earlier detection and complete later verification audit count. This does not establish who performed the work.</p><p>{e(verification_note)}</p><ul>{fixes or "<li>No remediation verifications with established evidence this month.</li>"}</ul>
<h2>Fixes recommended next month</h2><table><thead><tr><th>Severity</th><th>Finding</th><th>Next action</th></tr></thead><tbody>{recommendations or '<tr><td colspan="3">No current recommendations available.</td></tr>'}</tbody></table>
<h2>Compliance review status</h2><p>Not assessed as a legal or WCAG conformance determination. These are automated check execution results; manual and jurisdiction-specific review is still required.</p><ul>{compliance_html or "<li>No relevant automated check results recorded for this period.</li>"}</ul>
<h3>Evidence lineage</h3><p>{e(", ".join(data["source_run_ids"]) or "No audit evidence in this period.")}</p><p>PDF status: {e(pdf_status)}. Delivery: unsent draft; no scheduler enabled.</p>
<footer>{e(agency.get("footer", "Prepared for review"))}<br>{e(contact.get("email", ""))} {e(contact.get("phone", ""))}<br>{e(contact.get("website", ""))} {e(contact.get("address", ""))}</footer></body></html>"""


def draft_email(config, client, month, attachment=None):
    message = EmailMessage(policy=SMTP)
    message["Subject"] = f"{month} website report — {client['name']}"
    if config["contact"].get("email"):
        message["From"] = config["contact"]["email"]
    if client.get("email"):
        message["To"] = client["email"]
    message["X-Unsent"] = "1"
    message.set_content(
        f"Kia ora {client['name']},\n\nYour {month} website report is attached. "
        "It records audit findings, verified work and priorities for next month. "
        "Any financial figures are scenarios based on the disclosed assumptions, not measured losses.\n\n"
        f"Ngā mihi,\n{config['agency']['name']}\n"
    )
    if attachment:
        path = Path(attachment)
        subtype = "pdf" if path.suffix == ".pdf" else "html"
        message.add_attachment(
            path.read_bytes(),
            maintype="application" if subtype == "pdf" else "text",
            subtype=subtype,
            filename=path.name,
        )
    return message.as_bytes()


class MonthlyStore:
    def __init__(self, root):
        self.history = History(root)
        self.root = self.history.root / "monthly"
        with self.history.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS monthly_reports(id TEXT PRIMARY KEY, content_key TEXT, client_id TEXT, month TEXT, report TEXT)"
            )

    def list(self, client_id=None):
        with self.history.connect() as db:
            rows = db.execute(
                "SELECT report FROM monthly_reports WHERE (? IS NULL OR client_id=?) ORDER BY rowid DESC",
                (client_id, client_id),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def get(self, identity):
        with self.history.connect() as db:
            row = db.execute(
                "SELECT report FROM monthly_reports WHERE id=?", (identity,)
            ).fetchone()
        if row is None:
            raise KeyError(identity)
        return json.loads(row[0])

    def artifact(self, identity, kind):
        report = self.get(identity)
        item = report["manifest"][kind]
        path = Path(item["path"]).resolve()
        if not path.is_relative_to(self.root / identity) or not path.is_file():
            raise ValueError("Unregistered monthly artifact")
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("Monthly artifact integrity mismatch")
        return path


def generate_monthly(root, config, client_id, month=None, pdf=True, policy=None):
    from website_auditor.actions.policy import PolicyEngine
    from website_auditor.models import Action, Risk

    config = validate_config(config)
    client = get_client(config, client_id)
    month = month or previous_month(config["timezone"])
    month_bounds(month, config["timezone"])
    store = MonthlyStore(root)
    data = collect_month(store.history, client, month, config["timezone"])
    usable_current = data["current"] if not data["history_review"]["held_reasons"] else None
    current = usable_current or {
        "run_id": None,
        "url": client["url"],
        "defects": [],
        "status": "no_audit",
    }
    revenue = calculate_revenue(current, client.get("revenue"))
    if usable_current is None:
        revenue.update(
            status="unquantified",
            revenue_at_risk_nzd_monthly=None,
            potential_recovery_nzd_monthly=None,
            modeled_risk_percent=None,
            coverage="invalid_history" if data["history_review"]["held_reasons"] else "no_audit",
        )
    source = {
        "data": data,
        "agency": config["agency"],
        "contact": config["contact"],
        "pdf": pdf,
        "template_version": TEMPLATE_VERSION,
    }
    content_key = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
    action = Action(
        action_id="monthly-" + content_key[:24],
        name="Generate monthly report draft",
        category="reporting",
        risk=Risk.LOW,
        connector="local",
        domain=client["url"],
        environment="local",
        requires_authorization=False,
        payload={"client_id": client_id, "month": month},
        idempotency_key=content_key,
    )
    decision = (policy or PolicyEngine()).evaluate(
        action, paused=(store.root / "CANCELLED").exists()
    )
    if not config["reporting"]["enabled"] or not decision.allowed:
        return {
            "status": "blocked",
            "reason": "Monthly reporting disabled in agency config" if not config["reporting"]["enabled"] else decision.reason,
            "client_id": client_id,
            "month": month,
        }
    for old in store.list(client_id):
        if old["content_key"] == content_key and old["artifact_status"] == "ready":
            try:
                for kind in old["manifest"]:
                    store.artifact(old["id"], kind)
                return old
            except (KeyError, ValueError, OSError):
                pass
    identity = content_key[:24] + "-" + uuid.uuid4().hex[:8]
    directory = store.root / identity
    directory.mkdir(parents=True, exist_ok=False)
    html_path = directory / "monthly-report.html"
    atomic_write_text(
        html_path, render_monthly(data, config, revenue, "ok" if pdf else "not_requested")
    )
    pdf_path = directory / "monthly-report.pdf"
    pdf_error = None
    if pdf:
        try:
            export_pdf(html_path, pdf_path)
            if not pdf_path.is_file() or not pdf_path.read_bytes().startswith(b"%PDF"):
                raise ValueError("PDF export did not produce a valid PDF header")
        except Exception as exc:
            pdf_error = f"{type(exc).__name__}: {exc}"[:1000]
    pdf_status = "error" if pdf_error else "ok" if pdf else "not_requested"
    atomic_write_text(html_path, render_monthly(data, config, revenue, pdf_status))
    artifacts = {"html": html_path}
    if pdf and not pdf_error:
        artifacts["pdf"] = pdf_path
    atomic_write_json(directory / "revenue.json", revenue)
    atomic_write_text(directory / "roi.csv", roi_csv(revenue))
    artifacts.update(revenue=directory / "revenue.json", roi=directory / "roi.csv")
    email = draft_email(config, client, month, artifacts.get("pdf", html_path))
    from .common import atomic_write_bytes

    atomic_write_bytes(directory / "email.eml", email)
    artifacts["email"] = directory / "email.eml"
    atomic_write_json(
        directory / "action-preview.json",
        {
            "action": action.to_dict(),
            "decision": decision.to_dict(),
            "status": "draft_created",
            "external_dispatch": False,
        },
    )
    artifacts["action"] = directory / "action-preview.json"
    result = {
        "schema_version": 1,
        "template_version": TEMPLATE_VERSION,
        "id": identity,
        "content_key": content_key,
        "client_id": client_id,
        "month": month,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "artifact_status": "partial" if pdf_error else "ready",
        "data_status": data["data_status"],
        "status": "partial" if pdf_error or data["data_status"] != "complete" else "ready",
        "pdf": {"status": pdf_status, "reason": pdf_error},
        "delivery": {"status": "draft", "sent": False},
        "source_run_ids": data["source_run_ids"],
        "health_delta": data["health_delta"],
        "comparison": data["comparison"],
        "trend_document": data["trend_document"],
        "fixes_verified": data["fixes_verified"],
        "verification_review": data["verification_review"],
        "history_review": data["history_review"],
        "revenue": revenue,
        "artifacts": {k: str(p) for k, p in artifacts.items()},
    }
    atomic_write_json(directory / "monthly-report.json", result)
    artifacts["json"] = directory / "monthly-report.json"
    result["artifacts"]["json"] = str(artifacts["json"])
    result["manifest"] = {
        k: {
            "path": str(p),
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "size": p.stat().st_size,
        }
        for k, p in artifacts.items()
    }
    atomic_write_json(directory / "manifest.json", result["manifest"])
    with store.history.connect() as db:
        db.execute(
            "INSERT INTO monthly_reports VALUES(?,?,?,?,?)",
            (identity, content_key, client_id, month, json.dumps(result)),
        )
        db.execute(
            "INSERT INTO events(kind,payload) VALUES(?,?)",
            (
                "monthly_draft",
                json.dumps(
                    {
                        "id": identity,
                        "client_id": client_id,
                        "month": month,
                        "status": result["status"],
                    }
                ),
            ),
        )
    return result


def due_monthly(root, config, now=None):
    """Watchdog hook: local draft jobs only, no scheduler or connector activation."""
    zone = config["timezone"]
    now = now or datetime.now(ZoneInfo(zone))
    local = now.astimezone(ZoneInfo(zone))
    if not config["reporting"]["enabled"] or (Path(root) / "monthly/CANCELLED").exists():
        return []
    if local.day != 1:
        return []
    month = previous_month(zone, local)
    existing = MonthlyStore(root).list()
    return [
        {"client_id": c["id"], "month": month, "mode": "draft", "operation": "monthly_report"}
        for c in config["clients"]
        if not any(
            r["client_id"] == c["id"] and r["month"] == month and r["artifact_status"] == "ready"
            for r in existing
        )
    ]

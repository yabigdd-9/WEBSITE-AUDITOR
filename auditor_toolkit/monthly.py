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
from .revenue import calculate_revenue, roi_csv
from .storage import History

TEMPLATE_VERSION = 2


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


def collect_month(history, client, month, zone):
    previous_start, start, end = month_bounds(month, zone)
    with history.connect() as db:
        alias = client["url"].rstrip("/") if client["url"].endswith("/") else client["url"]
        raw = db.execute(
            "SELECT report FROM runs WHERE url IN (?,?)", (client["url"], alias)
        ).fetchall()
        events = db.execute(
            "SELECT timestamp,payload FROM events WHERE kind='remediation' ORDER BY id"
        ).fetchall()
    runs = [json.loads(row[0]) for row in raw]
    # Never combine one client's subdomains/paths or switch profiles silently.
    runs = sorted(
        [r for r in runs if r.get("profile") == client["profile"]],
        key=lambda r: instant(r["timestamp"]),
    )
    current_runs = [r for r in runs if start <= instant(r["timestamp"]) < end]
    prior_runs = [r for r in runs if previous_start <= instant(r["timestamp"]) < start]
    current = current_runs[-1] if current_runs else None
    prior = prior_runs[-1] if prior_runs else None
    known_findings = {
        d["finding_id"]: d for r in runs if instant(r["timestamp"]) < end for d in r["defects"]
    }
    selected_ids = {r["run_id"] for r in runs}
    completed = {}
    for timestamp, payload in events:
        record = json.loads(payload)
        if start <= instant(timestamp) < end and record.get("state") == "verified":
            identity = record.get("id")
            if identity not in known_findings or record.get("verification_run") not in selected_ids:
                continue
            verified_run = next(r for r in runs if r["run_id"] == record["verification_run"])
            if (
                verified_run["status"] != "complete"
                or instant(verified_run["timestamp"]) >= end
                or instant(verified_run["timestamp"]) > instant(timestamp)
            ):
                continue
            if any(d["finding_id"] == identity for d in verified_run["defects"]):
                continue
            completed[identity] = {
                "finding_id": identity,
                "defect": known_findings[identity]["defect"],
                "verified_at": timestamp,
                "verification_run": record["verification_run"],
                "present_again_at_month_end": bool(
                    current and any(d["finding_id"] == identity for d in current["defects"])
                ),
            }
    trend = []
    for run in current_runs + prior_runs:
        trend.append(
            {
                "run_id": run["run_id"],
                "timestamp": run["timestamp"],
                "status": run["status"],
                "health_score": run.get("health_score") if run["status"] == "complete" else None,
            }
        )
    trend.sort(key=lambda r: instant(r["timestamp"]))
    valid_comparison = all(
        r and r["status"] == "complete" and r.get("health_score") is not None
        for r in (current, prior)
    )
    delta = current["health_score"] - prior["health_score"] if valid_comparison else None
    recommendations = (
        sorted(
            current["defects"],
            key=lambda d: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(
                d.get("severity"), 4
            ),
        )
        if current
        else []
    )
    return {
        "month": month,
        "timezone": zone,
        "client": client,
        "current": current,
        "prior": prior,
        "trend": trend,
        "health_delta": delta,
        "fixes_verified": list(completed.values()),
        "recommendations": recommendations,
        "data_status": "no_audit" if current is None else current["status"],
        "source_run_ids": sorted(
            {r["run_id"] for r in current_runs + prior_runs}
            | {d["verification_run"] for d in completed.values()}
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
    score = current.get("health_score") if current and current["status"] == "complete" else None
    name = data["client"]["name"]
    summary = (
        f"{name}: {len(current['defects'])} findings recorded in the latest {data['month']} audit. "
        f"Audit status: {current['status']}. {len(data['fixes_verified'])} remediation verifications recorded this month."
        if current
        else f"No audit for {name} in {data['month']}. No current health or financial conclusion is available."
    )
    risk = revenue["revenue_at_risk_nzd_monthly"]
    risk_label = f"NZD {risk['low']}–{risk['high']}/month" if risk else "Not quantified"
    logo = (
        f'<img class="logo" alt="{e(agency["name"])} logo" src="{agency["logo_data"]}">'
        if agency.get("logo_data")
        else ""
    )
    trend_rows = "".join(
        f"<tr><td>{e(r['timestamp'])}</td><td>{e(r['status'])}</td><td>{e(_display(r['health_score']))}</td></tr>"
        for r in data["trend"]
    )
    fixes = "".join(
        f"<li>{e(d['defect'])} — verified {e(d['verified_at'])}; evidence {e(d['verification_run'])}"
        + ("; observed again by month end" if d["present_again_at_month_end"] else "")
        + "</li>"
        for d in data["fixes_verified"]
    )
    recommendations = "".join(
        f"<tr><td>{e(d.get('severity', 'review'))}</td><td>{e(d['defect'])}</td><td>{e(d.get('remediation_action') or 'Review evidence, prepare a local fix preview, then re-audit.')}</td></tr>"
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
    checks = current.get("checks", {}) if current else {}
    compliance = [
        {"check": key, **checks[key]}
        for key in ("axe", "accessibility_static", "ux", "headers", "tls")
        if key in checks
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
    points = []
    marks = []
    for i, run in enumerate(data["trend"]):
        x = 35 + i * 530 / max(1, len(data["trend"]) - 1)
        value = run["health_score"]
        if value is None:
            points.append(None)
            continue
        y = 95 - max(0, min(100, value)) * 0.65
        points.append((x, y))
        marks.append(
            f'<circle cx="{x}" cy="{y}" r="4" fill="#0f766e"/><text x="{x}" y="{y - 10}" text-anchor="middle" font-size="12">{e(value)}</text>'
        )
    for a, b in zip(points, points[1:]):
        if a is not None and b is not None:
            marks.append(
                f'<line x1="{a[0]}" y1="{a[1]}" x2="{b[0]}" y2="{b[1]}" stroke="#0f766e" stroke-width="2"/>'
            )
    chart = (
        '<svg role="img" aria-label="Health trend; table provides exact dates and values" viewBox="0 0 600 115" style="width:100%;max-height:110px"><title>Health trend, 0 to 100; missing checks have no plotted score</title><line x1="30" y1="95" x2="570" y2="95" stroke="#cbd5df"/>'
        + "".join(marks)
        + "</svg>"
        if marks
        else ""
    )
    compliance_html = "".join(
        "<li>"
        + e(c["check"])
        + ": "
        + e(c["status"])
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
tr,li {{ break-inside:avoid; }} thead {{ display:table-header-group; }} pre {{ white-space:pre-wrap; overflow-wrap:anywhere; font-size:11px; }}
.logo {{ max-width:180px; max-height:70px; }} footer {{ border-top:1px solid #cbd5df; margin-top:24px; font-size:12px; }}
@media print {{ body {{ margin:0; padding:0; }} .new-page {{ break-before:page; }} }}
</style></head><body><header>{logo}<p>{e(agency["name"])}</p><h1>Monthly website report</h1><p>{e(name)} · {e(data["month"])} · {e(data["timezone"])}</p><p>{e(data["client"]["url"])}</p></header>
<h2>Executive summary</h2><p>{e(summary)}</p><div class="kpi">Health: {e(_display(score))}</div><div class="kpi">Scenario revenue at risk: {e(risk_label)}</div>
<p>Month-over-month health change: {e(_display(data["health_delta"]))}. Comparisons require complete audits for both months using the same profile.</p>
<h2>Score trend</h2>{chart}<table><thead><tr><th>Observation</th><th>Status</th><th>Health</th></tr></thead><tbody>{trend_rows or '<tr><td colspan="3">No comparable audits in these months.</td></tr>'}</tbody></table>
<h2 class="new-page">Revenue at risk — scenario, not measurement</h2><p>{e(revenue["disclaimer"])}</p><p>{e(revenue["aggregation"])}</p>
<table><thead><tr><th>Defect</th><th>Modeled NZD/month range</th><th>Modeled fix cost range</th></tr></thead><tbody>{financial_rows or '<tr><td colspan="3">No quantified defects.</td></tr>'}</tbody></table>
<p>Potential monthly recovery: {e(_display(revenue["potential_recovery_nzd_monthly"]))}. Fix costs for modeled items: {e(_display(revenue["fix_cost_nzd"]))}.</p>
<p>Profit-based ROI over {e(revenue["horizon_months"])} months: {e(_display(revenue["profit_roi_percent"]))}%. Payback months by low/high benefit scenario: {e(payback_text)}.</p>
<h3>Inputs and provenance</h3><table><tbody>{inputs_html}</tbody></table><ul>{sources_html}</ul>
<p>Unquantified defect types: {e(", ".join(revenue["unquantified_defect_keys"]) or "None")}. Coverage: {e(revenue["coverage"].replace("_", " "))}.</p>
<h2 class="new-page">Fixes completed this month</h2><p>Only recorded verification events count as completed; disappearance alone does not prove agency work.</p><ul>{fixes or "<li>No verified remediation events recorded this month.</li>"}</ul>
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
    current = data["current"] or {
        "run_id": None,
        "url": client["url"],
        "defects": [],
        "status": "no_audit",
    }
    revenue = calculate_revenue(current, client.get("revenue"))
    if data["current"] is None:
        revenue.update(
            status="unquantified",
            revenue_at_risk_nzd_monthly=None,
            potential_recovery_nzd_monthly=None,
            modeled_risk_percent=None,
            coverage="no_audit",
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
        "fixes_verified": data["fixes_verified"],
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

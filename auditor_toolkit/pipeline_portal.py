"""Authenticated owner views with bounded, version-checked decisions."""

import html
import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from enum import StrEnum
from urllib.parse import parse_qs, urlencode

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from scripts.approval_controls import approve_proposal
from scripts.client_projects import accept_proposal, complete
from scripts.cloud_opportunities import reject_recommendation
from scripts.cloud_prospect_pipeline import metrics

PRE_OPEN = "<pre>"
PRE_CLOSE = "</pre>"


class DecisionAction(StrEnum):
    ACCEPT = "accept"
    COMPLETE = "complete"
    APPROVE = "approve"
    REJECT = "reject"


class PipelineViews:
    def __init__(self, store, session, csrf):
        self.store = store
        self.session = session
        self.csrf = csrf
        self.writes = {}

    def state(self):
        try:
            result = self.store.read()
            if result is None:
                raise ValueError("Uninitialized")
            return result
        except (ValueError, sqlite3.Error, OSError):
            raise HTTPException(503, "Pipeline records temporarily unavailable") from None

    def prospect(self, identity, document):
        if not re.fullmatch("[0-9a-f]{64}", identity) or identity not in document["prospects"]:
            raise HTTPException(404, "Prospect unavailable")
        return document["prospects"][identity]

    def escaped(self, value):
        return html.escape(str(value), quote=True)

    def page(self, title, body):
        return f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{self.escaped(title)} · MoneyMachine</title><style>body{{font:16px system-ui;margin:0;background:#f6f7f9;color:#192737}}main{{max-width:1100px;margin:auto;padding:24px}}nav{{display:flex;gap:20px;flex-wrap:wrap}}a{{color:#125c87}}table{{width:100%;border-collapse:collapse;background:white}}td,th{{text-align:left;padding:12px;border-bottom:1px solid #ddd}}.scroll{{overflow:auto}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px}}article{{padding:16px;background:white;border:1px solid #ddd;border-radius:8px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:white;padding:16px}}input,textarea,button{{font:inherit;padding:8px;max-width:100%;box-sizing:border-box}}label{{display:block;margin:12px 0}}textarea{{width:100%}}button{{cursor:pointer}}</style><main><nav><a href="/pipeline">Overview</a><a href="/pipeline/prospects">Prospects</a><a href="/pipeline/discovery">Discovery</a><a href="/pipeline/outreach">Outreach review</a><a href="/pipeline/projects">Projects</a><a href="/pipeline/health">System health</a><a href="/">Audit history</a></nav><h1>{self.escaped(title)}</h1>{body}</main></html>'

    def overview(self, request: Request):
        self.session(request)
        document = self.state()
        report = metrics(document)
        labels = {
            "prospects_found": "Reviewed prospects",
            "audits_succeeded": "Completed audits",
            "audits_failed": "Failed audits",
            "qualified_opportunities": "Internal opportunities",
            "proposal_reviews_pending": "Proposals awaiting review",
            "approvals_pending": "Scope reviews pending",
            "contacts_sent": "Owner-recorded provider acceptances",
            "active_projects": "Active projects",
        }
        cards = "".join(
            (
                f"<article><strong>{report[key]}</strong><br>{label}</article>"
                for key, label in labels.items()
            )
        )
        return self.page(
            "Pipeline overview",
            '<div class="cards">'
            + cards
            + f"</div><p>Sending is disabled. Pricing requires configured rates and scope.</p><p>Discovery candidates: {len(document.get('discovery_candidates', {}))}</p>",
        )

    def prospects(self, request: Request, q: str = "", status: str = "", offset: int = 0):
        self.session(request)
        if len(q) > 253 or len(status) > 40 or offset < 0:
            raise HTTPException(400, "Invalid search")
        records = [
            (identity, p)
            for identity, p in sorted(
                self.state()["prospects"].items(), key=lambda pair: pair[1]["domain"]
            )
            if (not status or p["status"] == status)
            and (
                q.casefold() in p["domain"].casefold()
                or q.casefold() in p.get("discovery", {}).get("business_name", "").casefold()
            )
        ]
        rows = (
            "".join(
                (
                    f"""<tr><td><a href="/pipeline/prospects/{identity}">{self.escaped(p["domain"])}</a></td><td>{self.escaped(p["status"])}</td><td>{self.escaped(p.get("opportunity", {}).get("score", "Unscored"))}</td></tr>"""
                    for identity, p in records[offset : offset + 25]
                )
            )
            or '<tr><td colspan="3">No matching prospects.</td></tr>'
        )
        navigation = ""
        for label, index in (("Previous", offset - 25), ("Next", offset + 25)):
            if 0 <= index < len(records):
                url = "/pipeline/prospects?" + urlencode(
                    {"q": q, "status": status, "offset": index}
                )
                navigation += f'<p><a href="{self.escaped(url)}">{label}</a></p>'
        return self.page(
            "Prospects",
            f'<form><label>Search business or domain <input name="q" value="{self.escaped(q)}"></label><label>Status <input name="status" value="{self.escaped(status)}"></label><button>Search</button></form><div class="scroll"><table><tr><th>Website</th><th>Audit state</th><th>Review score</th></tr>'
            + rows
            + "</table></div>"
            + navigation,
        )

    def detail(self, identity: str, request: Request):
        _, value = self.session(request)
        p = self.prospect(identity, self.state())
        identity = html.escape(identity, quote=True)
        form = ""
        if p.get("proposal_version"):
            form = f'''<form method="post" action="/pipeline/prospects/{identity}/reject"><input type="hidden" name="csrf" value="{value["csrf"]}"><input type="hidden" name="version" value="{p["proposal_version"]}"><label>Reason for rejection<textarea name="reason" maxlength="1000" required></textarea></label><button formaction="/pipeline/prospects/{identity}/approve">Approve internal proposal</button> <button>Reject recommendation</button></form>'''
            decisions = [a for a in p.get("approvals", []) if a["action_type"] == "proposal"]
            if (
                decisions
                and decisions[-1]["decision"] == "approved"
                and (decisions[-1]["version_sha256"] == p["proposal_version"])
            ):
                form += f'''<form method="post" action="/pipeline/prospects/{identity}/accept"><input type="hidden" name="csrf" value="{value["csrf"]}"><input type="hidden" name="version" value="{p["proposal_version"]}"><h2>Record customer acceptance</h2><label>Acceptance evidence SHA-256 <input name="acceptance_evidence" pattern="[0-9a-f]{{64}}" required></label><label>Acceptance note<textarea name="reason" maxlength="1000" required></textarea></label><label><input type="checkbox" name="owner_verified" value="true" required> I verified the customer accepted this exact proposal version.</label><button>Create project record</button></form>'''
        return self.page(
            p["domain"],
            "<p>Internal review only. Detailed encrypted report archives are not decrypted here.</p><p>Archive retrieval is available only after an artifact reference is registered.</p>"
            + form
            + PRE_OPEN
            + self.escaped(json.dumps(p, indent=2))
            + PRE_CLOSE,
        )

    def discovered(self, request: Request, offset: int = 0):
        self.session(request)
        if offset < 0:
            raise HTTPException(400, "Invalid page")
        candidates = sorted(
            self.state().get("discovery_candidates", {}).values(), key=lambda c: c["domain"]
        )
        return self.page(
            "Discovery review",
            "<p>Imported candidates require independent eligibility review before auditing.</p>"
            + PRE_OPEN
            + self.escaped(json.dumps(candidates[offset : offset + 25], indent=2))
            + PRE_CLOSE,
        )

    def health(self, request: Request):
        self.session(request)
        document = self.state()
        today = datetime.now(timezone.utc).isoformat()[:10]
        report = {
            "daily_hard_cap": 6,
            "attempts_recorded_today": sum(
                (
                    e.get("action") == "audit" and e.get("timestamp_utc", "").startswith(today)
                    for e in document["events"]
                )
            ),
            "paid_api_calls": 0,
            "automatic_sending": "disabled",
            "storage": "private SQLite",
            "hosted_storage": "not verified",
            "free_tier_remaining": "unknown; provider accounting required",
            "durable_encrypted_archive": "not configured",
            "recent_events": document["events"][-25:],
        }
        if self.store.operations_path.exists():
            from scripts.operational_ledger import OperationalLedger

            try:
                report["operational_ledger"] = OperationalLedger(
                    self.store.operations_path
                ).summary(document)
            except (ValueError, sqlite3.Error, OSError):
                report["operational_ledger"] = "unavailable; processing must remain blocked"
        return self.page(
            "System health", PRE_OPEN + self.escaped(json.dumps(report, indent=2)) + PRE_CLOSE
        )

    def outreach(self, request: Request):
        self.session(request)
        records = [
            {
                "domain": p["domain"],
                "drafts": p.get("outreach_drafts", []),
                "approvals": p.get("approvals", []),
                "events": p.get("outreach_events", []),
                "suppressed": p["status"] == "suppressed",
            }
            for p in self.state()["prospects"].values()
            if p.get("outreach_drafts")
        ]
        return self.page(
            "Outreach review",
            "<p>Live sending is disabled. Sandbox results are simulated and send no messages.</p><pre>"
            + self.escaped(json.dumps(records, indent=2))
            + PRE_CLOSE,
        )

    def completion_form(self, identity, project, kind, item, token):
        action = html.escape(
            f"/pipeline/prospects/{identity}/projects/{project['project_id']}/{kind}/{item['id']}/complete",
            quote=True,
        )
        title = self.escaped(item.get("title", item.get("action", "Tracking item")))
        return f'<form method="post" action="{action}"><input type="hidden" name="csrf" value="{self.escaped(token)}"><h3>{title}</h3><label>Completion evidence SHA-256<input name="completion_evidence" pattern="[0-9a-f]{{64}}" required></label><label>Completion note<input name="reason" maxlength="1000" required></label><button>Record completion</button></form>'

    def project_card(self, identity, project, token):
        forms = "".join(
            (
                self.completion_form(identity, project, kind, item, token)
                for kind, items in (
                    ("task", project["tasks"]),
                    ("milestone", project["milestones"]),
                )
                for item in items
                if item["status"] != "complete"
            )
        )
        return (
            "<article><h2>"
            + self.escaped(project["domain"])
            + "</h2>"
            + PRE_OPEN
            + self.escaped(json.dumps(project, indent=2))
            + PRE_CLOSE
            + forms
            + "</article>"
        )

    def projects(self, request: Request, offset: int = 0):
        _, value = self.session(request)
        if offset < 0:
            raise HTTPException(400, "Invalid page")
        records = [
            (identity, project)
            for identity, p in self.state()["prospects"].items()
            for project in p.get("projects", {}).values()
        ]
        content = "<p>Tracking records do not execute client changes, send handovers or collect payments.</p>"
        content += "".join(
            (
                self.project_card(identity, project, value["csrf"])
                for identity, project in sorted(records, key=lambda pair: pair[1]["project_id"])[
                    offset : offset + 25
                ]
            )
        )
        if offset + 25 < len(records):
            content += f'<p><a href="/pipeline/projects?offset={offset + 25}">Next projects</a></p>'
        return self.page("Client projects", content)

    @staticmethod
    async def limited_body(request):
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 4096:
                raise HTTPException(413, "Review too large")
        return raw

    @staticmethod
    def parse_input(raw, content_type, action):
        parsers = {
            "application/json": json.loads,
            "application/x-www-form-urlencoded": lambda data: {
                key: values[-1]
                for key, values in parse_qs(data.decode(), keep_blank_values=True).items()
            },
        }
        parser = parsers.get(content_type.split(";", 1)[0])
        if parser is None:
            raise HTTPException(415, "Unsupported review format")
        try:
            data = parser(raw)
            fields = {"version", "reason", "csrf"}
            if action == DecisionAction.ACCEPT:
                fields |= {"acceptance_evidence", "owner_verified"}
            if action == DecisionAction.COMPLETE:
                fields = {"completion_evidence", "reason", "csrf"}
            if not isinstance(data, dict) or set(data) - fields:
                raise ValueError("Invalid review")
        except ValueError:
            raise HTTPException(400, "Invalid review") from None
        return data

    def check_review_rate(self, key, now):
        self.writes[key] = [t for t in self.writes.get(key, []) if now - t < 60]
        if len(self.writes[key]) >= 20:
            raise HTTPException(429, "Review rate exceeded")
        self.writes[key].append(now)

    @staticmethod
    def record_completion(p, data, request, now):
        complete(
            p,
            request.path_params["project_id"],
            kind=request.path_params["kind"],
            item_id=request.path_params["item_id"],
            completion_evidence=data.get("completion_evidence"),
            actor="authenticated-owner",
            reason=data.get("reason"),
            now=now,
        )

    @staticmethod
    def record_acceptance(p, data, _request, now):
        accept_proposal(
            p,
            data["version"],
            acceptance_evidence=data.get("acceptance_evidence"),
            owner_verified=data.get("owner_verified") is True
            or data.get("owner_verified") == "true",
            actor="authenticated-owner",
            reason=data.get("reason"),
            now=now,
        )

    @staticmethod
    def record_approval(p, data, _request, now):
        approve_proposal(
            p, data["version"], actor="authenticated-owner", reason=data.get("reason"), now=now
        )

    @staticmethod
    def record_rejection(p, data, _request, now):
        reject_recommendation(p, actor="authenticated-owner", reason=data.get("reason"), now=now)

    def apply_decision(self, p, data, request, action, now):
        if action != DecisionAction.COMPLETE:
            if not p.get("proposal_version") or p["proposal_version"] != data.get("version"):
                raise HTTPException(409, "Proposal version changed; review again")
        handlers = {
            DecisionAction.COMPLETE: self.record_completion,
            DecisionAction.ACCEPT: self.record_acceptance,
            DecisionAction.APPROVE: self.record_approval,
            DecisionAction.REJECT: self.record_rejection,
        }
        handlers[action](p, data, request, now)

    async def reject(self, identity: str, request: Request):
        key, value = self.session(request)
        action = DecisionAction(request.url.path.rsplit("/", 1)[-1])
        raw = await self.limited_body(request)
        data = self.parse_input(raw, request.headers.get("content-type", ""), action)
        self.csrf(request, value, data.get("csrf"))
        now = time.time()
        self.check_review_rate(key, now)
        try:
            with self.store.transaction() as document:
                self.apply_decision(self.prospect(identity, document), data, request, action, now)
        except ValueError:
            raise HTTPException(
                400, "Check the decision, evidence reference and prerequisites"
            ) from None
        except (sqlite3.Error, OSError):
            raise HTTPException(503, "Pipeline busy; retry after processing completes") from None
        destination = (
            "/pipeline/projects"
            if action in {DecisionAction.ACCEPT, DecisionAction.COMPLETE}
            else f"/pipeline/prospects/{identity}"
        )
        return RedirectResponse(destination, status_code=303)


def attach_pipeline(app, store, session, csrf):
    views = PipelineViews(store, session, csrf)
    pages = [
        ("/pipeline", views.overview),
        ("/pipeline/prospects", views.prospects),
        ("/pipeline/prospects/{identity}", views.detail),
        ("/pipeline/discovery", views.discovered),
        ("/pipeline/health", views.health),
        ("/pipeline/outreach", views.outreach),
        ("/pipeline/projects", views.projects),
    ]
    for route, endpoint in pages:
        app.add_api_route(route, endpoint, methods=["GET"], response_class=HTMLResponse)
    actions = [
        "/pipeline/prospects/{identity}/reject",
        "/pipeline/prospects/{identity}/approve",
        "/pipeline/prospects/{identity}/accept",
        "/pipeline/prospects/{identity}/projects/{project_id}/{kind}/{item_id}/complete",
    ]
    for route in actions:
        app.add_api_route(route, views.reject, methods=["POST"])

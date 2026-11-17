"""Owner-only pipeline views mounted into the existing loopback portal."""

import html
import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode


def attach_pipeline(app, store, session, csrf):
    from fastapi import HTTPException, Request
    from fastapi.responses import HTMLResponse, RedirectResponse

    from scripts.approval_controls import approve_proposal
    from scripts.client_projects import accept_proposal, complete
    from scripts.cloud_opportunities import reject_recommendation
    from scripts.cloud_prospect_pipeline import metrics

    writes = {}

    def state():
        try:
            result = store.read()
            if result is None:
                raise ValueError("Uninitialized")
            return result
        except (ValueError, sqlite3.Error, OSError):
            raise HTTPException(503, "Pipeline records temporarily unavailable") from None

    def prospect(identity, document):
        if not re.fullmatch(r"[0-9a-f]{64}", identity) or identity not in document["prospects"]:
            raise HTTPException(404, "Prospect unavailable")
        return document["prospects"][identity]

    def escaped(value):
        return html.escape(str(value), quote=True)

    def page(title, body):
        return (
            '<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{escaped(title)} · MoneyMachine</title><style>'
            'body{font:16px system-ui;margin:0;background:#f6f7f9;color:#192737}'
            'main{max-width:1100px;margin:auto;padding:24px}nav{display:flex;gap:20px;flex-wrap:wrap}'
            'a{color:#125c87}table{width:100%;border-collapse:collapse;background:white}'
            'td,th{text-align:left;padding:12px;border-bottom:1px solid #ddd}'
            '.scroll{overflow:auto}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px}'
            'article{padding:16px;background:white;border:1px solid #ddd;border-radius:8px}'
            'pre{white-space:pre-wrap;overflow-wrap:anywhere;background:white;padding:16px}'
            'input,textarea,button{font:inherit;padding:8px;max-width:100%;box-sizing:border-box}'
            'label{display:block;margin:12px 0}textarea{width:100%}button{cursor:pointer}'
            '</style><main><nav><a href="/pipeline">Overview</a>'
            '<a href="/pipeline/prospects">Prospects</a><a href="/pipeline/discovery">Discovery</a>'
            '<a href="/pipeline/outreach">Outreach review</a>'
            '<a href="/pipeline/projects">Projects</a>'
            '<a href="/pipeline/health">System health</a><a href="/">Audit history</a></nav>'
            f'<h1>{escaped(title)}</h1>{body}</main></html>'
        )

    @app.get("/pipeline", response_class=HTMLResponse)
    def overview(request: Request):
        session(request)
        document = state()
        report = metrics(document)
        labels = {
            "prospects_found": "Reviewed prospects", "audits_succeeded": "Completed audits",
            "audits_failed": "Failed audits", "qualified_opportunities": "Internal opportunities",
            "proposal_reviews_pending": "Proposals awaiting review", "approvals_pending": "Scope reviews pending",
            "contacts_sent": "Owner-recorded provider acceptances",
            "active_projects": "Active projects",
        }
        cards = "".join(
            f'<article><strong>{report[key]}</strong><br>{label}</article>'
            for key, label in labels.items()
        )
        return page("Pipeline overview", '<div class="cards">' + cards + '</div>'
                    '<p>Sending is disabled. Pricing requires configured rates and scope.</p>'
                    f'<p>Discovery candidates: {len(document.get("discovery_candidates", {}))}</p>')

    @app.get("/pipeline/prospects", response_class=HTMLResponse)
    def prospects(request: Request, q: str = "", status: str = "", offset: int = 0):
        session(request)
        if len(q) > 253 or len(status) > 40 or offset < 0:
            raise HTTPException(400, "Invalid search")
        # Bounded private state (<=100 prospects), deterministic sorted pages.
        records = [
            (identity, p) for identity, p in sorted(state()["prospects"].items(), key=lambda pair: pair[1]["domain"])
            if (not status or p["status"] == status) and
            (q.casefold() in p["domain"].casefold() or
             q.casefold() in p.get("discovery", {}).get("business_name", "").casefold())
        ]
        rows = "".join(
            f'<tr><td><a href="/pipeline/prospects/{identity}">{escaped(p["domain"])}</a></td>'
            f'<td>{escaped(p["status"])}</td><td>{escaped(p.get("opportunity", {}).get("score", "Unscored"))}</td></tr>'
            for identity, p in records[offset:offset + 25]
        ) or '<tr><td colspan="3">No matching prospects.</td></tr>'
        navigation = ""
        for label, index in (("Previous", offset - 25), ("Next", offset + 25)):
            if 0 <= index < len(records):
                url = "/pipeline/prospects?" + urlencode(dict(q=q, status=status, offset=index))
                navigation += f'<p><a href="{escaped(url)}">{label}</a></p>'
        return page("Prospects", '<form><label>Search business or domain '
                    f'<input name="q" value="{escaped(q)}"></label><label>Status '
                    f'<input name="status" value="{escaped(status)}"></label><button>Search</button></form>'
                    '<div class="scroll"><table><tr><th>Website</th><th>Audit state</th><th>Review score</th></tr>'
                    + rows + '</table></div>' + navigation)

    @app.get("/pipeline/prospects/{identity}", response_class=HTMLResponse)
    def detail(identity: str, request: Request):
        _, value = session(request)
        p = prospect(identity, state())
        form = ""
        if p.get("proposal_version"):
            form = (
                f'<form method="post" action="/pipeline/prospects/{escaped(identity)}/reject">'
                f'<input type="hidden" name="csrf" value="{escaped(value["csrf"])}">'
                f'<input type="hidden" name="version" value="{escaped(p["proposal_version"])}">'
                '<label>Reason for rejection<textarea name="reason" maxlength="1000" required></textarea></label>'
                f'<button formaction="/pipeline/prospects/{escaped(identity)}/approve">Approve internal proposal</button> '
                '<button>Reject recommendation</button></form>'
            )
            decisions = [a for a in p.get("approvals", []) if a["action_type"] == "proposal"]
            if decisions and decisions[-1]["decision"] == "approved" and decisions[-1]["version_sha256"] == p["proposal_version"]:
                form += (
                    f'<form method="post" action="/pipeline/prospects/{escaped(identity)}/accept">'
                    f'<input type="hidden" name="csrf" value="{escaped(value["csrf"])}">'
                    f'<input type="hidden" name="version" value="{escaped(p["proposal_version"])}">'
                    '<h2>Record customer acceptance</h2><label>Acceptance evidence SHA-256 '
                    '<input name="acceptance_evidence" pattern="[0-9a-f]{64}" required></label>'
                    '<label>Acceptance note<textarea name="reason" maxlength="1000" required></textarea></label>'
                    '<label><input type="checkbox" name="owner_verified" value="true" required>'
                    ' I verified the customer accepted this exact proposal version.</label>'
                    '<button>Create project record</button></form>'
                )
        return page(p["domain"], '<p>Internal review only. Detailed encrypted report archives are not decrypted here.</p>'
                    '<p>Archive retrieval is available only after an artifact reference is registered.</p>'
                    + form + '<pre>' + escaped(json.dumps(p, indent=2)) + '</pre>')

    @app.get("/pipeline/discovery", response_class=HTMLResponse)
    def discovered(request: Request, offset: int = 0):
        session(request)
        if offset < 0:
            raise HTTPException(400, "Invalid page")
        candidates = sorted(state().get("discovery_candidates", {}).values(), key=lambda c: c["domain"])
        return page("Discovery review", '<p>Imported candidates require independent eligibility review before auditing.</p>'
                    + '<pre>' + escaped(json.dumps(candidates[offset:offset + 25], indent=2)) + '</pre>')

    @app.get("/pipeline/health", response_class=HTMLResponse)
    def health(request: Request):
        session(request)
        document = state()
        today = datetime.now(timezone.utc).isoformat()[:10]
        report = dict(
            daily_hard_cap=6,
            attempts_recorded_today=sum(e.get("action") == "audit" and
                                       e.get("timestamp_utc", "")[:10] == today for e in document["events"]),
            paid_api_calls=0, automatic_sending="disabled", storage="private SQLite",
            hosted_storage="not verified", free_tier_remaining="unknown; provider accounting required",
            durable_encrypted_archive="not configured",
            recent_events=document["events"][-25:],
        )
        return page("System health", '<pre>' + escaped(json.dumps(report, indent=2)) + '</pre>')

    @app.get("/pipeline/outreach", response_class=HTMLResponse)
    def outreach(request: Request):
        session(request)
        records = [dict(domain=p["domain"], drafts=p.get("outreach_drafts", []),
                        approvals=p.get("approvals", []), events=p.get("outreach_events", []),
                        suppressed=p["status"] == "suppressed")
                   for p in state()["prospects"].values() if p.get("outreach_drafts")]
        return page("Outreach review", '<p>Live sending is disabled. Sandbox results are simulated and send no messages.</p>'
                    '<pre>' + escaped(json.dumps(records, indent=2)) + '</pre>')

    @app.get("/pipeline/projects", response_class=HTMLResponse)
    def projects(request: Request, offset: int = 0):
        _, value = session(request)
        if offset < 0:
            raise HTTPException(400, "Invalid page")
        records = [(identity, project) for identity, p in state()["prospects"].items()
                   for project in p.get("projects", {}).values()]
        content = '<p>Tracking records do not execute client changes, send handovers or collect payments.</p>'
        for identity, project in sorted(records, key=lambda pair: pair[1]["project_id"])[offset:offset + 25]:
            forms = ""
            for kind, items in (("task", project["tasks"]), ("milestone", project["milestones"])):
                for item in items:
                    if item["status"] == "complete":
                        continue
                    forms += (
                        f'<form method="post" action="/pipeline/prospects/{escaped(identity)}/projects/{escaped(project["project_id"])}/{escaped(kind)}/{escaped(item["id"])}/complete">'
                        f'<input type="hidden" name="csrf" value="{escaped(value["csrf"])}">'
                        f'<h3>{escaped(item.get("title", item.get("action", "Tracking item")))}</h3>'
                        '<label>Completion evidence SHA-256<input name="completion_evidence" pattern="[0-9a-f]{64}" required></label>'
                        '<label>Completion note<input name="reason" maxlength="1000" required></label>'
                        '<button>Record completion</button></form>'
                    )
            content += '<article><h2>' + escaped(project["domain"]) + '</h2><pre>' + escaped(json.dumps(project, indent=2)) + '</pre>' + forms + '</article>'
        if offset + 25 < len(records):
            content += f'<p><a href="/pipeline/projects?offset={offset + 25}">Next projects</a></p>'
        return page("Client projects", content)

    @app.post("/pipeline/prospects/{identity}/reject")
    @app.post("/pipeline/prospects/{identity}/approve")
    @app.post("/pipeline/prospects/{identity}/accept")
    @app.post("/pipeline/prospects/{identity}/projects/{project_id}/{kind}/{item_id}/complete")
    async def reject(identity: str, request: Request):
        key, value = session(request)
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 4096:
                raise HTTPException(413, "Review too large")
        try:
            if request.headers.get("content-type", "").startswith("application/json"):
                data = json.loads(raw)
            elif request.headers.get("content-type", "").startswith("application/x-www-form-urlencoded"):
                data = {k: v[-1] for k, v in parse_qs(raw.decode(), keep_blank_values=True).items()}
            else:
                raise HTTPException(415, "Unsupported review format")
            fields = {"version", "reason", "csrf"}
            if request.url.path.endswith("/accept"):
                fields |= {"acceptance_evidence", "owner_verified"}
            if request.url.path.endswith("/complete"):
                fields = {"completion_evidence", "reason", "csrf"}
            if not isinstance(data, dict) or set(data) - fields:
                raise ValueError("Invalid review")
        except (ValueError, UnicodeError):
            raise HTTPException(400, "Invalid review") from None
        csrf(request, value, data.get("csrf"))
        now = time.time()
        writes[key] = [t for t in writes.get(key, []) if now - t < 60]
        if len(writes[key]) >= 20:
            raise HTTPException(429, "Review rate exceeded")
        writes[key].append(now)
        try:
            with store.transaction() as document:
                p = prospect(identity, document)
                if request.url.path.endswith("/complete"):
                    complete(
                        p, request.path_params["project_id"], kind=request.path_params["kind"],
                        item_id=request.path_params["item_id"], completion_evidence=data.get("completion_evidence"),
                        actor="authenticated-owner", reason=data.get("reason"), now=now,
                    )
                elif not p.get("proposal_version") or p["proposal_version"] != data.get("version"):
                    raise HTTPException(409, "Proposal version changed; review again")
                elif request.url.path.endswith("/accept"):
                    accept_proposal(
                        p, data["version"], acceptance_evidence=data.get("acceptance_evidence"),
                        owner_verified=data.get("owner_verified") is True or data.get("owner_verified") == "true",
                        actor="authenticated-owner", reason=data.get("reason"), now=now,
                    )
                elif request.url.path.endswith("/approve"):
                    approve_proposal(p, data["version"], actor="authenticated-owner", reason=data.get("reason"), now=now)
                else:
                    reject_recommendation(p, actor="authenticated-owner", reason=data.get("reason"), now=now)
        except ValueError:
            raise HTTPException(400, "Check the decision, evidence reference and prerequisites") from None
        except (sqlite3.Error, OSError):
            raise HTTPException(503, "Pipeline busy; retry after processing completes") from None
        destination = "/pipeline/projects" if request.url.path.endswith(("/accept", "/complete")) else f"/pipeline/prospects/{identity}"
        return RedirectResponse(destination, status_code=303)

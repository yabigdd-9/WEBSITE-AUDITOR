"""Single-owner portal with explicit authenticated route composition."""

import hashlib
import html
import json
import secrets
import time
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .common import atomic_write_json
from .storage import History

CSRF_REQUIRED = "CSRF token required"
BINARY_TYPE = "application/octet-stream"
LOGIN_PATH = "/login"


def setup_password(root, password):
    from argon2 import PasswordHasher

    if len(password) < 12:
        raise ValueError("Use at least 12 characters")
    path = Path(root) / "portal-auth.json"
    atomic_write_json(path, {"password_hash": PasswordHasher().hash(password)})
    path.chmod(384)
    return path


class OwnerPortal:
    def __init__(self, app, history, root, password_hash, session_seconds, pipeline_db):
        self.app = app
        self.history = history
        self.root = root
        self.password_hash = password_hash
        self.session_seconds = session_seconds
        self.pipeline_db = pipeline_db
        self.attempts = {}

    def session(self, request):
        token = request.cookies.get("wa_session", "")
        key = hashlib.sha256(token.encode()).hexdigest()
        value = self.app.state.sessions.get(key)
        if not value or value["expires"] <= time.time():
            self.app.state.sessions.pop(key, None)
            raise HTTPException(401, "Login required")
        return (key, value)

    def csrf(self, request, value, submitted=None):
        expected_origin = str(request.base_url).rstrip("/")
        if request.headers.get("origin") not in (None, expected_origin):
            raise HTTPException(403, "Origin rejected")
        if not isinstance(submitted, (str, type(None))):
            raise HTTPException(403, CSRF_REQUIRED)
        if not secrets.compare_digest(
            (submitted or request.headers.get("x-csrf-token", "")).encode(), value["csrf"].encode()
        ):
            raise HTTPException(403, CSRF_REQUIRED)

    async def headers(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; form-action 'self'"
        )
        return response

    def login_page(self):
        return '<h1>Website Auditor</h1><form method="post" action="/login"><label>Password <input name="password" type="password" autocomplete="current-password" required></label><button>Log in</button></form>'

    async def login(self, request: Request):
        if request.headers.get("origin") not in (None, str(request.base_url).rstrip("/")):
            raise HTTPException(403, "Origin rejected")
        address = request.client.host
        now = time.time()
        self.attempts[address] = [t for t in self.attempts.get(address, []) if now - t < 60]
        if len(self.attempts[address]) >= 5:
            raise HTTPException(429, "Try again in one minute")
        self.attempts[address].append(now)
        form = await request.form()
        try:
            PasswordHasher().verify(self.password_hash, str(form.get("password", "")))
        except VerificationError:
            raise HTTPException(401, "Invalid password") from None
        token = secrets.token_urlsafe(32)
        self.app.state.sessions = {
            k: v for k, v in self.app.state.sessions.items() if v["expires"] > now
        }
        self.app.state.sessions[hashlib.sha256(token.encode()).hexdigest()] = {
            "expires": now + self.session_seconds,
            "csrf": secrets.token_urlsafe(32),
        }
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            "wa_session", token, httponly=True, samesite="strict", max_age=self.session_seconds
        )
        return response

    def session_info(self, request: Request):
        _, value = self.session(request)
        return {"csrf": value["csrf"], "expires": value["expires"]}

    async def logout(self, request: Request):
        key, value = self.session(request)
        form = await request.form()
        submitted = request.headers.get("x-csrf-token") or str(form.get("csrf", ""))
        if not secrets.compare_digest(submitted, value["csrf"]):
            raise HTTPException(403, CSRF_REQUIRED)
        self.app.state.sessions.pop(key, None)
        response = RedirectResponse(LOGIN_PATH, status_code=303)
        response.delete_cookie("wa_session")
        return response

    def dashboard(self, request: Request, q: str = ""):
        try:
            _, value = self.session(request)
        except HTTPException:
            return RedirectResponse(LOGIN_PATH, status_code=303)
        rows = "".join(
            (
                "<tr><td>"
                + html.escape(r["url"])
                + "</td><td>"
                + html.escape(r["status"])
                + "</td><td>"
                + str(r["health_score"])
                + '</td><td><a href="/runs/'
                + r["run_id"]
                + '">View evidence</a></td></tr>'
                for r in self.history.list(q)
            )
        )
        return (
            "<h1>Website Auditor</h1><p>"
            + (
                '<a href="/pipeline">Business pipeline</a> · '
                if self.pipeline_db is not None
                else ""
            )
            + '<a href="/monthly">Monthly report drafts</a></p><form><label>Search sites <input name="q" value="'
            + html.escape(q, quote=True)
            + '"></label><button>Search</button></form><table><thead><tr><th>Site</th><th>Status</th><th>Health</th><th>Report</th></tr></thead><tbody>'
            + rows
            + '</tbody></table><form method="post" action="/logout"><input type="hidden" name="csrf" value="'
            + value["csrf"]
            + '"><button>Log out</button></form>'
        )

    def monthly_reports(self, request: Request):
        self.session(request)
        from .monthly import MonthlyStore

        store = MonthlyStore(self.root)
        rows = []
        for report in store.list():
            identity = report["id"]
            manifest = report.get("manifest", {})
            links = " ".join(
                (
                    f'<a href="/monthly-artifacts/{identity}/{kind}">{html.escape(kind)}</a>'
                    for kind in ("pdf", "html", "email", "json", "revenue", "roi", "action")
                    if kind in manifest
                )
            )
            rows.append(
                f"<tr><td>{html.escape(str(report.get('client_id', '')))}</td><td>{html.escape(str(report.get('month', '')))}</td><td>{html.escape(str(report.get('status', '')))}</td><td>{links}</td></tr>"
            )
        body = "".join(rows) or '<tr><td colspan="4">No monthly report drafts available.</td></tr>'
        return f'<h1>Monthly report drafts</h1><p><a href="/">Back to dashboard</a></p><table><thead><tr><th>Client</th><th>Month</th><th>Status</th><th>Artifacts</th></tr></thead><tbody>{body}</tbody></table>'

    def monthly_artifact(self, identity: str, kind: str, request: Request):
        self.session(request)
        from .monthly import MonthlyStore

        try:
            path = MonthlyStore(self.root).artifact(identity, kind)
        except (KeyError, ValueError, OSError):
            raise HTTPException(404, "Monthly artifact unavailable") from None
        return FileResponse(path, filename=path.name, media_type=BINARY_TYPE)

    def run_view(self, run_id: str, request: Request):
        self.session(request)
        try:
            report = self.history.get(run_id)
        except KeyError:
            raise HTTPException(404, "Unknown run") from None
        safe_run_id = html.escape(run_id, quote=True)
        links = " ".join(
            (
                f'<a href="/artifacts/{safe_run_id}/{html.escape(k)}">Download {html.escape(k)}</a>'
                for k in report["artifacts"]
            )
        )
        return (
            "<h1>Audit evidence</h1>"
            + links
            + "<pre>"
            + html.escape(json.dumps(report, indent=2))
            + "</pre>"
        )

    def artifact(self, run_id: str, kind: str, request: Request):
        self.session(request)
        try:
            path = self.history.artifact(run_id, kind)
        except (KeyError, ValueError):
            raise HTTPException(404, "Artifact unavailable") from None
        return FileResponse(path, filename=path.name, media_type=BINARY_TYPE)

    async def remediation(self, identity: str, request: Request):
        _, value = self.session(request)
        self.csrf(request, value)
        data = await request.json()
        try:
            self.history.transition(identity, data["state"], data.get("metadata"))
        except (KeyError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from None
        return {"status": "updated"}

    def health_check(self):
        try:
            from pathlib import Path

            if not Path(self.app.state.root).exists():
                raise RuntimeError("Root directory does not exist")
            return {"status": "ok"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


def _attach_private_pipeline(app, owner, pipeline_db):
    from scripts.pipeline_store import PipelineStore

    from .pipeline_portal import attach_pipeline

    if not Path(pipeline_db).is_file():
        raise ValueError("Initialize the private pipeline database before serving")
    store = PipelineStore(Path(pipeline_db))
    if store.read() is None:
        raise ValueError("Initialize the private pipeline database before serving")
    attach_pipeline(app, store, owner.session, owner.csrf)


def create_app(root, session_seconds=3600, pipeline_db=None):
    history = History(root)
    auth_file = Path(root) / "portal-auth.json"
    if not auth_file.is_file():
        raise ValueError("Run wa dashboard --set-password before serving")
    password_hash = json.loads(auth_file.read_text())["password_hash"]
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )
    app.state.sessions = {}
    app.state.history = history
    app.state.root = root
    owner = OwnerPortal(app, history, root, password_hash, session_seconds, pipeline_db)
    app.middleware("http")(owner.headers)
    routes = [
        (LOGIN_PATH, owner.login_page, ["GET"], HTMLResponse),
        (LOGIN_PATH, owner.login, ["POST"], None),
        ("/api/session", owner.session_info, ["GET"], None),
        ("/logout", owner.logout, ["POST"], None),
        ("/", owner.dashboard, ["GET"], HTMLResponse),
        ("/monthly", owner.monthly_reports, ["GET"], HTMLResponse),
        ("/monthly-artifacts/{identity}/{kind}", owner.monthly_artifact, ["GET"], None),
        ("/runs/{run_id}", owner.run_view, ["GET"], HTMLResponse),
        ("/artifacts/{run_id}/{kind}", owner.artifact, ["GET"], None),
        ("/api/remediations/{identity}", owner.remediation, ["POST"], None),
        ("/health", owner.health_check, ["GET"], None),
    ]
    for route, endpoint, methods, response_class in routes:
        options = {"response_class": response_class} if response_class else {}
        app.add_api_route(route, endpoint, methods=methods, **options)
    if pipeline_db is not None:
        _attach_private_pipeline(app, owner, pipeline_db)
    return app

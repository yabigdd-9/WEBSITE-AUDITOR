"""Single-operator local portal with opaque, expiring server-side sessions."""

import hashlib
import html
import json
import secrets
import time
from pathlib import Path

from .common import atomic_write_json
from .storage import History


def setup_password(root, password):
    from argon2 import PasswordHasher

    if len(password) < 12:
        raise ValueError("Use at least 12 characters")
    path = Path(root) / "portal-auth.json"
    atomic_write_json(path, {"password_hash": PasswordHasher().hash(password)})
    path.chmod(0o600)
    return path


def create_app(root, session_seconds=3600):
    from argon2 import PasswordHasher
    from argon2.exceptions import VerificationError
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
    from starlette.middleware.trustedhost import TrustedHostMiddleware

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
    attempts = {}

    def session(request):
        token = request.cookies.get("wa_session", "")
        key = hashlib.sha256(token.encode()).hexdigest()
        value = app.state.sessions.get(key)
        if not value or value["expires"] <= time.time():
            app.state.sessions.pop(key, None)
            raise HTTPException(401, "Login required")
        return key, value

    def csrf(request, value):
        expected_origin = str(request.base_url).rstrip("/")
        if request.headers.get("origin") not in (None, expected_origin):
            raise HTTPException(403, "Origin rejected")
        if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), value["csrf"]):
            raise HTTPException(403, "CSRF token required")

    @app.middleware("http")
    async def headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; form-action 'self'"
        )
        return response

    @app.get("/login", response_class=HTMLResponse)
    def login_page():
        return '<h1>Website Auditor</h1><form method="post" action="/login"><label>Password <input name="password" type="password" autocomplete="current-password" required></label><button>Log in</button></form>'

    @app.post("/login")
    async def login(request: Request):
        if request.headers.get("origin") not in (None, str(request.base_url).rstrip("/")):
            raise HTTPException(403, "Origin rejected")
        address = request.client.host
        now = time.time()
        attempts[address] = [t for t in attempts.get(address, []) if now - t < 60]
        if len(attempts[address]) >= 5:
            raise HTTPException(429, "Try again in one minute")
        attempts[address].append(now)
        form = await request.form()
        try:
            PasswordHasher().verify(password_hash, str(form.get("password", "")))
        except VerificationError:
            raise HTTPException(401, "Invalid password") from None
        token = secrets.token_urlsafe(32)
        app.state.sessions = {k: v for k, v in app.state.sessions.items() if v["expires"] > now}
        app.state.sessions[hashlib.sha256(token.encode()).hexdigest()] = {
            "expires": now + session_seconds,
            "csrf": secrets.token_urlsafe(32),
        }
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            "wa_session", token, httponly=True, samesite="strict", max_age=session_seconds
        )
        return response

    @app.get("/api/session")
    def session_info(request: Request):
        _, value = session(request)
        return {"csrf": value["csrf"], "expires": value["expires"]}

    @app.post("/logout")
    async def logout(request: Request):
        key, value = session(request)
        form = await request.form()
        submitted = request.headers.get("x-csrf-token") or str(form.get("csrf", ""))
        if not secrets.compare_digest(submitted, value["csrf"]):
            raise HTTPException(403, "CSRF token required")
        app.state.sessions.pop(key, None)
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie("wa_session")
        return response

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request, q: str = ""):
        try:
            _, value = session(request)
        except HTTPException:
            return RedirectResponse("/login", status_code=303)
        rows = "".join(
            "<tr><td>"
            + html.escape(r["url"])
            + "</td><td>"
            + html.escape(r["status"])
            + "</td><td>"
            + str(r["health_score"])
            + '</td><td><a href="/runs/'
            + r["run_id"]
            + '">View evidence</a></td></tr>'
            for r in history.list(q)
        )
        return (
            '<h1>Website Auditor</h1><p><a href="/monthly">Monthly report drafts</a></p><form><label>Search sites <input name="q" value="'
            + html.escape(q, quote=True)
            + '"></label><button>Search</button></form><table><thead><tr>'
            "<th>Site</th><th>Status</th><th>Health</th><th>Report</th></tr></thead><tbody>"
            + rows
            + '</tbody></table><form method="post" action="/logout"><input type="hidden" name="csrf" value="'
            + value["csrf"]
            + '"><button>Log out</button></form>'
        )

    @app.get("/monthly", response_class=HTMLResponse)
    def monthly_reports(request: Request):
        session(request)

        from .monthly import MonthlyStore

        store = MonthlyStore(root)
        rows = []

        for report in store.list():
            identity = report["id"]
            manifest = report.get("manifest", {})

            links = " ".join(
                f'<a href="/monthly-artifacts/{identity}/{kind}">{html.escape(kind)}</a>'
                for kind in ("pdf", "html", "email", "json", "revenue", "roi", "action")
                if kind in manifest
            )

            rows.append(
                "<tr>"
                f"<td>{html.escape(str(report.get('client_id', '')))}</td>"
                f"<td>{html.escape(str(report.get('month', '')))}</td>"
                f"<td>{html.escape(str(report.get('status', '')))}</td>"
                f"<td>{links}</td>"
                "</tr>"
            )

        body = "".join(rows) or (
            '<tr><td colspan="4">No monthly report drafts available.</td></tr>'
        )

        return (
            "<h1>Monthly report drafts</h1>"
            '<p><a href="/">Back to dashboard</a></p>'
            "<table>"
            "<thead><tr>"
            "<th>Client</th><th>Month</th><th>Status</th><th>Artifacts</th>"
            "</tr></thead>"
            f"<tbody>{body}</tbody>"
            "</table>"
        )

    @app.get("/monthly-artifacts/{identity}/{kind}")
    def monthly_artifact(identity: str, kind: str, request: Request):
        session(request)

        from .monthly import MonthlyStore

        try:
            path = MonthlyStore(root).artifact(identity, kind)
        except (KeyError, ValueError, OSError):
            raise HTTPException(404, "Monthly artifact unavailable") from None

        return FileResponse(
            path,
            filename=path.name,
            media_type="application/octet-stream",
        )

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    def run_view(run_id: str, request: Request):
        session(request)
        try:
            report = history.get(run_id)
        except KeyError:
            raise HTTPException(404, "Unknown run") from None
        links = " ".join(
            f'<a href="/artifacts/{run_id}/{html.escape(k)}">Download {html.escape(k)}</a>'
            for k in report["artifacts"]
        )
        return (
            "<h1>Audit evidence</h1>"
            + links
            + "<pre>"
            + html.escape(json.dumps(report, indent=2))
            + "</pre>"
        )

    @app.get("/artifacts/{run_id}/{kind}")
    def artifact(run_id: str, kind: str, request: Request):
        session(request)
        try:
            path = history.artifact(run_id, kind)
        except (KeyError, ValueError):
            raise HTTPException(404, "Artifact unavailable") from None
        return FileResponse(path, filename=path.name, media_type="application/octet-stream")

    @app.post("/api/remediations/{identity}")
    async def remediation(identity: str, request: Request):
        _, value = session(request)
        csrf(request, value)
        data = await request.json()
        try:
            history.transition(identity, data["state"], data.get("metadata"))
        except (KeyError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from None
        return {"status": "updated"}

    @app.get("/health")
    def health_check():
        try:
            from pathlib import Path
            if not Path(app.state.root).exists():
                raise RuntimeError("Root directory does not exist")
            return {"status": "ok"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return app

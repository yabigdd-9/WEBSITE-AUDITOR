"""Single-operator local portal with opaque, expiring server-side sessions."""

import hashlib
import html
import json
import secrets
import time
from pathlib import Path

from .common import atomic_write_json
from .storage import History
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

CSRF_REQUIRED = "CSRF token required"
BINARY_TYPE = "application/octet-stream"
LOGIN_PATH = "/login"


def setup_password(root, password):
    from argon2 import PasswordHasher

    if len(password) < 12:
        raise ValueError("Use at least 12 characters")
    path = Path(root) / "portal-auth.json"
    atomic_write_json(path, {"password_hash": PasswordHasher().hash(password)})
    path.chmod(0o600)
    return path


class OwnerPortal:
    def __init__(self, app, history, root, password_hash, session_seconds, pipeline_db, region="default"):
        self.app = app
        self.history = history
        self.root = root
        self.password_hash = password_hash
        self.session_seconds = session_seconds
        self.pipeline_db = pipeline_db
        self.region = region
        self.attempts = {}

    def session(self, request):
        token = request.cookies.get("wa_session", "")
        key = hashlib.sha256(token.encode()).hexdigest()
        value = self.app.state.sessions.get(key)
        if not value or value["expires"] <= time.time():
            self.app.state.sessions.pop(key, None)
            raise HTTPException(401, "Login required")
        return (key, value)

    def session_info(self, request):
        token = request.cookies.get("wa_session", "")
        key = hashlib.sha256(token.encode()).hexdigest()
        value = self.app.state.sessions.get(key)
        if not value or value["expires"] <= time.time():
            raise HTTPException(401, "Login required")
        return {"csrf": value["csrf"], "expires": value["expires"]}

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
        return (
            '<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Owner login · Website Auditor</title><style>'
            'body{font:16px system-ui;margin:0;background:#f6f7f9;color:#192737}'
            'main{max-width:28rem;margin:auto;padding:24px}'
            'label{display:block;margin:16px 0}'
            'input,button{font:inherit;padding:12px;box-sizing:border-box;max-width:100%}'
            'input{display:block;width:100%;margin-top:8px}'
            '</style></head><body><main><h1>Website Auditor</h1>'
            '<form method="post" action="/login"><label>Password '
            '<input name="password" type="password" autocomplete="current-password" required>'
            '</label><button>Log in</button></form></main></body></html>'
        )

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
        self.app.state.sessions = {k: v for k, v in self.app.state.sessions.items() if v["expires"] > time.time()}
        self.app.state.sessions[hashlib.sha256(token.encode()).hexdigest()] = {
            "expires": now + self.session_seconds,
            "csrf": secrets.token_urlsafe(32),
        }
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            "wa_session",
            token,
            httponly=True,
            samesite="strict",
            max_age=self.session_seconds,
            path="/",
        )
        return response

    async def logout(self, request: Request):
        key, value = self.session(request)
        form = await request.form()
        submitted = request.headers.get("x-csrf-token") or str(form.get("csrf", ""))
        if not secrets.compare_digest(submitted, value["csrf"]):
            raise HTTPException(403, "CSRF token required")
        self.app.state.sessions.pop(key, None)
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie("wa_session")
        return response


def create_app(root, session_seconds=3600, pipeline_db=None, report_archive_root=None, pipeline_postgres=False, region="default", region_config=None):
    """Create the portal app with multi-region support.

    Args:
        root: Root directory for portal data.
        session_seconds: Session timeout in seconds.
        pipeline_db: Optional pipeline database path.
        report_archive_root: Optional report archive root.
        pipeline_postgres: Use Postgres for pipeline storage.
        region: Region identifier (default: "default").
        region_config: Optional region-specific configuration dict.
    """
    from .config import get_settings
    from .pipeline_portal import attach_pipeline
    from scripts.pipeline_store import PipelineStore
    from scripts.postgres_store import PostgresPipelineStore

    # Apply region-specific settings
    region_config = region_config or {}

    # Support both multi-region and legacy single-region modes
    # Check if we're in multi-region mode (regions/ subdirectory exists)
    regions_dir = Path(root) / "regions"
    if regions_dir.is_dir() and (regions_dir / region).is_dir():
        # Multi-region mode
        region_root = regions_dir / region
    else:
        # Legacy single-region mode - use root directly
        region_root = Path(root)

    history = History(region_root)
    auth_file = region_root / "portal-auth.json"
    if not auth_file.is_file():
        raise ValueError(f"Run wa dashboard --set-password --region {region} before serving")
    password_hash = json.loads(auth_file.read_text())["password_hash"]
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    settings = get_settings()
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts
    )
    app.state.sessions = {}
    app.state.history = history
    app.state.root = region_root
    app.state.region = region

    # Determine pipeline database
    if pipeline_postgres:
        pipeline_db = PostgresPipelineStore()
    elif pipeline_db is None:
        pipeline_db = PipelineStore(region_root / "pipeline.sqlite3")

    owner_portal = OwnerPortal(app, history, region_root, password_hash, session_seconds, pipeline_db, region)

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
        return owner_portal.login_page()

    @app.post("/login")
    async def login(request: Request):
        return await owner_portal.login(request)

    @app.get("/api/session")
    def session_info(request: Request):
        return owner_portal.session_info(request)

    @app.post("/logout")
    async def logout(request: Request):
        return await owner_portal.logout(request)

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request, q: str = ""):
        try:
            _, value = owner_portal.session(request)
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
        owner_portal.session(request)

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
        owner_portal.session(request)

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
        owner_portal.session(request)
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
        owner_portal.session(request)
        try:
            path = history.artifact(run_id, kind)
        except (KeyError, ValueError):
            raise HTTPException(404, "Artifact unavailable") from None
        return FileResponse(path, filename=path.name, media_type="application/octet-stream")

    @app.post("/api/remediations/{identity}")
    async def remediation(identity: str, request: Request):
        _, value = owner_portal.session(request)
        owner_portal.csrf(request, value)
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

    # Validate report_archive_root if provided
    if report_archive_root:
        if not report_archive_root.exists():
            raise ValueError("Report archive directory does not exist")
        if not report_archive_root.is_dir():
            raise ValueError("Report archive path is not a directory")
        # Check permissions (must be 0700)
        if report_archive_root.stat().st_mode & 0o077:
            raise ValueError("Report archive directory must have 0700 permissions")

    # Attach pipeline routes if pipeline_db is provided
    if pipeline_db:
        if isinstance(pipeline_db, Path):
            if not pipeline_db.exists():
                raise ValueError("Pipeline database does not exist")
            if not pipeline_db.is_file():
                raise ValueError("Pipeline database path is not a file")
            store = PipelineStore(pipeline_db)
        else:
            # PostgresPipelineStore instance
            store = pipeline_db
        attach_pipeline(app, store, owner_portal.session, owner_portal.csrf, report_archive_root)

    return app

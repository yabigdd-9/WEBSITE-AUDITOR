from __future__ import annotations

import argparse
import asyncio
import base64
import hmac
import html
import json
import logging
import os
import secrets
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .db import Database, DatabaseError, DatabaseIntegrityError, now_iso
from .mailer import MailConfigurationError, MailDeliveryError, send_account_link, smtp_configuration
from .security import (
    CONSENT_TEXT,
    CONSENT_VERSION,
    digest_token,
    hash_password,
    new_token,
    normalize_site,
    production_deployment,
    production_mode,
    valid_email_address,
    verify_password,
    verify_totp,
)

logger = logging.getLogger("catalyx_web")
PRIVILEGED_ROLES = {"owner", "admin", "reviewer", "support"}
REVIEW_ROLES = {"owner", "admin", "reviewer"}
APP_DIR = Path(__file__).parent
STATIC_DIR = APP_DIR / "static"
SESSION_SECONDS = 60 * 60 * 8
MAX_FORM_BYTES = 32_768


def _e(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _public_base_url(request: Request) -> str:
    configured = os.getenv("CATALYX_PUBLIC_BASE_URL", "").strip()
    if not configured:
        if production_mode():
            raise HTTPException(503, "The fixed public application URL is not configured.")
        configured = str(request.base_url).rstrip("/")
    parts = urlsplit(configured)
    try:
        parts.port
    except ValueError:
        raise HTTPException(503, "The fixed public application URL is invalid.") from None
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.path not in {"", "/"}
        or parts.query
        or parts.fragment
        or (production_mode() and parts.scheme != "https")
    ):
        raise HTTPException(503, "The fixed public application URL is invalid.")
    return configured.rstrip("/")


def _public_registration_open() -> bool:
    mode = os.getenv("CATALYX_REGISTRATION_MODE", "closed" if production_mode() else "open")
    return mode.strip().lower() == "open"


def _home_path_for_role(role: str) -> str:
    if role in REVIEW_ROLES:
        return "/admin"
    if role == "support":
        return "/admin/customers"
    return "/app"


def _page(title: str, body: str, *, user=None, active="", notice="", status=200) -> HTMLResponse:
    identity = ""
    if user:
        identity = (
            '<div class="identity"><span>' + _e(user["email"]) + '</span>'
            '<form method="post" action="/logout"><input type="hidden" name="csrf" value="'
            + _e(user["csrf_token"])
            + '"><button class="text-button" type="submit">Sign out</button></form></div>'
        )
    if user and user["role"] in PRIVILEGED_ROLES:
        if user["role"] == "support":
            links = [("/admin/customers", "Customers", "customers")]
        elif user["role"] == "reviewer":
            links = [
                ("/admin", "Operations", "admin"),
                ("/admin/audits", "Audit queue", "queue"),
                ("/admin/sites", "Sites", "sites"),
                ("/admin/jobs", "Jobs", "jobs"),
            ]
        else:
            links = [
                ("/admin", "Operations", "admin"),
                ("/admin/audits", "Audit queue", "queue"),
                ("/admin/sites", "Sites", "sites"),
                ("/admin/jobs", "Jobs", "jobs"),
                ("/admin/customers", "Customers", "customers"),
                ("/admin/privacy-requests", "Privacy requests", "privacy"),
                ("/admin/activity", "Activity", "activity"),
            ]
        nav = '<nav class="workspace-nav" aria-label="Administrator">' + "".join(
            '<a class="' + ("active" if active == key else "") + '"'
            + (' aria-current="page"' if active == key else "")
            + ' href="' + path + '">' + label + "</a>"
            for path, label, key in links
        ) + "</nav>"
    elif user:
        links = [
            ("/app", "Overview", "overview"),
            ("/app/sites", "Sites", "sites"),
            ("/app/audits", "Audit requests", "audits"),
            ("/app/settings", "Account", "settings"),
        ]
        nav = '<nav class="workspace-nav" aria-label="Customer">' + "".join(
            '<a class="' + ("active" if active == key else "") + '"'
            + (' aria-current="page"' if active == key else "")
            + ' href="' + path + '">' + label + "</a>"
            for path, label, key in links
        ) + "</nav>"
    else:
        links = [
            ("/how-it-works", "How it works"),
            ("/what-we-check", "What we check"),
            ("/security-and-privacy", "Security"),
        ]
        registration_link = (
            '<a class="nav-cta" href="/register">Create account</a>'
            if _public_registration_open()
            else ""
        )
        nav = '<nav class="public-nav" aria-label="Main">' + "".join(
            '<a href="' + path + '">' + label + "</a>" for path, label in links
        ) + '<a href="/login">Sign in</a>' + registration_link + '</nav>'
    notice_html = '<div class="notice" role="status">' + _e(notice) + "</div>" if notice else ""
    return HTMLResponse(
        '<!doctype html><html lang="en-NZ"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="theme-color" content="#f3f1e9"><meta name="description" content="'
        + _e("Website Auditor by CatalyxLabs: clear, evidence-led website reviews.")
        + '"><title>' + _e(title) + ' · CatalyxLabs Auditor</title>'
        '<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">'
        '<link rel="stylesheet" href="/static/site.css"></head><body>'
        '<a class="skip-link" href="#main">Skip to content</a>'
        '<header class="site-header"><a class="brand" href="/" aria-label="CatalyxLabs Auditor home">'
        '<span class="brand-mark" aria-hidden="true">C</span><span>Catalyx<span class="brand-light">Labs</span>'
        '<small>WEBSITE AUDITOR</small></span></a>' + nav + identity + '</header>' + notice_html
        + '<main id="main" tabindex="-1">' + body + '</main>'
        '<footer class="site-footer"><span>© CatalyxLabs · Website Auditor</span>'
        '<nav aria-label="Legal"><a href="/privacy">Privacy draft</a><a href="/terms">Terms draft</a>'
        '<a href="/security-and-privacy">Security</a></nav></footer></body></html>',
        status_code=status,
    )


def _button(label: str, tone="primary") -> str:
    return '<button class="button ' + tone + '" type="submit">' + _e(label) + "</button>"


def _form_csrf(user=None, request=None) -> str:
    token = user["csrf_token"] if user else request.cookies.get("catalyx_pre_csrf", "")
    if not user and not token:
        token = getattr(request.state, "pre_csrf", None) or secrets.token_urlsafe(32)
        request.state.pre_csrf = token
    return '<input type="hidden" name="csrf" value="' + _e(token) + '">'


def _parse_form(request: Request) -> dict[str, str]:
    # Forms are urlencoded; avoiding a multipart parser keeps the app's upload surface closed.
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/x-www-form-urlencoded":
        raise HTTPException(415, "Form content type is not supported")
    body = request.scope.get("_form_body", b"")
    values = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
    return {key: items[-1] for key, items in values.items()}


def _check_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    expected = str(request.base_url).rstrip("/")
    if origin and not hmac.compare_digest(origin.rstrip("/"), expected):
        raise HTTPException(403, "Request origin rejected")


def _state_label(state: str) -> str:
    labels = {
        "authorization_review": "Waiting for authorization review",
        "queued": "Approved · waiting for the secure scan worker",
        "running": "In progress",
        "quality_review": "Report quality review",
        "released": "Report ready",
        "denied": "Not approved",
        "cancelled": "Cancelled",
        "failed": "Unable to complete",
        "expired": "Expired",
        "withheld": "Report withheld",
        "deletion_pending": "Deletion requested",
        "deleted": "Deleted",
    }
    return labels.get(state, "Status unavailable")


def _table(rows: list[str], headings: list[str], empty: str, colspan=None) -> str:
    head = "".join("<th scope=\"col\">" + _e(item) + "</th>" for item in headings)
    if rows:
        body = "".join(rows)
    else:
        body = '<tr><td class="empty-cell" colspan="' + str(colspan or len(headings)) + '">' + _e(empty) + "</td></tr>"
    return '<div class="table-wrap"><table><thead><tr>' + head + "</tr></thead><tbody>" + body + "</tbody></table></div>"


def _customer_export(db, user_id: str, workspace_id: str) -> dict:
    """Build a minimized export from records owned by one customer account."""
    account = db.execute(
        "SELECT id,email,email_verified_at,created_at,disabled_at FROM users WHERE id=?",
        (user_id,),
    ).fetchone()
    membership = db.execute(
        "SELECT role,active,created_at FROM memberships WHERE user_id=? AND workspace_id=?",
        (user_id, workspace_id),
    ).fetchone()
    workspace = db.execute(
        "SELECT id,name,created_at FROM workspaces WHERE id=?",
        (workspace_id,),
    ).fetchone()
    sites = db.execute(
        "SELECT id,origin,host,label,created_at,deleted_at FROM sites "
        "WHERE workspace_id=? AND created_by=? ORDER BY created_at",
        (workspace_id, user_id),
    ).fetchall()
    audits = db.execute(
        "SELECT a.id,a.profile,a.state,a.created_at,a.updated_at,a.review_reason,s.host "
        "FROM audit_requests a JOIN sites s ON s.id=a.site_id "
        "WHERE a.workspace_id=? AND a.requested_by=? ORDER BY a.created_at",
        (workspace_id, user_id),
    ).fetchall()
    authorizations = db.execute(
        "SELECT id,site_id,statement,version,recorded_at FROM authorization_receipts "
        "WHERE workspace_id=? AND user_id=? ORDER BY recorded_at",
        (workspace_id, user_id),
    ).fetchall()
    released_reports = db.execute(
        "SELECT a.id audit_id,s.host,result.schema_version,result.profile,result.report_json,"
        "result.report_hash,result.created_at FROM audit_requests a "
        "JOIN sites s ON s.id=a.site_id "
        "JOIN audit_results result ON result.audit_id=a.id AND result.workspace_id=a.workspace_id "
        "JOIN report_releases release ON release.audit_id=a.id AND release.state='released' "
        "WHERE a.workspace_id=? AND a.requested_by=? ORDER BY result.created_at",
        (workspace_id, user_id),
    ).fetchall()
    privacy_requests = db.execute(
        "SELECT id,request_type,state,customer_note,created_at,updated_at "
        "FROM privacy_requests WHERE workspace_id=? AND user_id=? ORDER BY created_at",
        (workspace_id, user_id),
    ).fetchall()
    reports = []
    for row in released_reports:
        report = dict(row)
        report["report"] = json.loads(report.pop("report_json"))
        reports.append(report)
    return {
        "format": "catalyx-customer-data-export-v1",
        "exported_at": now_iso(),
        "account": dict(account) if account else None,
        "membership": dict(membership) if membership else None,
        "workspace": dict(workspace) if workspace else None,
        "sites": [dict(row) for row in sites],
        "audit_requests": [dict(row) for row in audits],
        "authorization_receipts": [dict(row) for row in authorizations],
        "released_reports": reports,
        "privacy_requests": [dict(row) for row in privacy_requests],
    }


def create_app(db_path: str | Path | None = None, local_mailbox_path: str | Path | None = None) -> FastAPI:
    hosted = production_mode()
    deployed = production_deployment()
    registration_mode = os.getenv(
        "CATALYX_REGISTRATION_MODE", "closed" if hosted else "open"
    ).strip().lower()
    if registration_mode not in {"closed", "open"}:
        raise RuntimeError("CATALYX_REGISTRATION_MODE must be closed or open.")
    mail_mode = os.getenv("CATALYX_MAIL_MODE", "smtp" if hosted else "local_mailbox").strip().lower()
    if mail_mode not in {"smtp", "local_mailbox"}:
        raise RuntimeError("CATALYX_MAIL_MODE must be smtp or local_mailbox.")
    if hosted:
        required = []
        database_url = os.getenv("CATALYX_DATABASE_URL", "").strip()
        public_url = os.getenv("CATALYX_PUBLIC_BASE_URL", "").strip()
        if not database_url.startswith(("postgres://", "postgresql://")):
            required.append("CATALYX_DATABASE_URL must point to PostgreSQL.")
        if not public_url.startswith("https://"):
            required.append("CATALYX_PUBLIC_BASE_URL must be a fixed HTTPS URL.")
        else:
            public_parts = urlsplit(public_url)
            try:
                public_parts.port
            except ValueError:
                required.append("CATALYX_PUBLIC_BASE_URL has an invalid port.")
            if (
                not public_parts.hostname
                or public_parts.username
                or public_parts.password
                or public_parts.path not in {"", "/"}
                or public_parts.query
                or public_parts.fragment
            ):
                required.append("CATALYX_PUBLIC_BASE_URL must contain only an HTTPS origin.")
        if mail_mode != "smtp":
            required.append("CATALYX_MAIL_MODE must be smtp.")
        else:
            try:
                smtp_configuration()
            except MailConfigurationError as exc:
                required.append(str(exc))
        if not os.getenv("CATALYX_TOTP_ENCRYPTION_KEY", "").strip():
            required.append("CATALYX_TOTP_ENCRYPTION_KEY is required.")
        if required:
            raise RuntimeError("Hosted startup configuration is incomplete " + " ".join(required))
    if hosted:
        path = os.getenv("CATALYX_DATABASE_URL", "").strip()
    else:
        path = db_path or os.getenv("CATALYX_DATABASE_URL") or os.getenv("CATALYX_DB_PATH", "state/catalyx-app.sqlite3")
    database = Database(path, initialize=not hosted)
    mailbox_path = Path(local_mailbox_path or os.getenv("CATALYX_LOCAL_MAILBOX", "state/catalyx-local-mailbox.json")).expanduser().resolve()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["localhost", "127.0.0.1", "testserver", "*.vercel.app", "catalyxlabs.com", "www.catalyxlabs.com"],
    )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.state.database = database
    app.state.registration_mode = registration_mode
    app.state.local_mailbox_path = mailbox_path
    app.state.local_mailbox = []
    app.state.scan_worker_enabled = False
    app.state.runtime_environment = "production" if deployed else "staging"
    app.state.dummy_password_hash = hash_password(new_token())

    def _read_local_messages() -> list[dict]:
        try:
            messages = json.loads(mailbox_path.read_text(encoding="utf-8")) if mailbox_path.exists() else []
        except (json.JSONDecodeError, OSError):
            messages = []
        if not isinstance(messages, list):
            return []
        current_time = int(time.time())
        return [
            message
            for message in messages
            if isinstance(message, dict)
            and isinstance(message.get("verification_url"), str)
            and isinstance(message.get("expires_at"), int)
            and message["expires_at"] > current_time
        ][-50:]

    def _write_local_messages(messages: list[dict]) -> None:
        mailbox_path.parent.mkdir(parents=True, exist_ok=True)
        saved = messages[-50:]
        mailbox_path.write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")
        mailbox_path.chmod(0o600)

    def _prune_local_messages(consumed_token: str | None = None) -> list[dict]:
        messages = _read_local_messages()
        if consumed_token:
            messages = [
                message
                for message in messages
                if urlsplit(message["verification_url"]).fragment != consumed_token
            ]
        app.state.local_mailbox[:] = messages
        if mailbox_path.exists():
            _write_local_messages(messages)
        return messages

    def _save_local_message(email: str, kind: str, link: str, expires_at: int) -> None:
        messages = _prune_local_messages()
        messages.append(
            {
                "email": email,
                "kind": kind,
                "verification_url": link,
                "created_at": now_iso(),
                "expires_at": expires_at,
            }
        )
        app.state.local_mailbox[:] = messages[-50:]
        _write_local_messages(app.state.local_mailbox)

    if mail_mode == "local_mailbox" and not deployed:
        _prune_local_messages()

    def _apply_security_headers(request: Request, response: Response) -> Response:
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
            "base-uri 'none'; form-action 'self'; frame-ancestors 'none'; object-src 'none'"
        )
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            try:
                content_length = int(request.headers.get("content-length", "0"))
            except ValueError:
                return _apply_security_headers(request, Response("Invalid content length", status_code=400))
            if content_length > MAX_FORM_BYTES:
                return _apply_security_headers(request, Response("Request too large", status_code=413))
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > MAX_FORM_BYTES:
                    return _apply_security_headers(request, Response("Request too large", status_code=413))
            request.scope["_form_body"] = bytes(body)
        response = await call_next(request)
        return _apply_security_headers(request, response)

    def _session(request: Request, required=True):
        token = request.cookies.get("catalyx_session", "")
        if not token:
            if required:
                raise HTTPException(401, "Sign in required")
            return None
        with database.connect() as db:
            row = db.execute(
                "SELECT s.user_id,s.workspace_id,s.csrf_token,s.expires_at,u.email,u.disabled_at,u.email_verified_at,m.role,m.active "
                "FROM sessions s JOIN users u ON u.id=s.user_id "
                "JOIN memberships m ON m.user_id=s.user_id AND m.workspace_id=s.workspace_id "
                "WHERE s.token_hash=?",
                (digest_token(token),),
            ).fetchone()
            if not row or row["expires_at"] <= int(time.time()) or row["disabled_at"] or not row["active"]:
                if row:
                    db.execute("DELETE FROM sessions WHERE token_hash=?", (digest_token(token),))
                if required:
                    raise HTTPException(401, "Sign in required")
                return None
            if not row["email_verified_at"] and required:
                raise HTTPException(403, "Verify your email address before continuing")
            return dict(row)

    def _need_role(user: dict, allowed: set[str]):
        if user["role"] not in allowed:
            raise HTTPException(403, "You do not have access to this page")

    def _check_csrf(request: Request, form: dict[str, str], user=None):
        _check_origin(request)
        expected = user["csrf_token"] if user else request.cookies.get("catalyx_pre_csrf", "")
        supplied = form.get("csrf", "")
        if not expected or not hmac.compare_digest(expected, supplied):
            raise HTTPException(403, "Refresh the page and try again")

    def _current_user_or_login(request: Request):
        try:
            user = _session(request)
        except HTTPException as exc:
            if exc.status_code in (401, 403):
                return None
            raise
        return user

    def _form_page(title, intro, form, *, user=None, request=None, notice="", status=200):
        body = (
            '<section class="auth-wrap"><p class="eyebrow">CATALYXLABS · WEBSITE AUDITOR</p>'
            '<h1>' + _e(title) + '</h1><p class="lead narrow">' + intro + '</p>'
            + notice_html(notice) + form + '</section>'
        )
        response = _page(title, body, user=user, notice="", status=status)
        if request and not user and not request.cookies.get("catalyx_pre_csrf"):
            response.set_cookie(
                "catalyx_pre_csrf", getattr(request.state, "pre_csrf", secrets.token_urlsafe(32)), httponly=True,
                samesite="strict", secure=production_mode(), max_age=900, path="/",
            )
        return response

    @app.get("/api/health")
    def health():
        return {"status": "ok", "environment": app.state.runtime_environment, "scan_worker": "disabled"}

    @app.get("/api/health/live")
    def health_live():
        return {"status": "ok"}

    @app.get("/api/health/ready")
    def health_ready():
        try:
            integrity = database.integrity_check()
            with database.connect() as db:
                db.execute("SELECT count(*) FROM audit_requests").fetchone()
            if integrity != "ok":
                raise DatabaseError("Application database is not ready")
        except DatabaseError:
            return Response(
                json.dumps({"status": "not_ready", "database": "unavailable"}),
                status_code=503,
                media_type="application/json",
            )
        return {"status": "ready", "database": "ok", "queue": "ok", "scan_worker": "disabled"}

    def _api_payload(request: Request) -> dict:
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise HTTPException(415, "Send a JSON request body")
        try:
            payload = json.loads(request.scope.get("_form_body", b"").decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise HTTPException(400, "The JSON request body is invalid") from None
        if not isinstance(payload, dict):
            raise HTTPException(400, "The JSON request body must be an object")
        return payload

    def _api_csrf(request: Request, user: dict) -> None:
        _check_origin(request)
        supplied = request.headers.get("x-csrf-token", "")
        if not supplied or not hmac.compare_digest(user["csrf_token"], supplied):
            raise HTTPException(403, "Refresh your session and try again")

    @app.get("/api/v1/me")
    def api_me(request: Request):
        user = _session(request)
        return {
            "user_id": user["user_id"],
            "email": user["email"],
            "role": user["role"],
            "workspace_id": user["workspace_id"],
            "csrf_token": user["csrf_token"],
        }

    @app.get("/api/v1/sites")
    def api_sites(request: Request):
        user = _session(request)
        _need_role(user, {"customer"})
        with database.connect() as db:
            rows = db.execute(
                "SELECT id,origin,host,label,created_at FROM sites "
                "WHERE workspace_id=? AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 100",
                (user["workspace_id"],),
            ).fetchall()
        return {"sites": [dict(row) for row in rows]}

    @app.post("/api/v1/sites")
    async def api_create_site(request: Request):
        user = _session(request)
        _need_role(user, {"customer"})
        _api_csrf(request, user)
        payload = _api_payload(request)
        try:
            origin, host = normalize_site(str(payload.get("url", "")))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        label = str(payload.get("label", "")).strip()[:100] or host
        site_id = str(uuid.uuid4())
        with database.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute(
                "SELECT count(*) FROM sites WHERE workspace_id=? AND deleted_at IS NULL",
                (user["workspace_id"],),
            ).fetchone()[0]
            if count >= 20:
                raise HTTPException(429, "A workspace can register up to 20 websites in this preview")
            try:
                db.execute(
                    "INSERT INTO sites(id,workspace_id,origin,host,label,created_by,created_at) VALUES(?,?,?,?,?,?,?)",
                    (site_id, user["workspace_id"], origin, host, label, user["user_id"], now_iso()),
                )
            except DatabaseIntegrityError:
                raise HTTPException(409, "This website origin is already registered") from None
            row = db.execute(
                "SELECT id,origin,host,label,created_at FROM sites WHERE id=?", (site_id,)
            ).fetchone()
        return Response(
            json.dumps({"site": dict(row)}),
            status_code=201,
            media_type="application/json",
        )

    @app.get("/api/v1/sites/{site_id}")
    def api_site_detail(request: Request, site_id: str):
        user = _session(request)
        _need_role(user, {"customer"})
        with database.connect() as db:
            site = db.execute(
                "SELECT id,origin,host,label,created_at FROM sites "
                "WHERE id=? AND workspace_id=? AND deleted_at IS NULL",
                (site_id, user["workspace_id"]),
            ).fetchone()
            if not site:
                raise HTTPException(404, "Website not found")
            audits = db.execute(
                "SELECT id,state,created_at,updated_at FROM audit_requests "
                "WHERE site_id=? AND workspace_id=? ORDER BY created_at DESC LIMIT 100",
                (site_id, user["workspace_id"]),
            ).fetchall()
        return {"site": dict(site), "audits": [dict(row) for row in audits]}

    @app.post("/api/v1/sites/{site_id}/audits")
    async def api_create_audit(request: Request, site_id: str):
        user = _session(request)
        _need_role(user, {"customer"})
        _api_csrf(request, user)
        payload = _api_payload(request)
        if payload.get("authorized") is not True:
            raise HTTPException(400, "Authorization confirmation is required")
        key = request.headers.get("idempotency-key", str(payload.get("idempotency_key", "")))
        if not key or len(key) > 80:
            raise HTTPException(400, "Provide a valid Idempotency-Key")
        timestamp = now_iso()
        with database.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            site = db.execute(
                "SELECT id FROM sites WHERE id=? AND workspace_id=? AND deleted_at IS NULL",
                (site_id, user["workspace_id"]),
            ).fetchone()
            if not site:
                raise HTTPException(404, "Website not found")
            existing = db.execute(
                "SELECT id,state FROM audit_requests WHERE workspace_id=? AND idempotency_key=?",
                (user["workspace_id"], key),
            ).fetchone()
            if existing:
                return {"audit": dict(existing), "created": False}
            cutoff = datetime.fromtimestamp(time.time() - 3600, UTC).isoformat(timespec="seconds")
            recent = db.execute(
                "SELECT count(*) FROM audit_requests WHERE workspace_id=? AND created_at>=?",
                (user["workspace_id"], cutoff),
            ).fetchone()[0]
            if recent >= 10:
                raise HTTPException(429, "This workspace has reached the hourly request limit")
            audit_id, authorization_id = str(uuid.uuid4()), str(uuid.uuid4())
            db.execute(
                "INSERT INTO authorization_receipts(id,workspace_id,site_id,user_id,statement,version,recorded_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (authorization_id, user["workspace_id"], site_id, user["user_id"], CONSENT_TEXT, CONSENT_VERSION, timestamp),
            )
            db.execute(
                "INSERT INTO audit_requests(id,workspace_id,site_id,requested_by,authorization_id,profile,state,idempotency_key,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (audit_id, user["workspace_id"], site_id, user["user_id"], authorization_id, "static", "authorization_review", key, timestamp, timestamp),
            )
        return Response(
            json.dumps({"audit": {"id": audit_id, "state": "authorization_review"}, "created": True}),
            status_code=201,
            media_type="application/json",
        )

    @app.get("/api/v1/audits")
    def api_audits(request: Request):
        user = _session(request)
        _need_role(user, {"customer"})
        with database.connect() as db:
            rows = db.execute(
                "SELECT a.id,a.state,a.created_at,a.updated_at,s.host FROM audit_requests a "
                "JOIN sites s ON s.id=a.site_id WHERE a.workspace_id=? ORDER BY a.created_at DESC LIMIT 100",
                (user["workspace_id"],),
            ).fetchall()
        return {"audits": [dict(row) for row in rows]}

    @app.get("/api/v1/audits/{audit_id}")
    def api_audit_detail(request: Request, audit_id: str):
        user = _session(request)
        _need_role(user, {"customer"})
        with database.connect() as db:
            row = db.execute(
                "SELECT a.id,a.state,a.created_at,a.updated_at,s.host,"
                "CASE WHEN rr.state='released' THEN ar.report_json ELSE NULL END report_json "
                "FROM audit_requests a JOIN sites s ON s.id=a.site_id "
                "LEFT JOIN audit_results ar ON ar.audit_id=a.id AND ar.workspace_id=a.workspace_id "
                "LEFT JOIN report_releases rr ON rr.audit_id=a.id AND rr.state='released' "
                "WHERE a.id=? AND a.workspace_id=?",
                (audit_id, user["workspace_id"]),
            ).fetchone()
        if not row:
            raise HTTPException(404, "Audit request not found")
        result = dict(row)
        report = result.pop("report_json")
        result["report"] = json.loads(report) if report else None
        return {"audit": result}

    @app.post("/api/v1/audits/{audit_id}/cancel")
    async def api_cancel_audit(request: Request, audit_id: str):
        user = _session(request)
        _need_role(user, {"customer"})
        _api_csrf(request, user)
        with database.connect() as db:
            result = db.execute(
                "UPDATE audit_requests SET state='cancelled',updated_at=?,review_reason='Cancelled by customer',worker_lease_until=NULL,worker_lease_token=NULL "
                "WHERE id=? AND workspace_id=? AND state IN ('authorization_review','queued','running')",
                (now_iso(), audit_id, user["workspace_id"]),
            )
            if result.rowcount != 1:
                exists = db.execute(
                    "SELECT id FROM audit_requests WHERE id=? AND workspace_id=?",
                    (audit_id, user["workspace_id"]),
                ).fetchone()
                if not exists:
                    raise HTTPException(404, "Audit request not found")
                raise HTTPException(409, "This request can no longer be cancelled")
            row = db.execute("SELECT id,state FROM audit_requests WHERE id=?", (audit_id,)).fetchone()
        return {"audit": dict(row)}

    @app.get("/api/v1/admin/overview")
    def api_admin_overview(request: Request):
        user = _session(request)
        _need_role(user, REVIEW_ROLES)
        with database.connect() as db:
            counts = {row["state"]: row["total"] for row in db.execute(
                "SELECT state,count(*) AS total FROM audit_requests GROUP BY state"
            )}
            customers = db.execute(
                "SELECT count(*) FROM users u JOIN memberships m ON m.user_id=u.id "
                "WHERE m.role='customer' AND m.active=1"
            ).fetchone()[0]
        return {"audit_states": counts, "active_customers": customers, "scan_worker": "disabled"}

    @app.get("/api/v1/admin/audits")
    def api_admin_audits(request: Request, state: str = ""):
        user = _session(request)
        _need_role(user, REVIEW_ROLES)
        valid_states = {"authorization_review", "queued", "running", "quality_review", "released", "denied", "failed", "withheld"}
        if state and state not in valid_states:
            raise HTTPException(400, "Unknown audit status")
        with database.connect() as db:
            query = (
                "SELECT a.id,a.state,a.created_at,a.updated_at,s.host,u.email FROM audit_requests a "
                "JOIN sites s ON s.id=a.site_id JOIN users u ON u.id=a.requested_by"
            )
            params: tuple = ()
            if state:
                query += " WHERE a.state=?"
                params = (state,)
            rows = db.execute(query + " ORDER BY a.created_at DESC LIMIT 200", params).fetchall()
        return {"audits": [dict(row) for row in rows]}

    @app.post("/api/v1/admin/audits/{audit_id}/decision")
    async def api_admin_decide_audit(request: Request, audit_id: str):
        user = _session(request)
        _need_role(user, REVIEW_ROLES)
        _api_csrf(request, user)
        payload = _api_payload(request)
        decision, reason = str(payload.get("decision", "")), str(payload.get("reason", "")).strip()
        if decision not in {"approve", "deny"} or len(reason) < 4 or len(reason) > 500:
            raise HTTPException(400, "Choose a decision and enter a reason")
        new_state = "queued" if decision == "approve" else "denied"
        with database.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id,state FROM audit_requests WHERE id=?", (audit_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Audit request not found")
            if row["state"] != "authorization_review":
                raise HTTPException(409, "This request has already been reviewed")
            changed = db.execute(
                "UPDATE audit_requests SET state=?,updated_at=?,reviewed_by=?,review_reason=? "
                "WHERE id=? AND state='authorization_review'",
                (new_state, now_iso(), user["user_id"], reason, audit_id),
            )
            if changed.rowcount != 1:
                raise HTTPException(409, "This request has already been reviewed")
            database.audit_admin(user, "audit_" + decision, "audit_request", audit_id, reason,
                                 {"from": "authorization_review", "to": new_state}, connection=db)
        return {"audit": {"id": audit_id, "state": new_state}}

    @app.post("/api/v1/admin/audits/{audit_id}/report-decision")
    async def api_admin_release_report(request: Request, audit_id: str):
        user = _session(request)
        _need_role(user, REVIEW_ROLES)
        _api_csrf(request, user)
        payload = _api_payload(request)
        decision, reason = str(payload.get("decision", "")), str(payload.get("reason", "")).strip()
        if decision not in {"release", "withhold"} or len(reason) < 4 or len(reason) > 500:
            raise HTTPException(400, "Choose whether to release or withhold the report and enter a reason")
        report_state = "released" if decision == "release" else "withheld"
        with database.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT a.state,r.report_hash FROM audit_requests a JOIN audit_results r ON r.audit_id=a.id WHERE a.id=?",
                (audit_id,),
            ).fetchone()
            if not row:
                raise HTTPException(404, "Report not found")
            if row["state"] != "quality_review":
                raise HTTPException(409, "This report is no longer awaiting review")
            db.execute(
                "INSERT INTO report_releases(audit_id,reviewer_id,state,reason,report_hash,created_at) VALUES(?,?,?,?,?,?)",
                (audit_id, user["user_id"], report_state, reason, row["report_hash"], now_iso()),
            )
            changed = db.execute(
                "UPDATE audit_requests SET state=?,updated_at=?,reviewed_by=?,review_reason=? WHERE id=? AND state='quality_review'",
                (report_state, now_iso(), user["user_id"], reason, audit_id),
            )
            if changed.rowcount != 1:
                raise HTTPException(409, "This report is no longer awaiting review")
            database.audit_admin(user, "report_" + decision, "audit_request", audit_id, reason,
                                 {"from": "quality_review", "to": report_state, "report_hash": row["report_hash"]}, connection=db)
        return {"audit": {"id": audit_id, "state": report_state}}

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        user = _current_user_or_login(request)
        if user:
            return RedirectResponse(_home_path_for_role(user["role"]), status_code=303)
        registration_action = (
            '<a class="button primary" href="/register">Create an account <span aria-hidden="true">↗</span></a>'
            if app.state.registration_mode == "open"
            else '<a class="button primary" href="/sample-report">View the sample report <span aria-hidden="true">↗</span></a>'
        )
        body = (
            '<section class="hero wrap"><div class="hero-copy"><p class="eyebrow">WEBSITE AUDITOR · CATALYXLABS</p>'
            '<h1>Find the evidence.<br><em>Choose the next fix.</em></h1>'
            '<p class="hero-lede">A clear review of the website details that shape how people find, understand, and use your business online.</p>'
            '<div class="actions">' + registration_action +
            '<a class="quiet-link" href="/how-it-works">See how it works <span aria-hidden="true">→</span></a></div>'
            '<p class="quiet-note">Audit requests are reviewed before work begins. Scanning is not enabled in this staging preview.</p></div>'
            '<aside class="report-teaser" aria-label="Illustrative report preview"><div class="report-top"><span class="live-dot"></span> ILLUSTRATIVE REPORT <span class="report-date">SAMPLE DATA</span></div>'
            '<div class="report-domain">morrow-electric.example</div><div class="report-line"><span>Page clarity</span><b>Review available</b></div>'
            '<div class="report-line"><span>Search metadata</span><b>3 checks shown</b></div><div class="report-line"><span>Technical signals</span><b>Evidence linked</b></div>'
            '<div class="report-foot"><span>Example only · no live site scan</span><a href="/sample-report">Open sample ↗</a></div></aside></section>'
            '<section class="proof-strip"><div><span class="strip-number">01</span><span>Every finding points to evidence</span></div>'
            '<div><span class="strip-number">02</span><span>Skipped checks stay visible</span></div><div><span class="strip-number">03</span><span>People choose what happens next</span></div></section>'
            '<section class="wrap split-section"><div><p class="eyebrow">A MORE USEFUL WEBSITE REVIEW</p><h2>Clear enough to act on.<br><em>Careful enough to trust.</em></h2></div>'
            '<div class="section-copy"><p>Website Auditor brings technical signals and page observations into one readable report. Each result shows what was checked, what was found, and where the evidence came from.</p>'
            '<p>It is a practical review, not a ranking promise, a compliance certificate, or proof of lost revenue.</p><a class="arrow-link" href="/what-we-check">Explore the current check areas <span aria-hidden="true">→</span></a></div></section>'
            '<section class="band"><div class="wrap band-inner"><div><p class="eyebrow">BUILT AROUND YOUR CONTROL</p><h2>Your site. Your permission.<br>Your decisions.</h2></div>'
            '<p>Requests include an authorization record and go to human review. Recommendations are for you to consider; the Auditor does not change your website.</p>'
            '<a class="button light" href="/security-and-privacy">How information is handled <span aria-hidden="true">↗</span></a></div></section>'
            '<section class="wrap final-cta"><p class="eyebrow">START WITH A CLEAR VIEW</p><h2>See what is there<br><em>before choosing what to do.</em></h2>'
            + registration_action + '</section>'
        )
        return _page("Evidence-led website reviews", body)

    @app.get("/how-it-works", response_class=HTMLResponse)
    def how_it_works():
        steps = [
            ("01", "Add a website", "Tell us the public website you manage and confirm you have permission to request a review."),
            ("02", "We review the request", "An administrator checks the authorization record and request before any audit work begins."),
            ("03", "Review the evidence", "When scanning is available, a report will distinguish findings, checks that passed, and checks that could not run."),
            ("04", "Choose your next step", "You decide whether to act on a recommendation. The Auditor does not edit or deploy changes to your site."),
        ]
        rows = "".join('<article class="step"><span>' + n + '</span><div><h2>' + h + '</h2><p>' + p + "</p></div></article>" for n,h,p in steps)
        body = '<section class="page-hero wrap"><p class="eyebrow">THE REVIEW JOURNEY</p><h1>Four steps from<br><em>question to evidence.</em></h1><p class="lead">A site review should make its limits as clear as its findings.</p></section><section class="wrap steps">' + rows + '</section><section class="wrap callout"><p><strong>Staging note:</strong> requests can be recorded for review, but the public scan worker is disabled while its network safety controls are being built and verified.</p></section>'
        return _page("How it works", body)

    @app.get("/what-we-check", response_class=HTMLResponse)
    def what_we_check():
        checks = [
            ("Page structure", "Titles, descriptions, canonical links, viewport metadata, image alternatives, and readable page content."),
            ("Structured data", "Whether common structured data is present; presence does not establish eligibility or correctness."),
            ("Technical responses", "The first page response, selected response headers, and supported security header signals."),
            ("Site hygiene", "Robots and sitemap signals, mixed content, and selected page links when the profile allows them."),
            ("Rendered checks", "Browser and accessibility checks are optional engine capabilities and are not enabled for this service."),
        ]
        rows = "".join('<article class="check-row"><span class="check-mark">+</span><div><h2>' + h + '</h2><p>' + p + "</p></div></article>" for h,p in checks)
        body = '<section class="page-hero wrap"><p class="eyebrow">THE AUDIT ENGINE</p><h1>Specific checks.<br><em>Visible limits.</em></h1><p class="lead">The manual staging profile checks one public page after an administrator approves a request. The customer web service does not start scans automatically.</p></section><section class="wrap check-list">' + rows + '</section><section class="wrap callout"><p>The fixed profile checks page metadata, structured data, selected response headers, mixed content, and robots.txt. Deep crawling, browser checks, accessibility rendering, and external tools stay disabled. Missing evidence and unavailable checks are not proof of a defect.</p></section>'
        return _page("What we check", body)

    @app.get("/security-and-privacy", response_class=HTMLResponse)
    def security_page():
        body = '<section class="page-hero wrap"><p class="eyebrow">SECURITY &amp; PRIVACY</p><h1>Permission first.<br><em>Data kept to purpose.</em></h1><p class="lead">Here is what this staging build does today, and what still needs an owner decision before public launch.</p></section><section class="wrap prose-grid"><article><h2>In this preview</h2><p>Account passwords are stored as one-way hashes. Sessions use opaque, expiring cookies. Site requests are scoped to a workspace, and administrator actions record who acted and why.</p><p>The app itself does not scan customer sites. An operator can invoke a manual local staging worker for an approved request; it checks one page and stores a sanitized report for review.</p></article><article><h2>Before production</h2><p>Hosting, data region, email delivery, retention, backup and restoration, support contacts, and final legal wording still need approval and verification.</p><p>The manual worker is not OS-isolated. Production needs an isolated worker and independently enforced egress controls in addition to the pinned connection checks.</p></article></section><section class="wrap callout"><p>This page describes the staging implementation, not an independent security certification or legal privacy notice.</p></section>'
        return _page("Security and privacy", body)

    @app.get("/pricing", response_class=HTMLResponse)
    def pricing():
        body = '<section class="page-hero wrap"><p class="eyebrow">PRICING</p><h1>Pricing is<br><em>not available yet.</em></h1><p class="lead">The service is being prepared. No price or paid plan has been approved.</p></section><section class="wrap callout"><p>Billing is disabled. We will publish terms only after the owner approves the offer, currency, tax treatment, and payment setup.</p></section>'
        return _page("Pricing", body)

    @app.get("/sample-report", response_class=HTMLResponse)
    def sample_report():
        body = '<section class="page-hero wrap"><p class="eyebrow">SYNTHETIC EXAMPLE</p><h1>What evidence<br><em>looks like in a report.</em></h1><p class="lead">This fictional example demonstrates the report format. No website was scanned and the findings do not describe a real business.</p></section><section class="wrap report-example"><div class="report-example-head"><div><p class="eyebrow">SAMPLE SITE</p><h2>morrow-electric.example</h2></div><span class="sample-badge">ILLUSTRATIVE ONLY</span></div><article class="finding"><span class="severity medium">REVIEW</span><div><h3>Page title is missing</h3><p><b>Evidence:</b> the sample page contains no title element.</p><p><b>Why it matters:</b> search previews may fall back to other page text.</p><p><b>Suggested next step:</b> add a concise title that describes this page.</p></div></article><article class="finding"><span class="severity neutral">NOT RUN</span><div><h3>Keyboard access review</h3><p>This check was not run in the fictional example. Its status is not a pass or a failure.</p></div></article><p class="report-disclaimer">A real report will show its run time, profile, evidence, and incomplete checks. A score is only a summary of measured checks.</p></section>'
        return _page("Illustrative sample report", body)

    def _public_draft(title: str, kind: str):
        body = '<section class="page-hero wrap"><p class="eyebrow">OWNER REVIEW REQUIRED</p><h1>' + _e(title) + '</h1><p class="lead">This page is a staging placeholder. CatalyxLabs must approve the final wording and business details before public launch.</p></section><section class="wrap callout"><p>No legal entity, postal address, support email, or retention promise has been invented for this preview.</p></section>'
        return _page(title + " draft", body)

    @app.get("/privacy", response_class=HTMLResponse)
    def privacy_draft():
        return _public_draft("Privacy notice", "privacy")

    @app.get("/terms", response_class=HTMLResponse)
    def terms_draft():
        return _public_draft("Terms of service", "terms")

    @app.get("/register", response_class=HTMLResponse)
    def register_page(request: Request):
        if app.state.registration_mode != "open":
            raise HTTPException(404, "Account registration is not open.")
        mail_note = (
            "A one-time verification link will be sent to your email address."
            if mail_mode == "smtp"
            else "A one-time verification link is saved to the private local staging mailbox."
        )
        form = '<form method="post" action="/register" class="form-stack">' + _form_csrf(request=request) + '<label>Email address<input type="email" name="email" autocomplete="email" required maxlength="254"></label><label>Password<input type="password" name="password" autocomplete="new-password" minlength="12" required><small>Use at least 12 characters.</small></label><label>Confirm password<input type="password" name="password_confirm" autocomplete="new-password" minlength="12" required></label><p class="form-note">' + _e(mail_note) + '</p>' + _button("Create account") + '</form><p class="auth-switch">Already registered? <a href="/login">Sign in</a></p>'
        return _form_page("A clearer view starts here", "Create a customer account to register a site for review.", form, request=request)

    @app.post("/register")
    async def register(request: Request):
        if app.state.registration_mode != "open":
            raise HTTPException(404, "Account registration is not open.")
        form = _parse_form(request)
        _check_csrf(request, form)
        _check_origin(request)
        address = request.client.host if request.client else "unknown"
        if not database.allow_rate_attempt("register", address, 5, 3600):
            raise HTTPException(429, "Registration limit reached. Try again later.")
        email = form.get("email", "").strip().lower()
        password = form.get("password", "")
        if not valid_email_address(email):
            return _form_page("A clearer view starts here", "Create a customer account to register a site for review.", "<p class=\"form-error\" role=\"alert\" aria-atomic=\"true\">Enter a valid email address.</p>" + register_form(request), request=request, status=400)
        if password != form.get("password_confirm"):
            return _form_page("A clearer view starts here", "Create a customer account to register a site for review.", "<p class=\"form-error\" role=\"alert\" aria-atomic=\"true\">The passwords do not match.</p>" + register_form(request), request=request, status=400)
        try:
            password_hash = hash_password(password)
            user_id, _ = database.create_customer(email, password_hash)
        except ValueError as exc:
            return _form_page("A clearer view starts here", "Create a customer account to register a site for review.", "<p class=\"form-error\" role=\"alert\" aria-atomic=\"true\">" + _e(exc) + "</p>" + register_form(request), request=request, status=400)
        except DatabaseIntegrityError:
            # Keep the response neutral to avoid disclosing registered addresses.
            return _form_page("Check your email", "If the address can be registered, a verification link will be sent.", '<p class="callout-text">Follow the verification instructions, then sign in.</p><a class="button primary" href="/login">Continue to sign in</a>', request=request)
        verify_token = new_token()
        verify_expires_at = int(time.time()) + 3600
        with database.connect() as db:
            db.execute("DELETE FROM verification_tokens WHERE expires_at<=?", (int(time.time()),))
            db.execute(
                "INSERT INTO verification_tokens(token_hash,user_id,expires_at,created_at) VALUES(?,?,?,?)",
                (digest_token(verify_token), user_id, verify_expires_at, now_iso()),
            )
        verification_url = _public_base_url(request) + "/verify#" + quote(verify_token)
        if mail_mode == "local_mailbox" and not deployed:
            # Keep the bearer token in the URL fragment so access logs and
            # referrer headers never receive it. verify.js moves it to a POST body.
            _save_local_message(email, "email_verification", verification_url, verify_expires_at)
            logger.info("Local email verification saved to the private staging mailbox")
        else:
            try:
                await asyncio.to_thread(send_account_link, email, "email_verification", verification_url)
            except MailDeliveryError:
                logger.warning("Account verification email could not be delivered")
        body = '<section class="auth-wrap"><p class="eyebrow">EMAIL VERIFICATION</p><h1>Check your inbox</h1><p class="lead narrow">A verification link is required before you can add a site or request an audit.</p><a class="button primary" href="/login">Continue to sign in</a><p class="auth-switch">Didn’t receive a message? <a href="/resend-verification">Request another verification link</a></p></section>'
        return _page("Check your email", body, notice="Account created. Verify your email to continue.")

    @app.get("/resend-verification", response_class=HTMLResponse)
    def resend_verification_page(request: Request):
        form = '<form method="post" action="/resend-verification" class="form-stack">' + _form_csrf(request=request) + '<label>Email address<input type="email" name="email" autocomplete="email" required maxlength="254"></label>' + _button("Send verification link") + '</form><p class="auth-switch"><a href="/login">Back to sign in</a></p>'
        return _form_page("Resend verification", "If the account needs verification, we will send a new one-time link.", form, request=request)

    @app.post("/resend-verification")
    async def resend_verification(request: Request):
        form = _parse_form(request)
        _check_csrf(request, form)
        _check_origin(request)
        address = request.client.host if request.client else "unknown"
        email = form.get("email", "").strip().lower()
        resend_message = None
        if database.allow_rate_attempt("verification_resend", address, 5, 3600):
            with database.connect() as db:
                row = db.execute(
                    "SELECT id FROM users WHERE email=? AND email_verified_at IS NULL AND disabled_at IS NULL",
                    (email,),
                ).fetchone()
                if row:
                    db.execute(
                        "DELETE FROM verification_tokens WHERE user_id=? OR expires_at<=?",
                        (row["id"], int(time.time())),
                    )
                    token = new_token()
                    token_expires_at = int(time.time()) + 3600
                    db.execute(
                        "INSERT INTO verification_tokens(token_hash,user_id,expires_at,created_at) VALUES(?,?,?,?)",
                        (digest_token(token), row["id"], token_expires_at, now_iso()),
                    )
                    link = _public_base_url(request) + "/verify#" + quote(token)
                    resend_message = (email, link, token_expires_at)
        if resend_message:
            if mail_mode == "local_mailbox" and not deployed:
                _save_local_message(
                    resend_message[0], "email_verification", resend_message[1], resend_message[2]
                )
            else:
                try:
                    await asyncio.to_thread(send_account_link, resend_message[0], "email_verification", resend_message[1])
                except MailDeliveryError:
                    logger.warning("Verification resend email could not be delivered")
        body = '<section class="auth-wrap"><p class="eyebrow">EMAIL VERIFICATION</p><h1>Check your inbox</h1><p class="lead narrow">If the account needs verification, a new one-time link is on its way.</p><a class="button primary" href="/login">Return to sign in</a></section>'
        return _page("Check your email", body)

    @app.get("/verify", response_class=HTMLResponse)
    def verify_email_page():
        body = '<section class="auth-wrap"><p class="eyebrow">EMAIL VERIFICATION</p><h1>Confirm your address</h1><p class="lead narrow">Use the one-time link sent when you created your account.</p><form method="post" action="/verify" class="form-stack" id="verify-form"><input type="hidden" name="token" id="verification-token" value=""><p id="verification-hint" class="form-note">If the button stays unavailable, open the original verification link again.</p><button class="button primary" type="submit" id="verify-button" disabled>Verify email</button></form></section>'
        response = _page("Confirm your email", body)
        page_html = response.body.decode("utf-8").replace(
            "</body>", '<script src="/static/verify.js" defer></script></body>'
        )
        return HTMLResponse(page_html)

    @app.post("/verify", response_class=HTMLResponse)
    async def verify_email(request: Request):
        form = _parse_form(request)
        token = form.get("token", "")
        if not token or len(token) > 128:
            return _page("Verification link unavailable", '<section class="auth-wrap"><h1>Verification link unavailable</h1><p class="lead">Request a new account verification link or sign in.</p><a href="/register">Create an account</a></section>', status=400)
        with database.connect() as db:
            row = db.execute("SELECT user_id,expires_at FROM verification_tokens WHERE token_hash=?", (digest_token(token),)).fetchone()
            if not row or row["expires_at"] <= int(time.time()):
                return _page("Verification link expired", '<section class="auth-wrap"><h1>This link has expired</h1><p class="lead">Create a new account or contact the site administrator.</p><a href="/register">Create an account</a></section>', status=400)
            db.execute("UPDATE users SET email_verified_at=? WHERE id=?", (now_iso(), row["user_id"]))
            db.execute("DELETE FROM verification_tokens WHERE token_hash=?", (digest_token(token),))
        if mail_mode == "local_mailbox" and not deployed:
            _prune_local_messages(consumed_token=token)
        return _page("Email verified", '<section class="auth-wrap"><p class="eyebrow">READY TO SIGN IN</p><h1>Email verified</h1><p class="lead">Your address is confirmed. Sign in to register a website for review.</p><a class="button primary" href="/login">Sign in</a></section>')

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request, next: str = ""):
        if request.cookies.get("catalyx_session"):
            user = _current_user_or_login(request)
            if user:
                return RedirectResponse(_home_path_for_role(user["role"]), status_code=303)
        return _form_page("Welcome back", "Sign in to continue to your private workspace.", login_form(request, next), request=request)

    @app.post("/login")
    async def login(request: Request):
        form = _parse_form(request)
        _check_csrf(request, form)
        _check_origin(request)
        address = request.client.host if request.client else "unknown"
        if not database.allow_rate_attempt("login", address, 8, 60):
            raise HTTPException(429, "Too many sign-in attempts. Try again in one minute.")
        email = form.get("email", "").strip().lower()
        if not database.rate_attempt_available("login_account", email, 12, 3600):
            raise HTTPException(429, "Too many sign-in attempts. Try again later.")
        with database.connect() as db:
            row = db.execute(
                "SELECT u.id,u.email,u.password_hash,u.email_verified_at,u.disabled_at,m.workspace_id,m.role,m.totp_secret "
                "FROM users u JOIN memberships m ON m.user_id=u.id AND m.active=1 WHERE u.email=? ORDER BY m.created_at LIMIT 1",
                (email,),
            ).fetchone()
        password_hash = row["password_hash"] if row else app.state.dummy_password_hash
        password_valid = verify_password(form.get("password", ""), password_hash)
        valid = bool(row and not row["disabled_at"] and password_valid)
        if not valid or not row["email_verified_at"]:
            database.allow_rate_attempt("login_account", email, 12, 3600)
            response = _form_page("Welcome back", "Sign in to continue to your private workspace.", '<p class="form-error" role="alert" aria-atomic="true">Sign-in unavailable. Check your email verification link or try your details again.</p>' + login_form(request), request=request, status=401)
            return response
        if row["role"] in PRIVILEGED_ROLES:
            totp_secret = (
                database.decrypt_totp_secret(row["totp_secret"], row["workspace_id"], row["id"])
                if row["totp_secret"]
                else ""
            )
            if not totp_secret or not verify_totp(totp_secret, form.get("otp", "")):
                database.allow_rate_attempt("login_account", email, 12, 3600)
                response = _form_page("Welcome back", "Sign in to continue to your private workspace.", '<p class="form-error" role="alert" aria-atomic="true">Sign-in unavailable. Check your authenticator code and try again.</p>' + login_form(request, require_otp=True), request=request, status=401)
                return response
        database.clear_rate_attempts("login_account", email)
        token = new_token()
        csrf_token = new_token()
        with database.connect() as db:
            db.execute("DELETE FROM sessions WHERE expires_at<=?", (int(time.time()),))
            db.execute("DELETE FROM sessions WHERE user_id=?", (row["id"],))
            db.execute(
                "INSERT INTO sessions(token_hash,user_id,workspace_id,csrf_token,expires_at,created_at) VALUES(?,?,?,?,?,?)",
                (digest_token(token), row["id"], row["workspace_id"], csrf_token, int(time.time()) + SESSION_SECONDS, now_iso()),
            )
        response = RedirectResponse(_home_path_for_role(row["role"]), status_code=303)
        response.delete_cookie("catalyx_pre_csrf", path="/")
        response.set_cookie(
            "catalyx_session", token, httponly=True, samesite="strict", secure=production_mode(),
            max_age=SESSION_SECONDS, path="/",
        )
        return response

    @app.get("/forgot-password", response_class=HTMLResponse)
    def forgot_password_page(request: Request):
        form = '<form method="post" action="/forgot-password" class="form-stack">' + _form_csrf(request=request) + '<label>Email address<input type="email" name="email" autocomplete="email" required maxlength="254"></label>' + _button("Send reset link") + '</form><p class="auth-switch"><a href="/login">Back to sign in</a></p>'
        return _form_page("Reset your password", "Enter your sign-in email. If it can be reset, we will send a one-time link.", form, request=request)

    @app.post("/forgot-password")
    async def request_password_reset(request: Request):
        form = _parse_form(request)
        _check_csrf(request, form)
        _check_origin(request)
        address = request.client.host if request.client else "unknown"
        allowed = database.allow_rate_attempt("password_reset_request", address, 5, 3600)
        email = form.get("email", "").strip().lower()
        reset_message = None
        if allowed:
            with database.connect() as db:
                row = db.execute("SELECT id FROM users WHERE email=? AND email_verified_at IS NOT NULL AND disabled_at IS NULL", (email,)).fetchone()
                if row:
                    db.execute("DELETE FROM password_reset_tokens WHERE user_id=? OR expires_at<=?", (row["id"], int(time.time())))
                    token = new_token()
                    token_expires_at = int(time.time()) + 1800
                    db.execute(
                        "INSERT INTO password_reset_tokens(token_hash,user_id,expires_at,created_at) VALUES(?,?,?,?)",
                        (digest_token(token), row["id"], token_expires_at, now_iso()),
                    )
                    reset_url = _public_base_url(request) + "/reset-password#" + quote(token)
                    reset_message = (email, reset_url, token_expires_at)
        if reset_message:
            if mail_mode == "local_mailbox" and not deployed:
                _save_local_message(
                    reset_message[0], "password_reset", reset_message[1], reset_message[2]
                )
                logger.info("Local password reset message saved to the private staging mailbox")
            else:
                try:
                    await asyncio.to_thread(send_account_link, reset_message[0], "password_reset", reset_message[1])
                except MailDeliveryError:
                    logger.warning("Password reset email could not be delivered")
        body = '<section class="auth-wrap"><p class="eyebrow">PASSWORD RESET</p><h1>Check your email</h1><p class="lead narrow">If the address can be reset, a one-time link is ready. The link expires after 30 minutes.</p><a class="button primary" href="/login">Return to sign in</a></section>'
        return _page("Check your email", body)

    @app.get("/reset-password", response_class=HTMLResponse)
    def reset_password_page():
        body = '<section class="auth-wrap"><p class="eyebrow">PASSWORD RESET</p><h1>Choose a new password</h1><p class="lead narrow">Use at least 12 characters. This link can be used once.</p><form method="post" action="/reset-password" class="form-stack"><input type="hidden" name="token" id="reset-token" value=""><label>New password<input type="password" name="password" autocomplete="new-password" minlength="12" required></label><label>Confirm new password<input type="password" name="password_confirm" autocomplete="new-password" minlength="12" required></label><p id="reset-hint" class="form-note">Open the original reset link if the button is unavailable.</p><button class="button primary" id="reset-button" type="submit" disabled>Save new password</button></form></section>'
        response = _page("Choose a new password", body)
        return HTMLResponse(response.body.decode("utf-8").replace("</body>", '<script src="/static/reset.js" defer></script></body>'))

    @app.post("/reset-password", response_class=HTMLResponse)
    async def reset_password(request: Request):
        form = _parse_form(request)
        address = request.client.host if request.client else "unknown"
        if not database.allow_rate_attempt("password_reset_submit", address, 10, 3600):
            raise HTTPException(429, "Too many reset attempts. Request a new link later.")
        token = form.get("token", "")
        if not token or len(token) > 128:
            return _page("Reset link unavailable", '<section class="auth-wrap"><h1>This link is unavailable</h1><p class="lead">Request another password reset link and try again.</p><a href="/forgot-password">Request a new link</a></section>', status=400)
        password, password_confirm = form.get("password", ""), form.get("password_confirm", "")
        if password != password_confirm:
            return _page("Password not updated", '<section class="auth-wrap"><h1>Passwords do not match</h1><p class="lead">Return to the one-time link and try again.</p><a href="/reset-password">Try again</a></section>', status=400)
        if len(password) < 12 or len(password) > 1024:
            return _page("Password not updated", '<section class="auth-wrap"><h1>Password not updated</h1><p class="lead">Use a password between 12 and 1024 characters.</p><a href="/reset-password">Try again</a></section>', status=400)
        with database.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "DELETE FROM password_reset_tokens WHERE token_hash=? AND expires_at>? RETURNING user_id",
                (digest_token(token), int(time.time())),
            ).fetchone()
            if not row:
                return _page("Reset link unavailable", '<section class="auth-wrap"><h1>This link is unavailable</h1><p class="lead">Request another password reset link and try again.</p><a href="/forgot-password">Request a new link</a></section>', status=400)
            password_hash = hash_password(password)
            updated = db.execute("UPDATE users SET password_hash=? WHERE id=? AND disabled_at IS NULL", (password_hash, row["user_id"]))
            if updated.rowcount != 1:
                return _page("Reset link unavailable", '<section class="auth-wrap"><h1>This link is unavailable</h1><p class="lead">Request another password reset link and try again.</p><a href="/forgot-password">Request a new link</a></section>', status=400)
            db.execute("DELETE FROM password_reset_tokens WHERE user_id=?", (row["user_id"],))
            db.execute("DELETE FROM sessions WHERE user_id=?", (row["user_id"],))
        if mail_mode == "local_mailbox" and not deployed:
            _prune_local_messages(consumed_token=token)
        return _page("Password updated", '<section class="auth-wrap"><p class="eyebrow">PASSWORD RESET</p><h1>Password updated</h1><p class="lead">Your other sessions were signed out. Sign in with your new password.</p><a class="button primary" href="/login">Sign in</a></section>')

    @app.post("/logout")
    async def logout(request: Request):
        user = _session(request)
        form = _parse_form(request)
        _check_csrf(request, form, user)
        with database.connect() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (digest_token(request.cookies.get("catalyx_session", "")),))
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie("catalyx_session", path="/")
        return response

    @app.get("/app", response_class=HTMLResponse)
    def customer_home(request: Request):
        user = _session(request)
        _need_role(user, {"customer"})
        with database.connect() as db:
            site_count = db.execute("SELECT count(*) FROM sites WHERE workspace_id=? AND deleted_at IS NULL", (user["workspace_id"],)).fetchone()[0]
            request_count = db.execute(
                "SELECT count(*) FROM audit_requests WHERE workspace_id=?",
                (user["workspace_id"],),
            ).fetchone()[0]
            requests = db.execute(
                "SELECT a.id,a.state,a.created_at,s.host FROM audit_requests a JOIN sites s ON s.id=a.site_id "
                "WHERE a.workspace_id=? ORDER BY a.created_at DESC LIMIT 5", (user["workspace_id"],)
            ).fetchall()
        request_rows = [
            '<tr><td><a href="/app/audits/' + _e(item["id"]) + '">' + _e(item["host"]) + '</a></td><td><span class="status">' + _e(_state_label(item["state"])) + '</span></td><td>' + _e(item["created_at"][:10]) + "</td></tr>"
            for item in requests
        ]
        body = '<section class="workspace-heading"><div><p class="eyebrow">YOUR WORKSPACE</p><h1>Good to see you.</h1><p class="lead">Add a website you manage, then submit it for authorization review.</p></div><a class="button primary" href="/app/sites">Add a website <span aria-hidden="true">↗</span></a></section><section class="metric-grid"><article class="metric"><span>Registered sites</span><strong>' + str(site_count) + '</strong><small>In your workspace</small></article><article class="metric"><span>Audit requests</span><strong>' + str(request_count) + '</strong><small>Recent requests shown below</small></article><article class="metric muted-metric"><span>Scanning</span><strong>Paused</strong><small>Worker security gate is closed</small></article></section><section class="content-section"><div class="section-heading"><div><p class="eyebrow">RECENT ACTIVITY</p><h2>Your audit requests</h2></div><a class="arrow-link" href="/app/audits">View all →</a></div>' + _table(request_rows, ["Website", "Status", "Submitted"], "No audit requests yet. Add a site and submit your first request.") + '</section><section class="callout compact"><p>When you submit a request, we save your permission confirmation and send it for admin review. This preview does not scan sites or create report results.</p></section>'
        return _page("Your workspace", body, user=user, active="overview")

    @app.get("/app/sites", response_class=HTMLResponse)
    def customer_sites(request: Request, notice: str = ""):
        user = _session(request)
        _need_role(user, {"customer"})
        with database.connect() as db:
            rows = db.execute("SELECT id,origin,host,label,created_at FROM sites WHERE workspace_id=? AND deleted_at IS NULL ORDER BY created_at DESC", (user["workspace_id"],)).fetchall()
        sites_rows = [
            '<tr><td><a href="/app/sites/' + _e(row["id"]) + '">' + _e(row["label"]) + '</a></td><td>' + _e(row["origin"]) + '</td><td>' + _e(row["created_at"][:10]) + "</td></tr>"
            for row in rows
        ]
        form = '<form method="post" action="/app/sites" class="form-grid">' + _form_csrf(user) + '<label>Website URL<input name="url" type="url" placeholder="https://example.co.nz" required maxlength="2048"></label><label>Short name<input name="label" maxlength="100" placeholder="My business website" required></label>' + _button("Add website") + '</form>'
        body = '<section class="workspace-heading"><div><p class="eyebrow">CUSTOMER WORKSPACE</p><h1>Your websites</h1><p class="lead">Register public sites that you own or are authorized to manage.</p></div></section><section class="content-section"><h2>Add a website</h2>' + form + '<p class="form-note">Only the site origin is saved. Query strings, page paths, and fragments are discarded.</p></section><section class="content-section"><h2>Registered websites</h2>' + _table(sites_rows,["Name","Website origin","Added"],"No websites added yet.") + '</section>'
        return _page("Your websites", body, user=user, active="sites", notice=notice)

    @app.post("/app/sites")
    async def create_site(request: Request):
        user = _session(request)
        _need_role(user, {"customer"})
        form = _parse_form(request)
        _check_csrf(request, form, user)
        try:
            origin, host = normalize_site(form.get("url", ""))
        except ValueError as exc:
            return _page("Your websites", '<section class="wrap content-section"><h1>Website not added</h1><p class="form-error" role="alert" aria-atomic="true">' + _e(exc) + '</p><a class="button primary" href="/app/sites">Try again</a></section>', user=user, active="sites", status=400)
        label = form.get("label", "").strip()[:100]
        if not label:
            label = host
        with database.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute("SELECT count(*) FROM sites WHERE workspace_id=? AND deleted_at IS NULL", (user["workspace_id"],)).fetchone()[0]
            if count >= 20:
                raise HTTPException(429, "A workspace can register up to 20 websites in this preview.")
            try:
                db.execute("INSERT INTO sites(id,workspace_id,origin,host,label,created_by,created_at) VALUES(?,?,?,?,?,?,?)", (str(uuid.uuid4()), user["workspace_id"], origin, host, label, user["user_id"], now_iso()))
            except DatabaseIntegrityError:
                return _page("Your websites", '<section class="wrap content-section"><h1>Website already registered</h1><p>This origin is already in your workspace.</p><a href="/app/sites">View your websites</a></section>', user=user, active="sites", status=409)
        return RedirectResponse("/app/sites?notice=Website%20added", status_code=303)

    @app.get("/app/sites/{site_id}", response_class=HTMLResponse)
    def customer_site(request: Request, site_id: str):
        user = _session(request)
        _need_role(user, {"customer"})
        with database.connect() as db:
            site = db.execute("SELECT id,origin,host,label,created_at FROM sites WHERE id=? AND workspace_id=? AND deleted_at IS NULL", (site_id, user["workspace_id"])).fetchone()
            if not site:
                raise HTTPException(404, "Website not found")
            audits = db.execute("SELECT id,state,created_at FROM audit_requests WHERE site_id=? AND workspace_id=? ORDER BY created_at DESC", (site_id, user["workspace_id"])).fetchall()
        audit_rows = ['<tr><td><a href="/app/audits/' + _e(row["id"]) + '">' + _e(row["id"][:8]) + '</a></td><td>' + _e(_state_label(row["state"])) + '</td><td>' + _e(row["created_at"][:10]) + "</td></tr>" for row in audits]
        form = '<form method="post" action="/app/sites/' + _e(site_id) + '/audit-request" class="form-stack">' + _form_csrf(user) + '<p>Request an administrator review for <strong>' + _e(site["origin"]) + '</strong>.</p><label class="check-label"><input type="checkbox" name="authorized" value="yes" required><span>' + _e(CONSENT_TEXT) + '</span></label><input type="hidden" name="idempotency_key" value="' + _e(str(uuid.uuid4())) + '">' + _button("Submit for review") + '</form>'
        body = '<section class="workspace-heading"><div><p class="eyebrow">REGISTERED WEBSITE</p><h1>' + _e(site["label"]) + '</h1><p class="lead">' + _e(site["origin"]) + '</p></div><a class="quiet-link" href="/app/sites">← All sites</a></section><section class="content-section"><h2>Request an audit</h2>' + form + '<p class="form-note">The request records your authorization statement and enters human review. It will not fetch this website in the current staging build.</p></section><section class="content-section"><h2>Request history</h2>' + _table(audit_rows,["Request","Status","Submitted"],"No requests for this website yet.") + '</section>'
        return _page(site["label"], body, user=user, active="sites")

    @app.post("/app/sites/{site_id}/audit-request")
    async def create_audit_request(request: Request, site_id: str):
        user = _session(request)
        _need_role(user, {"customer"})
        form = _parse_form(request)
        _check_csrf(request, form, user)
        if form.get("authorized") != "yes":
            raise HTTPException(400, "Authorization confirmation is required.")
        key = form.get("idempotency_key", "")
        if len(key) > 80 or not key:
            raise HTTPException(400, "Refresh the site page and submit again.")
        audit_id = str(uuid.uuid4())
        authorization_id = str(uuid.uuid4())
        timestamp = now_iso()
        with database.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            site = db.execute("SELECT id FROM sites WHERE id=? AND workspace_id=? AND deleted_at IS NULL", (site_id, user["workspace_id"])).fetchone()
            if not site:
                raise HTTPException(404, "Website not found")
            existing = db.execute("SELECT id FROM audit_requests WHERE workspace_id=? AND idempotency_key=?", (user["workspace_id"], key)).fetchone()
            if existing:
                return RedirectResponse("/app/audits/" + existing["id"], status_code=303)
            cutoff = datetime.fromtimestamp(time.time() - 3600, UTC).isoformat(timespec="seconds")
            recent = db.execute(
                "SELECT count(*) FROM audit_requests WHERE workspace_id=? AND created_at>=?",
                (user["workspace_id"], cutoff),
            ).fetchone()[0]
            if recent >= 10:
                raise HTTPException(429, "This workspace has reached the hourly request limit.")
            db.execute("INSERT INTO authorization_receipts(id,workspace_id,site_id,user_id,statement,version,recorded_at) VALUES(?,?,?,?,?,?,?)", (authorization_id, user["workspace_id"], site_id, user["user_id"], CONSENT_TEXT, CONSENT_VERSION, timestamp))
            db.execute("INSERT INTO audit_requests(id,workspace_id,site_id,requested_by,authorization_id,profile,state,idempotency_key,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (audit_id, user["workspace_id"], site_id, user["user_id"], authorization_id, "static", "authorization_review", key, timestamp, timestamp))
        return RedirectResponse("/app/audits/" + audit_id, status_code=303)

    @app.get("/app/audits", response_class=HTMLResponse)
    def customer_audits(request: Request):
        user = _session(request)
        _need_role(user, {"customer"})
        with database.connect() as db:
            audits = db.execute("SELECT a.id,a.state,a.created_at,s.host FROM audit_requests a JOIN sites s ON s.id=a.site_id WHERE a.workspace_id=? ORDER BY a.created_at DESC", (user["workspace_id"],)).fetchall()
        rows = ['<tr><td><a href="/app/audits/' + _e(row["id"]) + '">' + _e(row["host"]) + '</a></td><td>' + _e(_state_label(row["state"])) + '</td><td>' + _e(row["created_at"][:10]) + "</td></tr>" for row in audits]
        body = '<section class="workspace-heading"><div><p class="eyebrow">CUSTOMER WORKSPACE</p><h1>Audit requests</h1><p class="lead">Follow the review state of each request.</p></div></section><section class="content-section">' + _table(rows,["Website","Status","Submitted"],"No audit requests yet.") + '</section>'
        return _page("Audit requests", body, user=user, active="audits")

    @app.get("/app/audits/{audit_id}", response_class=HTMLResponse)
    def customer_audit(request: Request, audit_id: str):
        user = _session(request)
        _need_role(user, {"customer"})
        with database.connect() as db:
            row = db.execute("SELECT a.id,a.state,a.created_at,a.updated_at,s.host,s.origin, "
                             "CASE WHEN rr.state='released' THEN ar.report_json ELSE NULL END AS report_json "
                             "FROM audit_requests a JOIN sites s ON s.id=a.site_id "
                             "LEFT JOIN audit_results ar ON ar.audit_id=a.id AND ar.workspace_id=a.workspace_id "
                             "LEFT JOIN report_releases rr ON rr.audit_id=a.id AND rr.state='released' "
                             "WHERE a.id=? AND a.workspace_id=?", (audit_id, user["workspace_id"])).fetchone()
        if not row:
            raise HTTPException(404, "Audit request not found")
        body = '<section class="workspace-heading"><div><p class="eyebrow">AUDIT REQUEST · ' + _e(row["id"][:8]) + '</p><h1>' + _e(row["host"]) + '</h1><p class="lead">' + _e(row["origin"]) + '</p></div><a class="quiet-link" href="/app/audits">← All requests</a></section><section class="status-panel"><p class="eyebrow">CURRENT STATUS</p><h2>' + _e(_state_label(row["state"])) + '</h2><p>Submitted ' + _e(row["created_at"]) + '</p>'
        if row["state"] in {"authorization_review", "queued", "running"}:
            body += '<form method="post" action="/app/audits/' + _e(audit_id) + '/cancel" class="cancel-form">' + _form_csrf(user) + '<button class="text-button" type="submit">Cancel this request</button></form>'
        if row["report_json"]:
            report = json.loads(row["report_json"])
            finding_rows = []
            for finding in report.get("findings", []):
                severity = finding.get("severity", "medium")
                finding_rows.append(
                    '<article class="finding"><span class="severity ' + _e(severity) + '">' + _e(severity.upper())
                    + '</span><div><h3>' + _e(finding.get("title", "Finding")) + '</h3><p>'
                    + '<strong>Potential effect:</strong> ' + _e(finding.get("impact", "Review the check evidence.")) + '</p><p>'
                    + '<strong>Severity:</strong> ' + _e(finding.get("severity_rationale", "Confirm this finding before acting.")) + '</p><p>'
                    + '<strong>Suggested next step:</strong> ' + _e(finding.get("recommendation", "Review this item.")) + '</p><small>Evidence reference: '
                    + _e(finding.get("evidence_ref", "check")) + '</small></div></article>'
                )
            check_rows = []
            for name, result in report.get("checks", {}).items():
                check_rows.append(
                    '<tr><td>' + _e(name.replace("_", " ").title()) + '</td><td>'
                    + _e(result.get("status", "unknown").replace("_", " ").title()) + '</td><td>'
                    + _e(result.get("reason", result.get("limitation", ""))) + "</td></tr>"
                )
            body += '<section class="content-section"><p class="eyebrow">RELEASED REPORT · ' + _e(report.get("profile", "static")) + '</p><h2>Findings</h2>'
            body += "".join(finding_rows) if finding_rows else '<p class="callout-text">No findings were recorded in the checks that ran. This is not a certification.</p>'
            body += '<h2>What ran</h2>' + _table(check_rows, ["Check", "Status", "Note"], "No check results.") + '</section>'
        else:
            body += '</section><section class="callout compact"><p>No report is available until an approved audit has run and an administrator releases its quality-reviewed report. The current preview does not enable public scanning.</p></section>'
        return _page("Audit request", body, user=user, active="audits")

    @app.post("/app/audits/{audit_id}/cancel")
    async def customer_cancel_audit(request: Request, audit_id: str):
        user = _session(request)
        _need_role(user, {"customer"})
        form = _parse_form(request)
        _check_csrf(request, form, user)
        with database.connect() as db:
            result = db.execute(
                "UPDATE audit_requests SET state='cancelled',updated_at=?,review_reason='Cancelled by customer',worker_lease_until=NULL,worker_lease_token=NULL "
                "WHERE id=? AND workspace_id=? AND state IN ('authorization_review','queued','running')",
                (now_iso(), audit_id, user["workspace_id"]),
            )
            if result.rowcount != 1:
                exists = db.execute("SELECT id FROM audit_requests WHERE id=? AND workspace_id=?", (audit_id, user["workspace_id"])).fetchone()
                if not exists:
                    raise HTTPException(404, "Audit request not found")
                raise HTTPException(409, "This request can no longer be cancelled")
        return RedirectResponse("/app/audits/" + audit_id, status_code=303)

    @app.get("/app/settings", response_class=HTMLResponse)
    def customer_settings(request: Request):
        user = _session(request)
        _need_role(user, {"customer"})
        with database.connect() as db:
            requests = db.execute(
                "SELECT id,request_type,state,created_at FROM privacy_requests WHERE user_id=? ORDER BY created_at DESC LIMIT 20",
                (user["user_id"],),
            ).fetchall()
        rows = []
        for row in requests:
            action = ""
            if row["state"] == "approved" and row["request_type"] in {"access", "export"}:
                action = (
                    '<form method="post" action="/app/settings/privacy-requests/'
                    + _e(row["id"])
                    + '/export">'
                    + _form_csrf(user)
                    + '<button class="button primary" type="submit">Download my data</button></form>'
                )
            rows.append(
                '<tr><td>' + _e(row["request_type"].title())
                + '</td><td>' + _e(row["state"].replace("_", " ").title())
                + '</td><td>' + _e(row["created_at"][:10])
                + '</td><td>' + action + "</td></tr>"
            )
        privacy_form = (
            '<form method="post" action="/app/settings/privacy-requests" class="form-stack">'
            + _form_csrf(user)
            + '<label>Request type<select name="request_type" required><option value="access">Access to my account data</option><option value="export">A copy of my account data</option><option value="delete">Delete my account and associated data</option></select></label>'
            + '<label>Details (optional)<textarea name="customer_note" rows="3" maxlength="500"></textarea></label>'
            + _button("Submit privacy request")
            + '</form>'
        )
        body = '<section class="workspace-heading"><div><p class="eyebrow">ACCOUNT</p><h1>Account settings</h1><p class="lead">Manage your account details and data requests.</p></div></section><section class="content-section"><h2>Sign-in address</h2><p>' + _e(user["email"]) + '</p><p class="form-note">Email changes are not available in this staging build.</p></section><section class="callout"><p>Privacy and deletion requests need an identity check and a defined retention policy. The operator workflow will be enabled before customer launch.</p></section>'
        body = body.replace(
            '<section class="callout"><p>Privacy and deletion requests need an identity check and a defined retention policy. The operator workflow will be enabled before customer launch.</p></section>',
            '<section class="content-section"><h2>Your privacy requests</h2>' + _table(rows, ["Request", "Status", "Submitted", "Available action"], "No privacy requests yet.") + '</section><section class="content-section"><h2>Request access, export, or deletion</h2>' + privacy_form + '<p class="form-note">An administrator must verify your request before an access or export download becomes available. Deletion remains paused until retention and backup rules are approved.</p></section>',
        )
        return _page("Account settings", body, user=user, active="settings")

    @app.post("/app/settings/privacy-requests")
    async def create_privacy_request(request: Request):
        user = _session(request)
        _need_role(user, {"customer"})
        form = _parse_form(request)
        _check_csrf(request, form, user)
        request_type = form.get("request_type", "")
        note = form.get("customer_note", "").strip()[:500]
        if request_type not in {"access", "export", "delete"}:
            raise HTTPException(400, "Choose a valid privacy request type.")
        with database.connect() as db:
            pending = db.execute(
                "SELECT id FROM privacy_requests WHERE user_id=? AND state IN ('received','identity_review','approved') LIMIT 1",
                (user["user_id"],),
            ).fetchone()
            if pending:
                raise HTTPException(409, "You already have a privacy request awaiting review.")
            db.execute(
                "INSERT INTO privacy_requests(id,workspace_id,user_id,request_type,state,customer_note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), user["workspace_id"], user["user_id"], request_type, "received", note, now_iso(), now_iso()),
            )
        return RedirectResponse("/app/settings", status_code=303)

    @app.post("/app/settings/privacy-requests/{privacy_id}/export")
    async def download_customer_export(request: Request, privacy_id: str):
        user = _session(request)
        _need_role(user, {"customer"})
        form = _parse_form(request)
        _check_csrf(request, form, user)
        with database.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            privacy_request = db.execute(
                "SELECT id,request_type FROM privacy_requests "
                "WHERE id=? AND user_id=? AND workspace_id=? AND state='approved'",
                (privacy_id, user["user_id"], user["workspace_id"]),
            ).fetchone()
            if not privacy_request or privacy_request["request_type"] not in {"access", "export"}:
                raise HTTPException(404, "Approved data export request not found")
            bundle = _customer_export(db, user["user_id"], user["workspace_id"])
            changed = db.execute(
                "UPDATE privacy_requests SET state='completed',updated_at=? "
                "WHERE id=? AND user_id=? AND state='approved'",
                (now_iso(), privacy_id, user["user_id"]),
            )
            if changed.rowcount != 1:
                raise HTTPException(409, "This data request has already been completed")
            database.audit_admin(
                user,
                "privacy_export_downloaded",
                "privacy_request",
                privacy_id,
                "Customer downloaded their approved account data export",
                {"format": bundle["format"]},
                connection=db,
            )
        export_name = "catalyx-account-export-" + user["user_id"][:8] + ".json"
        return Response(
            json.dumps(bundle, sort_keys=True, separators=(",", ":")),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="' + export_name + '"'},
        )

    @app.get("/admin", response_class=HTMLResponse)
    def admin_home(request: Request):
        user = _session(request)
        _need_role(user, REVIEW_ROLES)
        with database.connect() as db:
            pending = db.execute("SELECT count(*) FROM audit_requests WHERE state='authorization_review'").fetchone()[0]
            queued = db.execute("SELECT count(*) FROM audit_requests WHERE state='queued'").fetchone()[0]
            quality_review = db.execute("SELECT count(*) FROM audit_requests WHERE state='quality_review'").fetchone()[0]
            failed = db.execute("SELECT count(*) FROM audit_requests WHERE state='failed'").fetchone()[0]
            customer_count = db.execute("SELECT count(*) FROM users u JOIN memberships m ON m.user_id=u.id WHERE m.role='customer' AND m.active=1").fetchone()[0]
            recent = db.execute("SELECT a.id,a.state,a.created_at,s.host FROM audit_requests a JOIN sites s ON s.id=a.site_id ORDER BY a.created_at DESC LIMIT 6").fetchall()
        rows = ['<tr><td><a href="/admin/audits/' + _e(row["id"]) + '">' + _e(row["host"]) + '</a></td><td>' + _e(_state_label(row["state"])) + '</td><td>' + _e(row["created_at"][:10]) + "</td></tr>" for row in recent]
        body = '<section class="workspace-heading"><div><p class="eyebrow">CATALYXLABS · OPERATIONS</p><h1>Review desk</h1><p class="lead">Customer and job controls for the Website Auditor staging service.</p></div><span class="worker-badge"><i></i> Public worker disabled</span></section><section class="metric-grid"><article class="metric"><span>Authorization review</span><strong>' + str(pending) + '</strong><small>Requests needing a decision</small></article><article class="metric"><span>Waiting for worker</span><strong>' + str(queued) + '</strong><small>Approved requests</small></article><article class="metric"><span>Report quality review</span><strong>' + str(quality_review) + '</strong><small>Awaiting release decision</small></article><article class="metric"><span>Customers</span><strong>' + str(customer_count) + '</strong><small>Active customer memberships</small></article><article class="metric"><span>Failed jobs</span><strong>' + str(failed) + '</strong><small>Recorded outcomes only</small></article></section><section class="content-section"><div class="section-heading"><div><p class="eyebrow">LATEST REQUESTS</p><h2>Audit queue</h2></div><a class="arrow-link" href="/admin/audits">Open queue →</a></div>' + _table(rows,["Website","Status","Submitted"],"No audit requests yet.") + '</section><section class="callout compact"><h2>Launch gates</h2><ul class="blocker-list"><li>Production hosting is not approved: Vercel Hobby terms exclude commercial use. The local Cloudflare probe includes a separate WebCrypto prototype that passes, but auth integration, D1 persistence, measured CPU fit, and restricted scan egress remain unproven.</li><li>SQLite is local-only. The PostgreSQL adapter has no live integration, approved data region, or restore evidence.</li><li>The paid-services cap is $0. Keep billing and paid providers off.</li><li>Customer email delivery is not configured. Scans remain queued until a separate worker and restricted egress are verified.</li><li>Retention, backup, support and incident response, approved legal copy, and a customer support contact still need owner review.</li></ul></section>'
        return _page("Operations", body, user=user, active="admin")

    @app.get("/admin/audits", response_class=HTMLResponse)
    def admin_audits(request: Request, state: str = ""):
        user = _session(request)
        _need_role(user, REVIEW_ROLES)
        valid_states = {"authorization_review", "queued", "running", "quality_review", "released", "denied", "failed", "withheld"}
        if state and state not in valid_states:
            raise HTTPException(400, "Unknown audit status")
        with database.connect() as db:
            sql = "SELECT a.id,a.state,a.created_at,s.host,u.email FROM audit_requests a JOIN sites s ON s.id=a.site_id JOIN users u ON u.id=a.requested_by"
            params: tuple = ()
            if state:
                sql += " WHERE a.state=?"
                params = (state,)
            rows = db.execute(sql + " ORDER BY a.created_at DESC LIMIT 200", params).fetchall()
        table = ['<tr><td><a href="/admin/audits/' + _e(row["id"]) + '">' + _e(row["host"]) + '</a></td><td>' + _e(row["email"]) + '</td><td>' + _e(_state_label(row["state"])) + '</td><td>' + _e(row["created_at"][:10]) + "</td></tr>" for row in rows]
        filters = '<div class="filter-row"><a href="/admin/audits">All</a>' + "".join('<a href="/admin/audits?state=' + value + '">' + _e(_state_label(value)) + "</a>" for value in ("authorization_review", "queued", "failed")) + "</div>"
        body = '<section class="workspace-heading"><div><p class="eyebrow">ADMIN REVIEW</p><h1>Audit queue</h1><p class="lead">Review permissions and request state. Sensitive network details are not collected.</p></div></section><section class="content-section">' + filters + _table(table,["Website","Customer","Status","Submitted"],"No requests match this view.") + '</section>'
        return _page("Audit queue", body, user=user, active="queue")

    @app.get("/admin/sites", response_class=HTMLResponse)
    def admin_sites(request: Request):
        user = _session(request)
        _need_role(user, REVIEW_ROLES)
        with database.connect() as db:
            rows = db.execute(
                "SELECT s.id,s.host,s.origin,s.label,s.created_at,u.email, "
                "(SELECT count(*) FROM authorization_receipts ar WHERE ar.site_id=s.id) receipt_count "
                "FROM sites s JOIN users u ON u.id=s.created_by WHERE s.deleted_at IS NULL "
                "ORDER BY s.created_at DESC LIMIT 300"
            ).fetchall()
        table = [
            '<tr><td>' + _e(row["host"]) + '</td><td>' + _e(row["email"]) + '</td><td>'
            + ("Recorded" if row["receipt_count"] else "No audit request") + '</td><td>'
            + _e(row["created_at"][:10]) + "</td></tr>"
            for row in rows
        ]
        body = '<section class="workspace-heading"><div><p class="eyebrow">SITE REGISTER</p><h1>Customer websites</h1><p class="lead">Origins and authorization receipts recorded by customer requests.</p></div></section><section class="content-section">' + _table(table, ["Host", "Customer", "Authorization", "Added"], "No websites registered.") + '</section>'
        return _page("Customer websites", body, user=user, active="sites")

    @app.get("/admin/jobs", response_class=HTMLResponse)
    def admin_jobs(request: Request):
        user = _session(request)
        _need_role(user, REVIEW_ROLES)
        with database.connect() as db:
            rows = db.execute(
                "SELECT a.id,a.state,a.created_at,a.updated_at,a.attempt_count,a.review_reason,s.host,u.email FROM audit_requests a "
                "JOIN sites s ON s.id=a.site_id JOIN users u ON u.id=a.requested_by "
                "WHERE a.state IN ('queued','running','failed','expired') ORDER BY a.updated_at DESC LIMIT 200"
            ).fetchall()
            counts = {row["state"]: row["total"] for row in db.execute("SELECT state,count(*) AS total FROM audit_requests GROUP BY state")}
        table = [
            '<tr><td><a href="/admin/audits/' + _e(row["id"]) + '">' + _e(row["host"]) + '</a></td><td>'
            + _e(row["email"]) + '</td><td>' + _e(_state_label(row["state"])) + '</td><td>'
            + str(row["attempt_count"]) + '</td><td>' + _e(row["review_reason"] or "—")
            + '</td><td>' + _e(row["updated_at"][:16]) + "</td></tr>"
            for row in rows
        ]
        summary = "".join(
            '<article class="metric"><span>' + _e(_state_label(state)) + '</span><strong>' + str(counts.get(state, 0)) + '</strong><small>Recorded requests</small></article>'
            for state in ("authorization_review", "queued", "running", "quality_review", "failed", "expired")
        )
        body = '<section class="workspace-heading"><div><p class="eyebrow">QUEUE CONTROL</p><h1>Jobs and requests</h1><p class="lead">State counts come from persisted requests. Failed requests remain available for review; retries require a reviewer reason. There is no active worker.</p></div><span class="worker-badge"><i></i> Worker off</span></section><section class="metric-grid job-metrics">' + summary + '</section><section class="content-section">' + _table(table, ["Website", "Customer", "State", "Attempts", "Last outcome", "Updated"], "No queued, running, or failed jobs.") + '</section>'
        return _page("Jobs and queue", body, user=user, active="jobs")

    @app.get("/admin/operations", response_class=HTMLResponse)
    def admin_operations(request: Request):
        user = _session(request)
        _need_role(user, {"owner", "admin"})
        integrity = database.integrity_check()
        with database.connect() as db:
            users = db.execute("SELECT count(*) FROM users").fetchone()[0]
            requests = db.execute("SELECT count(*) FROM audit_requests").fetchone()[0]
        health = "Healthy" if integrity == "ok" else "Needs investigation"
        body = (
            '<section class="workspace-heading"><div><p class="eyebrow">SYSTEM STATUS</p><h1>Operations</h1>'
            '<p class="lead">Local staging service health and launch blockers.</p></div></section>'
            '<section class="metric-grid"><article class="metric"><span>Application database</span><strong>' + health
            + '</strong><small>Database connection check</small></article><article class="metric"><span>Scan worker</span>'
            '<strong>Disabled</strong><small>Requests stay queued</small></article><article class="metric"><span>Customer accounts</span>'
            '<strong>' + str(users) + '</strong><small>Persisted users</small></article><article class="metric"><span>Audit requests</span>'
            '<strong>' + str(requests) + '</strong><small>Persisted request records</small></article></section>'
            '<section class="content-section"><h2>Production blockers</h2><ul class="blocker-list">'
            '<li>Production hosting is not approved. Vercel Hobby terms exclude commercial use. The local Cloudflare WebCrypto prototype passes, but auth integration, D1 persistence, measured CPU fit, and restricted scan egress remain unproven.</li>'
            '<li>SQLite is local-only. The PostgreSQL adapter has not been tested against a live database; production region and migration/restore evidence are missing.</li>'
            '<li>The plan sets paid services to $0. Keep billing and paid providers off until a complete zero-cost hosting and database path is proven.</li>'
            '<li>Account verification and password-reset links use the local staging mailbox. Approved production email delivery or an alternative is not configured.</li>'
            '<li>The manual fetch path pins checked public addresses; independent worker/container egress isolation and durable queue operations are still missing.</li>'
            '<li>Retention, encrypted backup, restoration, incident support, approved privacy/terms wording, and a customer-facing support contact need an owner-reviewed policy.</li>'
            '</ul></section>'
        )
        return _page("Operations", body, user=user, active="admin")

    @app.get("/admin/privacy-requests", response_class=HTMLResponse)
    def admin_privacy_requests(request: Request):
        user = _session(request)
        _need_role(user, {"owner", "admin"})
        with database.connect() as db:
            rows = db.execute(
                "SELECT p.id,p.request_type,p.state,p.created_at,u.email FROM privacy_requests p "
                "JOIN users u ON u.id=p.user_id ORDER BY p.created_at DESC LIMIT 200"
            ).fetchall()
        table = [
            '<tr><td><a href="/admin/privacy-requests/' + _e(row["id"]) + '">' + _e(row["request_type"].title())
            + '</a></td><td>' + _e(row["email"]) + '</td><td>' + _e(row["state"].replace("_", " ").title())
            + '</td><td>' + _e(row["created_at"][:10]) + "</td></tr>"
            for row in rows
        ]
        body = '<section class="workspace-heading"><div><p class="eyebrow">DATA RIGHTS</p><h1>Privacy requests</h1><p class="lead">Review account access, export, and deletion requests.</p></div></section><section class="content-section">' + _table(table, ["Request", "Customer", "Status", "Submitted"], "No privacy requests.") + '</section><section class="callout"><p>Access/export downloads require recorded identity review and approval, then close after the customer downloads their account-scoped file. Deletion remains paused until retention, backup lifecycle, identity verification, and deletion rules are approved.</p></section>'
        return _page("Privacy requests", body, user=user, active="privacy")

    @app.get("/admin/privacy-requests/{privacy_id}", response_class=HTMLResponse)
    def admin_privacy_detail(request: Request, privacy_id: str):
        user = _session(request)
        _need_role(user, {"owner", "admin"})
        with database.connect() as db:
            row = db.execute(
                "SELECT p.id,p.request_type,p.state,p.customer_note,p.admin_reason,p.created_at,u.id user_id,u.email "
                "FROM privacy_requests p JOIN users u ON u.id=p.user_id WHERE p.id=?",
                (privacy_id,),
            ).fetchone()
        if not row:
            raise HTTPException(404, "Privacy request not found")
        body = '<section class="workspace-heading"><div><p class="eyebrow">DATA RIGHTS REVIEW</p><h1>' + _e(row["request_type"].title()) + ' request</h1><p class="lead">' + _e(row["email"]) + ' · ' + _e(row["created_at"]) + '</p></div><a class="quiet-link" href="/admin/privacy-requests">← All requests</a></section><section class="detail-grid"><article class="detail-card"><p class="eyebrow">CUSTOMER REQUEST</p><h2>' + _e(row["state"].replace("_", " ").title()) + '</h2><p>' + (_e(row["customer_note"]) or "No additional details supplied.") + '</p></article><article class="detail-card"><p class="eyebrow">DATA POLICY</p><h2>' + ("Export available after verification" if row["request_type"] in {"access", "export"} else "Deletion remains paused") + '</h2><p>' + ("After identity review, approve the request to let this customer download a minimized JSON copy of their own account records. The download is recorded and the request closes after delivery." if row["request_type"] in {"access", "export"} else "Do not complete deletion until the owner-approved retention, backup, and deletion process is available.") + '</p></article></section>'
        if row["state"] == "received":
            body += '<section class="content-section"><h2>Update review status</h2><form method="post" action="/admin/privacy-requests/' + _e(privacy_id) + '/decision" class="form-stack">' + _form_csrf(user) + '<label>Reason<textarea name="reason" minlength="4" maxlength="500" required></textarea></label><div class="actions"><button class="button primary" type="submit" name="decision" value="identity_review">Mark identity review</button><button class="button danger" type="submit" name="decision" value="declined">Decline request</button></div></form></section>'
        elif row["state"] == "identity_review" and row["request_type"] in {"access", "export"}:
            body += '<section class="content-section"><h2>Complete identity review</h2><form method="post" action="/admin/privacy-requests/' + _e(privacy_id) + '/decision" class="form-stack">' + _form_csrf(user) + '<label>Verification evidence and approval reason<textarea name="reason" minlength="4" maxlength="500" required></textarea></label><button class="button primary" type="submit" name="decision" value="approve_export">Approve customer download</button></form></section>'
        if row["admin_reason"]:
            body += '<section class="callout"><p>Review note: ' + _e(row["admin_reason"]) + '</p></section>'
        return _page("Privacy request review", body, user=user, active="privacy")

    @app.post("/admin/privacy-requests/{privacy_id}/decision")
    async def admin_decide_privacy(request: Request, privacy_id: str):
        user = _session(request)
        _need_role(user, {"owner", "admin"})
        form = _parse_form(request)
        _check_csrf(request, form, user)
        decision, reason = form.get("decision", ""), form.get("reason", "").strip()
        if decision not in {"identity_review", "declined", "approve_export"} or len(reason) < 4 or len(reason) > 500:
            raise HTTPException(400, "Choose a supported review action and enter a reason.")
        with database.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id,state,request_type FROM privacy_requests WHERE id=?", (privacy_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Privacy request not found")
            target_state = decision
            expected_state = "received"
            if decision == "approve_export":
                if row["request_type"] not in {"access", "export"}:
                    raise HTTPException(400, "Deletion requests cannot be approved for export.")
                target_state = "approved"
                expected_state = "identity_review"
            if row["state"] != expected_state:
                raise HTTPException(409, "This privacy request is not at the required review stage.")
            changed = db.execute(
                "UPDATE privacy_requests SET state=?,admin_reason=?,reviewed_by=?,updated_at=? WHERE id=? AND state=?",
                (target_state, reason, user["user_id"], now_iso(), privacy_id, expected_state),
            )
            if changed.rowcount != 1:
                raise HTTPException(409, "This privacy request has already been reviewed.")
            database.audit_admin(user, "privacy_request_" + decision, "privacy_request", privacy_id, reason, {"from": expected_state, "to": target_state}, connection=db)
        return RedirectResponse("/admin/privacy-requests/" + privacy_id, status_code=303)

    @app.get("/admin/audits/{audit_id}", response_class=HTMLResponse)
    def admin_audit_detail(request: Request, audit_id: str):
        user = _session(request)
        _need_role(user, REVIEW_ROLES)
        with database.connect() as db:
            row = db.execute("SELECT a.id,a.state,a.created_at,a.updated_at,a.profile,a.review_reason,a.authorization_id,a.attempt_count,s.host,s.origin,u.id requester_id,u.email,ar.statement,ar.version,ar.recorded_at, "
                             "result.report_json,result.report_hash,result.profile AS result_profile,release.state AS release_state "
                             "FROM audit_requests a JOIN sites s ON s.id=a.site_id JOIN users u ON u.id=a.requested_by "
                             "JOIN authorization_receipts ar ON ar.id=a.authorization_id "
                             "LEFT JOIN audit_results result ON result.audit_id=a.id "
                             "LEFT JOIN report_releases release ON release.audit_id=a.id WHERE a.id=?", (audit_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Audit request not found")
        worker_detail = (
            "A sanitized report is waiting for this quality review."
            if row["state"] == "quality_review"
            else "The local retry limit has been reached. This request remains failed for review and cannot be retried through the current workflow."
            if row["state"] == "failed" and row["attempt_count"] >= 2
            else "The request failed. A reviewer may return it to the queue with a recorded reason."
            if row["state"] == "failed"
            else "The public service worker is disabled. A separate manual local staging worker can process approved requests."
        )
        body = '<section class="workspace-heading"><div><p class="eyebrow">ADMIN REVIEW · ' + _e(row["id"][:8]) + '</p><h1>' + _e(row["host"]) + '</h1><p class="lead">' + _e(row["origin"]) + '</p></div><a class="quiet-link" href="/admin/audits">← Queue</a></section><section class="detail-grid"><article class="detail-card"><p class="eyebrow">REQUEST</p><h2>' + _e(_state_label(row["state"])) + '</h2><dl><dt>Customer</dt><dd>' + _e(row["email"]) + '</dd><dt>Submitted</dt><dd>' + _e(row["created_at"]) + '</dd><dt>Attempts</dt><dd>' + str(row["attempt_count"]) + '</dd><dt>Profile requested</dt><dd>Static checks</dd><dt>Authorization receipt</dt><dd>' + _e(row["version"]) + ' · ' + _e(row["recorded_at"]) + '</dd></dl><blockquote>' + _e(row["statement"]) + '</blockquote></article><article class="detail-card"><p class="eyebrow">WORKER STATUS</p><h2>' + ("Report ready" if row["state"] == "quality_review" else "Not running") + '</h2><p>' + _e(worker_detail) + '</p></article></section>'
        if row["state"] == "authorization_review":
            body += '<section class="content-section"><h2>Record a decision</h2><form method="post" action="/admin/audits/' + _e(audit_id) + '/decision" class="form-stack">' + _form_csrf(user) + '<label>Reason for the decision<textarea name="reason" rows="3" minlength="4" maxlength="500" required></textarea></label><div class="actions"><button class="button primary" name="decision" value="approve" type="submit">Approve for queue</button><button class="button danger" name="decision" value="deny" type="submit">Deny request</button></div></form></section>'
        elif row["state"] == "quality_review" and row["report_json"]:
            report = json.loads(row["report_json"])
            report_findings = [
                '<article class="finding"><span class="severity ' + _e(item.get("severity", "medium")) + '">' + _e(item.get("severity", "medium").upper())
                + '</span><div><h3>' + _e(item.get("title", "Finding")) + '</h3><p><strong>Potential effect:</strong> ' + _e(item.get("impact", "Review the check evidence."))
                + '</p><p><strong>Severity:</strong> ' + _e(item.get("severity_rationale", "Confirm before acting.")) + '</p><p><strong>Next step:</strong> ' + _e(item.get("recommendation", "Review with the site owner."))
                + '</p><small>' + _e(item.get("evidence_ref", "check")) + '</small></div></article>'
                for item in report.get("findings", [])
            ]
            report_checks = [
                '<tr><td>' + _e(name.replace("_", " ").title()) + '</td><td>' + _e(result.get("status", "unknown").replace("_", " ").title())
                + '</td><td>' + _e(result.get("reason", result.get("limitation", ""))) + '</td></tr>'
                for name, result in report.get("checks", {}).items()
            ]
            body += '<section class="content-section"><p class="eyebrow">QUALITY REVIEW · ' + _e(report.get("profile", "static")) + '</p><h2>Findings</h2>'
            body += "".join(report_findings) if report_findings else '<p>No findings in the checks that ran. Verify completeness before release.</p>'
            body += '<h2>Check status</h2>' + _table(report_checks, ["Check", "Status", "Note"], "No check results.")
            body += '<form method="post" action="/admin/audits/' + _e(audit_id) + '/report-decision" class="form-stack">' + _form_csrf(user) + '<label>Release or withhold reason<textarea name="reason" rows="3" minlength="4" maxlength="500" required></textarea></label><div class="actions"><button class="button primary" name="decision" value="release" type="submit">Release report to customer</button><button class="button danger" name="decision" value="withhold" type="submit">Withhold report</button></div></form></section>'
        elif row["state"] == "failed" and row["attempt_count"] < 2:
            body += '<section class="content-section"><h2>Retry request</h2><form method="post" action="/admin/audits/' + _e(audit_id) + '/retry" class="form-stack">' + _form_csrf(user) + '<label>Reason<textarea name="reason" minlength="4" maxlength="500" required></textarea></label><button class="button primary" type="submit">Return to queue</button></form></section>'
        elif row["review_reason"]:
            body += '<section class="callout"><p>Review note: ' + _e(row["review_reason"]) + '</p></section>'
        return _page("Audit request review", body, user=user, active="queue")

    @app.post("/admin/audits/{audit_id}/decision")
    async def admin_decide_audit(request: Request, audit_id: str):
        user = _session(request)
        _need_role(user, REVIEW_ROLES)
        form = _parse_form(request)
        _check_csrf(request, form, user)
        decision, reason = form.get("decision"), form.get("reason", "").strip()
        if decision not in {"approve", "deny"} or len(reason) < 4 or len(reason) > 500:
            raise HTTPException(400, "Choose a decision and enter a reason.")
        new_state = "queued" if decision == "approve" else "denied"
        with database.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id,state FROM audit_requests WHERE id=?", (audit_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Audit request not found")
            if row["state"] != "authorization_review":
                raise HTTPException(409, "This request has already been reviewed.")
            changed = db.execute("UPDATE audit_requests SET state=?,updated_at=?,reviewed_by=?,review_reason=? WHERE id=? AND state='authorization_review'", (new_state, now_iso(), user["user_id"], reason, audit_id))
            if changed.rowcount != 1:
                raise HTTPException(409, "This request has already been reviewed.")
            database.audit_admin(user, "audit_" + decision, "audit_request", audit_id, reason, {"from": "authorization_review", "to": new_state}, connection=db)
        return RedirectResponse("/admin/audits/" + audit_id, status_code=303)

    @app.post("/admin/audits/{audit_id}/report-decision")
    async def admin_release_report(request: Request, audit_id: str):
        user = _session(request)
        _need_role(user, REVIEW_ROLES)
        form = _parse_form(request)
        _check_csrf(request, form, user)
        decision, reason = form.get("decision", ""), form.get("reason", "").strip()
        if decision not in {"release", "withhold"} or len(reason) < 4 or len(reason) > 500:
            raise HTTPException(400, "Choose whether to release or withhold the report and enter a reason.")
        report_state = "released" if decision == "release" else "withheld"
        with database.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT a.state,r.report_hash FROM audit_requests a JOIN audit_results r ON r.audit_id=a.id WHERE a.id=?",
                (audit_id,),
            ).fetchone()
            if not row:
                raise HTTPException(404, "Report not found")
            if row["state"] != "quality_review":
                raise HTTPException(409, "This report is no longer awaiting review.")
            db.execute(
                "INSERT INTO report_releases(audit_id,reviewer_id,state,reason,report_hash,created_at) VALUES(?,?,?,?,?,?)",
                (audit_id, user["user_id"], report_state, reason, row["report_hash"], now_iso()),
            )
            changed = db.execute(
                "UPDATE audit_requests SET state=?,updated_at=?,reviewed_by=?,review_reason=? WHERE id=? AND state='quality_review'",
                (report_state, now_iso(), user["user_id"], reason, audit_id),
            )
            if changed.rowcount != 1:
                raise HTTPException(409, "This report is no longer awaiting review.")
            database.audit_admin(user, "report_" + decision, "audit_request", audit_id, reason, {"from": "quality_review", "to": report_state, "report_hash": row["report_hash"]}, connection=db)
        return RedirectResponse("/admin/audits/" + audit_id, status_code=303)

    @app.post("/admin/audits/{audit_id}/retry")
    async def admin_retry_audit(request: Request, audit_id: str):
        user = _session(request)
        _need_role(user, REVIEW_ROLES)
        form = _parse_form(request)
        _check_csrf(request, form, user)
        reason = form.get("reason", "").strip()
        if len(reason) < 4 or len(reason) > 500:
            raise HTTPException(400, "Enter a reason for retrying this request.")
        with database.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state,attempt_count FROM audit_requests WHERE id=?", (audit_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Audit request not found")
            if row["state"] != "failed" or row["attempt_count"] >= 2:
                raise HTTPException(409, "This request has no retry remaining.")
            changed = db.execute(
                "UPDATE audit_requests SET state='queued',updated_at=?,reviewed_by=?,review_reason=?,worker_lease_until=NULL,worker_lease_token=NULL WHERE id=? AND state='failed'",
                (now_iso(), user["user_id"], reason, audit_id),
            )
            if changed.rowcount != 1:
                raise HTTPException(409, "This request has no retry remaining.")
            database.audit_admin(user, "audit_retry", "audit_request", audit_id, reason, {"attempt_count": row["attempt_count"]}, connection=db)
        return RedirectResponse("/admin/audits/" + audit_id, status_code=303)

    @app.get("/admin/customers", response_class=HTMLResponse)
    def admin_customers(request: Request):
        user = _session(request)
        _need_role(user, {"owner", "admin", "support"})
        with database.connect() as db:
            rows = db.execute("SELECT u.id,u.email,u.email_verified_at,u.disabled_at,u.created_at,m.role, count(DISTINCT s.id) sites "
                              "FROM users u JOIN memberships m ON m.user_id=u.id LEFT JOIN sites s ON s.workspace_id=m.workspace_id "
                              "WHERE m.role='customer' GROUP BY u.id ORDER BY u.created_at DESC LIMIT 200").fetchall()
        table = ['<tr><td><a href="/admin/customers/' + _e(row["id"]) + '">' + _e(row["email"]) + '</a></td><td>' + ("Verified" if row["email_verified_at"] else "Unverified") + '</td><td>' + ("Disabled" if row["disabled_at"] else "Active") + '</td><td>' + str(row["sites"]) + '</td></tr>' for row in rows]
        body = '<section class="workspace-heading"><div><p class="eyebrow">ACCOUNT SUPPORT</p><h1>Customers</h1><p class="lead">Review account status and registered sites.</p></div></section><section class="content-section">' + _table(table,["Email","Verification","Access","Sites"],"No customer accounts yet.") + '</section>'
        return _page("Customers", body, user=user, active="customers")

    @app.get("/admin/customers/{customer_id}", response_class=HTMLResponse)
    def admin_customer(request: Request, customer_id: str):
        user = _session(request)
        _need_role(user, {"owner", "admin", "support"})
        with database.connect() as db:
            customer = db.execute("SELECT u.id,u.email,u.email_verified_at,u.disabled_at,u.created_at,m.workspace_id "
                                  "FROM users u JOIN memberships m ON m.user_id=u.id WHERE u.id=? AND m.role='customer'", (customer_id,)).fetchone()
            if not customer:
                raise HTTPException(404, "Customer not found")
            sites = db.execute("SELECT id,host,origin,created_at FROM sites WHERE workspace_id=? AND deleted_at IS NULL ORDER BY created_at DESC", (customer["workspace_id"],)).fetchall()
            audits = db.execute("SELECT id,state,created_at FROM audit_requests WHERE workspace_id=? ORDER BY created_at DESC LIMIT 50", (customer["workspace_id"],)).fetchall()
        site_rows = ['<tr><td>' + _e(row["host"]) + '</td><td>' + _e(row["origin"]) + '</td><td>' + _e(row["created_at"][:10]) + "</td></tr>" for row in sites]
        audit_rows = ['<tr><td><a href="/admin/audits/' + _e(row["id"]) + '">' + _e(row["id"][:8]) + '</a></td><td>' + _e(_state_label(row["state"])) + '</td><td>' + _e(row["created_at"][:10]) + "</td></tr>" for row in audits]
        body = '<section class="workspace-heading"><div><p class="eyebrow">CUSTOMER ACCOUNT</p><h1>' + _e(customer["email"]) + '</h1><p class="lead">Created ' + _e(customer["created_at"][:10]) + ' · ' + ("Email verified" if customer["email_verified_at"] else "Email not verified") + '</p></div><a class="quiet-link" href="/admin/customers">← Customers</a></section><section class="content-section"><h2>Registered sites</h2>' + _table(site_rows,["Host","Origin","Added"],"No sites registered.") + '</section><section class="content-section"><h2>Audit history</h2>' + _table(audit_rows,["Request","Status","Submitted"],"No audit requests.") + '</section>'
        if not customer["disabled_at"] and user["role"] in {"owner", "admin"}:
            body += '<section class="content-section"><h2>Access control</h2><form method="post" action="/admin/customers/' + _e(customer_id) + '/disable" class="form-stack">' + _form_csrf(user) + '<label>Reason<textarea name="reason" minlength="4" maxlength="500" required></textarea></label><button class="button danger" type="submit">Disable account and revoke sessions</button></form></section>'
        return _page("Customer account", body, user=user, active="customers")

    @app.post("/admin/customers/{customer_id}/disable")
    async def admin_disable_customer(request: Request, customer_id: str):
        user = _session(request)
        _need_role(user, {"owner", "admin"})
        form = _parse_form(request)
        _check_csrf(request, form, user)
        reason = form.get("reason", "").strip()
        if len(reason) < 4:
            raise HTTPException(400, "Enter a reason for disabling this account.")
        with database.connect() as db:
            customer = db.execute("SELECT id FROM users WHERE id=?", (customer_id,)).fetchone()
            membership = db.execute("SELECT role FROM memberships WHERE user_id=?", (customer_id,)).fetchone()
            if not customer or not membership or membership["role"] != "customer":
                raise HTTPException(404, "Customer not found")
            db.execute("UPDATE users SET disabled_at=? WHERE id=?", (now_iso(), customer_id))
            db.execute("DELETE FROM sessions WHERE user_id=?", (customer_id,))
            database.audit_admin(user, "customer_disabled", "user", customer_id, reason, {}, connection=db)
        return RedirectResponse("/admin/customers/" + customer_id, status_code=303)

    @app.get("/admin/activity", response_class=HTMLResponse)
    def admin_activity(request: Request):
        user = _session(request)
        _need_role(user, {"owner", "admin"})
        with database.connect() as db:
            rows = db.execute("SELECT a.created_at,u.email,a.actor_role,a.action,a.target_type,a.target_id,a.reason "
                              "FROM admin_activity a JOIN users u ON u.id=a.actor_id ORDER BY a.created_at DESC LIMIT 250").fetchall()
        table = ['<tr><td>' + _e(row["created_at"]) + '</td><td>' + _e(row["email"]) + ' · ' + _e(row["actor_role"]) + '</td><td>' + _e(row["action"]) + '</td><td>' + _e(row["target_type"]) + ' ' + _e(row["target_id"][:12]) + '</td><td>' + _e(row["reason"]) + "</td></tr>" for row in rows]
        body = '<section class="workspace-heading"><div><p class="eyebrow">ACCOUNTABILITY</p><h1>Administrator activity</h1><p class="lead">High-impact actions include an actor, target, time, and reason.</p></div></section><section class="content-section">' + _table(table,["Time","Actor","Action","Target","Reason"],"No administrator actions recorded.") + '</section>'
        return _page("Administrator activity", body, user=user, active="activity")

    @app.exception_handler(HTTPException)
    async def safe_http_error(request: Request, exc: HTTPException):
        user = _current_user_or_login(request)
        message = _e(exc.detail if isinstance(exc.detail, str) else "The request could not be completed.")
        if request.url.path.startswith("/api/"):
            return Response(json.dumps({"error": message}), status_code=exc.status_code, media_type="application/json")
        body = '<section class="wrap content-section"><p class="eyebrow">REQUEST NOT COMPLETED</p><h1>' + str(exc.status_code) + '</h1><p class="lead">' + message + '</p><a class="button primary" href="' + ("/app" if user else "/") + '">Return</a></section>'
        return _page("Request not completed", body, user=user, status=exc.status_code)

    return app


def register_form(request: Request) -> str:
    note = (
        "A one-time verification link will be sent to your email address."
        if os.getenv("CATALYX_MAIL_MODE", "smtp" if production_mode() else "local_mailbox") == "smtp"
        else "A one-time verification link is saved to the private local staging mailbox."
    )
    return '<form method="post" action="/register" class="form-stack">' + _form_csrf(request=request) + '<label>Email address<input type="email" name="email" autocomplete="email" required maxlength="254"></label><label>Password<input type="password" name="password" autocomplete="new-password" minlength="12" required><small>Use at least 12 characters.</small></label><label>Confirm password<input type="password" name="password_confirm" autocomplete="new-password" minlength="12" required></label><p class="form-note">' + _e(note) + '</p><button class="button primary" type="submit">Create account</button></form><p class="auth-switch">Already registered? <a href="/login">Sign in</a></p>'


def login_form(request: Request, next_path="", require_otp=False) -> str:
    token_field = _form_csrf(request=request)
    otp = '<label>Authenticator code<input name="otp" inputmode="numeric" pattern="[0-9]{6}" autocomplete="one-time-code" required></label>' if require_otp else ''
    create_account = (
        '<p class="auth-switch">New to Website Auditor? <a href="/register">Create an account</a></p>'
        if _public_registration_open()
        else ""
    )
    return '<form method="post" action="/login" class="form-stack">' + token_field + '<label>Email address<input type="email" name="email" autocomplete="username" required maxlength="254"></label><label>Password<input type="password" name="password" autocomplete="current-password" required></label>' + otp + _button("Sign in") + '</form><p class="auth-switch"><a href="/forgot-password">Forgot your password?</a></p>' + create_account


def notice_html(notice: str) -> str:
    return '<div class="notice inline-notice" role="status">' + _e(notice) + '</div>' if notice else ''


def bootstrap_admin(db_path: str, email: str) -> None:
    password = __import__("getpass").getpass("New admin password (12+ characters): ")
    confirm = __import__("getpass").getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("Passwords did not match.")
    password_hash = hash_password(password)
    secret = base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
    database = Database(db_path)
    database.create_admin(email.strip().lower(), password_hash, secret)
    logger.info("Admin account created for %s", email)
    print("Add this TOTP secret to a named authenticator account. It is shown once; store it securely:")
    print(secret)
    print(f"Provisioning URI: otpauth://totp/CatalyxLabs:{quote(email)}?secret={secret}&issuer=CatalyxLabs&digits=6&period=30")


def main() -> None:
    parser = argparse.ArgumentParser(description="CatalyxLabs Website Auditor web application")
    parser.add_argument("--db", default=os.getenv("CATALYX_DATABASE_URL") or os.getenv("CATALYX_DB_PATH", "state/catalyx-app.sqlite3"))
    parser.add_argument("--show-local-mailbox", action="store_true", help="Display local staging verification links")
    parser.add_argument("--create-admin", metavar="EMAIL", help="Create a named MFA-protected administrator")
    parser.add_argument("--run-worker-once", action="store_true", help="Process one reviewed request in local staging")
    args = parser.parse_args()
    if args.show_local_mailbox:
        mailbox_path = Path(os.getenv("CATALYX_LOCAL_MAILBOX", "state/catalyx-local-mailbox.json")).expanduser()
        if not mailbox_path.exists():
            raise SystemExit("No local verification messages are available.")
        print(mailbox_path.read_text(encoding="utf-8"))
        return
    if args.create_admin:
        bootstrap_admin(args.db, args.create_admin)
        return
    if args.run_worker_once:
        if production_mode() or os.getenv("CATALYX_ENABLE_LOCAL_WORKER") != "1":
            raise SystemExit("The manual worker is disabled. Set CATALYX_ENABLE_LOCAL_WORKER=1 in a local staging environment only.")
        from .worker import run_once

        print(json.dumps(run_once(args.db), sort_keys=True))
        return
    print("Run the staging server with: uvicorn catalyx_web.app:app --host 127.0.0.1 --port 4174")


app = create_app()

if __name__ == "__main__":
    main()

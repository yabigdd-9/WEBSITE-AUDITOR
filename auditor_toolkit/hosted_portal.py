"""HTTPS-only deployment factory for the existing private Postgres pipeline views.

No provisioning, audit, migration, bootstrap or fallback to local storage occurs
on startup or a page view. Runtime values belong in the host's secret settings.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import secrets
import time
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from argon2 import PasswordHasher, extract_parameters
from argon2.exceptions import VerificationError
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from auditor_toolkit.portal import CSRF_REQUIRED, LOGIN_PATH, OwnerPortal
from scripts.portal_auth_store import PostgresPortalAuth
from scripts.postgres_store import PostgresPipelineStore

UNAVAILABLE = "Private dashboard temporarily unavailable"
HOSTED_COOKIE = "__Host-wa_session"


@dataclass(frozen=True)
class HostedConfig:
    origin: str
    password_hash: str
    pepper: bytes
    session_seconds: int = 3600

    def validate(self):
        if not isinstance(self.origin, str) or not isinstance(self.password_hash, str):
            raise ValueError("Hosted origin and password hash are required")
        parsed = urlsplit(self.origin)
        if (parsed.scheme != "https" or parsed.path or parsed.query or parsed.fragment
                or parsed.username or parsed.password
                or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?(?::[0-9]{1,5})?", parsed.netloc)
                or parsed.hostname in {"localhost", "127.0.0.1"} or "." not in parsed.hostname):
            raise ValueError("Configure one exact HTTPS portal origin")
        try:
            extract_parameters(self.password_hash)
        except Exception:
            raise ValueError("Configure an Argon2id owner password hash privately") from None
        if (not self.password_hash.startswith("$argon2id$") or len(self.password_hash) > 512
                or not isinstance(self.pepper, bytes) or len(self.pepper) != 32
                or type(self.session_seconds) is not int or not 300 <= self.session_seconds <= 86400):
            raise ValueError("Invalid bounded hosted authentication settings")
        return self

    @classmethod
    def from_environment(cls):
        try:
            return cls(
                os.environ["WA_PORTAL_ORIGIN"], os.environ["WA_PORTAL_PASSWORD_HASH"],
                base64.b64decode(os.environ["WA_PORTAL_AUTH_PEPPER_B64"], validate=True),
                int(os.environ.get("WA_PORTAL_SESSION_SECONDS", "3600")),
            ).validate()
        except Exception:
            raise ValueError("Configure hosted portal origin and authentication secrets privately") from None


class HTTPSBoundary:
    def __init__(self, app, *, origin):
        self.app = app
        self.authority = urlsplit(origin).netloc

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            hosts = [v.decode("latin1").lower() for k, v in scope["headers"] if k.lower() == b"host"]
            if scope.get("scheme") != "https" or hosts != [self.authority]:
                response = JSONResponse(
                    {"detail": "HTTPS and the configured host are required"}, status_code=400,
                    headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


async def bounded_form(request):
    if request.headers.get("content-type", "").split(";")[0] != "application/x-www-form-urlencoded":
        raise HTTPException(415, "A form submission is required")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 4096:
            raise HTTPException(413, "Form too large")
    try:
        fields = parse_qs(raw.decode(), keep_blank_values=True, strict_parsing=True, max_num_fields=4)
        if any(len(values) != 1 for values in fields.values()):
            raise ValueError("Duplicate fields")
        return {key: values[0] for key, values in fields.items()}
    except ValueError:
        raise HTTPException(400, "Invalid form") from None


class HostedOwnerPortal(OwnerPortal):
    def __init__(self, app, config, auth):
        super().__init__(app, None, None, config.password_hash, config.session_seconds, True)
        self.config = config
        self.auth = auth

    def check_origin(self, request):
        if request.headers.getlist("origin") != [self.config.origin]:
            raise HTTPException(403, "Origin rejected")

    def session(self, request):
        token = request.cookies.get(HOSTED_COOKIE, "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            raise HTTPException(401, "Login required")
        key = hashlib.sha256(token.encode()).hexdigest()
        try:
            value = self.auth.get(key)
        except ValueError:
            raise HTTPException(503, UNAVAILABLE) from None
        if value is None:
            raise HTTPException(401, "Login required")
        return key, value

    def csrf(self, request, value, submitted=None):
        self.check_origin(request)
        super().csrf(request, value, submitted)
        key, _ = self.session(request)
        try:
            allowed = self.auth.write_attempt(key)
        except ValueError:
            raise HTTPException(503, UNAVAILABLE) from None
        if not allowed:
            raise HTTPException(429, "Review rate exceeded")

    async def headers(self, request, call_next):
        response = await super().headers(request, call_next)
        response.headers["Strict-Transport-Security"] = "max-age=15552000"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    async def login(self, request: Request):
        self.check_origin(request)
        fields = await bounded_form(request)
        if set(fields) != {"password"}:
            raise HTTPException(400, "Invalid login form")
        try:
            allowed = self.auth.login_attempt(request.client.host if request.client else "unknown")
        except ValueError:
            raise HTTPException(503, UNAVAILABLE) from None
        if not allowed:
            raise HTTPException(429, "Try again in one minute")
        try:
            PasswordHasher().verify(self.password_hash, fields["password"])
        except VerificationError:
            raise HTTPException(401, "Invalid password") from None
        token = secrets.token_urlsafe(32)
        try:
            self.auth.issue(
                hashlib.sha256(token.encode()).hexdigest(), secrets.token_urlsafe(32),
                time.time() + self.session_seconds,
            )
        except ValueError:
            raise HTTPException(503, UNAVAILABLE) from None
        response = RedirectResponse("/pipeline", status_code=303)
        response.set_cookie(
            HOSTED_COOKIE, token, httponly=True, secure=True, samesite="strict",
            max_age=self.session_seconds, path="/",
        )
        return response

    async def logout(self, request: Request):
        key, value = self.session(request)
        form = await bounded_form(request)
        if set(form) != {"csrf"}:
            raise HTTPException(403, CSRF_REQUIRED)
        self.csrf(request, value, form["csrf"])
        try:
            self.auth.revoke(key)
        except ValueError:
            raise HTTPException(503, UNAVAILABLE) from None
        response = RedirectResponse(LOGIN_PATH, status_code=303)
        response.delete_cookie(HOSTED_COOKIE, secure=True, httponly=True, samesite="strict")
        return response


def create_hosted_app(*, config=None, store=None):
    from auditor_toolkit.pipeline_portal import attach_pipeline

    config = (config or HostedConfig.from_environment()).validate()
    store = store if store is not None else PostgresPipelineStore()
    if store.read() is None:
        raise ValueError("Import the verified private pipeline state before hosting")
    auth = PostgresPortalAuth(store, pepper=config.pepper, password_hash=config.password_hash)
    auth.verify_schema()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.pipeline_store = store
    app.state.hosted = True
    owner = HostedOwnerPortal(app, config, auth)
    app.middleware("http")(owner.headers)
    app.add_middleware(HTTPSBoundary, origin=config.origin)
    app.add_api_route(LOGIN_PATH, owner.login_page, methods=["GET"], response_class=HTMLResponse)
    app.add_api_route(LOGIN_PATH, owner.login, methods=["POST"])
    app.add_api_route("/api/session", owner.session_info, methods=["GET"])
    app.add_api_route("/logout", owner.logout, methods=["POST"])
    attach_pipeline(app, store, owner.session, owner.csrf)

    @app.get("/")
    def home(request: Request):
        owner.session(request)
        return RedirectResponse("/pipeline", status_code=303)

    @app.get("/health")
    def health():
        try:
            if store.read() is None:
                raise ValueError("No state")
        except ValueError:
            raise HTTPException(503, UNAVAILABLE) from None
        return {"status": "ok"}

    return app

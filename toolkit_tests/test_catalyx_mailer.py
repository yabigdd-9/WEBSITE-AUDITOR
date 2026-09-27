from __future__ import annotations

import base64
import re
from email.message import EmailMessage
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

from catalyx_web import app as app_module
from catalyx_web import mailer
from catalyx_web.app import create_app
from catalyx_web.db import Database
from catalyx_web.security import production_deployment, valid_email_address

SMTP_ENV = {
    "CATALYX_EXTERNAL_SEND_ALLOWED": "true",
    "CATALYX_SMTP_HOST": "smtp.example.invalid",
    "CATALYX_SMTP_PORT": "587",
    "CATALYX_SMTP_USERNAME": "auditor@example.invalid",
    "CATALYX_SMTP_PASSWORD": "test-secret",
    "CATALYX_SMTP_FROM": "CatalyxLabs <auditor@example.invalid>",
}


class FakeSMTP:
    def __init__(self):
        self.started_tls = False
        self.logged_in = None
        self.message = None

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def ehlo(self):
        return None

    def starttls(self, **_kwargs):
        self.started_tls = True

    def login(self, username, password):
        self.logged_in = (username, password)

    def send_message(self, message):
        self.message = message


def test_smtp_account_message_uses_starttls_and_fixed_templates(monkeypatch):
    smtp = FakeSMTP()
    monkeypatch.setattr(mailer.smtplib, "SMTP", lambda *_args, **_kwargs: smtp)

    mailer.send_account_link(
        "customer@example.invalid",
        "email_verification",
        "https://catalyxlabs.com/verify#one-time-token",
        environ=SMTP_ENV,
    )

    assert smtp.started_tls
    assert smtp.logged_in == (SMTP_ENV["CATALYX_SMTP_USERNAME"], SMTP_ENV["CATALYX_SMTP_PASSWORD"])
    assert isinstance(smtp.message, EmailMessage)
    assert smtp.message["To"] == "customer@example.invalid"
    assert smtp.message["Subject"] == "Confirm your CatalyxLabs Website Auditor email"
    assert "one-time-token" in smtp.message.get_content()


def test_smtp_account_message_supports_implicit_tls(monkeypatch):
    smtp = FakeSMTP()
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", lambda *_args, **_kwargs: smtp)
    config = {**SMTP_ENV, "CATALYX_SMTP_PORT": "465"}

    mailer.send_account_link("customer@example.invalid", "password_reset", "https://example.invalid/reset#token", environ=config)

    assert smtp.logged_in == (config["CATALYX_SMTP_USERNAME"], config["CATALYX_SMTP_PASSWORD"])
    assert smtp.message["Subject"] == "Reset your CatalyxLabs Website Auditor password"


@pytest.mark.parametrize(
    "changes",
    [
        {"CATALYX_SMTP_PORT": "25"},
        {"CATALYX_SMTP_PASSWORD": ""},
        {"CATALYX_SMTP_FROM": "invalid-address"},
        {"CATALYX_SMTP_HOST": "bad host"},
    ],
)
def test_smtp_configuration_rejects_unsafe_or_incomplete_values(changes):
    with pytest.raises(mailer.MailConfigurationError):
        mailer.smtp_configuration({**SMTP_ENV, **changes})


def test_smtp_delivery_requires_explicit_external_send_flag(monkeypatch):
    monkeypatch.setattr(
        mailer.smtplib,
        "SMTP",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("SMTP must not be called")),
    )
    disabled = {key: value for key, value in SMTP_ENV.items() if key != "CATALYX_EXTERNAL_SEND_ALLOWED"}
    with pytest.raises(mailer.MailConfigurationError, match="delivery is disabled"):
        mailer.send_account_link(
            "customer@example.invalid",
            "password_reset",
            "https://example.invalid/reset#token",
            environ=disabled,
        )


def test_smtp_failure_hides_provider_details(monkeypatch):
    def fail(*_args, **_kwargs):
        raise OSError("private provider detail")

    monkeypatch.setattr(mailer.smtplib, "SMTP", fail)
    with pytest.raises(mailer.MailDeliveryError, match="could not be delivered") as error:
        mailer.send_account_link("customer@example.invalid", "password_reset", "https://example.invalid/reset#token", environ=SMTP_ENV)
    assert "private provider detail" not in str(error.value)


@pytest.mark.parametrize(
    "address",
    ["customer@example.invalid", "name+tag@example.co.nz"],
)
def test_valid_email_address_accepts_one_mailbox(address):
    assert valid_email_address(address)


@pytest.mark.parametrize(
    "address",
    [
        "",
        "@example.invalid",
        "customer@example",
        "customer@example.invalid,other@example.invalid",
        "customer@example.invalid\r\nBcc: other@example.invalid",
        "two..dots@example.invalid",
    ],
)
def test_valid_email_address_rejects_invalid_or_multi_recipient_syntax(address):
    assert not valid_email_address(address)


def test_vercel_preview_is_hosted_but_not_production(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "preview")
    monkeypatch.setenv("CATALYX_ENV", "production")

    assert production_deployment() is False


def test_vercel_preview_requires_isolated_hosted_configuration(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "preview")
    monkeypatch.setenv("CATALYX_ENV", "development")
    monkeypatch.delenv("CATALYX_REGISTRATION_MODE", raising=False)
    for name in (
        "CATALYX_DATABASE_URL",
        "CATALYX_PUBLIC_BASE_URL",
        "CATALYX_TOTP_ENCRYPTION_KEY",
        "CATALYX_EXTERNAL_SEND_ALLOWED",
        "CATALYX_SMTP_HOST",
        "CATALYX_SMTP_PORT",
        "CATALYX_SMTP_USERNAME",
        "CATALYX_SMTP_PASSWORD",
        "CATALYX_SMTP_FROM",
        "CATALYX_MAIL_MODE",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError, match="Hosted startup configuration is incomplete"):
        create_app()

    monkeypatch.setenv("CATALYX_DATABASE_URL", "postgresql://auditor:secret@db.example.invalid/preview")
    monkeypatch.setenv("CATALYX_PUBLIC_BASE_URL", "https://preview.example.invalid")
    monkeypatch.setenv("CATALYX_TOTP_ENCRYPTION_KEY", base64.urlsafe_b64encode(bytes(range(32))).decode())
    monkeypatch.setenv("CATALYX_MAIL_MODE", "smtp")
    for name, value in SMTP_ENV.items():
        monkeypatch.setenv(name, value)

    app = create_app()
    assert app.state.database.database_url.endswith("/preview")
    assert app.state.scan_worker_enabled is False
    assert app.state.runtime_environment == "staging"

    hosted_client = TestClient(app)
    assert hosted_client.get("/register").status_code == 404
    assert 'href="/register"' not in hosted_client.get("/").text
    assert "View the sample report" in hosted_client.get("/").text
    assert "New to Website Auditor?" not in hosted_client.get("/login").text

    monkeypatch.setenv("CATALYX_REGISTRATION_MODE", "open")
    explicitly_open_client = TestClient(create_app())
    assert explicitly_open_client.get("/register").status_code == 200


def test_hosted_account_email_is_disabled_by_default(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "preview")
    monkeypatch.setenv("CATALYX_ENV", "staging")
    monkeypatch.setenv("CATALYX_DATABASE_URL", "postgresql://auditor:secret@db.example.invalid/preview")
    monkeypatch.setenv("CATALYX_PUBLIC_BASE_URL", "https://preview.example.invalid")
    monkeypatch.setenv("CATALYX_TOTP_ENCRYPTION_KEY", base64.urlsafe_b64encode(bytes(range(32))).decode())
    monkeypatch.delenv("CATALYX_MAIL_MODE", raising=False)
    monkeypatch.delenv("CATALYX_EXTERNAL_SEND_ALLOWED", raising=False)
    for name in (
        "CATALYX_SMTP_HOST",
        "CATALYX_SMTP_PORT",
        "CATALYX_SMTP_USERNAME",
        "CATALYX_SMTP_PASSWORD",
        "CATALYX_SMTP_FROM",
    ):
        monkeypatch.delenv(name, raising=False)

    app = create_app()

    assert app.state.mail_mode == "disabled"
    assert app.state.external_send_allowed is False


def test_hosted_smtp_requires_explicit_send_enablement(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "preview")
    monkeypatch.setenv("CATALYX_ENV", "staging")
    monkeypatch.setenv("CATALYX_DATABASE_URL", "postgresql://auditor:secret@db.example.invalid/preview")
    monkeypatch.setenv("CATALYX_PUBLIC_BASE_URL", "https://preview.example.invalid")
    monkeypatch.setenv("CATALYX_TOTP_ENCRYPTION_KEY", base64.urlsafe_b64encode(bytes(range(32))).decode())
    monkeypatch.setenv("CATALYX_MAIL_MODE", "smtp")
    monkeypatch.delenv("CATALYX_EXTERNAL_SEND_ALLOWED", raising=False)
    for name, value in SMTP_ENV.items():
        if name != "CATALYX_EXTERNAL_SEND_ALLOWED":
            monkeypatch.setenv(name, value)

    with pytest.raises(RuntimeError, match="CATALYX_EXTERNAL_SEND_ALLOWED=true"):
        create_app()


def test_open_registration_is_rejected_when_mail_delivery_is_disabled(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "preview")
    monkeypatch.setenv("CATALYX_ENV", "staging")
    monkeypatch.setenv("CATALYX_DATABASE_URL", "postgresql://auditor:secret@db.example.invalid/preview")
    monkeypatch.setenv("CATALYX_PUBLIC_BASE_URL", "https://preview.example.invalid")
    monkeypatch.setenv("CATALYX_TOTP_ENCRYPTION_KEY", base64.urlsafe_b64encode(bytes(range(32))).decode())
    monkeypatch.setenv("CATALYX_REGISTRATION_MODE", "open")
    monkeypatch.setenv("CATALYX_MAIL_MODE", "disabled")
    monkeypatch.delenv("CATALYX_EXTERNAL_SEND_ALLOWED", raising=False)

    with pytest.raises(RuntimeError, match="Open registration requires"):
        create_app()


def test_vercel_production_environment_overrides_stale_staging_label(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv("CATALYX_ENV", "staging")

    assert production_deployment() is True


def test_hosted_preview_does_not_fall_back_to_ephemeral_sqlite_or_mailbox(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "preview")
    monkeypatch.setenv("CATALYX_ENV", "staging")
    for name in (
        "CATALYX_DATABASE_URL",
        "CATALYX_PUBLIC_BASE_URL",
        "CATALYX_TOTP_ENCRYPTION_KEY",
        "CATALYX_EXTERNAL_SEND_ALLOWED",
        "CATALYX_SMTP_HOST",
        "CATALYX_SMTP_PORT",
        "CATALYX_SMTP_USERNAME",
        "CATALYX_SMTP_PASSWORD",
        "CATALYX_SMTP_FROM",
        "CATALYX_MAIL_MODE",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(RuntimeError, match="Hosted startup configuration is incomplete"):
        create_app()


def test_hosted_startup_requires_explicit_runtime_configuration(monkeypatch):
    monkeypatch.setenv("CATALYX_ENV", "production")
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    for name in (
        "CATALYX_DATABASE_URL",
        "CATALYX_PUBLIC_BASE_URL",
        "CATALYX_TOTP_ENCRYPTION_KEY",
        "CATALYX_EXTERNAL_SEND_ALLOWED",
        "CATALYX_SMTP_HOST",
        "CATALYX_SMTP_PORT",
        "CATALYX_SMTP_USERNAME",
        "CATALYX_SMTP_PASSWORD",
        "CATALYX_SMTP_FROM",
        "CATALYX_MAIL_MODE",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError, match="Hosted startup configuration is incomplete"):
        create_app()


def test_hosted_startup_accepts_configured_external_dependencies(monkeypatch, tmp_path):
    monkeypatch.setenv("CATALYX_ENV", "production")
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    monkeypatch.setenv("CATALYX_DATABASE_URL", "postgresql://auditor:secret@db.example.invalid/auditor")
    monkeypatch.setenv("CATALYX_PUBLIC_BASE_URL", "https://catalyxlabs.com")
    monkeypatch.setenv("CATALYX_TOTP_ENCRYPTION_KEY", base64.urlsafe_b64encode(bytes(range(32))).decode())
    monkeypatch.setenv("CATALYX_MAIL_MODE", "smtp")
    for name, value in SMTP_ENV.items():
        monkeypatch.setenv(name, value)

    app = create_app(tmp_path / "ignored.sqlite3")

    assert app.state.database.database_url.startswith("postgresql://")
    assert app.state.scan_worker_enabled is False
    assert app.state.runtime_environment == "production"
    assert not (tmp_path / "ignored.sqlite3").exists()


def test_hosted_startup_rejects_local_mailbox_and_non_origin_public_url(monkeypatch):
    monkeypatch.setenv("CATALYX_ENV", "production")
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    monkeypatch.setenv("CATALYX_DATABASE_URL", "postgresql://auditor:secret@db.example.invalid/auditor")
    monkeypatch.setenv("CATALYX_PUBLIC_BASE_URL", "https://catalyxlabs.com/unexpected-path")
    monkeypatch.setenv("CATALYX_TOTP_ENCRYPTION_KEY", base64.urlsafe_b64encode(bytes(range(32))).decode())
    monkeypatch.setenv("CATALYX_MAIL_MODE", "local_mailbox")
    for name, value in SMTP_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("CATALYX_EXTERNAL_SEND_ALLOWED", "false")

    with pytest.raises(RuntimeError, match="HTTPS origin|must be smtp"):
        create_app()


def test_smtp_registration_and_resend_use_one_time_links_without_real_delivery(monkeypatch, tmp_path):
    for name, value in SMTP_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("CATALYX_MAIL_MODE", "smtp")
    sent = []
    monkeypatch.setattr(app_module, "send_account_link", lambda *args: sent.append(args))
    client = TestClient(create_app(tmp_path / "app.sqlite3", tmp_path / "mailbox.json"))
    response = client.get("/register")
    csrf = re.search(r'name="csrf" value="([^"]+)"', response.text).group(1)
    address = "smtp-customer@example.invalid"
    password = "a-long-account-password-456"
    response = client.post(
        "/register",
        data={"csrf": csrf, "email": address, "password": password, "password_confirm": password},
    )
    assert response.status_code == 200
    assert len(sent) == 1
    assert sent[0][0:2] == (address, "email_verification")

    resend_page = client.get("/resend-verification")
    resend_csrf = re.search(r'name="csrf" value="([^"]+)"', resend_page.text).group(1)
    response = client.post(
        "/resend-verification",
        data={"csrf": resend_csrf, "email": address},
    )
    assert response.status_code == 200
    assert "If the account needs verification" in response.text
    assert len(sent) == 2
    assert sent[1][0:2] == (address, "email_verification")
    assert urlparse(sent[0][2]).fragment != urlparse(sent[1][2]).fragment
    assert not (tmp_path / "mailbox.json").exists()


def test_smtp_account_email_budgets_are_shared_per_route_and_reserve_recovery(monkeypatch, tmp_path):
    for name, value in SMTP_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("CATALYX_MAIL_MODE", "smtp")
    monkeypatch.setattr(
        app_module,
        "AUTH_EMAIL_LIMITS_PER_HOUR",
        {"registration": 2, "verification_resend": 2, "password_reset": 2},
    )
    sent = []
    monkeypatch.setattr(app_module, "send_account_link", lambda *args: sent.append(args))
    app = create_app(tmp_path / "app.sqlite3", tmp_path / "mailbox.json")

    first = TestClient(app, client=("198.51.100.10", 8000))
    registration_page = first.get("/register")
    password = "a-long-account-password-456"
    response = first.post(
        "/register",
        data={
            "csrf": re.search(r'name="csrf" value="([^"]+)"', registration_page.text).group(1),
            "email": "first-cap@example.invalid",
            "password": password,
            "password_confirm": password,
        },
    )
    assert response.status_code == 200
    assert len(sent) == 1

    resend_page = first.get("/resend-verification")
    response = first.post(
        "/resend-verification",
        data={
            "csrf": re.search(r'name="csrf" value="([^"]+)"', resend_page.text).group(1),
            "email": "first-cap@example.invalid",
        },
    )
    assert response.status_code == 200
    assert len(sent) == 2

    distributed = TestClient(app, client=("198.51.100.11", 8000))
    registration_page = distributed.get("/register")
    response = distributed.post(
        "/register",
        data={
            "csrf": re.search(r'name="csrf" value="([^"]+)"', registration_page.text).group(1),
            "email": "second-cap@example.invalid",
            "password": password,
            "password_confirm": password,
        },
    )
    assert response.status_code == 200
    assert len(sent) == 3

    # Signup and resend traffic cannot spend the separately reserved reset
    # budget. Verify a real account locally without sending a verification link.
    from catalyx_web.security import hash_password

    reset_email = "reset-cap@example.invalid"
    reset_user_id, _ = app.state.database.create_customer(reset_email, hash_password(password))
    with app.state.database.connect() as db:
        db.execute(
            "UPDATE users SET email_verified_at=? WHERE id=?",
            ("2026-09-28T00:00:00+00:00", reset_user_id),
        )
    reset_client = TestClient(app, client=("198.51.100.12", 8000))
    reset_page = reset_client.get("/forgot-password")
    response = reset_client.post(
        "/forgot-password",
        data={
            "csrf": re.search(r'name="csrf" value="([^"]+)"', reset_page.text).group(1),
            "email": reset_email,
        },
    )
    assert response.status_code == 200
    assert len(sent) == 4

    # The registration budget is now exhausted across distinct IPs, but its
    # failure remains neutral and does not consume another route's allowance.
    third = TestClient(app, client=("198.51.100.13", 8000))
    registration_page = third.get("/register")
    response = third.post(
        "/register",
        data={
            "csrf": re.search(r'name="csrf" value="([^"]+)"', registration_page.text).group(1),
            "email": "third-cap@example.invalid",
            "password": password,
            "password_confirm": password,
        },
    )
    assert response.status_code == 200
    assert len(sent) == 4
    assert "If the address can be registered" in response.text


def test_existing_recovery_links_survive_replacement_delivery_failure(monkeypatch, tmp_path):
    for name, value in SMTP_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("CATALYX_MAIL_MODE", "smtp")
    fail_delivery = False
    sent = []

    def send_or_fail(*args):
        sent.append(args)
        if fail_delivery:
            raise app_module.MailDeliveryError("Account link could not be delivered.")

    monkeypatch.setattr(app_module, "send_account_link", send_or_fail)
    db_path = tmp_path / "app.sqlite3"
    client = TestClient(create_app(db_path, tmp_path / "mailbox.json"))
    email = "delivery-failure@example.invalid"
    password = "a-long-account-password-456"
    page = client.get("/register")
    response = client.post(
        "/register",
        data={
            "csrf": re.search(r'name="csrf" value="([^"]+)"', page.text).group(1),
            "email": email,
            "password": password,
            "password_confirm": password,
        },
    )
    assert response.status_code == 200

    with Database(db_path).connect() as db:
        user = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
    first_verification_token = urlparse(sent[0][2]).fragment
    first_verification_hash = app_module.digest_token(first_verification_token)
    fail_delivery = True
    page = client.get("/resend-verification")
    response = client.post(
        "/resend-verification",
        data={
            "csrf": re.search(r'name="csrf" value="([^"]+)"', page.text).group(1),
            "email": email,
        },
    )
    assert response.status_code == 200
    with Database(db_path).connect() as db:
        assert db.execute(
            "SELECT count(*) FROM verification_tokens WHERE user_id=? AND token_hash=?",
            (user["id"], first_verification_hash),
        ).fetchone()[0] == 1
    first_verification = client.post("/verify", data={"token": first_verification_token})
    assert first_verification.status_code == 200
    with Database(db_path).connect() as db:
        assert db.execute(
            "SELECT count(*) FROM verification_tokens WHERE user_id=?", (user["id"],)
        ).fetchone()[0] == 0

    fail_delivery = False
    page = client.get("/forgot-password")
    response = client.post(
        "/forgot-password",
        data={
            "csrf": re.search(r'name="csrf" value="([^"]+)"', page.text).group(1),
            "email": email,
        },
    )
    assert response.status_code == 200
    first_reset_token = urlparse(sent[-1][2]).fragment
    first_reset_hash = app_module.digest_token(first_reset_token)

    fail_delivery = True
    page = client.get("/forgot-password")
    response = client.post(
        "/forgot-password",
        data={
            "csrf": re.search(r'name="csrf" value="([^"]+)"', page.text).group(1),
            "email": email,
        },
    )
    assert response.status_code == 200
    with Database(db_path).connect() as db:
        assert db.execute(
            "SELECT count(*) FROM password_reset_tokens WHERE user_id=? AND token_hash=?",
            (user["id"], first_reset_hash),
        ).fetchone()[0] == 1
    response = client.post(
        "/reset-password",
        data={
            "token": first_reset_token,
            "password": "a-new-password-for-the-account-789",
            "password_confirm": "a-new-password-for-the-account-789",
        },
    )
    assert response.status_code == 200
    with Database(db_path).connect() as db:
        assert db.execute(
            "SELECT count(*) FROM password_reset_tokens WHERE user_id=?", (user["id"],)
        ).fetchone()[0] == 0


def test_email_header_recipient_lists_are_rejected():
    with pytest.raises(ValueError, match="message data is invalid"):
        mailer.send_account_link(
            "first@example.invalid,second@example.invalid",
            "email_verification",
            "https://catalyxlabs.com/verify#token",
            environ=SMTP_ENV,
        )

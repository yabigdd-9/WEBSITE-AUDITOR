from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import socket
import stat
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from urllib.parse import urlparse

import dns.exception
import dns.resolver
import httpx
import pytest
from fastapi.testclient import TestClient

from catalyx_web.app import create_app, create_runtime_app
from catalyx_web.customer_audit import _robots_can_fetch, run_authorized_static_audit
from catalyx_web.db import Database, DatabaseError, _postgres_row_factory, _PostgresConnection
from catalyx_web.egress import (
    EgressCancelledError,
    EgressPolicyError,
    EgressTransportError,
    PinnedEgressTransport,
)
from catalyx_web.security import hash_password, normalize_site, production_mode, totp_code


def form_token(response) -> str:
    match = re.search(r'name="csrf" value="([^"]+)"', response.text)
    assert match, response.text
    return match.group(1)


class FakeAddressResolver:
    def __init__(self, records):
        self.records = records
        self.calls = []

    def resolve(self, name, record_type, *, lifetime, search):
        self.calls.append((name, record_type, lifetime, search))
        records = self.records.get(record_type, ())
        if not records:
            raise dns.resolver.NoAnswer
        return [SimpleNamespace(address=address) for address in records]


def register_and_login(client: TestClient, email: str) -> str:
    response = client.get("/register")
    csrf = form_token(response)
    response = client.post(
        "/register",
        data={"csrf": csrf, "email": email, "password": "a-long-local-password-123", "password_confirm": "a-long-local-password-123"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    message = next(message for message in client.app.state.local_mailbox if message["email"] == email)
    verification_link = urlparse(message["verification_url"])
    assert not verification_link.query
    assert verification_link.fragment
    assert client.get(verification_link.path).status_code == 200
    assert client.post("/verify", data={"token": verification_link.fragment}).status_code == 200
    response = client.get("/login")
    csrf = form_token(response)
    response = client.post(
        "/login",
        data={"csrf": csrf, "email": email, "password": "a-long-local-password-123"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return message["verification_url"]


def add_site(client: TestClient) -> str:
    response = client.get("/app/sites")
    csrf = form_token(response)
    response = client.post(
        "/app/sites",
        data={"csrf": csrf, "url": "https://example.co.nz/path?session=secret", "label": "Example site"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    response = client.get("/app/sites")
    match = re.search(r'href="/app/sites/([0-9a-f-]{36})"', response.text)
    assert match
    assert "session=secret" not in response.text
    return match.group(1)


def submit_audit(client: TestClient, site_id: str) -> str:
    response = client.get(f"/app/sites/{site_id}")
    csrf = form_token(response)
    key = re.search(r'name="idempotency_key" value="([^"]+)"', response.text).group(1)
    response = client.post(
        f"/app/sites/{site_id}/audit-request",
        data={"csrf": csrf, "authorized": "yes", "idempotency_key": key},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return urlparse(response.headers["location"]).path.rsplit("/", 1)[1]


def test_public_pages_and_readiness_are_truthful(tmp_path):
    db_path = tmp_path / "app.sqlite3"
    client = TestClient(create_app(db_path, tmp_path / "mailbox.json"))
    response = client.get("/")
    assert response.status_code == 200
    assert "Scanning is not enabled in this staging preview" in response.text
    assert client.get("/api/health").json() == {"status": "ok", "environment": "staging", "scan_worker": "disabled"}
    assert client.get("/api/health/live").json() == {"status": "ok"}
    assert client.get("/api/health/ready").json() == {"status": "ready", "database": "ok", "queue": "ok", "scan_worker": "disabled"}
    assert "ILLUSTRATIVE ONLY" in client.get("/sample-report").text
    assert client.get("/what-we-check").status_code == 200
    assert stat.S_IMODE(db_path.stat().st_mode) == 0o600


@pytest.mark.parametrize("module_name", ["mm_transport", "mm_model_router", "mm_approval"])
def test_app_startup_blocks_money_machine_authority_modules(tmp_path, monkeypatch, module_name):
    database_path = tmp_path / "must-not-be-created.sqlite3"
    monkeypatch.setitem(sys.modules, module_name, object())

    with pytest.raises(RuntimeError, match="cannot load Money Machine"):
        create_runtime_app(database_path, tmp_path / "mailbox.json")

    assert not database_path.exists()


def test_accessibility_error_announcement_and_current_page_state(tmp_path):
    client = TestClient(create_app(tmp_path / "app.sqlite3", tmp_path / "mailbox.json"))
    register_page = client.get("/register")
    error = client.post(
        "/register",
        data={
            "csrf": form_token(register_page),
            "email": "accessible@example.invalid",
            "password": "a-long-local-password-123",
            "password_confirm": "a-different-password-456",
        },
    )
    assert error.status_code == 400
    assert '<p class="form-error" role="alert" aria-atomic="true">The passwords do not match.</p>' in error.text

    register_and_login(client, "accessible@example.invalid")
    workspace = client.get("/app")
    assert '<a class="active" aria-current="page" href="/app">Overview</a>' in workspace.text


def test_customer_dashboard_counts_all_requests_and_shows_only_five_recent(tmp_path):
    client = TestClient(create_app(tmp_path / "app.sqlite3", tmp_path / "mailbox.json"))
    register_and_login(client, "dashboard-count@example.invalid")
    site_id = add_site(client)
    for _ in range(6):
        submit_audit(client, site_id)

    dashboard = client.get("/app")

    assert dashboard.status_code == 200
    assert '<span>Audit requests</span><strong>6</strong>' in dashboard.text
    assert dashboard.text.count('href="/app/audits/') == 5


def test_sqlite_database_file_permissions_are_owner_only(tmp_path, monkeypatch):
    db_path = tmp_path / "app.sqlite3"
    Database(db_path)
    assert stat.S_IMODE(db_path.stat().st_mode) == 0o600

    db_path.chmod(0o644)
    Database(db_path)
    assert stat.S_IMODE(db_path.stat().st_mode) == 0o600

    linked_path = tmp_path / "linked.sqlite3"
    linked_path.symlink_to(db_path)
    with pytest.raises(DatabaseError, match="must not be a symbolic link"):
        Database(linked_path)

    def deny_permission_change(_descriptor, _mode):
        raise PermissionError("permission change denied")

    with monkeypatch.context() as patch_context:
        patch_context.setattr("catalyx_web.db.os.fchmod", deny_permission_change)
        with pytest.raises(DatabaseError, match="permissions could not be secured"):
            Database(tmp_path / "unsecure.sqlite3")


def test_admin_totp_secrets_are_encrypted_and_legacy_seeds_are_migrated(tmp_path):
    db_path = tmp_path / "app.sqlite3"
    database = Database(db_path)
    secret = "JBSWY3DPEHPK3PXP"
    user_id = database.create_admin(
        "encrypted-admin@example.invalid",
        hash_password("a-long-admin-password-456"),
        secret,
    )
    with database.connect() as db:
        membership = db.execute(
            "SELECT workspace_id,user_id,totp_secret FROM memberships WHERE user_id=?",
            (user_id,),
        ).fetchone()
    assert membership["totp_secret"].startswith("enc:v1:")
    assert secret not in membership["totp_secret"]
    assert database.decrypt_totp_secret(
        membership["totp_secret"], membership["workspace_id"], membership["user_id"]
    ) == secret
    assert stat.S_IMODE((tmp_path / "app.sqlite3.totp-key").stat().st_mode) == 0o600

    # A version-4 local database may have a legacy seed from before encryption.
    with database.connect() as db:
        db.execute(
            "UPDATE memberships SET totp_secret=? WHERE user_id=?",
            (secret, user_id),
        )
    migrated_database = Database(db_path)
    with migrated_database.connect() as db:
        migrated = db.execute(
            "SELECT workspace_id,user_id,totp_secret FROM memberships WHERE user_id=?",
            (user_id,),
        ).fetchone()
    assert migrated["totp_secret"].startswith("enc:v1:")
    assert migrated_database.decrypt_totp_secret(
        migrated["totp_secret"], migrated["workspace_id"], migrated["user_id"]
    ) == secret


def test_totp_key_rotation_validates_then_reencrypts_atomically(tmp_path):
    db_path = tmp_path / "rotation.sqlite3"
    old_key = b"o" * 32
    new_key = b"n" * 32
    database = Database(db_path, totp_encryption_key=old_key)
    first_secret = "JBSWY3DPEHPK3PXP"
    second_secret = "KRSXG5DSNFXGOIDB"
    first_id = database.create_admin(
        "first-admin@example.invalid",
        hash_password("a-long-admin-password-456"),
        first_secret,
    )
    second_id = database.create_admin(
        "second-admin@example.invalid",
        hash_password("another-long-admin-password-789"),
        second_secret,
    )

    dry_run = database.rotate_totp_secrets(old_key, new_key)
    assert dry_run == {
        "total": 2,
        "rotated": 0,
        "would_rotate": 2,
        "already_current": 0,
        "applied": False,
    }
    with database.connect() as db:
        old_envelopes = {
            row["user_id"]: row["totp_secret"]
            for row in db.execute(
                "SELECT user_id,totp_secret FROM memberships WHERE user_id IN (?,?)",
                (first_id, second_id),
            )
        }

    applied = database.rotate_totp_secrets(old_key, new_key, apply=True)
    assert applied["rotated"] == 2
    new_database = Database(db_path, initialize=False, totp_encryption_key=new_key)
    with new_database.connect() as db:
        new_rows = {
            row["user_id"]: row
            for row in db.execute(
                "SELECT workspace_id,user_id,totp_secret FROM memberships WHERE user_id IN (?,?)",
                (first_id, second_id),
            )
        }
    assert new_database.decrypt_totp_secret(
        new_rows[first_id]["totp_secret"], new_rows[first_id]["workspace_id"], first_id
    ) == first_secret
    assert new_database.decrypt_totp_secret(
        new_rows[second_id]["totp_secret"], new_rows[second_id]["workspace_id"], second_id
    ) == second_secret
    assert all(new_rows[user_id]["totp_secret"] != envelope for user_id, envelope in old_envelopes.items())

    repeated = new_database.rotate_totp_secrets(old_key, new_key)
    assert repeated["would_rotate"] == 0
    assert repeated["already_current"] == 2


def test_totp_key_rotation_wrong_key_changes_nothing(tmp_path):
    db_path = tmp_path / "rotation-wrong-key.sqlite3"
    old_key = b"o" * 32
    new_key = b"n" * 32
    wrong_key = b"x" * 32
    database = Database(db_path, totp_encryption_key=old_key)
    user_id = database.create_admin(
        "admin@example.invalid",
        hash_password("a-long-admin-password-456"),
        "JBSWY3DPEHPK3PXP",
    )
    with database.connect() as db:
        previous = db.execute(
            "SELECT totp_secret FROM memberships WHERE user_id=?", (user_id,)
        ).fetchone()["totp_secret"]

    with pytest.raises(ValueError, match="matches neither rotation key"):
        database.rotate_totp_secrets(wrong_key, new_key, apply=True)

    with database.connect() as db:
        current = db.execute(
            "SELECT totp_secret FROM memberships WHERE user_id=?", (user_id,)
        ).fetchone()["totp_secret"]
    assert current == previous


def test_totp_key_rotation_command_defaults_to_validation_and_never_prints_keys(
    tmp_path, monkeypatch, capsys
):
    from catalyx_web.totp_key_rotation import main

    db_path = tmp_path / "rotation-cli.sqlite3"
    old_key = b"o" * 32
    new_key = b"n" * 32
    old_encoded = base64.urlsafe_b64encode(old_key).decode("ascii")
    new_encoded = base64.urlsafe_b64encode(new_key).decode("ascii")
    monkeypatch.setenv("CATALYX_TOTP_ROTATION_OLD_KEY", old_encoded)
    monkeypatch.setenv("CATALYX_TOTP_ROTATION_NEW_KEY", new_encoded)
    database = Database(db_path, totp_encryption_key=old_key)
    user_id = database.create_admin(
        "cli-admin@example.invalid",
        hash_password("a-long-admin-password-456"),
        "JBSWY3DPEHPK3PXP",
    )
    monkeypatch.setattr("sys.argv", ["catalyx-totp-key-rotate", "--database", str(db_path)])

    main()
    dry_run_output = capsys.readouterr().out
    assert "validated total=1 would_rotate=1 already_current=0 applied=false" in dry_run_output
    assert old_encoded not in dry_run_output
    assert new_encoded not in dry_run_output

    monkeypatch.setattr(
        "sys.argv", ["catalyx-totp-key-rotate", "--database", str(db_path), "--apply"]
    )
    main()
    applied_output = capsys.readouterr().out
    assert "rotated total=1 would_rotate=1 already_current=0 applied=true" in applied_output
    assert old_encoded not in applied_output
    assert new_encoded not in applied_output
    with Database(db_path, initialize=False, totp_encryption_key=new_key).connect() as db:
        assert db.execute("SELECT 1 FROM memberships WHERE user_id=?", (user_id,)).fetchone()


def test_totp_key_rotation_command_does_not_create_a_missing_database(tmp_path, monkeypatch):
    from catalyx_web.totp_key_rotation import main

    db_path = tmp_path / "missing.sqlite3"
    monkeypatch.setattr("sys.argv", ["catalyx-totp-key-rotate", "--database", str(db_path)])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert not db_path.exists()


def test_postgres_requires_an_explicit_totp_encryption_key(monkeypatch):
    monkeypatch.delenv("CATALYX_TOTP_ENCRYPTION_KEY", raising=False)
    with pytest.raises(DatabaseError, match="CATALYX_TOTP_ENCRYPTION_KEY is required"):
        Database("postgresql://local.invalid/catalyx", initialize=False)


def test_email_links_use_the_configured_fixed_public_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("CATALYX_PUBLIC_BASE_URL", "https://preview.example.invalid")
    client = TestClient(create_app(tmp_path / "app.sqlite3", tmp_path / "mailbox.json"))
    verification_url = register_and_login(client, "fixed-origin@example.invalid")
    assert verification_url.startswith("https://preview.example.invalid/verify#")
    assert not client.app.state.local_mailbox


def test_production_refuses_dynamic_email_link_host_without_fixed_public_origin(monkeypatch):
    from fastapi import HTTPException
    from starlette.requests import Request

    from catalyx_web.app import _public_base_url

    for key in ("CATALYX_ENV", "VERCEL", "K_SERVICE", "AWS_LAMBDA_FUNCTION_NAME", "CATALYX_PUBLIC_BASE_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("VERCEL", "1")
    scope = {"type": "http", "scheme": "https", "server": ("attacker.vercel.app", 443), "headers": [], "method": "GET", "path": "/", "query_string": b""}
    with pytest.raises(HTTPException) as error:
        _public_base_url(Request(scope))
    assert error.value.status_code == 503


def test_serverless_platform_cannot_be_downgraded_to_local_mode(monkeypatch):
    for key in ("CATALYX_ENV", "VERCEL", "K_SERVICE", "AWS_LAMBDA_FUNCTION_NAME"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("CATALYX_ENV", "development")
    assert production_mode()

    monkeypatch.delenv("VERCEL")
    assert not production_mode()

    monkeypatch.setenv("CATALYX_ENV", "staging")
    assert production_mode()


def test_postgres_adapter_keeps_mapping_and_positional_rows_and_binds_parameters():
    class FakeConnection:
        def execute(self, statement, parameters):
            self.statement = statement
            self.parameters = parameters
            return "cursor"

    fake = FakeConnection()
    psycopg_types = SimpleNamespace(IntegrityError=type("FakeIntegrityError", (Exception,), {}), Error=Exception)
    connection = _PostgresConnection(fake, psycopg_types)
    assert connection.execute("SELECT id FROM users WHERE email=?", ("safe@example.invalid",)) == "cursor"
    assert fake.statement == "SELECT id FROM users WHERE email=%s"
    assert fake.parameters == ("safe@example.invalid",)

    cursor = SimpleNamespace(description=[SimpleNamespace(name="id"), SimpleNamespace(name="count")])
    row = _postgres_row_factory(cursor)(("user-1", 3))
    assert row["id"] == "user-1"
    assert row[0] == "user-1"
    assert row[1] == 3


def test_auth_rate_limits_persist_between_database_instances_and_hash_subjects(tmp_path):
    database_path = tmp_path / "rate-limits.sqlite3"
    first = Database(database_path)
    assert first.allow_rate_attempt("login", "203.0.113.12", 2, 60, now=1000)
    assert first.allow_rate_attempt("login", "203.0.113.12", 2, 60, now=1001)

    restarted = Database(database_path)
    assert not restarted.allow_rate_attempt("login", "203.0.113.12", 2, 60, now=1002)
    assert restarted.allow_rate_attempt("login", "203.0.113.13", 2, 60, now=1002)
    assert restarted.allow_rate_attempt("login", "203.0.113.12", 2, 60, now=1060)

    with restarted.connect() as db:
        stored = [row["subject_hash"] for row in db.execute("SELECT subject_hash FROM auth_rate_limits")]
    assert "203.0.113.12" not in stored
    assert all(len(value) == 64 for value in stored)


def test_auth_rate_limit_attempt_reservations_are_atomic_across_connections(tmp_path):
    database = Database(tmp_path / "concurrent-rate-limits.sqlite3")
    with ThreadPoolExecutor(max_workers=16) as pool:
        decisions = list(
            pool.map(
                lambda _attempt: database.allow_rate_attempt(
                    "login_account", "customer@example.invalid", 12, 3600
                ),
                range(32),
            )
        )

    assert sum(decisions) == 12


def test_login_failure_limit_is_account_scoped_and_persistent(tmp_path):
    db_path = tmp_path / "account-rate-limit.sqlite3"
    mailbox_path = tmp_path / "mailbox.json"
    app = create_app(db_path, mailbox_path)
    register_and_login(TestClient(app), "customer@example.invalid")

    for attempt in range(12):
        client = TestClient(app, client=(f"203.0.113.{attempt + 1}", 8000))
        login_page = client.get("/login")
        response = client.post(
            "/login",
            data={
                "csrf": form_token(login_page),
                "email": "CUSTOMER@example.invalid",
                "password": "incorrect-password-for-test",
            },
        )
        assert response.status_code == 401

    restarted_app = create_app(db_path, mailbox_path)
    blocked = TestClient(restarted_app, client=("203.0.113.100", 8000))
    login_page = blocked.get("/login")
    limited = blocked.post(
        "/login",
        data={
            "csrf": form_token(login_page),
            "email": "customer@example.invalid",
            "password": "incorrect-password-for-test",
        },
    )
    assert limited.status_code == 429

    with Database(db_path).connect() as db:
        stored_subjects = [
            row["subject_hash"]
            for row in db.execute(
                "SELECT subject_hash FROM auth_rate_limits WHERE scope='login_account'"
            )
        ]
    assert len(stored_subjects) == 1
    assert all(len(subject) == 64 for subject in stored_subjects)
    assert "customer@example.invalid" not in stored_subjects

    database = Database(db_path)
    assert database.rate_attempt_available(
        "login_account", "customer@example.invalid", 12, 3600, now=10**10
    )

    clear_email = "success@example.invalid"
    register_and_login(TestClient(restarted_app), clear_email)
    failed_client = TestClient(restarted_app, client=("203.0.114.1", 8000))
    login_page = failed_client.get("/login")
    assert failed_client.post(
        "/login",
        data={"csrf": form_token(login_page), "email": clear_email, "password": "wrong"},
    ).status_code == 401
    successful_client = TestClient(restarted_app, client=("203.0.114.2", 8000))
    login_page = successful_client.get("/login")
    assert successful_client.post(
        "/login",
        data={
            "csrf": form_token(login_page),
            "email": clear_email,
            "password": "a-long-local-password-123",
        },
        follow_redirects=False,
    ).status_code == 303
    with Database(db_path).connect() as db:
        assert db.execute(
            "SELECT 1 FROM auth_rate_limits WHERE scope='login_account' AND subject_hash=?",
            (hashlib.sha256(clear_email.encode()).hexdigest(),),
        ).fetchone() is None


def test_schema_v3_database_migrates_to_persistent_auth_rate_limits(tmp_path):
    database_path = tmp_path / "upgrade.sqlite3"
    old_database = Database(database_path)
    with old_database.connect() as db:
        db.execute("DROP TABLE auth_rate_limits")
        db.execute("PRAGMA user_version=3")

    upgraded = Database(database_path)
    assert upgraded.allow_rate_attempt("login", "192.0.2.4", 2, 60, now=2000)
    with upgraded.connect() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 5
        columns = {row["name"] for row in db.execute("PRAGMA table_info(audit_requests)")}
        assert "worker_lease_token" in columns


def test_password_reset_is_neutral_one_time_and_revokes_sessions(tmp_path):
    db_path = tmp_path / "app.sqlite3"
    mailbox_path = tmp_path / "mailbox.json"
    client = TestClient(create_app(db_path, mailbox_path))

    forgot_page = client.get("/forgot-password")
    unknown_response = client.post(
        "/forgot-password",
        data={"csrf": form_token(forgot_page), "email": "missing@example.invalid"},
    )
    assert unknown_response.status_code == 200
    assert "If the address can be reset" in unknown_response.text
    assert not mailbox_path.exists()

    register_and_login(client, "customer@example.invalid")
    site_page = client.get("/app")
    assert site_page.status_code == 200
    login_page = TestClient(create_app(db_path, mailbox_path)).get("/login")
    assert "Forgot your password?" in login_page.text
    forgot_page = client.get("/forgot-password")
    reset_response = client.post(
        "/forgot-password",
        data={"csrf": form_token(forgot_page), "email": "customer@example.invalid"},
    )
    assert reset_response.status_code == 200
    messages = json.loads(mailbox_path.read_text())
    message = next(item for item in messages if item["kind"] == "password_reset")
    reset_link = urlparse(message["verification_url"])
    assert reset_link.path == "/reset-password"
    assert not reset_link.query
    assert reset_link.fragment
    assert stat.S_IMODE(mailbox_path.stat().st_mode) == 0o600
    assert client.get(reset_link.path).status_code == 200

    changed = client.post(
        "/reset-password",
        data={
            "token": reset_link.fragment,
            "password": "a-new-local-password-456",
            "password_confirm": "a-new-local-password-456",
        },
    )
    assert changed.status_code == 200
    assert "Your other sessions were signed out" in changed.text
    assert not any(item["kind"] == "password_reset" for item in json.loads(mailbox_path.read_text()))
    assert not any(item["kind"] == "password_reset" for item in client.app.state.local_mailbox)
    assert client.get("/app").status_code == 401
    assert client.post(
        "/reset-password",
        data={
            "token": reset_link.fragment,
            "password": "another-new-password-789",
            "password_confirm": "another-new-password-789",
        },
    ).status_code == 400
    login_page = client.get("/login")
    old_password = client.post(
        "/login",
        data={"csrf": form_token(login_page), "email": "customer@example.invalid", "password": "a-long-local-password-123"},
        follow_redirects=False,
    )
    assert old_password.status_code == 401
    login_page = client.get("/login")
    new_password = client.post(
        "/login",
        data={"csrf": form_token(login_page), "email": "customer@example.invalid", "password": "a-new-local-password-456"},
        follow_redirects=False,
    )
    assert new_password.status_code == 303


def test_local_mailbox_prunes_expired_bearer_links_on_startup(tmp_path):
    db_path = tmp_path / "app.sqlite3"
    mailbox_path = tmp_path / "mailbox.json"
    mailbox_path.write_text(
        json.dumps(
            [
                {
                    "email": "expired@example.invalid",
                    "kind": "password_reset",
                    "verification_url": "https://auditor.example.invalid/reset-password#expired-token",
                    "created_at": "2026-09-27T00:00:00+00:00",
                    "expires_at": int(time.time()) - 1,
                },
                {
                    "email": "current@example.invalid",
                    "kind": "email_verification",
                    "verification_url": "https://auditor.example.invalid/verify#current-token",
                    "created_at": "2026-09-28T00:00:00+00:00",
                    "expires_at": int(time.time()) + 600,
                },
            ]
        )
    )

    client = TestClient(create_app(db_path, mailbox_path))

    stored = json.loads(mailbox_path.read_text())
    assert [item["email"] for item in stored] == ["current@example.invalid"]
    assert client.app.state.local_mailbox == stored
    assert stat.S_IMODE(mailbox_path.stat().st_mode) == 0o600


def test_browser_responses_include_security_headers(tmp_path):
    client = TestClient(
        create_app(tmp_path / "app.sqlite3", tmp_path / "mailbox.json"),
        base_url="https://catalyxlabs.com",
    )

    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Cache-Control"] == "no-store"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"

    oversized = client.post(
        "/login",
        content="x" * 32_769,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert oversized.status_code == 413
    assert oversized.headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'self'" in oversized.headers["Content-Security-Policy"]


def test_versioned_api_enforces_tenancy_and_admin_review(tmp_path):
    db_path = tmp_path / "app.sqlite3"
    mailbox_path = tmp_path / "mailbox.json"
    customer = TestClient(create_app(db_path, mailbox_path))
    assert customer.get("/api/v1/me").status_code == 401
    register_and_login(customer, "api-customer@example.invalid")
    me = customer.get("/api/v1/me").json()
    assert me["role"] == "customer"
    headers = {"X-CSRF-Token": me["csrf_token"]}

    site_response = customer.post(
        "/api/v1/sites",
        json={"url": "https://example.co.nz/private/path?token=secret", "label": "Example"},
        headers=headers,
    )
    assert site_response.status_code == 201
    site = site_response.json()["site"]
    assert site["origin"] == "https://example.co.nz"
    assert "private" not in json.dumps(site)
    assert customer.get("/api/v1/sites").json()["sites"][0]["id"] == site["id"]
    assert customer.post(
        "/api/v1/sites",
        json={"url": "http://127.0.0.1", "label": "Local"},
        headers=headers,
    ).status_code == 400
    assert customer.post(
        "/api/v1/sites",
        json={"url": "https://second.example", "label": "Second"},
    ).status_code == 403

    audit_response = customer.post(
        f"/api/v1/sites/{site['id']}/audits",
        json={"authorized": True},
        headers={**headers, "Idempotency-Key": "api-request-0001"},
    )
    assert audit_response.status_code == 201
    audit = audit_response.json()["audit"]
    assert audit["state"] == "authorization_review"
    duplicate = customer.post(
        f"/api/v1/sites/{site['id']}/audits",
        json={"authorized": True},
        headers={**headers, "Idempotency-Key": "api-request-0001"},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["created"] is False
    assert duplicate.json()["audit"]["id"] == audit["id"]
    assert customer.get(f"/api/v1/audits/{audit['id']}").json()["audit"]["report"] is None

    other_customer = TestClient(create_app(db_path, tmp_path / "other-mailbox.json"))
    register_and_login(other_customer, "other-api-customer@example.invalid")
    assert other_customer.get(f"/api/v1/sites/{site['id']}").status_code == 404
    assert other_customer.get(f"/api/v1/audits/{audit['id']}").status_code == 404
    assert customer.get("/api/v1/admin/audits").status_code == 403

    admin_secret = "JBSWY3DPEHPK3PXP"
    Database(db_path).create_admin("api-admin@example.invalid", hash_password("a-long-admin-password-456"), admin_secret)
    admin = TestClient(create_app(db_path, tmp_path / "admin-mailbox.json"))
    login_page = admin.get("/login")
    admin_login = admin.post(
        "/login",
        data={"csrf": form_token(login_page), "email": "api-admin@example.invalid", "password": "a-long-admin-password-456", "otp": totp_code(admin_secret)},
        follow_redirects=False,
    )
    assert admin_login.status_code == 303
    admin_me = admin.get("/api/v1/me").json()
    assert admin_me["role"] == "owner"
    queue = admin.get("/api/v1/admin/audits?state=authorization_review").json()["audits"]
    assert any(row["id"] == audit["id"] for row in queue)
    decision = admin.post(
        f"/api/v1/admin/audits/{audit['id']}/decision",
        json={"decision": "approve", "reason": "Authorization details reviewed"},
        headers={"X-CSRF-Token": admin_me["csrf_token"]},
    )
    assert decision.status_code == 200
    assert decision.json()["audit"]["state"] == "queued"
    assert customer.get(f"/api/v1/audits/{audit['id']}").json()["audit"]["state"] == "queued"

    reviewer_secret = "MZXW6YTBOI"
    Database(db_path).create_admin("reviewer@example.invalid", hash_password("a-long-reviewer-password-789"), reviewer_secret)
    with Database(db_path).connect() as db:
        db.execute("UPDATE memberships SET role='reviewer' WHERE user_id=(SELECT id FROM users WHERE email=?)", ("reviewer@example.invalid",))
    reviewer = TestClient(create_app(db_path, tmp_path / "reviewer-mailbox.json"))
    reviewer_login_page = reviewer.get("/login")
    assert reviewer.post(
        "/login",
        data={"csrf": form_token(reviewer_login_page), "email": "reviewer@example.invalid", "password": "a-long-reviewer-password-789", "otp": totp_code(reviewer_secret)},
        follow_redirects=False,
    ).status_code == 303
    assert reviewer.get("/admin").status_code == 200
    reviewer_home = reviewer.get("/admin").text
    nav = re.search(r'<nav class="workspace-nav"[^>]*>(.*?)</nav>', reviewer_home).group(1)
    assert "/admin/audits" in nav and "/admin/jobs" in nav
    assert "/admin/customers" not in nav and "/admin/privacy-requests" not in nav and "/admin/activity" not in nav
    assert reviewer.get("/admin/customers").status_code == 403
    assert reviewer.get("/admin/privacy-requests").status_code == 403


def test_admin_route_role_matrix(tmp_path):
    db_path = tmp_path / "roles.sqlite3"
    clients = {}

    customer = TestClient(create_app(db_path, tmp_path / "customer-mailbox.json"))
    register_and_login(customer, "role-customer@example.invalid")
    clients["customer"] = customer

    database = Database(db_path)
    for role in ("owner", "admin", "reviewer", "support"):
        email = f"role-{role}@example.invalid"
        password = "a-long-role-password-456"
        secret = "JBSWY3DPEHPK3PXP"
        user_id = database.create_admin(email, hash_password(password), secret)
        if role != "owner":
            with database.connect() as db:
                db.execute("UPDATE memberships SET role=? WHERE user_id=?", (role, user_id))
        client = TestClient(create_app(db_path, tmp_path / f"{role}-mailbox.json"))
        login_page = client.get("/login")
        response = client.post(
            "/login",
            data={
                "csrf": form_token(login_page),
                "email": email,
                "password": password,
                "otp": totp_code(secret),
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        clients[role] = client

    reviewer_roles = {"owner", "admin", "reviewer"}
    owner_admin_roles = {"owner", "admin"}
    customer_support_roles = {"owner", "admin", "support"}
    read_routes = (
        ("/admin", reviewer_roles, 200),
        ("/admin/audits", reviewer_roles, 200),
        ("/admin/audits/missing-audit", reviewer_roles, 404),
        ("/admin/sites", reviewer_roles, 200),
        ("/admin/jobs", reviewer_roles, 200),
        ("/admin/operations", owner_admin_roles, 200),
        ("/admin/privacy-requests", owner_admin_roles, 200),
        ("/admin/privacy-requests/missing-request", owner_admin_roles, 404),
        ("/admin/customers", customer_support_roles, 200),
        ("/admin/customers/missing-customer", customer_support_roles, 404),
        ("/admin/activity", owner_admin_roles, 200),
        ("/api/v1/admin/overview", reviewer_roles, 200),
        ("/api/v1/admin/audits", reviewer_roles, 200),
    )
    for role, client in clients.items():
        for path, allowed_roles, allowed_status in read_routes:
            expected = allowed_status if role in allowed_roles else 403
            assert client.get(path).status_code == expected, (role, path)

    assert "Production hosting is not approved" in clients["owner"].get("/admin").text
    assert "WebCrypto prototype passes" in clients["owner"].get("/admin/operations").text

    mutation_routes = (
        (
            "POST",
            "/admin/audits/missing-audit/decision",
            {"decision": "approve", "reason": "Role matrix review"},
            reviewer_roles,
            False,
        ),
        (
            "POST",
            "/admin/audits/missing-audit/report-decision",
            {"decision": "release", "reason": "Role matrix review"},
            reviewer_roles,
            False,
        ),
        (
            "POST",
            "/admin/audits/missing-audit/retry",
            {"reason": "Role matrix review"},
            reviewer_roles,
            False,
        ),
        (
            "POST",
            "/admin/privacy-requests/missing-request/decision",
            {"decision": "identity_review", "reason": "Role matrix review"},
            owner_admin_roles,
            False,
        ),
        (
            "POST",
            "/admin/customers/missing-customer/disable",
            {"reason": "Role matrix review"},
            owner_admin_roles,
            False,
        ),
        (
            "POST",
            "/api/v1/admin/audits/missing-audit/decision",
            {"decision": "approve", "reason": "Role matrix review"},
            reviewer_roles,
            True,
        ),
        (
            "POST",
            "/api/v1/admin/audits/missing-audit/report-decision",
            {"decision": "release", "reason": "Role matrix review"},
            reviewer_roles,
            True,
        ),
    )
    for role, client in clients.items():
        csrf = client.get("/api/v1/me").json()["csrf_token"]
        for method, path, payload, allowed_roles, is_json in mutation_routes:
            if is_json:
                response = client.request(
                    method,
                    path,
                    json=payload,
                    headers={"X-CSRF-Token": csrf},
                )
            else:
                response = client.request(
                    method,
                    path,
                    data={"csrf": csrf, **payload},
                )
            expected = 404 if role in allowed_roles else 403
            assert response.status_code == expected, (role, method, path)


def test_customer_ownership_and_request_review_with_admin_mfa(tmp_path, monkeypatch):
    db_path = tmp_path / "app.sqlite3"
    client_a = TestClient(create_app(db_path, tmp_path / "mailbox-a.json"))
    register_and_login(client_a, "a@example.invalid")
    site_id = add_site(client_a)
    audit_id = submit_audit(client_a, site_id)
    detail = client_a.get(f"/app/audits/{audit_id}")
    assert detail.status_code == 200
    assert "Waiting for authorization review" in detail.text
    assert "does not enable public scanning" in detail.text

    client_b = TestClient(create_app(db_path, tmp_path / "mailbox-b.json"))
    register_and_login(client_b, "b@example.invalid")
    assert client_b.get(f"/app/audits/{audit_id}").status_code == 404

    secret = "JBSWY3DPEHPK3PXP"
    database = Database(db_path)
    password_hash = hash_password("a-long-admin-password-456")
    database.create_admin("admin@example.invalid", password_hash, secret)
    admin = TestClient(create_app(db_path, tmp_path / "mailbox-admin.json"))
    login_page = admin.get("/login")
    response = admin.post(
        "/login",
        data={"csrf": form_token(login_page), "email": "admin@example.invalid", "password": "a-long-admin-password-456", "otp": "abcdef"},
        follow_redirects=False,
    )
    assert response.status_code == 401
    login_page = admin.get("/login")
    response = admin.post(
        "/login",
        data={"csrf": form_token(login_page), "email": "admin@example.invalid", "password": "a-long-admin-password-456", "otp": totp_code(secret)},
        follow_redirects=False,
    )
    assert response.status_code == 303
    detail = admin.get(f"/admin/audits/{audit_id}")
    assert detail.status_code == 200
    csrf = form_token(detail)
    decision = admin.post(
        f"/admin/audits/{audit_id}/decision",
        data={"csrf": csrf, "decision": "approve", "reason": "Authorization details reviewed"},
        follow_redirects=False,
    )
    assert decision.status_code == 303
    customer_detail = client_a.get(f"/app/audits/{audit_id}")
    assert "Approved · waiting for the secure scan worker" in customer_detail.text
    assert client_b.get(f"/app/audits/{audit_id}").status_code == 404

    def staged_result(_origin, *, cancel_check=None):
        return {
            "schema_version": 1,
            "profile": "customer_static_single_page_v1",
            "status": "complete",
            "site_host": "example.co.nz",
            "started_at": "2026-09-27T00:00:00+00:00",
            "completed_at": "2026-09-27T00:00:01+00:00",
            "checks": {"fetch": {"status": "complete", "http_status": 200}},
            "findings": [{"id": "sample-id", "check": "page", "title": "Sample finding", "severity": "low", "confidence": "observed", "evidence_ref": "checks.page", "recommendation": "Review the page metadata."}],
            "limitations": ["deep_crawl", "browser"],
        }

    from catalyx_web import worker

    monkeypatch.setattr(worker, "run_authorized_static_audit", staged_result)
    result = worker.run_once(db_path)
    assert result["status"] == "quality_review"
    assert "Sample finding" not in client_a.get(f"/app/audits/{audit_id}").text
    quality_page = admin.get(f"/admin/audits/{audit_id}")
    assert "Sample finding" in quality_page.text
    response = admin.post(
        f"/admin/audits/{audit_id}/report-decision",
        data={"csrf": form_token(quality_page), "decision": "release", "reason": "Evidence and coverage reviewed"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    released = client_a.get(f"/app/audits/{audit_id}")
    assert "Sample finding" in released.text
    assert client_b.get(f"/app/audits/{audit_id}").status_code == 404
    with database.connect() as db:
        state = db.execute("SELECT state FROM audit_requests WHERE id=?", (audit_id,)).fetchone()["state"]
        actions = db.execute("SELECT action,reason FROM admin_activity WHERE target_id=?", (audit_id,)).fetchall()
    assert state == "released"
    assert [(row["action"], row["reason"]) for row in actions] == [
        ("audit_approve", "Authorization details reviewed"),
        ("report_release", "Evidence and coverage reviewed"),
    ]

    cancelled_id = submit_audit(client_a, site_id)
    cancel_page = client_a.get(f"/app/audits/{cancelled_id}")
    response = client_a.post(
        f"/app/audits/{cancelled_id}/cancel",
        data={"csrf": form_token(cancel_page)},
        follow_redirects=False,
    )
    assert response.status_code == 303
    with database.connect() as db:
        assert db.execute("SELECT state FROM audit_requests WHERE id=?", (cancelled_id,)).fetchone()["state"] == "cancelled"

    settings = client_a.get("/app/settings")
    response = client_a.post(
        "/app/settings/privacy-requests",
        data={"csrf": form_token(settings), "request_type": "delete", "customer_note": "Please review my account deletion request."},
        follow_redirects=False,
    )
    assert response.status_code == 303
    with database.connect() as db:
        privacy_id = db.execute("SELECT id FROM privacy_requests WHERE user_id=(SELECT id FROM users WHERE email='a@example.invalid')").fetchone()["id"]
    privacy_detail = admin.get(f"/admin/privacy-requests/{privacy_id}")
    assert privacy_detail.status_code == 200
    review = admin.post(
        f"/admin/privacy-requests/{privacy_id}/decision",
        data={"csrf": form_token(privacy_detail), "decision": "identity_review", "reason": "Confirm identity before processing"},
        follow_redirects=False,
    )
    assert review.status_code == 303
    with database.connect() as db:
        assert db.execute("SELECT state FROM privacy_requests WHERE id=?", (privacy_id,)).fetchone()["state"] == "identity_review"
    deletion_review = admin.get(f"/admin/privacy-requests/{privacy_id}")
    blocked_export = admin.post(
        f"/admin/privacy-requests/{privacy_id}/decision",
        data={"csrf": form_token(deletion_review), "decision": "approve_export", "reason": "Wrong request type"},
        follow_redirects=False,
    )
    assert blocked_export.status_code == 400


def test_approved_privacy_export_is_account_scoped_and_one_time(tmp_path):
    db_path = tmp_path / "app.sqlite3"
    customer = TestClient(create_app(db_path, tmp_path / "mailbox-customer.json"))
    register_and_login(customer, "export@example.invalid")
    site_id = add_site(customer)
    submit_audit(customer, site_id)

    other_customer = TestClient(create_app(db_path, tmp_path / "mailbox-other.json"))
    register_and_login(other_customer, "other-export@example.invalid")
    add_site(other_customer)

    database = Database(db_path)
    database.create_admin(
        "privacy-admin@example.invalid",
        hash_password("a-long-admin-password-456"),
        "JBSWY3DPEHPK3PXP",
    )
    admin = TestClient(create_app(db_path, tmp_path / "mailbox-admin.json"))
    login_page = admin.get("/login")
    login = admin.post(
        "/login",
        data={
            "csrf": form_token(login_page),
            "email": "privacy-admin@example.invalid",
            "password": "a-long-admin-password-456",
            "otp": totp_code("JBSWY3DPEHPK3PXP"),
        },
        follow_redirects=False,
    )
    assert login.status_code == 303

    settings = customer.get("/app/settings")
    submitted = customer.post(
        "/app/settings/privacy-requests",
        data={"csrf": form_token(settings), "request_type": "export", "customer_note": "Please provide my account records."},
        follow_redirects=False,
    )
    assert submitted.status_code == 303
    with database.connect() as db:
        privacy_id = db.execute(
            "SELECT id FROM privacy_requests WHERE user_id=(SELECT id FROM users WHERE email='export@example.invalid')"
        ).fetchone()["id"]

    review = admin.get(f"/admin/privacy-requests/{privacy_id}")
    assert "Complete identity review" not in review.text
    identity_check = admin.post(
        f"/admin/privacy-requests/{privacy_id}/decision",
        data={"csrf": form_token(review), "decision": "identity_review", "reason": "Contact matched account records"},
        follow_redirects=False,
    )
    assert identity_check.status_code == 303
    review = admin.get(f"/admin/privacy-requests/{privacy_id}")
    assert "Approve customer download" in review.text
    approval = admin.post(
        f"/admin/privacy-requests/{privacy_id}/decision",
        data={"csrf": form_token(review), "decision": "approve_export", "reason": "Verified account owner by callback"},
        follow_redirects=False,
    )
    assert approval.status_code == 303

    settings = customer.get("/app/settings")
    download = customer.post(
        f"/app/settings/privacy-requests/{privacy_id}/export",
        data={"csrf": form_token(settings)},
    )
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("application/json")
    assert download.headers["content-disposition"].startswith("attachment;")
    exported = download.json()
    assert exported["format"] == "catalyx-customer-data-export-v1"
    assert exported["account"]["email"] == "export@example.invalid"
    assert [site["host"] for site in exported["sites"]] == ["example.co.nz"]
    assert len(exported["audit_requests"]) == 1
    assert "other-export@example.invalid" not in json.dumps(exported)
    exported_text = json.dumps(exported)
    assert all(secret_field not in exported_text for secret_field in ("password_hash", "totp_secret", "csrf_token"))
    assert other_customer.post(
        f"/app/settings/privacy-requests/{privacy_id}/export",
        data={"csrf": form_token(other_customer.get("/app/settings"))},
    ).status_code == 404
    assert customer.post(
        f"/app/settings/privacy-requests/{privacy_id}/export",
        data={"csrf": form_token(customer.get("/app/settings"))},
    ).status_code == 404
    with database.connect() as db:
        state = db.execute("SELECT state FROM privacy_requests WHERE id=?", (privacy_id,)).fetchone()["state"]
        audit_events = db.execute(
            "SELECT actor_role,action FROM admin_activity WHERE target_id=? ORDER BY created_at",
            (privacy_id,),
        ).fetchall()
    assert state == "completed"
    assert {row["action"] for row in audit_events} == {
        "privacy_request_identity_review",
        "privacy_request_approve_export",
        "privacy_export_downloaded",
    }
    assert any(row["actor_role"] == "customer" and row["action"] == "privacy_export_downloaded" for row in audit_events)


def test_site_normalization_and_csrf_rejection(tmp_path):
    client = TestClient(create_app(tmp_path / "app.sqlite3", tmp_path / "mailbox.json"))
    register_page = client.get("/register")
    response = client.post(
        "/register",
        data={"email": "x@example.invalid", "password": "a-long-local-password-123", "password_confirm": "a-long-local-password-123"},
    )
    assert response.status_code == 403
    assert register_page.status_code == 200
    assert normalize_site("example.co.nz/path?token=secret") == ("https://example.co.nz", "example.co.nz")
    assert normalize_site("https://[2606:4700:4700::1111]/path") == (
        "https://[2606:4700:4700::1111]",
        "2606:4700:4700::1111",
    )
    for forbidden in (
        "http://127.0.0.1",
        "http://[::1]",
        "http://localhost",
        "file:///etc/passwd",
        "http://127.1",
        "http://2130706433",
        "http://0x7f000001",
        "http://0177.0.0.1",
        "http://[::ffff:127.0.0.1]",
        "http://[fc00::1]",
        "http://[ff02::1]",
        "http://169.254.169.254",
        "http://240.0.0.1",
        "https://bad..example.com",
        "https://-bad.example.com",
        "https://bad_.example.com",
        "https://example.com..",
        "https://user:password@example.com",
        "http://example.com:443",
        "https://example.com:80",
        "https://example.com:8443",
    ):
        try:
            normalize_site(forbidden)
        except ValueError:
            pass
        else:
            raise AssertionError(f"local or unsupported address was accepted: {forbidden}")


def test_transport_resolves_at_connection_time_and_blocks_private_answer():
    resolver = FakeAddressResolver({"A": ["127.0.0.1"]})
    transport = PinnedEgressTransport(resolver=resolver)
    try:
        try:
            transport.handle_request(httpx.Request("GET", "https://example.com/"))
        except EgressPolicyError as exc:
            assert "non-public" in str(exc)
        else:
            raise AssertionError("connection-time private DNS answer was accepted")
    finally:
        transport.close()
    assert [call[1] for call in resolver.calls] == ["A", "AAAA"]


def test_dns_pinning_rejects_mixed_public_and_private_answers():
    resolver = FakeAddressResolver({"A": ["93.184.216.34", "10.0.0.8"]})
    with pytest.raises(EgressPolicyError, match="non-public"):
        PinnedEgressTransport(resolver=resolver)._resolve_public("example.com", 443)


@pytest.mark.parametrize(
    ("family", "address"),
    [
        (socket.AF_INET, "0.0.0.0"),
        (socket.AF_INET, "10.0.0.8"),
        (socket.AF_INET, "127.0.0.1"),
        (socket.AF_INET, "169.254.169.254"),
        (socket.AF_INET, "192.0.2.1"),
        (socket.AF_INET, "224.0.0.1"),
        (socket.AF_INET, "240.0.0.1"),
        (socket.AF_INET6, "::"),
        (socket.AF_INET6, "::1"),
        (socket.AF_INET6, "::ffff:127.0.0.1"),
        (socket.AF_INET6, "2001:db8::1"),
        (socket.AF_INET6, "fc00::1"),
        (socket.AF_INET6, "fe80::1"),
        (socket.AF_INET6, "ff02::1"),
    ],
)
def test_dns_pinning_rejects_non_public_address_classes(family, address):
    record_type = "AAAA" if family == socket.AF_INET6 else "A"
    resolver = FakeAddressResolver({record_type: [address]})
    with pytest.raises(EgressPolicyError, match="non-public"):
        PinnedEgressTransport(resolver=resolver)._resolve_public("example.com", 443)


def test_dns_pinning_applies_resolver_timeout():
    class TimeoutResolver:
        def resolve(self, name, record_type, *, lifetime, search):
            assert 0 < lifetime <= 0.25
            raise dns.exception.Timeout

    transport = PinnedEgressTransport(dns_timeout=0.25, resolver=TimeoutResolver())
    with pytest.raises(EgressTransportError, match="Target name could not be resolved"):
        transport._resolve_public("example.com", 443)


def test_pinned_transport_connects_to_the_vetted_address(monkeypatch):
    addresses = []
    sockets = []

    class FakeSocket:
        def settimeout(self, value):
            self.timeout = value

        def connect(self, address):
            addresses.append(address)

        def sendall(self, data):
            self.request = data

        def makefile(self, mode):
            return io.BytesIO(b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: 2\r\n\r\nOK")

        def close(self):
            pass

    def make_socket(*args, **kwargs):
        fake = FakeSocket()
        sockets.append(fake)
        return fake

    monkeypatch.setattr(socket, "socket", make_socket)
    resolver = FakeAddressResolver({"A": ["93.184.216.34"]})
    transport = PinnedEgressTransport(resolver=resolver)
    try:
        response = transport.handle_request(httpx.Request("GET", "http://example.com/"))
        assert response.status_code == 200
        assert response.text == "OK"
        assert addresses == [("93.184.216.34", 80)]
        assert b"Host: example.com" in sockets[0].request
    finally:
        transport.close()


def test_pinned_transport_checks_cancellation_while_reading_response(monkeypatch):
    class FakeSocket:
        def settimeout(self, _value):
            pass

        def connect(self, _address):
            pass

        def sendall(self, _data):
            pass

        def makefile(self, _mode):
            return io.BytesIO(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: 2\r\n\r\nOK"
            )

        def close(self):
            pass

    monkeypatch.setattr(socket, "socket", lambda *_args, **_kwargs: FakeSocket())
    calls = 0

    def cancel_after_body_chunk():
        nonlocal calls
        calls += 1
        return calls >= 5

    transport = PinnedEgressTransport(
        resolver=FakeAddressResolver({"A": ["93.184.216.34"]}),
        cancel_check=cancel_after_body_chunk,
    )
    with pytest.raises(EgressCancelledError):
        transport.handle_request(httpx.Request("GET", "http://example.com/"))


def test_static_audit_checks_cancellation_before_network_request():
    requests = []
    transport = httpx.MockTransport(
        lambda request: requests.append(str(request.url))
        or httpx.Response(404, request=request)
    )
    with pytest.raises(EgressCancelledError):
        run_authorized_static_audit(
            "http://93.184.216.34", transport=transport, cancel_check=lambda: True
        )
    assert requests == []


def test_fixed_static_profile_respects_robots_and_does_not_crawl():
    requests = []

    def respond(request):
        requests.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(404, request=request)
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8", "x-content-type-options": "nosniff"},
            content=(
                "<html><head><title>Sample site</title></head><body><h1>Sample</h1>"
                "<a href='/another-page?token=do-not-save'>Another page</a>"
                "<img src='https://third-party.example/pixel' alt='sample'>"
                "<p>Contact owner@example.invalid for details.</p></body></html>"
            ),
            request=request,
        )

    report = run_authorized_static_audit("http://93.184.216.34", transport=httpx.MockTransport(respond))
    serialized = json.dumps(report)
    assert report["status"] == "complete"
    assert requests == ["http://93.184.216.34/robots.txt", "http://93.184.216.34/"]
    assert "owner@example.invalid" not in serialized
    assert "do-not-save" not in serialized
    assert "third-party.example" not in serialized
    assert report["checks"]["deep_crawl"]["status"] == "not_run"


def test_fixed_static_profile_blocks_disallowed_robots_and_redirects():
    requests = []

    def disallow(request):
        requests.append(str(request.url))
        return httpx.Response(200, headers={"content-type": "text/plain"}, content="User-agent: *\nDisallow: /", request=request)

    blocked = run_authorized_static_audit("http://93.184.216.34", transport=httpx.MockTransport(disallow))
    assert blocked["status"] == "blocked"
    assert requests == ["http://93.184.216.34/robots.txt"]

    requests.clear()

    def private_redirect(request):
        requests.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(404, request=request)
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"}, request=request)

    failed = run_authorized_static_audit("http://93.184.216.34", transport=httpx.MockTransport(private_redirect))
    assert failed["status"] == "failed"
    assert requests == ["http://93.184.216.34/robots.txt", "http://93.184.216.34/"]


def test_fixed_profile_checks_robots_for_redirected_path_before_fetching_it():
    requests = []

    def redirect_to_disallowed_path(request):
        requests.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                headers={"content-type": "text/plain"},
                content="User-agent: *\nAllow: /\nDisallow: /private",
                request=request,
            )
        if request.url.path == "/":
            return httpx.Response(302, headers={"location": "/private"}, request=request)
        return httpx.Response(200, content="must not be fetched", request=request)

    report = run_authorized_static_audit(
        "https://example.com", transport=httpx.MockTransport(redirect_to_disallowed_path)
    )
    assert report["status"] == "blocked"
    assert report["checks"]["robots"] == {"status": "blocked", "result": "disallowed"}
    assert requests == ["https://example.com/robots.txt", "https://example.com/"]


def test_fixed_profile_checks_robots_for_www_alias_before_fetching_it():
    requests = []

    def redirect_to_disallowed_alias(request):
        requests.append(str(request.url))
        if request.url.host == "example.com" and request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                headers={"content-type": "text/plain"},
                content="User-agent: *\nAllow: /",
                request=request,
            )
        if request.url.host == "example.com" and request.url.path == "/":
            return httpx.Response(301, headers={"location": "https://www.example.com/"}, request=request)
        if request.url.host == "www.example.com" and request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                headers={"content-type": "text/plain"},
                content="User-agent: *\nDisallow: /",
                request=request,
            )
        return httpx.Response(200, content="must not be fetched", request=request)

    report = run_authorized_static_audit(
        "https://example.com", transport=httpx.MockTransport(redirect_to_disallowed_alias)
    )
    assert report["status"] == "blocked"
    assert report["checks"]["robots"] == {"status": "blocked", "result": "disallowed"}
    assert requests == [
        "https://example.com/robots.txt",
        "https://example.com/",
        "https://www.example.com/robots.txt",
    ]


def test_robots_policy_merges_matching_groups_and_uses_specific_rules():
    rules = (
        "User-agent: CatalyxLabs\n"
        "Disallow: /private\n"
        "User-agent: Website-Auditor\n"
        "Allow: /private/public\n"
        "Disallow: /*.pdf$\n"
        "Allow: /same\n"
        "Disallow: /same"
    )
    assert not _robots_can_fetch(rules, "https://example.com/private/admin")
    assert _robots_can_fetch(rules, "https://example.com/private/public/report")
    assert not _robots_can_fetch(rules, "https://example.com/reports/final.pdf")
    assert _robots_can_fetch(rules, "https://example.com/reports/final.pdf?download=1")
    assert _robots_can_fetch(rules, "https://example.com/same")
    encoded_reserved = "User-agent: *\nDisallow: /files/with-%2A.html"
    assert not _robots_can_fetch(
        encoded_reserved, "https://example.com/files/with-*.html"
    )
    excessive_rules = "User-agent: *\n" + "".join(
        f"Allow: /path-{index}\n" for index in range(2_049)
    )
    assert not _robots_can_fetch(excessive_rules, "https://example.com/")


def test_worker_fencing_token_rejects_a_result_after_lease_reclaim(tmp_path, monkeypatch):
    db_path = tmp_path / "fenced-worker.sqlite3"
    customer = TestClient(create_app(db_path, tmp_path / "customer-mailbox.json"))
    register_and_login(customer, "fenced@example.invalid")
    audit_id = submit_audit(customer, add_site(customer))

    secret = "JBSWY3DPEHPK3PXP"
    database = Database(db_path)
    database.create_admin("reviewer@example.invalid", hash_password("a-long-reviewer-password-456"), secret)
    reviewer = TestClient(create_app(db_path, tmp_path / "reviewer-mailbox.json"))
    login_page = reviewer.get("/login")
    response = reviewer.post(
        "/login",
        data={
            "csrf": form_token(login_page),
            "email": "reviewer@example.invalid",
            "password": "a-long-reviewer-password-456",
            "otp": totp_code(secret),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    detail = reviewer.get(f"/admin/audits/{audit_id}")
    response = reviewer.post(
        f"/admin/audits/{audit_id}/decision",
        data={
            "csrf": form_token(detail),
            "decision": "approve",
            "reason": "Queue fencing regression",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    from catalyx_web import worker

    calls = 0
    reclaimed_results = []

    def staged_result(_origin, *, cancel_check=None):
        nonlocal calls
        calls += 1
        if calls == 1:
            with database.connect() as db:
                db.execute(
                    "UPDATE audit_requests SET worker_lease_until=0 WHERE id=?",
                    (audit_id,),
                )
            reclaimed_results.append(worker.run_once(db_path))
        return {
            "schema_version": 1,
            "profile": "customer_static_single_page_v1",
            "status": "complete",
            "site_host": "example.invalid",
            "started_at": "2026-09-28T00:00:00+00:00",
            "completed_at": "2026-09-28T00:00:01+00:00",
            "checks": {"fetch": {"status": "complete", "http_status": 200}},
            "findings": [],
            "limitations": [],
        }

    monkeypatch.setattr(worker, "run_authorized_static_audit", staged_result)
    stale_result = worker.run_once(db_path)

    assert calls == 2
    assert reclaimed_results[0]["status"] == "quality_review"
    assert reclaimed_results[0]["audit_id"] == audit_id
    assert len(reclaimed_results[0]["report_hash"]) == 64
    assert stale_result == {"status": "lease_lost"}
    with database.connect() as db:
        row = db.execute(
            "SELECT state,worker_lease_token FROM audit_requests WHERE id=?",
            (audit_id,),
        ).fetchone()
        result_count = db.execute(
            "SELECT COUNT(*) FROM audit_results WHERE audit_id=?",
            (audit_id,),
        ).fetchone()[0]
    assert row["state"] == "quality_review"
    assert row["worker_lease_token"] is None
    assert result_count == 1


def test_customer_can_cancel_running_audit_and_worker_stops(tmp_path, monkeypatch):
    db_path = tmp_path / "cancel-worker.sqlite3"
    customer = TestClient(create_app(db_path, tmp_path / "customer-mailbox.json"))
    register_and_login(customer, "cancel-running@example.invalid")
    audit_id = submit_audit(customer, add_site(customer))

    secret = "JBSWY3DPEHPK3PXP"
    database = Database(db_path)
    database.create_admin("reviewer@example.invalid", hash_password("a-long-reviewer-password-456"), secret)
    reviewer = TestClient(create_app(db_path, tmp_path / "reviewer-mailbox.json"))
    login_page = reviewer.get("/login")
    response = reviewer.post(
        "/login",
        data={
            "csrf": form_token(login_page),
            "email": "reviewer@example.invalid",
            "password": "a-long-reviewer-password-456",
            "otp": totp_code(secret),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    detail = reviewer.get(f"/admin/audits/{audit_id}")
    response = reviewer.post(
        f"/admin/audits/{audit_id}/decision",
        data={
            "csrf": form_token(detail),
            "decision": "approve",
            "reason": "Running cancellation regression",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    from catalyx_web import worker

    def cancel_during_audit(_origin, *, cancel_check=None):
        customer_me = customer.get("/api/v1/me").json()
        response = customer.post(
            f"/api/v1/audits/{audit_id}/cancel",
            headers={"X-CSRF-Token": customer_me["csrf_token"]},
        )
        assert response.status_code == 200
        assert response.json()["audit"]["state"] == "cancelled"
        assert cancel_check is not None and cancel_check()
        raise EgressCancelledError("cancelled for test")

    monkeypatch.setattr(worker, "run_authorized_static_audit", cancel_during_audit)
    assert worker.run_once(db_path) == {"status": "cancelled", "audit_id": audit_id}
    with database.connect() as db:
        row = db.execute(
            "SELECT state,worker_lease_until,worker_lease_token FROM audit_requests WHERE id=?",
            (audit_id,),
        ).fetchone()
        result_count = db.execute(
            "SELECT COUNT(*) FROM audit_results WHERE audit_id=?",
            (audit_id,),
        ).fetchone()[0]
    assert row["state"] == "cancelled"
    assert row["worker_lease_until"] is None
    assert row["worker_lease_token"] is None
    assert result_count == 0


def test_failed_job_queue_shows_attempts_reason_and_retry_boundary(tmp_path):
    db_path = tmp_path / "failed-job-queue.sqlite3"
    customer = TestClient(create_app(db_path, tmp_path / "customer-mailbox.json"))
    register_and_login(customer, "failed-jobs@example.invalid")
    site_id = add_site(customer)
    retryable_id = submit_audit(customer, site_id)
    exhausted_id = submit_audit(customer, site_id)
    database = Database(db_path)
    with database.connect() as db:
        db.execute(
            "UPDATE audit_requests SET state='failed',attempt_count=1,review_reason=? WHERE id=?",
            ("The target could not be audited within the configured limits", retryable_id),
        )
        db.execute(
            "UPDATE audit_requests SET state='failed',attempt_count=2,review_reason=? WHERE id=?",
            ("Worker lease expired after the retry limit", exhausted_id),
        )

    secret = "JBSWY3DPEHPK3PXP"
    database.create_admin("queue-owner@example.invalid", hash_password("a-long-queue-owner-password-456"), secret)
    owner = TestClient(create_app(db_path, tmp_path / "owner-mailbox.json"))
    login_page = owner.get("/login")
    response = owner.post(
        "/login",
        data={
            "csrf": form_token(login_page),
            "email": "queue-owner@example.invalid",
            "password": "a-long-queue-owner-password-456",
            "otp": totp_code(secret),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    jobs_page = owner.get("/admin/jobs")
    assert "Attempts" in jobs_page.text
    assert "The target could not be audited within the configured limits" in jobs_page.text
    assert "Worker lease expired after the retry limit" in jobs_page.text
    retryable_page = owner.get(f"/admin/audits/{retryable_id}")
    assert "Retry request" in retryable_page.text
    response = owner.post(
        f"/admin/audits/{retryable_id}/retry",
        data={"csrf": form_token(retryable_page), "reason": "Retry after checking target status"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    exhausted_page = owner.get(f"/admin/audits/{exhausted_id}")
    assert "local retry limit has been reached" in exhausted_page.text
    assert "Retry request" not in exhausted_page.text
    response = owner.post(
        f"/admin/audits/{exhausted_id}/retry",
        data={"csrf": form_token(exhausted_page), "reason": "Attempt limit must remain enforced"},
        follow_redirects=False,
    )
    assert response.status_code == 409
    with database.connect() as db:
        retried = db.execute(
            "SELECT state,attempt_count FROM audit_requests WHERE id=?", (retryable_id,)
        ).fetchone()
        exhausted = db.execute(
            "SELECT state,attempt_count FROM audit_requests WHERE id=?", (exhausted_id,)
        ).fetchone()
    assert retried["state"] == "queued" and retried["attempt_count"] == 1
    assert exhausted["state"] == "failed" and exhausted["attempt_count"] == 2

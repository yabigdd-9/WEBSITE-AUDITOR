"""Real private Postgres -> owner portal -> restart, with no external requests."""

import base64
import copy
import hashlib
import json
import secrets
from pathlib import Path

import pytest
from argon2 import PasswordHasher
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auditor_toolkit.hosted_portal import (
    HOSTED_COOKIE,
    HostedConfig,
    HTTPSBoundary,
    create_hosted_app,
)
from scripts.checkpoint_to_postgres import import_checkpoint
from scripts.cloud_opportunities import enrich, load_policy
from scripts.cloud_prospect_pipeline import empty_state, event, metrics, unseal
from scripts.portal_auth_store import PostgresPortalAuth
from toolkit_tests.test_postgres_store import postgres as postgres
from toolkit_tests.test_postgres_store import psycopg
from toolkit_tests.test_postgres_store import store as store

ORIGIN = "https://owner.example.com"
PASSWORD = "synthetic-hosted-owner-password"
NOW = 1767225600


@pytest.fixture(autouse=True)
def private_runner_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    for name in ("MM_PAID_ALLOWED", "MM_ALLOW_EXTERNAL_FREE_MODELS", "MM_EXTERNAL_SEND_ALLOWED"):
        monkeypatch.setenv(name, "0")


@pytest.fixture(scope="module")
def config():
    return HostedConfig(ORIGIN, PasswordHasher().hash(PASSWORD), b"x" * 32)


def snapshot():
    state = empty_state()
    state["audit_runs"] = []
    for index, domain in enumerate(["example.com", "b.example.com", "c.example.com", "d.example.com", "e.example.com"]):
        key = hashlib.sha256(domain.encode()).hexdigest()
        findings = [dict(
            finding_id="synthetic-viewport", defect_key="viewport", severity="medium", confidence="observed",
            observed="Synthetic missing viewport", remediation_action="Review viewport",
            source_url="https://example.com", evidence_ref="html", evidence_check="html", evidence_check_status="ok",
        )] if index == 0 else []
        state["prospects"][key] = dict(
            domain=domain, status="suppressed" if index == 4 else "complete", attempts=1,
            draft="INTERNAL SCOPE DRAFT - DO NOT SEND" if index == 0 else None,
            audit={"domain": domain, "status": "COMPLETE", "run_id": f"fixture-{index}",
                   "timestamp": "2026-01-01T00:00:00+00:00", "findings": findings} if index < 4 else None,
        )
        if index < 4:
            state["audit_runs"].append(dict(
                audit_id=hashlib.sha256(f"audit-{index}".encode()).hexdigest(), prospect_id=key,
                status="complete", execution_timestamp="2026-01-01T00:00:00+00:00",
            ))
            event(state, NOW, "fixture", key, "audit", "succeeded")
    enrich(state, load_policy(Path(__file__).resolve().parents[1]), now=NOW)
    return state, hashlib.sha256(b"example.com").hexdigest()


@pytest.fixture
def private_portal(store, postgres, config):
    migration = next((Path(__file__).resolve().parents[1] / "supabase/migrations").glob("*hosted_portal_auth.sql"))
    with psycopg.connect(postgres, autocommit=True) as db:
        if db.execute("SELECT to_regclass('moneymachine.portal_sessions')").fetchone()[0] is None:
            db.execute(migration.read_text())
    with store.transaction(bootstrap=True) as state:
        event(state, 0, "setup", "0" * 64, "pause", "disabled")
    incoming, identity = snapshot()
    import_checkpoint(store, incoming, source_run="123", actor="fixture-owner", now=NOW)
    return store, identity, config


def client_for(store, config):
    return TestClient(create_hosted_app(config=config, store=store), base_url=ORIGIN)


def login(client):
    result = client.post("/login", data={"password": PASSWORD}, headers={"origin": ORIGIN}, follow_redirects=False)
    assert result.status_code == 303
    assert "Secure" in result.headers["set-cookie"]
    assert "HttpOnly" in result.headers["set-cookie"]
    assert "SameSite=strict" in result.headers["set-cookie"]
    return client.get("/api/session").json()["csrf"]


def test_environment_configuration_is_private_and_strict(config, monkeypatch):
    for key in ("WA_PORTAL_ORIGIN", "WA_PORTAL_PASSWORD_HASH", "WA_PORTAL_AUTH_PEPPER_B64"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError, match="privately"):
        HostedConfig.from_environment()
    monkeypatch.setenv("WA_PORTAL_ORIGIN", ORIGIN)
    monkeypatch.setenv("WA_PORTAL_PASSWORD_HASH", config.password_hash)
    monkeypatch.setenv("WA_PORTAL_AUTH_PEPPER_B64", base64.b64encode(config.pepper).decode())
    assert HostedConfig.from_environment() == config
    assert config.password_hash not in repr(config)
    assert repr(config.pepper) not in repr(config)
    for origin in ("http://owner.example.com", "https://owner.example.com/path", "https://*.example.com", "https://localhost"):
        with pytest.raises(ValueError):
            HostedConfig(origin, config.password_hash, config.pepper).validate()
    with pytest.raises(ValueError):
        HostedConfig(ORIGIN, "plaintext-is-not-a-hash", config.pepper).validate()


def test_https_boundary_ignores_untrusted_forwarded_headers():
    app = FastAPI()
    app.add_middleware(HTTPSBoundary, origin=ORIGIN)

    @app.get("/")
    def home():
        return {"ok": True}

    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get("/").status_code == 200
        assert client.get("/", headers={"host": "evil.example.com"}).status_code == 400
    with TestClient(app, base_url="http://owner.example.com") as client:
        assert client.get("/", headers={"x-forwarded-proto": "https"}).status_code == 400


def test_saved_pipeline_approvals_projects_and_session_survive_restart(private_portal):
    store, identity, config = private_portal
    with client_for(store, config) as first:
        csrf = login(first)
        before = copy.deepcopy(store.read())
        assert first.get("/pipeline").status_code == 200
        assert store.read() == before
        token = first.cookies.get(HOSTED_COOKIE)
        version = before["prospects"][identity]["proposal_version"]
        approval = {"csrf": csrf, "version": version, "reason": "Synthetic exact scope reviewed"}
        assert first.post(f"/pipeline/prospects/{identity}/approve", data=approval,
                          headers={"origin": ORIGIN}, follow_redirects=False).status_code == 303
    with client_for(store, config) as second:
        second.cookies.set(HOSTED_COOKIE, token)
        assert second.get("/api/session").json()["csrf"] == csrf
        overview = second.get("/pipeline")
        assert overview.status_code == 200
        assert overview.headers["strict-transport-security"] == "max-age=15552000"
        report = metrics(store.read())
        assert report["prospects_found"] == 5
        assert report["audits_succeeded"] == 4
        assert report["proposal_drafts_ready"] == 1
        assert second.post(f"/pipeline/prospects/{identity}/approve", data=approval,
                           headers={"origin": ORIGIN}, follow_redirects=False).status_code == 303
        assert len(store.read()["prospects"][identity]["approvals"]) == 1
        acceptance = {**approval, "owner_verified": "true", "acceptance_evidence": "a" * 64}
        assert second.post(f"/pipeline/prospects/{identity}/accept", data=acceptance,
                           headers={"origin": ORIGIN}, follow_redirects=False).status_code == 303
        assert len(store.read()["prospects"][identity]["projects"]) == 1
        assert second.post("/logout", data={"csrf": csrf}, headers={"origin": ORIGIN}, follow_redirects=False).status_code == 303
    with client_for(store, config) as third:
        third.cookies.set(HOSTED_COOKIE, token)
        assert third.get("/pipeline").status_code == 401
        login(third)
        assert len(store.read()["prospects"][identity]["projects"]) == 1
        assert metrics(store.read())["contacts_sent"] == 0


def test_owner_auth_origin_and_login_budget_survive_restart(private_portal, monkeypatch):
    monkeypatch.setattr("scripts.portal_auth_store.time.time", lambda: NOW)
    store, identity, config = private_portal
    with client_for(store, config) as client:
        for path in ("/pipeline", "/pipeline/prospects", f"/pipeline/prospects/{identity}", "/pipeline/projects", "/api/session"):
            assert client.get(path).status_code == 401
        assert client.post("/login", data={"password": PASSWORD}).status_code == 403
        assert client.post("/login", data={"password": PASSWORD}, headers={"origin": "https://evil.example.com"}).status_code == 403
        for _ in range(3):
            assert client.post("/login", data={"password": "wrong"}, headers={"origin": ORIGIN}).status_code == 401
    with client_for(store, config) as restarted:
        for _ in range(2):
            assert restarted.post("/login", data={"password": "wrong"}, headers={"origin": ORIGIN}).status_code == 401
        assert restarted.post("/login", data={"password": PASSWORD}, headers={"origin": ORIGIN}).status_code == 429


def test_session_storage_rotation_write_budget_and_expiry(private_portal):
    store, _, config = private_portal
    with client_for(store, config) as client:
        login(client)
        token = client.cookies.get(HOSTED_COOKIE)
    with store.connection() as db:
        rows = db.execute("SELECT token_hash,auth_version FROM moneymachine.portal_sessions").fetchall()
        assert token not in json.dumps(rows)
        assert rows[0][0] == hashlib.sha256(token.encode()).hexdigest()
    rotated = HostedConfig(ORIGIN, config.password_hash, b"y" * 32)
    with client_for(store, rotated) as restarted:
        restarted.cookies.set(HOSTED_COOKIE, token)
        assert restarted.get("/pipeline").status_code == 401
    auth = PostgresPortalAuth(store, pepper=config.pepper, password_hash=config.password_hash)
    for _ in range(20):
        assert auth.write_attempt("synthetic-session", now=NOW)
    restarted_auth = PostgresPortalAuth(store, pepper=config.pepper, password_hash=config.password_hash)
    assert restarted_auth.write_attempt("synthetic-session", now=NOW) is False
    digest = hashlib.sha256(b"synthetic-token").hexdigest()
    auth.issue(digest, secrets.token_urlsafe(32), NOW + 300, now=NOW)
    assert restarted_auth.get(digest, now=NOW + 1) is not None
    assert restarted_auth.get(digest, now=NOW + 300) is None


def test_postgres_worker_preserves_decisions_and_paired_ciphertext(private_portal, tmp_path, monkeypatch):
    from cryptography.fernet import Fernet

    from scripts import cloud_prospect_pipeline, postgres_store
    from scripts.cloud_storage_runner import run_postgres

    store, identity, config = private_portal
    with client_for(store, config) as client:
        csrf = login(client)
        version = store.read()["prospects"][identity]["proposal_version"]
        assert client.post(f"/pipeline/prospects/{identity}/approve", data={
            "csrf": csrf, "version": version, "reason": "Preserve exact reviewed version",
        }, headers={"origin": ORIGIN}, follow_redirects=False).status_code == 303
    approved = copy.deepcopy(store.read()["prospects"][identity]["approvals"])
    actual_main = cloud_prospect_pipeline.main
    monkeypatch.setattr(postgres_store, "PostgresPipelineStore", lambda: store)
    monkeypatch.setattr(cloud_prospect_pipeline, "main", lambda args: actual_main(["--postgres", "--paused"]))
    for name in ("BOOTSTRAP", "WA_RECOVERY_RUN"):
        monkeypatch.delenv(name, raising=False)
    key = Fernet.generate_key().decode()
    state_path = tmp_path / "pipeline-state.enc"
    run_postgres(state_path, key)
    assert store.read()["prospects"][identity]["approvals"] == approved
    assert unseal(state_path, key)["storage_authority"] == "postgres"
    paired = json.loads(Fernet(key.encode()).decrypt((tmp_path / "pipeline-postgres-backup.enc").read_bytes()))
    assert paired["content"]["state"]["prospects"][identity]["approvals"] == approved
    assert store.operational_summary()["reservations"] == 0
    assert metrics(store.read())["contacts_sent"] == 0


def test_portal_auth_tables_deny_unprivileged_reads(private_portal, postgres):
    for role in ("anon", "authenticated", "moneymachine_reader"):
        with psycopg.connect(postgres) as db:
            db.execute(psycopg.sql.SQL("SET ROLE {}").format(psycopg.sql.Identifier(role)))
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                db.execute("SELECT token_hash FROM moneymachine.portal_sessions").fetchall()


def test_hosted_error_paths_redact_storage_failures_and_reject_bad_forms(private_portal, monkeypatch):
    store, _, config = private_portal
    with client_for(store, config) as client:
        headers = {"origin": ORIGIN}
        assert client.post("/login", json={"password": PASSWORD}, headers=headers).status_code == 415
        assert client.post("/login", data={"unexpected": "field"}, headers=headers).status_code == 400
        assert client.post("/login", content="password=x&password=y", headers={
            **headers, "content-type": "application/x-www-form-urlencoded",
        }).status_code == 400
        assert client.post("/login", data={"password": "x" * 5000}, headers=headers).status_code == 413
        login(client)

        def private_failure(*args, **kwargs):
            raise ValueError("password=synthetic-private-value")

        monkeypatch.setattr(PostgresPortalAuth, "get", private_failure)
        result = client.get("/pipeline")
        assert result.status_code == 503
        assert "synthetic-private-value" not in result.text
        monkeypatch.setattr(store, "read", private_failure)
        result = client.get("/health")
        assert result.status_code == 503
        assert "synthetic-private-value" not in result.text


def test_shared_write_limit_blocks_owner_changes_after_restart(private_portal, monkeypatch):
    monkeypatch.setattr("scripts.portal_auth_store.time.time", lambda: NOW)
    store, identity, config = private_portal
    with client_for(store, config) as client:
        csrf = login(client)
        token = client.cookies.get(HOSTED_COOKIE)
    auth = PostgresPortalAuth(store, pepper=config.pepper, password_hash=config.password_hash)
    key = hashlib.sha256(token.encode()).hexdigest()
    for _ in range(20):
        assert auth.write_attempt(key)
    before = copy.deepcopy(store.read())
    with client_for(store, config) as restarted:
        restarted.cookies.set(HOSTED_COOKIE, token)
        version = before["prospects"][identity]["proposal_version"]
        result = restarted.post(f"/pipeline/prospects/{identity}/approve", data={
            "version": version, "reason": "Synthetic over-limit review", "csrf": csrf,
        }, headers={"origin": ORIGIN})
        assert result.status_code == 429
    assert store.read() == before

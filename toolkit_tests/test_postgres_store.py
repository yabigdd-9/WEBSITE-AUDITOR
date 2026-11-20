"""Real disposable PostgreSQL tests; never uses a cloud credential or sends."""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

psycopg = pytest.importorskip("psycopg")
pgserver = pytest.importorskip("pgserver")
from scripts import cloud_prospect_pipeline as pipeline  # noqa: E402
from scripts.postgres_store import PROJECT_REF, PostgresPipelineStore, connection_options  # noqa: E402
from toolkit_tests.platform_helpers import commit_mutation, interrupt_reserved_transaction  # noqa: E402

MIGRATION = next((Path(__file__).resolve().parents[1] / "supabase/migrations").glob("*private_pipeline_store.sql"))


def sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


@pytest.fixture(scope="module")
def postgres():
    with tempfile.TemporaryDirectory(prefix="mmdb-") as directory:
        server = pgserver.get_server(Path(directory) / "pg", cleanup_mode="delete")
        try:
            uri = server.get_uri()
            with psycopg.connect(uri, autocommit=True) as db:
                for role in ("anon", "authenticated", "service_role", "postgres"):
                    if not db.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                        db.execute(psycopg.sql.SQL("CREATE ROLE {} NOLOGIN").format(psycopg.sql.Identifier(role)))
                db.execute(MIGRATION.read_text())
            yield uri
        finally:
            server.cleanup()


def reset_local(uri):
    # Only disposable local fixture administration, never a runtime store method.
    with psycopg.connect(uri, autocommit=True) as db:
        tables = [r[0] for r in db.execute("SELECT tablename FROM pg_tables WHERE schemaname='moneymachine' AND tablename!='schema_version'")]
        query = psycopg.sql.SQL("TRUNCATE {} CASCADE").format(psycopg.sql.SQL(",").join(
            psycopg.sql.Identifier("moneymachine", name) for name in tables))
        db.execute(query)


@pytest.fixture
def store(postgres):
    reset_local(postgres)
    return PostgresPipelineStore(connect=lambda: psycopg.connect(postgres, autocommit=True))


def initialize(store):
    with store.transaction(bootstrap=True):
        pass


def test_independent_process_persistence_and_consistent_reader(store, postgres):
    with store.transaction(bootstrap=True) as state:
        state["prospects"][sha("example.com")] = dict(domain="example.com", status="queued", draft=None)
    expected = copy.deepcopy(state)
    command = [sys.executable, "-c", """
import sys,json,psycopg
from scripts.postgres_store import PostgresPipelineStore
store=PostgresPipelineStore(connect=lambda: psycopg.connect(sys.argv[1],autocommit=True))
print(json.dumps(store.read()))
""", postgres]
    assert json.loads(subprocess.check_output(command, text=True)) == expected
    with store.transaction() as state:
        state["events"].append({"uncommitted": True})
        assert store.read() == expected
    assert store.read() == state
    assert store.prospects(query="EXAMPLE", limit=1) == list(expected["prospects"].values())
    assert store.prospects(query="%") == []
    assert store.prospects(offset=1) == []


def test_bootstrap_and_writer_lock_prevent_duplicate_work(store, postgres):
    with pytest.raises(ValueError):
        commit_mutation(store, lambda _: None)
    initialize(store)
    with pytest.raises(ValueError):
        commit_mutation(store, lambda _: None, bootstrap=True)
    competing = PostgresPipelineStore(connect=lambda: psycopg.connect(postgres, autocommit=True))
    with store.transaction():
        with pytest.raises(ValueError):
            commit_mutation(competing, lambda s: pytest.fail("Competing writer reached selection"))
    assert len(store.operational_summary()["jobs"]) == 2


def test_failed_transactions_never_refund_request_budget(store):
    initialize(store)
    for index in range(3):
        prospect_id, audit_id = sha("p"), sha(str(index))
        with pytest.raises(RuntimeError):
            interrupt_reserved_transaction(store, prospect_id, audit_id)
    with store.transaction():
        assert not store.reserve_attempt(sha("p"), sha("fourth"), now=0, daily_limit=6)
    assert store.read() == pipeline.empty_state()
    assert store.operational_summary()["reservations"] == 3


def test_legacy_daily_per_run_and_idempotent_limits(store):
    with store.transaction(bootstrap=True) as state:
        for index in range(3):
            pipeline.event(state, 0, "legacy", sha(str(index)), "audit", "failed", "audit_failed")
    for index in range(3):
        with store.transaction():
            assert store.reserve_attempt(sha("p" + str(index)), sha(str(index)), now=0, daily_limit=6)
            assert store.reserve_attempt(sha("p" + str(index)), sha(str(index)), now=0, daily_limit=6)
    with store.transaction():
        assert not store.reserve_attempt(sha("extra"), sha("extra"), now=0, daily_limit=6)
        for index in range(3):
            assert store.reserve_attempt(sha("next" + str(index)), sha("next" + str(index)), now=86400, daily_limit=6)
        assert not store.reserve_attempt(sha("fourth"), sha("fourth"), now=86400, daily_limit=6)


def test_process_crash_preserves_quotas_and_recovers_lock(store, postgres):
    initialize(store)
    command = [sys.executable, "-c", """
import os,sys,hashlib,psycopg
from scripts.postgres_store import PostgresPipelineStore
store=PostgresPipelineStore(connect=lambda: psycopg.connect(sys.argv[1],autocommit=True))
with store.transaction() as state:
 assert store.reserve_attempt(hashlib.sha256(b'p').hexdigest(),hashlib.sha256(b'a').hexdigest(),now=0,daily_limit=6)
 state['events'].append({'uncommitted':True})
 os._exit(19)
""", postgres]
    assert subprocess.run(command, check=False).returncode == 19
    assert store.read()["events"] == []
    with store.transaction():
        pass
    summary = store.operational_summary()
    assert summary["reservations"] == 1
    assert any(j["status"] == "interrupted" for j in summary["jobs"])


def test_committed_job_marker_repairs_interrupted_status(store):
    initialize(store)
    with patch.object(store, "finish_job", return_value=None):
        with store.transaction():
            pass
    pending = store.operational_summary()["jobs"][0]
    assert pending["status"] == "running"
    with store.transaction():
        pass
    repaired = next(j for j in store.operational_summary()["jobs"] if j["id"] == pending["id"])
    assert repaired["status"] == "succeeded"


def test_history_suppression_and_foreign_keys_cannot_be_bypassed(store):
    identity = sha("example.com")
    with store.transaction(bootstrap=True) as state:
        state["prospects"][identity] = dict(domain="example.com", status="suppressed", approvals=[{"proof": "immutable"}])
        state["events"] = [{"proof": "immutable"}]
    before = store.read()
    for change in (
        lambda s: s.update(events=[]),
        lambda s: s["prospects"][identity].update(status="queued"),
        lambda s: s["prospects"][identity].update(approvals=[]),
        lambda s: s.update(business_events=[dict(event_id="x", entity_id="missing")]),
    ):
        with pytest.raises(ValueError):
            commit_mutation(store, change)
        assert store.read() == before


def test_rls_and_table_privileges_deny_public_access_and_refunds(store, postgres):
    initialize(store)
    for role in ("anon", "authenticated", "service_role"):
        with psycopg.connect(postgres, autocommit=True) as db:
            db.execute(psycopg.sql.SQL("SET ROLE {}").format(psycopg.sql.Identifier(role)))
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                db.execute("SELECT * FROM moneymachine.prospects")
    with psycopg.connect(postgres, autocommit=True) as db:
        db.execute("SET ROLE moneymachine_worker")
        for query in ("DELETE FROM moneymachine.reservations", "UPDATE moneymachine.events SET body='{}'", "DELETE FROM moneymachine.prospects"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                db.execute(query)
        flags = db.execute("SELECT bool_and(relrowsecurity AND relforcerowsecurity) FROM pg_class WHERE relnamespace='moneymachine'::regnamespace AND relkind='r'").fetchone()
        assert flags == (True,)


def test_pipeline_runs_on_existing_postgres_contract_without_sends(store):
    calls = []
    def audit(sites, workspace, entries):
        calls.extend(sites)
        entries.append(dict(run_id="synthetic-canonical", findings=[], internal_scope_draft="review"))
        return [dict(status="COMPLETE")]
    with tempfile.TemporaryDirectory() as directory:
        with store.transaction(bootstrap=True) as state:
            metrics = pipeline.process(state, [dict(domain="example.com", url="https://example.com/")],
                now=0, run_id="postgres-fixture", workspace=Path(directory), robots=lambda _: True,
                audit=audit, attempt_reserver=store.reserve_attempt)
        assert len(calls) == 1
        assert metrics["contacts_sent"] == 0
        assert store.read()["audit_runs"] == state["audit_runs"]
        assert store.operational_summary()["reservations"] == 1


def test_private_export_restores_failed_quota_and_rejects_reset(store, postgres):
    initialize(store)
    prospect_id, audit_id = sha("p"), sha("a")
    with pytest.raises(RuntimeError):
        interrupt_reserved_transaction(store, prospect_id, audit_id)
    before = store.read()
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "backup.json"
        store.backup(target)
        assert target.stat().st_mode & 0o777 == 0o600
        with pytest.raises(FileExistsError):
            store.backup(target)
        with pytest.raises(ValueError, match="empty migrated"):
            store.restore_empty(target)
        reset_local(postgres)
        store.restore_empty(target)
        assert store.read() == before
        assert store.operational_summary()["reservations"] == 1
        target.write_bytes(target.read_bytes().replace(b'"schema_version": 1', b'"schema_version": 2'))
        with pytest.raises(ValueError, match="checksum"):
            store.restore_empty(target)


def test_paused_cli_and_authenticated_portal_use_postgres(store, monkeypatch, capsys):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from auditor_toolkit.portal import create_app, setup_password
    initialize(store)
    with patch("scripts.postgres_store.PostgresPipelineStore", return_value=store):
        for name in ("MM_PAID_ALLOWED", "MM_ALLOW_EXTERNAL_FREE_MODELS", "MM_EXTERNAL_SEND_ALLOWED"):
            monkeypatch.setenv(name, "0")
        assert pipeline.main(["--postgres", "--paused"]) == 0
        assert "contacts_sent" in capsys.readouterr().out
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            setup_password(root, "synthetic-postgres-owner")
            with TestClient(create_app(root, pipeline_postgres=True)) as client:
                assert client.get("/pipeline").status_code == 401
                assert client.post("/login", data={"password": "synthetic-postgres-owner"}, follow_redirects=False).status_code == 303
                assert client.get("/pipeline").status_code == 200
                health = client.get("/pipeline/health")
                assert health.status_code == 200
                assert "private Postgres" in health.text
                assert "password" not in health.text


@pytest.mark.parametrize("change", [
    {"host": "evil.example"}, {"port": "6543"}, {"sslmode": "require"},
    {"sslmode": "disable"}, {"dbname": "other"}, {"password": ""},
    {"hostaddr": "127.0.0.1"}, {"sslrootcert": "/tmp/custom-root"},
])
def test_connection_target_and_tls_cannot_be_overridden(change):
    from psycopg.conninfo import make_conninfo
    options = dict(host=f"db.{PROJECT_REF}.supabase.co", port="5432", dbname="postgres",
                   user="moneymachine_runner", password="synthetic-only", sslmode="verify-full")
    dsn = make_conninfo(**{**options, **change})
    with pytest.raises(ValueError, match="Configure the selected project's"):
        connection_options(dsn)


def test_missing_credentials_fail_closed_without_raw_output(monkeypatch, capsys):
    monkeypatch.delenv("WA_POSTGRES_DSN", raising=False)
    for name in ("MM_PAID_ALLOWED", "MM_ALLOW_EXTERNAL_FREE_MODELS", "MM_EXTERNAL_SEND_ALLOWED"):
        monkeypatch.setenv(name, "0")
    assert pipeline.main(["--postgres", "--paused"]) == 2
    output = capsys.readouterr().out
    assert "Pipeline blocked" in output
    assert "password" not in output


def test_project_versions_artifact_relations_and_audit_order_survive_reload(store):
    from scripts.approval_controls import approve_proposal
    from scripts.client_projects import accept_proposal
    from scripts.cloud_opportunities import digest
    from scripts.report_archive import registration
    from toolkit_tests.test_report_archive import envelope

    identity = sha("example.com")
    body = dict(kind="INTERNAL_PROPOSAL_DRAFT", items=[dict(finding_id="fixture", recommendation="Synthetic task")])
    version = digest(body)
    with store.transaction(bootstrap=True) as state:
        state["prospects"][identity] = dict(domain="example.com", status="complete", draft="Synthetic scope",
            proposal_version=version, proposal_versions=[{**body, "version_sha256": version}])
        state["audit_runs"] = [dict(audit_id=sha("z"), prospect_id=identity, status="complete")]
    with store.transaction() as state:
        prospect = state["prospects"][identity]
        approve_proposal(prospect, version, actor="fixture-owner", reason="Synthetic review", now=1767225600)
        project = accept_proposal(prospect, version, actor="fixture-owner", reason="Synthetic acceptance",
            owner_verified=True, acceptance_evidence="a" * 64, now=1767225600)
        state["audit_runs"].append(dict(audit_id=sha("a"), prospect_id=identity, status="partial"))
        data = envelope()
        registered, artifact = registration(state, data, expected_sha256=hashlib.sha256(data).hexdigest(),
            audit_ids=[sha("z")], source_run_id="123", source_artifact_id="456",
            created_at="2026-01-01T00:00:00Z", source_expires_at="2026-01-31T00:00:00Z",
            retain_until="2026-03-01T00:00:00Z", owner_reviewed=True, actor="fixture-owner",
            reason="Synthetic archive association", now=1767225600)
        state.clear()
        state.update(registered)
    restored = store.read()
    assert restored == state
    assert restored["audit_runs"][0]["audit_id"] == sha("z")
    assert restored["audit_artifact_links"][0]["artifact_id"] == artifact
    assert restored["prospects"][identity]["projects"][project]["frozen_proposal"]["version_sha256"] == version
    def mutation(document):
        document["prospects"][identity]["projects"][project]["frozen_proposal"]["items"] = []
    with pytest.raises(ValueError):
        commit_mutation(store, mutation)
    assert store.read() == restored


@pytest.mark.parametrize("pooled", [False, True])
def test_selected_direct_and_session_connections_are_accepted(pooled):
    from psycopg.conninfo import make_conninfo
    host = "aws-1-ap-southeast-2.pooler.supabase.com" if pooled else f"db.{PROJECT_REF}.supabase.co"
    user = "moneymachine_runner." + PROJECT_REF if pooled else "moneymachine_runner"
    dsn = make_conninfo(host=host, port="5432", dbname="postgres", user=user,
                       password="synthetic-only", sslmode="verify-full")
    options = connection_options(dsn)
    assert options["host"] == host
    assert options["user"] == user
    assert options["sslrootcert"] == "system"
    assert options["connect_timeout"] == 10


def test_runtime_setup_checks_authenticated_identity_and_privilege_drift(store, postgres):
    from scripts.postgres_store import PostgresPipelineStore
    # The fixture's administrator can SET ROLE but is not a safe runtime login.
    with pytest.raises(ValueError, match="restricted principal"):
        store.verify_runtime_identity()
    with psycopg.connect(postgres, autocommit=True) as db:
        db.execute("CREATE ROLE moneymachine_runner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT")
        db.execute("GRANT moneymachine_worker TO moneymachine_runner")
    restricted = PostgresPipelineStore(connect=lambda: psycopg.connect(
        postgres, user="moneymachine_runner", autocommit=True))
    restricted.verify_runtime_identity()
    with psycopg.connect(postgres, autocommit=True) as db:
        db.execute("ALTER ROLE moneymachine_runner CREATEDB")
    try:
        with pytest.raises(ValueError, match="restricted principal"):
            restricted.verify_runtime_identity()
    finally:
        with psycopg.connect(postgres, autocommit=True) as db:
            db.execute("ALTER ROLE moneymachine_runner NOCREATEDB")

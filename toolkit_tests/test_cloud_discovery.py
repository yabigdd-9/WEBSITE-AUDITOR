import copy
import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from scripts import cloud_discovery as discovery
from scripts import cloud_prospect_pipeline as pipeline
from scripts.pipeline_store import SCHEMA, PipelineStore


@pytest.fixture
def workspace():
    with tempfile.TemporaryDirectory() as directory:
        yield Path(directory)


def bundle(workspace, rows):
    path = workspace / "export.json"
    path.write_text(json.dumps(rows))
    return path


def ingest(state, path, source="curated", now=0, **kwargs):
    return discovery.import_export(
        state,
        path,
        source=source,
        source_url="https://source.example.com/export",
        terms_reviewed=kwargs.pop("terms_reviewed", True),
        now=now,
        run_id="fixture-import",
        **kwargs,
    )


def test_existing_adapter_normalizes_merges_and_minimizes(workspace):
    path = bundle(
        workspace,
        [
            {
                "name": "Fixture Business",
                "website": "https://WWW.Example.COM/about",
                "city": "Christchurch",
                "category": "plumber",
                "email": "not-retained@example.com",
            },
            {"name": "Fixture Business", "website": "https://example.com/"},
            {"name": "Blocked", "website": "https://127.0.0.1"},
        ],
    )
    store = PipelineStore(workspace / "discovery.sqlite3")
    with store.transaction(bootstrap=True) as state:
        result = ingest(state, path)
        assert result == dict(
            new_candidates=1, merged_candidates=0, rejected_rows=1, total_candidates=1
        )
    with store.transaction() as state:
        assert ingest(state, path, now=10)["new_candidates"] == 0
    saved = store.read()
    candidate = next(iter(saved["discovery_candidates"].values()))
    assert candidate["domain"] == "example.com"
    assert candidate["region"] == "Christchurch"
    assert candidate["category"] == "plumber"
    assert candidate["first_seen"] == pipeline.timestamp(0)
    assert candidate["last_seen"] == pipeline.timestamp(10)
    assert candidate["eligibility_status"] == "pending_policy_review"
    assert len(saved["discovery_events"]) == 1
    assert "not-retained" not in json.dumps(saved)
    assert saved["prospects"] == {}


@pytest.mark.parametrize(
    "source,document,category",
    [
        (
            "osm",
            {
                "elements": [
                    {
                        "id": 42,
                        "tags": {
                            "name": "Fixture",
                            "website": "https://example.com",
                            "addr:city": "Christchurch",
                            "craft": "electrician",
                        },
                    }
                ]
            },
            "electrician",
        ),
        (
            "nzbn",
            [
                {
                    "nzbn": "9429000000000",
                    "entityName": "Fixture",
                    "websiteUrl": "https://example.com",
                    "city": "Christchurch",
                    "category": "builder",
                }
            ],
            "builder",
        ),
    ],
)
def test_existing_source_specific_export_adapters(workspace, source, document, category):
    state = pipeline.empty_state()
    assert ingest(state, bundle(workspace, document), source)["new_candidates"] == 1
    candidate = next(iter(state["discovery_candidates"].values()))
    assert candidate["category"] == category
    assert candidate["sources"][0]["source_record_id"]
    assert candidate["verification_status"] == "unverified"


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://user:secret@example.com",
        "https://localhost",
        "https://127.0.0.1",
        "https://[::1]",
        "https://169.254.169.254",
        "https://2130706433",
        "https://0x7f.0.0.1",
        "https://localhost.example.com",
        "https://foo.internal",
        "https://foo.localhost",
        "https://example.com:8080",
        "https://bad..example.com",
        "https://-bad.example.com",
        "https://example.com/?token=secret",
        "https://foo.invalid",
        "https://exa\nmple.com",
        "file:///etc/passwd",
    ],
)
def test_unsafe_urls_rejected(url):
    with pytest.raises(ValueError):
        discovery.canonical_domain(url)


def test_cloud_guard_runs_before_legacy_root_url_normalization(workspace):
    state = pipeline.empty_state()
    path = bundle(
        workspace,
        [
            {"website": "https://exa\nmple.com"},
            {"website": "https://example.com/?token=secret"},
            {"website": "http://example.com"},
            {"website": "https://example.com"},
        ],
    )
    result = ingest(state, path)
    assert result["rejected_rows"] == 3
    assert result["new_candidates"] == 1
    assert "token=secret" not in json.dumps(state)


def test_discovery_cannot_queue_audit_until_independent_policy_review(workspace):
    state = pipeline.empty_state()
    ingest(state, bundle(workspace, [{"name": "Fixture", "website": "https://example.com"}]))

    def forbidden(*args):
        pytest.fail("Unreviewed discovery caused a request")

    pipeline.process(
        state,
        [],
        now=0,
        run_id="unreviewed",
        workspace=workspace,
        audit=forbidden,
        robots=forbidden,
    )
    assert state["prospects"] == {}
    rows = [{"domain": "www.example.com", "url": "https://www.example.com"}]
    pipeline.process(
        state,
        rows,
        now=1,
        run_id="reviewed",
        workspace=workspace,
        daily_limit=0,
        audit=forbidden,
        robots=forbidden,
    )
    prospect = next(iter(state["prospects"].values()))
    candidate = next(iter(state["discovery_candidates"].values()))
    assert prospect["domain"] == "www.example.com"
    assert prospect["discovery"]["business_name"] == "Fixture"
    assert candidate["prospect_id"] == hashlib.sha256(b"www.example.com").hexdigest()
    assert candidate["eligibility_status"] == "reviewed_allowlist"
    rows[0]["suppressed"] = True
    pipeline.process(
        state,
        rows,
        now=2,
        run_id="suppressed",
        workspace=workspace,
        audit=forbidden,
        robots=forbidden,
    )
    assert candidate["eligibility_status"] == "blocked"


def test_terms_and_capacity_failures_are_atomic(workspace):
    state = pipeline.empty_state()
    path = bundle(workspace, [{"website": "https://example.com"}])
    before = copy.deepcopy(state)
    with pytest.raises(ValueError):
        ingest(state, path, terms_reviewed=False)
    assert state == before

    with pytest.raises(ValueError):
        ingest(state, path, source="unreviewed-directory")
    assert state == before
    path = bundle(workspace, [{"website": f"https://s{i}.example.com"} for i in range(101)])
    with pytest.raises(ValueError):
        ingest(state, path)
    assert state == before


def test_cli_import_is_offline_and_prints_counts_only(workspace, monkeypatch, capsys):
    import socket

    def forbidden(*args, **kwargs):
        pytest.fail("Discovery import used the network")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    path = bundle(workspace, [{"name": "Private fixture name", "website": "https://example.com"}])
    db = workspace / "queue.sqlite3"
    args = [
        "--database",
        str(db),
        "--input",
        str(path),
        "--source",
        "curated",
        "--source-url",
        "https://source.example.com/export",
        "--terms-reviewed",
    ]
    assert discovery.main([*args, "--bootstrap"]) == 0
    assert discovery.main(args) == 0
    output = capsys.readouterr().out
    assert "Private fixture name" not in output
    assert "example.com" not in output
    assert len(PipelineStore(db).read()["discovery_candidates"]) == 1


def test_v1_database_migration_preserves_original_history_and_restores_backup(workspace):
    path = workspace / "legacy.sqlite3"
    with sqlite3.connect(path) as db:
        for statement in SCHEMA:
            db.execute(statement)
        db.execute("PRAGMA user_version=1")
        db.execute("INSERT INTO metadata VALUES(1,?)", ('{"schema_version":1}',))
    path.chmod(0o600)
    store = PipelineStore(path)
    assert store.read() == pipeline.empty_state()
    with store.transaction() as state:
        ingest(state, bundle(workspace, [{"website": "https://example.com"}]))
    backup = workspace / "backup.sqlite3"
    store.backup(backup)
    assert PipelineStore(backup).read() == store.read()
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 3
    with pytest.raises(ValueError):
        with store.transaction() as state:
            state["discovery_events"] = []

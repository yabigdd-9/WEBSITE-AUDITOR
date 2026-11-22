"""Synthetic cutover/recovery tests. No real download, audit or send."""

import copy

import pytest

from scripts.checkpoint_to_postgres import import_checkpoint
from scripts.cloud_prospect_pipeline import empty_state, event
from scripts.fetch_migration_checkpoint import WORKFLOW_PATH, fetch_latest
from scripts.pipeline_store import PipelineStore


@pytest.fixture(autouse=True)
def private_runner_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))


def target(tmp_path):
    store = PipelineStore(tmp_path / "private.sqlite3")
    with store.transaction(bootstrap=True) as state:
        event(state, 0, "setup", "0" * 64, "pause", "disabled")
    return store


def test_import_preserves_history_and_is_idempotent(tmp_path):
    store = target(tmp_path)
    incoming = empty_state()
    event(incoming, 1, "source", "a" * 64, "audit", "failed", "audit_failed")
    original = copy.deepcopy(incoming)
    result = import_checkpoint(store, incoming, source_run="123", actor="synthetic-owner", now=2)
    saved = store.read()
    assert saved["events"][0]["run_id"] == "setup"
    assert saved["events"][1] == incoming["events"][0]
    assert saved["storage_authority"] == "postgres"
    assert result["already_imported"] is False
    assert incoming == original
    assert import_checkpoint(store, incoming, source_run="123", actor="synthetic-owner", now=3)["already_imported"] is True
    assert store.read() == saved
    with pytest.raises(ValueError, match="differs"):
        import_checkpoint(store, incoming, source_run="124", actor="synthetic-owner", now=4)
    assert store.read() == saved


def test_import_refuses_unknown_settings_and_preserves_target(tmp_path):
    store = target(tmp_path)
    with store.transaction() as state:
        state["owner_settings"] = {"paused": True}
    before = store.read()
    with pytest.raises(ValueError, match="destination"):
        import_checkpoint(store, empty_state(), source_run="123", actor="owner", now=2)
    assert store.read() == before


def test_import_cannot_refund_aborted_reservations(tmp_path):
    store = target(tmp_path)
    with pytest.raises(RuntimeError):
        with store.transaction():
            assert store.reserve_attempt("a" * 64, "b" * 64, now=0, daily_limit=6)
            raise RuntimeError("Synthetic interrupted work")
    before = store.read()
    with pytest.raises(ValueError, match="reservations"):
        import_checkpoint(store, empty_state(), source_run="123", actor="owner", now=2)
    assert store.read() == before
    assert store.operational_summary()["reservations"] == 1


@pytest.mark.parametrize("source,actor", [("0", "owner"), ("../123", "owner"), ("123", "")])
def test_invalid_import_identity_fails_before_storage(source, actor):
    with pytest.raises(ValueError):
        import_checkpoint(None, empty_state(), source_run=source, actor=actor)


def source_query(**options):
    def query(args):
        if args[0] == "run":
            return [{"databaseId": 124 if options.get("newer") else 123}]
        if args[-1].endswith("/jobs"):
            return {"jobs": [{"name": "draft-pipeline", "conclusion": "failure" if options.get("failed") else "success"}]}
        if args[-1].endswith("/artifacts"):
            return {"artifacts": [{"id": 9, "name": "pipeline-state", "size_in_bytes": 100, "expired": options.get("expired", False)}]}
        return {"head_branch": "untrusted" if options.get("untrusted") else "master", "event": "push",
                "path": WORKFLOW_PATH, "status": "completed", "conclusion": "success"}
    return query


def test_migration_source_is_latest_trusted_completed_worker(tmp_path):
    destination = tmp_path / "pipeline-state.enc"

    def download(identity, directory):
        assert identity == 123
        (directory / "pipeline-state.enc").write_bytes(b"synthetic-ciphertext-only")

    result = fetch_latest(repo="synthetic/repo", source_run=123, current_run=200,
                          destination=destination, query=source_query(), download=download)
    assert result == {"source_run": 123, "artifact_id": 9}
    assert destination.read_bytes() == b"synthetic-ciphertext-only"
    assert destination.stat().st_mode & 0o077 == 0


@pytest.mark.parametrize("options", [{"newer": True}, {"failed": True}, {"expired": True}, {"untrusted": True}])
def test_unverified_sources_never_download(tmp_path, options):
    def forbid_download(*args):
        pytest.fail("Unverified source was downloaded")

    with pytest.raises(ValueError):
        fetch_latest(repo="synthetic/repo", source_run=123, current_run=200,
                     destination=tmp_path / "state.enc", query=source_query(**options), download=forbid_download)


def test_checkpoint_default_and_unknown_backend_never_fall_back(tmp_path, monkeypatch):
    from scripts import cloud_pipeline_checkpoint, cloud_prospect_pipeline, cloud_storage_runner

    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setenv("GITHUB_REPOSITORY", "synthetic/repo")
    monkeypatch.setenv("GITHUB_RUN_ID", "200")
    for name in ("WA_PIPELINE_STORAGE", "BOOTSTRAP", "WA_RECOVERY_RUN"):
        monkeypatch.delenv(name, raising=False)
    restored, executed = [], []
    monkeypatch.setattr(cloud_pipeline_checkpoint, "restore", lambda **kwargs: restored.append(kwargs))
    monkeypatch.setattr(cloud_prospect_pipeline, "main", lambda args: executed.append(args) or 0)
    assert cloud_storage_runner.main() == 0
    assert restored[0]["bootstrap"] is False
    assert executed == [["--state", str(tmp_path / "pipeline-state.enc"), "--daily-limit", "0"]]
    monkeypatch.setenv("WA_PIPELINE_STORAGE", "typo")
    assert cloud_storage_runner.main() == 2
    assert len(restored) == 1
    assert len(executed) == 1



def test_checkpoint_runner_lost_upload_resume_cannot_reaudit(tmp_path, monkeypatch):
    """Restore an older ciphertext twice as if the first job died before artifact upload.

    The currently authorized checkpoint-only worker may resume queue/draft state
    but must not make even a robots request until a pre-HTTP durable barrier exists.
    """
    import shutil

    fernet = pytest.importorskip("cryptography.fernet").Fernet

    from scripts import cloud_opportunities, cloud_pipeline_checkpoint, cloud_storage_runner
    from scripts import cloud_prospect_pipeline as pipeline

    key = fernet.generate_key().decode()
    source = tmp_path / "last-trusted.enc"
    pipeline.seal(pipeline.empty_state(), source, key)
    for name, value in {
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_REPOSITORY": "synthetic/repo",
        "GITHUB_RUN_ID": "501",
        "WA_PIPELINE_STORAGE": "checkpoint",
        "WA_PIPELINE_STATE_KEY": key,
        "MM_PAID_ALLOWED": "0",
        "MM_ALLOW_EXTERNAL_FREE_MODELS": "0",
        "MM_EXTERNAL_SEND_ALLOWED": "0",
    }.items():
        monkeypatch.setenv(name, value)
    for name in ("BOOTSTRAP", "WA_RECOVERY_RUN", "WA_OUTCOMES_ENCRYPTED"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        cloud_pipeline_checkpoint, "restore",
        lambda **options: shutil.copyfile(source, options["state_path"]),
    )
    monkeypatch.setattr(pipeline, "policy_rows", lambda _: [
        {"domain": "example.com", "url": "https://example.com/"}
    ])
    monkeypatch.setattr(cloud_opportunities, "load_policy", lambda _: None)

    def forbidden_request(*_args, **_kwargs):
        pytest.fail("Lost-upload recovery attempted to repeat a website request")

    original_process = pipeline.process

    def observe_process(*args, **kwargs):
        assert kwargs["daily_limit"] == 0
        return original_process(
            *args, **kwargs, audit=forbidden_request, robots=forbidden_request,
        )

    monkeypatch.setattr(pipeline, "process", observe_process)
    assert cloud_storage_runner.main() == 0
    state_path = tmp_path / "pipeline-state.enc"
    first_state = pipeline.unseal(state_path, key)
    assert len(first_state["prospects"]) == 1
    assert first_state["audit_runs"] == []
    assert next(iter(first_state["prospects"].values()))["attempts"] == 0

    # The first runner finished its script but never uploaded its new artifact;
    # the second must restore the last trusted ciphertext, not use local state.
    state_path.unlink()
    monkeypatch.setenv("GITHUB_RUN_ID", "502")
    assert cloud_storage_runner.main() == 0
    resumed = pipeline.unseal(state_path, key)
    assert len(resumed["prospects"]) == 1
    assert resumed["audit_runs"] == []
    assert next(iter(resumed["prospects"].values()))["attempts"] == 0
    assert pipeline.metrics(resumed)["contacts_sent"] == 0


def test_postgres_bootstrap_is_refused_before_connecting(tmp_path, monkeypatch):
    fernet_module = pytest.importorskip("cryptography.fernet")

    from scripts.cloud_storage_runner import run_postgres

    monkeypatch.setenv("BOOTSTRAP", "true")
    with pytest.raises(ValueError, match="migration"):
        run_postgres(tmp_path / "state.enc", fernet_module.Fernet.generate_key().decode())


def test_verify_only_requires_a_valid_encrypted_source_and_never_connects(tmp_path, monkeypatch, capsys):
    from scripts import checkpoint_to_postgres, postgres_store
    from scripts.cloud_prospect_pipeline import seal

    fernet = pytest.importorskip("cryptography.fernet").Fernet
    for name in ("MM_PAID_ALLOWED", "MM_ALLOW_EXTERNAL_FREE_MODELS", "MM_EXTERNAL_SEND_ALLOWED"):
        monkeypatch.setenv(name, "0")

    key = fernet.generate_key().decode()
    checkpoint = tmp_path / "trusted.enc"
    state = empty_state()
    event(state, 0, "private-fixture", "a" * 64, "pause", "disabled")
    seal(state, checkpoint, key)

    def forbidden_connection():
        pytest.fail("Verification connected to Postgres")

    monkeypatch.setattr(postgres_store, "PostgresPipelineStore", forbidden_connection)
    args = ["--verify-only", "--checkpoint", str(checkpoint), "--source-run", "123"]
    monkeypatch.setenv("WA_PIPELINE_STATE_KEY", fernet.generate_key().decode())
    assert checkpoint_to_postgres.main(args) == 2
    assert "blocked" in capsys.readouterr().out

    monkeypatch.setenv("WA_PIPELINE_STATE_KEY", key)
    assert checkpoint_to_postgres.main(args) == 0
    assert capsys.readouterr().out == "Trusted encrypted checkpoint verified in memory.\n"

    state["storage_authority"] = "postgres"
    seal(state, checkpoint, key)
    assert checkpoint_to_postgres.main(args) == 2
    assert "blocked" in capsys.readouterr().out

"""Two-runner recovery with disposable Postgres and synthetic ciphertext only."""

import base64
import hashlib
import os
from pathlib import Path

import pytest

from scripts import cloud_prospect_pipeline as pipeline
from scripts import postgres_store
from scripts.checkpoint_to_postgres import import_checkpoint
from scripts.cloud_storage_runner import run_postgres
from toolkit_tests.platform_helpers import assert_replay_sends_no_requests
from toolkit_tests.test_postgres_store import crash_postgres_writer
from toolkit_tests.test_postgres_store import postgres as postgres
from toolkit_tests.test_postgres_store import store as store

STATE_FILE = "pipeline-state.enc"
PAIRED_FILE = "pipeline-postgres-backup.enc"

pytestmark = pytest.mark.skipif(
    not os.environ.get("WA_SYNTHETIC_RECOVERY_DIR"),
    reason="Run using the synthetic two-runner recovery workflow",
)


def fixture_key(run_id):
    # Public input is intentional. Only generated fixture data can be exported.
    digest = hashlib.sha256(f"website-auditor-synthetic-recovery:{run_id}".encode()).digest()
    return base64.urlsafe_b64encode(digest)


def test_export_after_crash(store, postgres, monkeypatch):
    root = Path(os.environ["WA_SYNTHETIC_RECOVERY_DIR"]).resolve()
    root.mkdir(mode=0o700)
    monkeypatch.setenv("RUNNER_TEMP", str(root.parent))
    monkeypatch.delenv("WA_RECOVERY_RUN", raising=False)
    monkeypatch.delenv("BOOTSTRAP", raising=False)
    for name in ("MM_PAID_ALLOWED", "MM_ALLOW_EXTERNAL_FREE_MODELS", "MM_EXTERNAL_SEND_ALLOWED"):
        monkeypatch.setenv(name, "0")

    with store.transaction(bootstrap=True):
        pass
    import_checkpoint(store, pipeline.empty_state(), source_run="1", actor="synthetic-owner", now=0)
    crash_postgres_writer(postgres)
    assert store.operational_summary()["reservations"] == 1
    assert len(store.read()["events"]) == 1

    actual_main = pipeline.main
    monkeypatch.setattr(postgres_store, "PostgresPipelineStore", lambda: store)
    monkeypatch.setattr(pipeline, "main", lambda args: actual_main(["--postgres", "--paused"]))
    run_postgres(root / STATE_FILE, fixture_key(os.environ["GITHUB_RUN_ID"]).decode())
    assert {file.name for file in root.iterdir()} == {STATE_FILE, PAIRED_FILE}


def test_restore_on_fresh_runner(store, tmp_path, monkeypatch):
    from cryptography.fernet import Fernet, InvalidToken

    root = Path(os.environ["WA_SYNTHETIC_RECOVERY_DIR"]).resolve()
    monkeypatch.setenv("RUNNER_TEMP", str(root.parent))
    key = fixture_key(os.environ["GITHUB_RUN_ID"])
    cipher = Fernet(key)
    ciphertext = (root / PAIRED_FILE).read_bytes()
    with pytest.raises(InvalidToken):
        Fernet(fixture_key("wrong-key-fixture")).decrypt(ciphertext)
    decoded = bytearray(base64.urlsafe_b64decode(ciphertext))
    decoded[-1] ^= 1
    with pytest.raises(InvalidToken):
        cipher.decrypt(base64.urlsafe_b64encode(decoded))

    checkpoint = pipeline.unseal(root / STATE_FILE, key.decode())
    backup = tmp_path / "paired.json"
    backup.touch(mode=0o600, exist_ok=False)
    backup.write_bytes(cipher.decrypt(ciphertext))
    assert store.read() is None
    store.restore_empty(backup)
    assert store.read() == checkpoint
    assert checkpoint["checkpoint_import"]["source_run"] == "1"
    assert store.operational_summary()["reservations"] == 1
    with store.connection() as db:
        assert store.daily_usage(db, "1970-01-01", checkpoint) == 1

    with pytest.raises(ValueError, match="empty migrated destination"):
        store.restore_empty(backup)
    assert store.read() == checkpoint

    assert_replay_sends_no_requests(store, tmp_path)
    assert store.operational_summary()["reservations"] == 1
    assert pipeline.metrics(store.read())["contacts_sent"] == 0

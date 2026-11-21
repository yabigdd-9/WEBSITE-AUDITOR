"""Restore a hosted backup using only the disposable PostgreSQL fixture."""

import os
from pathlib import Path

import pytest

from scripts import cloud_prospect_pipeline as pipeline
from scripts.postgres_backup import MAX_BACKUP, export_private
from toolkit_tests.test_postgres_store import postgres as postgres
from toolkit_tests.test_postgres_store import store as store


@pytest.mark.skipif(
    not os.environ.get("WA_HOSTED_RECOVERY_DIR"),
    reason="Requires the hosted encrypted recovery artifacts",
)
def test_hosted_archive_round_trip(store, tmp_path):
    from cryptography.fernet import Fernet

    root = Path(os.environ["WA_HOSTED_RECOVERY_DIR"])
    key = os.environ.pop("WA_PIPELINE_STATE_KEY")
    checkpoint = pipeline.unseal(root / "pipeline-state.enc", key)
    with (root / "pipeline-postgres-backup.enc").open("rb") as stream:
        ciphertext = stream.read(2 * MAX_BACKUP + 1)
    assert len(ciphertext) <= 2 * MAX_BACKUP, "Encrypted backup exceeds bound"

    backup = tmp_path / "paired.json"
    restored = tmp_path / "restored.json"
    try:
        backup.touch(mode=0o600, exist_ok=False)
        backup.write_bytes(Fernet(key.encode()).decrypt(ciphertext))
        store.restore_empty(backup)
        assert store.read() == checkpoint
        export_private(store, restored)
        assert restored.read_bytes() == backup.read_bytes()
    finally:
        backup.unlink(missing_ok=True)
        restored.unlink(missing_ok=True)

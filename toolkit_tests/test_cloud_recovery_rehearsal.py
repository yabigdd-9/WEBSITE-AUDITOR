"""Synthetic paired backup transfer between isolated CI jobs."""

import base64
import hashlib
import os
from pathlib import Path

import pytest

stage = os.environ.get("WA_SYNTHETIC_RECOVERY_STAGE")
if not stage:
    pytest.skip("Requires the synthetic recovery rehearsal workflow", allow_module_level=True)

from cryptography.fernet import Fernet, InvalidToken  # noqa: E402

from scripts.cloud_prospect_pipeline import event  # noqa: E402
from toolkit_tests.platform_helpers import interrupt_reserved_transaction  # noqa: E402
from toolkit_tests.test_postgres_store import postgres as postgres  # noqa: E402
from toolkit_tests.test_postgres_store import sha  # noqa: E402
from toolkit_tests.test_postgres_store import store as store  # noqa: E402


def fixture_cipher(run_id):
    # Public inputs are intentional. Only generated fixture data can be exported.
    digest = hashlib.sha256(f"website-auditor-synthetic-recovery:{run_id}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def test_paired_recovery_across_runners(store, tmp_path):
    artifact = Path(os.environ["WA_SYNTHETIC_RECOVERY_ARTIFACT"])
    cipher = fixture_cipher(os.environ["GITHUB_RUN_ID"])
    prospect_id = sha("synthetic-prospect")
    checkpoint = tmp_path / "private-paired.json"

    if stage == "prepare":
        with store.transaction(bootstrap=True) as state:
            event(state, 0, "synthetic-source", prospect_id, "pause", "disabled")
        with pytest.raises(RuntimeError, match="Synthetic interruption"):
            interrupt_reserved_transaction(store, prospect_id, sha("synthetic-interrupted-audit"))
        assert store.operational_summary()["reservations"] == 1
        store.backup(checkpoint)
        artifact.write_bytes(cipher.encrypt(checkpoint.read_bytes()))
        return

    assert stage == "restore"
    ciphertext = artifact.read_bytes()
    with pytest.raises(InvalidToken):
        fixture_cipher("wrong-key-fixture").decrypt(ciphertext)
    assert store.read() is None
    fd = os.open(checkpoint, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(cipher.decrypt(ciphertext))
    store.restore_empty(checkpoint)

    saved = store.read()
    assert saved["events"][0]["run_id"] == "synthetic-source"
    assert len(saved["events"]) == 1
    with store.transaction():
        assert not store.reserve_attempt(prospect_id, sha("synthetic-retry"), now=0, daily_limit=1)
    assert store.operational_summary()["reservations"] == 1
    with pytest.raises(ValueError, match="empty migrated destination"):
        store.restore_empty(checkpoint)
    assert store.read() == saved

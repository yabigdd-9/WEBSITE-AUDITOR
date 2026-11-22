import base64
import copy
import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from scripts import report_archive as reports
from scripts import report_vault as vault
from scripts.pipeline_store import VERSION, PipelineStore
from toolkit_tests.platform_helpers import commit_mutation

NOW = 1767225600
CREATED = "2026-01-01T00:00:00Z"
EXPIRES = "2026-01-31T00:00:00Z"
RETAIN = "2026-03-01T00:00:00Z"
AUDIT_ID = hashlib.sha256(b"synthetic-audit").hexdigest()
PROSPECT_ID = hashlib.sha256(b"example.com").hexdigest()


def envelope():
    # Structure-only fixture: not asserted to be authentically decryptable.
    return json.dumps({
        "format": vault.FORMAT,
        "ephemeral_public_key": base64.b64encode(b"p" * 32).decode(),
        "salt": base64.b64encode(b"s" * 16).decode(),
        "nonce": base64.b64encode(b"n" * 12).decode(),
        "ciphertext": base64.b64encode(b"encrypted-fixture" * 4).decode(),
    }).encode()


@pytest.fixture
def workspace():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        archive_root = root / "sealed"
        archive_root.mkdir(mode=0o700)
        store = PipelineStore(root / "pipeline.sqlite3")
        with store.transaction(bootstrap=True) as state:
            state["prospects"][PROSPECT_ID] = {"domain": "example.com", "status": "complete", "draft": None}
            state["audit_runs"] = [{
                "audit_id": AUDIT_ID, "prospect_id": PROSPECT_ID, "domain": "example.com",
                "status": "complete", "canonical_run_id": "canonical-fixture",
                "execution_timestamp": CREATED,
            }]
        yield root, store, reports.EncryptedReportArchive(archive_root)


def options(data, **changes):
    fields = dict(
        expected_sha256=hashlib.sha256(data).hexdigest(), audit_ids=[AUDIT_ID],
        source_run_id="123", source_artifact_id="456", created_at=CREATED,
        source_expires_at=EXPIRES, retain_until=RETAIN, owner_reviewed=True,
        actor="fixture-owner", reason="Locally reviewed fixture association", now=NOW,
    )
    return {**fields, **changes}


def import_fixture(workspace, data=None):
    root, store, archive = workspace
    data = data or envelope()
    source = root / "download.enc.json"
    source.write_bytes(data)
    return reports.import_ciphertext(store, archive, source, **options(data))


def test_index_copy_and_restore_are_idempotent_without_decryption(workspace, monkeypatch):
    root, store, archive = workspace

    def forbidden(*args):
        pytest.fail("Archive custody attempted private-key decryption")

    monkeypatch.setattr(vault, "decrypt_document", forbidden)
    identity = import_fixture(workspace)
    assert import_fixture(workspace) == identity
    state = store.read()
    assert len(state["report_artifacts"]) == 1
    assert len(state["audit_artifact_links"]) == 1
    assert state["audit_artifact_links"][0]["canonical_run_id"] == "canonical-fixture"
    assert state["report_artifacts"][identity]["verification_status"] == "envelope_and_checksum_only"
    assert archive.read(identity) == envelope()
    assert archive.path(identity).stat().st_mode & 0o777 == 0o600
    backup = root / "backup.sqlite3"
    store.backup(backup)
    assert PipelineStore(backup).read() == state
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT COUNT(*) FROM report_artifacts").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM audit_artifact_links").fetchone()[0] == 1


def test_existing_vault_crypto_roundtrips_only_on_owner_device(workspace):
    pytest.importorskip("cryptography")
    private, public = vault.new_keypair()
    document = {"kind": "synthetic_private_review", "sites": [{"run_id": "canonical-fixture"}]}
    data = vault.encrypt_document(document, public)
    identity = import_fixture(workspace, data)
    _, store, archive = workspace
    assert vault.decrypt_document(archive.read(identity), private) == document
    assert private not in json.dumps(store.read())


@pytest.mark.parametrize("change", [
    {"format": "plaintext"}, {"private_key": "never-index-this"},
    {"ciphertext": "not-base64!"}, {"ciphertext": "YQ=="},
    {"nonce": "YQ=="}, {"salt": []}, {"ephemeral_public_key": "YQ=="},
])
def test_malformed_and_plaintext_envelopes_are_rejected(change):
    value = json.loads(envelope())
    value.update(change)
    data = json.dumps(value).encode()
    with pytest.raises(ValueError):
        reports.validate_envelope(data)


def test_duplicate_fields_size_and_source_symlinks_are_rejected(workspace):
    duplicate = b'{"format":"x","format":"y"}'
    oversized = b"x" * (vault.MAX_ENVELOPE_BYTES + 1)
    for data in (duplicate, oversized, b'{"plaintext":"private"}'):
        with pytest.raises(ValueError):
            reports.validate_envelope(data)
    root, _, _ = workspace
    source = root / "source.enc.json"
    source.write_bytes(envelope())
    link = root / "link.enc.json"
    link.symlink_to(source)
    with pytest.raises(ValueError):
        reports.read_envelope(link)


@pytest.mark.parametrize("change", [
    {"expected_sha256": "0" * 64}, {"owner_reviewed": False}, {"audit_ids": ["unknown"]},
    {"audit_ids": [AUDIT_ID, AUDIT_ID]}, {"source_run_id": "../private"},
    {"source_artifact_id": "token=secret"}, {"retain_until": CREATED},
    {"retain_until": "2030-01-01T00:00:00Z"}, {"source_expires_at": "2027-01-01T00:00:00Z"},
])
def test_registration_gates_are_atomic(workspace, change):
    _, store, archive = workspace
    before = store.read()
    parameters = options(envelope(), **change)
    with pytest.raises(ValueError):
        reports.registration(before, envelope(), **parameters)
    assert store.read() == before
    assert list(archive.root.iterdir()) == []


def test_expiry_missing_corrupt_and_unconfigured_archive_status(workspace):
    _, store, archive = workspace
    identity = import_fixture(workspace)
    metadata = store.read()["report_artifacts"][identity]
    assert reports.availability(metadata, archive, now=NOW) == "AVAILABLE"
    assert reports.availability(metadata, None, now=NOW) == "ARCHIVE_NOT_CONFIGURED"
    assert reports.availability(metadata, archive, now=NOW + 100 * 86400) == "EXPIRED"
    assert archive.path(identity).is_file()  # Expiry never silently deletes files.
    archive.path(identity).write_bytes(envelope() + b" ")
    assert reports.availability(metadata, archive, now=NOW) == "CORRUPT"
    archive.path(identity).unlink()
    assert reports.availability(metadata, archive, now=NOW) == "MISSING"


def test_quota_symlink_and_permissions_fail_closed(workspace, monkeypatch):
    root, _, archive = workspace
    monkeypatch.setattr(reports, "MAX_ARCHIVE_BYTES", 1)
    data = envelope()
    with pytest.raises(ValueError):
        archive.put(data)
    monkeypatch.setattr(reports, "MAX_ARCHIVE_BYTES", 50_000_000)
    identity = hashlib.sha256(data).hexdigest()
    secret = root / "private.txt"
    secret.write_text("never serve this")
    secret.chmod(0o600)
    archive.path(identity).symlink_to(secret)
    with pytest.raises(ValueError):
        archive.put(data)
    assert secret.read_text() == "never serve this"
    archive.root.chmod(0o755)
    with pytest.raises(ValueError):
        archive.read(identity)


def test_linking_partial_runs_does_not_qualify_or_rewrite_audits(workspace):
    root, _, archive = workspace
    other = PipelineStore(root / "partial.sqlite3")
    with other.transaction(bootstrap=True) as state:
        state["prospects"][PROSPECT_ID] = {"domain": "example.com", "status": "retry", "draft": None}
        state["audit_runs"] = [{"audit_id": AUDIT_ID, "prospect_id": PROSPECT_ID,
                                "status": "partial", "canonical_run_id": None}]
    before = copy.deepcopy(other.read())
    data = envelope()
    path = root / "partial.enc.json"
    path.write_bytes(data)
    reports.import_ciphertext(other, archive, path, **options(data))
    after = other.read()
    assert after["prospects"] == before["prospects"]
    assert after["audit_runs"] == before["audit_runs"]
    assert after["audit_artifact_links"][0]["audit_status"] == "partial"


def test_metadata_links_and_retentions_are_immutable(workspace):
    _, store, _ = workspace
    identity = import_fixture(workspace)
    before = store.read()
    mutations = [
        lambda s: s["report_artifacts"][identity].update(retain_until="2030-01-01T00:00:00+00:00"),
        lambda s: s.update(audit_artifact_links=[]),
    ]
    for mutation in mutations:
        with pytest.raises(ValueError):
            commit_mutation(store, mutation)
        assert store.read() == before


def test_v3_upgrade_preserves_old_state_and_operational_history(workspace):
    _, store, _ = workspace
    before = store.read()
    with sqlite3.connect(store.path) as db:
        db.execute("DROP TABLE audit_artifact_links")
        db.execute("DROP TABLE report_artifacts")
        db.execute("PRAGMA user_version=3")
    assert store.read() == before
    with sqlite3.connect(store.path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == VERSION


@pytest.mark.parametrize("change", [
    {"audit_id": "unknown"}, {"artifact_id": "unknown"},
    {"owner_reviewed": False}, {"audit_status": "partial"},
])
def test_invalid_new_associations_fail_atomically(workspace, change):
    _, store, _ = workspace
    import_fixture(workspace)
    before = store.read()
    def mutation(state):
        link = {**state["audit_artifact_links"][0], **change}
        state["audit_artifact_links"].append(link)
    with pytest.raises(ValueError):
        commit_mutation(store, mutation)
    assert store.read() == before

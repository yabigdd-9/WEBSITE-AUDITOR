"""Release check semantics: no unverified success or fictitious rollback."""

import hashlib
import json
import sqlite3

import mm_deploy
import mm_operator
import mm_pipeline
import pytest


@pytest.fixture
def harness(tmp_path, monkeypatch):
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE businesses(id INTEGER PRIMARY KEY)")
    recorded = []
    logged = []
    monkeypatch.setattr(mm_deploy, "_record", recorded.append)
    monkeypatch.setattr(mm_deploy, "log", logged.append)
    monkeypatch.setattr(mm_deploy, "root", lambda: tmp_path)
    monkeypatch.setattr(
        mm_deploy, "_run", lambda *args, **kwargs: (0, "known-sha\n", "")
    )
    monkeypatch.setattr(mm_pipeline, "health", lambda d: {"states": {}})
    gates = {
        "record_current_version": {"commit": "known-sha"},
        "create_rollback_point": {"backup": "/synthetic/verified-backup"},
    }
    yield db, gates, recorded, logged
    db.close()


def test_passed_checks_never_claim_deployment_or_promotion(harness):
    db, gates, recorded, logged = harness
    result = mm_deploy._post_deploy(db, {"candidate": "synthetic"}, gates)

    assert result["status"] == "PRE_RELEASE_CHECKS_PASSED"
    assert result["failed_post_checks"] == []
    assert result["rollback_review_required"] is False
    assert result["rollback_performed"] is False
    assert result["deployment_performed"] is False
    assert result["release_authorized"] is False
    assert all(v is True for v in result["post_deploy_checks"].values())
    assert recorded[0]["status"] == result["status"]
    assert logged[0]["kind"] == "pre_release_checks_passed"


def test_foreign_key_violation_blocks_release_without_claiming_rollback(harness):
    db, gates, recorded, logged = harness
    db.executescript(
        "CREATE TABLE parent(id INTEGER PRIMARY KEY);"
        "CREATE TABLE child(pid INTEGER REFERENCES parent(id));"
        "INSERT INTO child(pid) VALUES (999);"
    )

    result = mm_deploy._post_deploy(db, {"candidate": "synthetic"}, gates)

    assert result["status"] == "RELEASE_BLOCKED"
    assert result["post_deploy_checks"]["database_integrity"] is True
    assert result["post_deploy_checks"]["database_foreign_keys"] is False
    assert "database_foreign_keys" in result["failed_post_checks"]
    assert result["rollback_review_required"] is True
    assert result["rollback_performed"] is False
    assert recorded[0]["rollback_performed"] is False
    assert logged[0]["kind"] == "release_verification_blocked"


def test_missing_post_checks_fail_closed(harness, monkeypatch):
    db, gates, recorded, _ = harness

    def broken_health(_):
        raise OSError("synthetic unavailable")

    monkeypatch.setattr(mm_pipeline, "health", broken_health)
    result = mm_deploy._post_deploy(db, {"candidate": "synthetic"}, gates)

    assert result["status"] == "RELEASE_BLOCKED"
    assert "health_surface" in result["failed_post_checks"]
    assert "version_matches" in result["failed_post_checks"]
    assert "post_check_error" in result["post_deploy_checks"]
    assert result["rollback_performed"] is False
    assert recorded[0]["status"] != "ROLLED_BACK"


@pytest.mark.parametrize("git_result", [
    (1, "", "error"), (0, "wrong-revision\n", ""),
])
def test_missing_or_mismatched_revision_fails_closed(harness, monkeypatch, git_result):
    db, gates, _, _ = harness
    monkeypatch.setattr(mm_deploy, "_run", lambda *a, **kw: git_result)
    result = mm_deploy._post_deploy(db, {"candidate": "synthetic"}, gates)

    assert result["status"] == "RELEASE_BLOCKED"
    assert result["post_deploy_checks"]["version_matches"] is False
    assert "version_matches" in result["failed_post_checks"]
    assert result["release_authorized"] is False
    assert result["rollback_performed"] is False


def fixture_backup(tmp_path, *, bad_foreign_key=False):
    """Synthetic backup with real SQLite bytes and checksummed manifest."""
    folder = tmp_path / "backup"
    folder.mkdir()
    db_path = folder / "money_machine.db"
    with sqlite3.connect(db_path) as d:
        d.execute("CREATE TABLE businesses(id INTEGER PRIMARY KEY)")
        if bad_foreign_key:
            d.execute(
                "CREATE TABLE jobs(owner_id INTEGER REFERENCES businesses(id))"
            )
            d.execute("INSERT INTO jobs(owner_id) VALUES(234)")
    manifest = folder / "manifest.json"
    manifest.write_text(json.dumps({
        "created_at": "2030-01-01T00:00:00+00:00",
        "items": [{
            "source": "/never-opened/production.db",
            "path": str(db_path),
            "sha256": hashlib.sha256(db_path.read_bytes()).hexdigest(),
        }],
    }))
    return folder, db_path, manifest


def test_restore_checker_verifies_only_staged_copy(tmp_path):
    folder, database, manifest = fixture_backup(tmp_path)
    original_db = database.read_bytes()
    original_manifest = manifest.read_bytes()

    result = mm_deploy.verify_backup_restore(folder)

    assert result["status"] == "VERIFIED_STAGING_RESTORE"
    assert result["verified_manifest_items"] == 1
    assert result["sqlite_integrity"] == "ok"
    assert result["foreign_key_violations"] == 0
    assert result["staging_only"] is True
    assert result["source_modified"] is False
    assert result["live_restore_performed"] is False
    assert database.read_bytes() == original_db
    assert manifest.read_bytes() == original_manifest
    assert not list(tmp_path.glob("**/restored.db"))


def test_restore_checker_rejects_checksum_mismatch(tmp_path):
    folder, database, _ = fixture_backup(tmp_path)
    with database.open("ab") as fh:
        fh.write(b"tampered")

    assert mm_deploy.verify_backup_restore(folder)["reason"] == "backup_checksum_mismatch"


def test_restore_checker_rejects_foreign_key_violations(tmp_path):
    folder, _, _ = fixture_backup(tmp_path, bad_foreign_key=True)

    result = mm_deploy.verify_backup_restore(folder)

    assert result["status"] == "RESTORE_CHECK_BLOCKED"
    assert result["reason"] == "staging_foreign_keys_failed"


def test_restore_checker_rejects_manifest_paths_outside_backup(tmp_path):
    folder, _, manifest = fixture_backup(tmp_path)
    outside = tmp_path / "outside.db"
    outside.write_bytes(b"outside")
    payload = json.loads(manifest.read_text())
    payload["items"][0]["path"] = str(outside)
    payload["items"][0]["sha256"] = hashlib.sha256(outside.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(payload))

    result = mm_deploy.verify_backup_restore(folder)

    assert result["status"] == "RESTORE_CHECK_BLOCKED"
    assert result["reason"] == "manifest_path_escape"


def test_restore_checker_rejects_missing_manifest(tmp_path):
    folder, _, manifest = fixture_backup(tmp_path)
    manifest.unlink()

    assert mm_deploy.verify_backup_restore(folder)["reason"] == "manifest_missing_or_symlink"


def test_restore_command_does_not_connect_to_live_database(tmp_path, monkeypatch, capsys):
    folder, _, _ = fixture_backup(tmp_path)
    monkeypatch.setattr(
        mm_operator,
        "connect",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("restore-check must not open the live ledger")
        ),
    )

    assert mm_operator.main(["restore-check", "--bundle", str(folder)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "VERIFIED_STAGING_RESTORE"
    assert result["live_restore_performed"] is False
    assert mm_operator.main([
        "restore-check", "--bundle", str(tmp_path / "absent")
    ]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "RESTORE_CHECK_BLOCKED"

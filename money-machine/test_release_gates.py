"""Release check semantics: no unverified success or fictitious rollback."""

import sqlite3

import mm_deploy
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

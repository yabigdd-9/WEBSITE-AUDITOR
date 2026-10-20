"""Pinned reader contract with synthetic files; no service, database or network."""
import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import mm_soak as soak
import pytest


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    monkeypatch.setattr(soak, "ROOT", root)
    monkeypatch.setattr(soak, "PY", sys.executable)
    monkeypatch.setattr("socket.socket.connect", lambda *a: pytest.fail("network forbidden"))
    monkeypatch.setattr("socket.getaddrinfo", lambda *a: pytest.fail("DNS forbidden"))
    config = root / "synthetic-config.json"
    config.write_text('{"send": false}')
    doc = {"schema_version": 1, "release_id": "fixture", "source_sha": "a" * 40,
           "repository_realpath": str(root), "python_realpath": str(Path(sys.executable).resolve()),
           "database_realpath": str(root / "database/money_machine.db"),
           "scheduler_identity": "synthetic-label",
           "configuration": [{"realpath": str(config), "sha256": hashlib.sha256(config.read_bytes()).hexdigest()}]}
    manifest = root / "approved-manifest.json"
    modules = []
    for name in ("runtime_bootstrap.py", "supervisor/cli.py", "mm_core.py"):
        path = root / "money-machine" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('# synthetic source\n')
        modules.append({"path": str(path.relative_to(root)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    environment = {key: value for key, value in os.environ.items()
                   if not any(word in key.upper() for word in ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL"))}
    for command in (["git", "init", "-q"], ["git", "add", "money-machine"],
                    ["git", "-c", "core.hooksPath=/dev/null", "-c", "user.name=Synthetic",
                     "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"]):
        subprocess.run(command, cwd=root, env=environment, check=True, capture_output=True)
    doc["source_sha"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root,
                                                env=environment, text=True).strip()
    manifest.write_text(json.dumps(doc))
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    receipt = copy.deepcopy(doc)
    receipt.pop("schema_version")
    receipt.update(pid=12345, expected_sha=receipt.pop("source_sha"),
                   status="IMPORTS_VERIFIED", identity_status="STARTUP_IDENTITY_VERIFIED",
                   attestation_mode="PINNED_STARTUP", isolated_python=True,
                   python_executable=sys.executable, manifest_sha256=digest, modules=modules)
    folder = root / "state/runtime-startup"
    folder.mkdir(parents=True)
    (root / "state/supervisor.pid").write_text("12345")
    path = folder / "12345.json"
    path.write_text(json.dumps(receipt))
    return root, manifest, digest, path, receipt


def read(evidence):
    _, manifest, digest, _, _ = evidence
    return soak.startup_attestation(manifest_path=manifest, manifest_sha256=digest)


def test_pinned_startup_identity_is_not_live_process_acceptance(evidence):
    result = read(evidence)
    assert result["verified"] is True
    assert result["startup_identity_verified"] is True
    assert result["runtime_identity_status"] == "UNKNOWN"
    assert result["identity_failure_code"] is None
    assert not (evidence[0] / "database").exists()


def test_receipt_cannot_self_approve_without_independent_manifest(evidence):
    result = soak.startup_attestation()
    assert result["verified"] is True  # preserve legacy source-only meaning
    assert result["startup_identity_verified"] is False
    assert result["identity_failure_code"] == "approved_manifest_missing"


@pytest.mark.parametrize("field,value", [
    ("pid", 67890), ("pid", True), ("manifest_sha256", "0" * 64),
    ("expected_sha", "b" * 40), ("scheduler_identity", "other"),
    ("database_realpath", "/wrong/database.db"), ("repository_realpath", "/wrong"),
    ("python_realpath", "/wrong/python"), ("identity_status", "FAILED"),
    ("attestation_mode", "SOURCE_ONLY"), ("isolated_python", False),
    ("configuration", []), ("status", "FAILED"),
])
def test_stale_or_mismatched_receipt_never_verifies_identity(evidence, field, value):
    evidence[4][field] = value
    evidence[3].write_text(json.dumps(evidence[4]))
    result = read(evidence)
    assert result["startup_identity_verified"] is False
    assert result["runtime_identity_status"] == "UNKNOWN"


def test_configuration_drift_invalidates_pinned_startup_identity(evidence):
    (evidence[0] / "synthetic-config.json").write_text("PRIVATE FIXTURE CHANGED")
    result = read(evidence)
    assert result["startup_identity_verified"] is False
    assert "PRIVATE FIXTURE" not in json.dumps(result)


def test_changed_approval_bytes_fail_even_with_receipt_hash(evidence):
    evidence[1].write_text('{"different": true}')
    assert read(evidence)["startup_identity_verified"] is False


def test_duplicate_manifest_fields_fail_closed(evidence):
    raw = evidence[1].read_text().replace('"schema_version":', '"schema_version": 2, "schema_version":', 1)
    evidence[1].write_text(raw)
    digest = hashlib.sha256(evidence[1].read_bytes()).hexdigest()
    evidence[4]["manifest_sha256"] = digest
    evidence[3].write_text(json.dumps(evidence[4]))
    result = soak.startup_attestation(manifest_path=evidence[1], manifest_sha256=digest)
    assert result["startup_identity_verified"] is False


@pytest.mark.parametrize("change", [
    "wrong_db", "outside_config", "duplicate_config", "alias_config", "empty_config",
    "wrong_python", "wrong_root", "bad_version", "bad_revision", "nested_document",
])
def test_matching_receipt_cannot_make_invalid_manifest_acceptable(evidence, change):
    root, manifest, _, receipt_path, receipt = evidence
    doc = json.loads(manifest.read_text())
    if change == "wrong_db":
        doc["database_realpath"] = str(root / "other.db")
    elif change == "outside_config":
        doc["configuration"][0]["realpath"] = "/outside/synthetic-config.json"
    elif change == "duplicate_config":
        doc["configuration"] *= 2
    elif change == "alias_config":
        alias = root / "config-alias.json"
        alias.symlink_to(root / "synthetic-config.json")
        doc["configuration"][0]["realpath"] = str(alias)
    elif change == "empty_config":
        doc["configuration"] = []
    elif change == "wrong_python":
        doc["python_realpath"] = str(root / "wrong-python")
    elif change == "wrong_root":
        doc["repository_realpath"] = str(root / "wrong-root")
    elif change == "bad_version":
        doc["schema_version"] = True
    elif change == "bad_revision":
        doc["source_sha"] = "not-a-revision"
    for field in ("release_id", "repository_realpath", "python_realpath", "database_realpath",
                  "configuration", "scheduler_identity"):
        receipt[field] = doc[field]
    receipt["expected_sha"] = doc["source_sha"]
    manifest.write_text('[' * 2000 + '0' + ']' * 2000 if change == "nested_document" else json.dumps(doc))
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    receipt["manifest_sha256"] = digest
    receipt_path.write_text(json.dumps(receipt))
    result = soak.startup_attestation(manifest_path=manifest, manifest_sha256=digest)
    assert result["startup_identity_verified"] is False
    assert result["identity_failure_code"] == "startup_identity_unverified"
    assert not (root / "database").exists()


def test_matching_disk_and_receipt_hashes_cannot_override_approved_commit(evidence):
    root, _, _, receipt_path, receipt = evidence
    entry = receipt["modules"][0]
    path = root / entry["path"]
    path.write_text("# different from approved commit\n")
    entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    receipt_path.write_text(json.dumps(receipt))
    result = read(evidence)
    assert result["verified"] is True  # legacy disk/receipt consistency only
    assert result["startup_identity_verified"] is False
    assert result["runtime_identity_status"] == "UNKNOWN"

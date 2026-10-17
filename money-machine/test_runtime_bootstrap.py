"""Disposable Git trees prove literal bytecode drift blocks process startup."""
import json
import os
import py_compile
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path / "checkout"
    source = root / "money-machine"
    source.mkdir(parents=True)
    shutil.copyfile(Path(__file__).with_name("runtime_bootstrap.py"), source / "runtime_bootstrap.py")
    (source / "supervisor").mkdir()
    (source / "supervisor/__init__.py").write_text('"""Fixture package."""\n')
    (source / "supervisor/cli.py").write_text('import fixture_worker\ndef main(args):\n    print(fixture_worker.VALUE)\n    return 0\n')
    (source / "fixture_worker.py").write_text('VALUE = "NEW"\n')
    environment = {key: value for key, value in os.environ.items()
                   if not any(word in key.upper() for word in ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL"))}
    environment.update(MM_ROOT=str(root), GIT_AUTHOR_NAME="Synthetic", GIT_AUTHOR_EMAIL="fixture@example.invalid",
                       GIT_COMMITTER_NAME="Synthetic", GIT_COMMITTER_EMAIL="fixture@example.invalid")
    for command in (["git", "init", "-q"], ["git", "add", "money-machine"], ["git", "commit", "-qm", "synthetic"]):
        subprocess.run(command, cwd=root, env=environment, check=True, capture_output=True)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, env=environment, text=True).strip()
    return root, source, environment, revision


def start(checkout, revision=None, manifest=None, manifest_digest=None):
    root, source, environment, expected = checkout
    extra = ["--manifest", str(manifest), "--manifest-sha256", manifest_digest] if manifest else []
    result = subprocess.run([sys.executable, "-I", str(source / "runtime_bootstrap.py"),
                             "--expected-sha", revision or expected, *extra, "--", "--help"],
                            cwd=root, env=environment, capture_output=True, text=True, timeout=30)
    receipt = json.loads(next((root / "state/runtime-startup").glob("*.json")).read_text())
    return result, receipt


def test_committed_import_execution_produces_receipt(checkout):
    result, receipt = start(checkout)
    assert result.returncode == 0
    assert "NEW" in result.stdout
    assert receipt["status"] == "IMPORTS_VERIFIED"
    assert {record["path"] for record in receipt["modules"]} >= {
        "money-machine/runtime_bootstrap.py", "money-machine/supervisor/cli.py", "money-machine/fixture_worker.py"}


def test_wrong_revision_rejected_before_target_import(checkout):
    result, receipt = start(checkout, "0" * 40)
    assert result.returncode == 3
    assert receipt["failure_code"] == "checkout_revision_changed"
    assert "NEW" not in result.stdout


def test_source_drift_rejected_before_target_executes(checkout):
    _, source, _, _ = checkout
    (source / "fixture_worker.py").write_text('VALUE = "BAD"\n')
    result, receipt = start(checkout)
    assert result.returncode == 3
    assert receipt["failure_code"] == "application_source_changed"
    assert "BAD" not in result.stdout


def test_stale_module_literal_is_detected_despite_valid_timestamp_cache(checkout):
    _, source, _, _ = checkout
    module = source / "fixture_worker.py"
    original = module.stat()
    module.write_text('VALUE = "OLD"\n')
    os.utime(module, ns=(original.st_atime_ns, original.st_mtime_ns))
    py_compile.compile(str(module), doraise=True)
    module.write_text('VALUE = "NEW"\n')
    os.utime(module, ns=(original.st_atime_ns, original.st_mtime_ns))
    result, receipt = start(checkout)
    assert result.returncode == 3
    assert receipt["failure_code"] == "stale_loaded_code"
    assert "OLD" not in result.stdout


def test_optional_import_cannot_hide_a_failed_attestation(checkout):
    root, source, environment, _ = checkout
    (source / "supervisor/cli.py").write_text('try:\n    import fixture_worker\nexcept RuntimeError:\n    pass\ndef main(args):\n    print("SHOULD NOT START")\n    return 0\n')
    subprocess.run(["git", "add", "money-machine/supervisor/cli.py"], cwd=root, env=environment, check=True)
    subprocess.run(["git", "commit", "-qm", "synthetic guarded import"], cwd=root, env=environment, check=True)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, env=environment, text=True).strip()
    (source / "fixture_worker.py").write_text('VALUE = "BAD"\n')
    result, receipt = start(checkout, revision)
    assert result.returncode == 3
    assert receipt["status"] == "FAILED"
    assert "SHOULD NOT START" not in result.stdout


def test_configured_runtime_root_must_match_verified_checkout(checkout):
    root, _, environment, _ = checkout
    environment["MM_ROOT"] = str(root.parent)
    result, receipt = start(checkout)
    assert result.returncode == 3
    assert receipt["failure_code"] == "runtime_root_mismatch"
    assert "NEW" not in result.stdout


def approved_manifest(checkout, **updates):
    import hashlib
    root, _, environment, revision = checkout
    root = root.resolve()
    config = root / "fixture-config.json"
    config.write_text('{"synthetic": true}')
    environment["MM_SCHEDULER_ID"] = "synthetic-operator"
    doc = {"schema_version": 1, "release_id": "fixture-release", "source_sha": revision,
           "repository_realpath": str(root), "python_realpath": str(Path(sys.executable).resolve()),
           "database_realpath": str(root / "database/money_machine.db"),
           "configuration": [{"realpath": str(config), "sha256": hashlib.sha256(config.read_bytes()).hexdigest()}],
           "scheduler_identity": "synthetic-operator"}
    doc.update(updates)
    manifest = root / "manifest.json"
    manifest.write_text(json.dumps(doc))
    return manifest, hashlib.sha256(manifest.read_bytes()).hexdigest()


def test_manifest_startup_identity_never_attests_existing_runtime(checkout):
    manifest, digest = approved_manifest(checkout)
    result, receipt = start(checkout, manifest=manifest, manifest_digest=digest)
    assert result.returncode == 0, result.stderr
    assert receipt["status"] == "STARTUP_IDENTITY_VERIFIED"
    assert receipt["existing_runtime_status"] == "UNKNOWN"
    assert receipt["manifest_sha256"] == digest
    assert not (checkout[0] / "database").exists()  # target resolution never opens DB


@pytest.mark.parametrize("updates,code", [
    ({"schema_version": 2}, "manifest_schema_invalid"),
    ({"source_sha": "0" * 40}, "manifest_revision_mismatch"),
    ({"database_realpath": "/wrong/database.db"}, "manifest_database_mismatch"),
    ({"python_realpath": "/wrong/python"}, "manifest_interpreter_mismatch"),
    ({"scheduler_identity": "other"}, "manifest_scheduler_mismatch"),
    ({"configuration": []}, "manifest_configuration_missing"),
])
def test_manifest_mismatch_denies_target_dispatch(checkout, updates, code):
    manifest, digest = approved_manifest(checkout, **updates)
    result, receipt = start(checkout, manifest=manifest, manifest_digest=digest)
    assert result.returncode == 3
    assert receipt["failure_code"] == code
    assert "NEW" not in result.stdout


def test_changed_config_and_unapproved_manifest_are_rejected(checkout):
    manifest, digest = approved_manifest(checkout)
    result, receipt = start(checkout, manifest=manifest, manifest_digest="0" * 64)
    assert result.returncode == 3
    assert receipt["failure_code"] == "manifest_approval_mismatch"
    (checkout[0] / "fixture-config.json").write_text("secret fixture changed")
    result, receipt = start(checkout, manifest=manifest, manifest_digest=digest)
    assert result.returncode == 3
    assert receipt["failure_code"] == "manifest_configuration_changed"
    assert "secret fixture changed" not in result.stderr


def test_manifest_change_during_target_invalidates_receipt(checkout):
    root, source, environment, _ = checkout
    (source / "supervisor/cli.py").write_text(
        'from pathlib import Path\ndef main(args):\n'
        '    Path(__file__).resolve().parents[2].joinpath("fixture-config.json").write_text("changed")\n'
        '    return 0\n')
    subprocess.run(["git", "add", "money-machine/supervisor/cli.py"], cwd=root, env=environment, check=True)
    subprocess.run(["git", "commit", "-qm", "synthetic drift"], cwd=root, env=environment, check=True)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, env=environment, text=True).strip()
    current = root, source, environment, revision
    manifest, digest = approved_manifest(current)
    result, receipt = start(current, manifest=manifest, manifest_digest=digest)
    assert result.returncode == 3
    assert receipt["status"] == "FAILED"
    assert receipt["failure_code"] == "manifest_configuration_changed"


def test_manifest_rejects_symlink_configuration_alias(checkout):
    import hashlib
    manifest, _ = approved_manifest(checkout)
    alias = checkout[0] / "config-alias.json"
    alias.symlink_to(checkout[0] / "fixture-config.json")
    doc = json.loads(manifest.read_text())
    doc["configuration"][0]["realpath"] = str(alias)
    manifest.write_text(json.dumps(doc))
    result, receipt = start(checkout, manifest=manifest,
                            manifest_digest=hashlib.sha256(manifest.read_bytes()).hexdigest())
    assert result.returncode == 3
    assert receipt["failure_code"] == "manifest_path_alias"

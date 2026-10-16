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


def start(checkout, revision=None):
    root, source, environment, expected = checkout
    result = subprocess.run([sys.executable, "-I", str(source / "runtime_bootstrap.py"),
                             "--expected-sha", revision or expected, "--", "--help"],
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

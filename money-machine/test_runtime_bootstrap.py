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
    command = [sys.executable, "-I", str(source / "runtime_bootstrap.py"),
               "--expected-sha", revision or expected, *extra, "--", "--help"]
    with subprocess.Popen(command, cwd=root, env=environment,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as child:
        try:
            stdout, stderr = child.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate()
            raise
        result = subprocess.CompletedProcess(command, child.returncode, stdout, stderr)
        receipt = json.loads((root / "state/runtime-startup" / (str(child.pid) + ".json")).read_text())
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
    assert receipt["status"] == "IMPORTS_VERIFIED"
    assert receipt["identity_status"] == "STARTUP_IDENTITY_VERIFIED"
    assert receipt["existing_runtime_status"] == "UNKNOWN"
    assert receipt["manifest_sha256"] == digest
    assert not (checkout[0] / "database").exists()  # target resolution never opens DB


def test_manifest_outside_checkout_is_rejected(checkout):
    manifest, digest = approved_manifest(checkout)
    outside = checkout[0].parent / 'outside-manifest.json'
    shutil.copyfile(manifest, outside)
    result, receipt = start(checkout, manifest=outside, manifest_digest=digest)
    assert result.returncode == 3
    assert receipt['failure_code'] == 'manifest_path_invalid'


def test_oversized_manifest_is_rejected(checkout):
    manifest, digest = approved_manifest(checkout)
    manifest.write_bytes(b' ' * (1024 * 1024 + 1))
    result, receipt = start(checkout, manifest=manifest, manifest_digest=digest)
    assert result.returncode == 3
    assert receipt['failure_code'] == 'manifest_too_large'


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


def test_strict_receipt_remains_compatible_with_existing_soak_reader(checkout, monkeypatch):
    import mm_soak
    root, source, environment, _ = checkout
    (source / "mm_core.py").write_text('"""Synthetic core import."""\n')
    (source / "supervisor/cli.py").write_text(
        'import fixture_worker\nimport mm_core\ndef main(args):\n    return 0\n')
    subprocess.run(["git", "add", "money-machine"], cwd=root, env=environment, check=True)
    subprocess.run(["git", "commit", "-qm", "synthetic consumer contract"],
                   cwd=root, env=environment, check=True)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root,
                                       env=environment, text=True).strip()
    current = root, source, environment, revision
    manifest, digest = approved_manifest(current)
    result, receipt = start(current, manifest=manifest, manifest_digest=digest)
    assert result.returncode == 0, result.stderr
    (root / "state/supervisor.pid").write_text(str(receipt["pid"]))
    monkeypatch.setattr(mm_soak, "ROOT", root)
    observed = mm_soak.startup_attestation()
    assert observed["verified"] is True  # existing meaning: source imports only
    assert receipt["identity_status"] == "STARTUP_IDENTITY_VERIFIED"
    assert receipt["existing_runtime_status"] == "UNKNOWN"
    path = root / "state/runtime-startup" / (str(receipt["pid"]) + ".json")
    receipt.update(status="FAILED", identity_status="FAILED")
    path.write_text(json.dumps(receipt))
    assert mm_soak.startup_attestation()["verified"] is False


def test_batched_sources_match_git_for_unusual_paths(checkout):
    import runtime_bootstrap as bootstrap
    root, source, environment, _ = checkout
    names = ["space name.py", "line\nbreak.py", "unicodé.py"]
    for name in names:
        (source / name).write_bytes(b"VALUE = 'synthetic'\n")
    subprocess.run(["git", "add", "money-machine"], cwd=root, env=environment, check=True)
    subprocess.run(["git", "commit", "-qm", "synthetic unusual paths"], cwd=root, env=environment, check=True)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, env=environment, text=True).strip()
    observed = bootstrap.committed_sources(root, revision)
    for name in names:
        path = "money-machine/" + name
        assert observed[path] == subprocess.check_output(["git", "show", revision + ":" + path], cwd=root)


@pytest.mark.parametrize("body", [b"wrong header\n", b"a" * 40 + b" blob 3\nxy", b"a" * 40 + b" blob 3\nxyz\ntrailing"])
def test_batched_sources_reject_malformed_output(tmp_path, monkeypatch, body):
    import runtime_bootstrap as bootstrap
    listing = b"100644 blob " + b"a" * 40 + b" 3\tmoney-machine/test.py\0"
    monkeypatch.setattr(bootstrap, "git", lambda *args: listing)
    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess([], 0, body, b""))
    with pytest.raises(bootstrap.RevisionError):
        bootstrap.committed_sources(tmp_path, "a" * 40)


@pytest.mark.parametrize("fault", [subprocess.TimeoutExpired("fixture", 30), subprocess.CalledProcessError(1, "fixture")])
def test_batched_sources_reject_failed_reader(tmp_path, monkeypatch, fault):
    import runtime_bootstrap as bootstrap
    listing = b"100644 blob " + b"a" * 40 + b" 3\tmoney-machine/test.py\0"
    monkeypatch.setattr(bootstrap, "git", lambda *args: listing)
    def failed(*args, **kwargs):
        raise fault
    monkeypatch.setattr(bootstrap.subprocess, "run", failed)
    with pytest.raises(bootstrap.RevisionError):
        bootstrap.committed_sources(tmp_path, "a" * 40)


def test_batched_sources_use_only_two_git_processes(checkout, monkeypatch):
    import runtime_bootstrap as bootstrap
    root, _, _, revision = checkout
    original = bootstrap.subprocess.run
    commands = []
    def recorded(command, *args, **kwargs):
        commands.append(command)
        return original(command, *args, **kwargs)
    monkeypatch.setattr(bootstrap.subprocess, "run", recorded)
    assert bootstrap.committed_sources(root, revision)
    assert len(commands) == 2
    assert commands[0][3] == "ls-tree"
    assert commands[1][3] == "cat-file"


@pytest.mark.parametrize("nested", [False, True])
def test_manifest_duplicate_fields_deny_dispatch(checkout, nested):
    import hashlib

    manifest, _ = approved_manifest(checkout)
    raw = manifest.read_text()
    if nested:
        raw = raw.replace('"sha256":', '"sha256": "' + "0" * 64 + '", "sha256":', 1)
    else:
        raw = raw.replace('"schema_version":', '"schema_version": 2, "schema_version":', 1)
    manifest.write_text(raw)
    result, receipt = start(checkout, manifest=manifest,
                            manifest_digest=hashlib.sha256(manifest.read_bytes()).hexdigest())
    assert result.returncode == 3
    assert receipt["failure_code"] == "manifest_duplicate_field"
    assert "NEW" not in result.stdout


def test_excessively_nested_manifest_has_bounded_failure_receipt(checkout):
    import hashlib

    manifest, _ = approved_manifest(checkout)
    manifest.write_text('[' * 2000 + '0' + ']' * 2000)
    result, receipt = start(checkout, manifest=manifest,
                            manifest_digest=hashlib.sha256(manifest.read_bytes()).hexdigest())
    assert result.returncode == 3
    assert receipt["status"] == "FAILED"
    assert receipt["identity_status"] == "FAILED"
    assert receipt["failure_code"] == "manifest_unreadable_or_invalid"
    assert "Traceback" not in result.stderr
    assert "NEW" not in result.stdout

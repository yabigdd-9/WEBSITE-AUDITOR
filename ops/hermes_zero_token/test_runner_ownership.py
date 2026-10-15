"""Synthetic contract, process deadline and concurrent ownership regressions."""

import importlib.util
import json
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def runner(tmp_path, monkeypatch):
    specification = importlib.util.spec_from_file_location(
        "synthetic_runner", Path(__file__).with_name("runner.py")
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    monkeypatch.setattr(module, "AUDIT_LOG", tmp_path / "audit.jsonl")
    monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("HERMES_ZERO_TOKEN_DISABLE_ALL", "0")
    return module


@pytest.mark.parametrize("nested", [{}, {"production_written": False}, {"inner": {}}])
def test_nested_object_cannot_bypass_production_write_guard(runner, nested):
    def main():
        print(json.dumps({"production_written": True, "nested": nested}))
        return 0

    assert runner._execute_worker_module(SimpleNamespace(main=main), "fixture")[0] == 3


@pytest.mark.parametrize("value", [None, 0, "false", "", []])
def test_production_write_attestation_requires_boolean_false(runner, value):
    def main():
        print(json.dumps({"production_written": value}))
        return 0

    assert runner._execute_worker_module(SimpleNamespace(main=main), "fixture")[0] == 3
    assert runner._validate_worker_result(0, '{}', '', "fixture")[0] == 3


def test_pretty_report_with_nested_objects_and_diagnostics(runner):
    report = {"production_written": False, "nested": {"counts": {"rows": 1}},
              "quoted": 'brace } and escaped quote "'}
    stdout = "starting worker\n" + json.dumps(report, indent=2) + "\nfinished\n"
    assert runner._parse_worker_report(stdout, "fixture") == report
    assert runner._validate_worker_result(0, stdout, "", "fixture")[0] == 0


def test_truncated_report_is_not_replaced_with_nested_attestation(runner):
    stdout = '{"production_written":true,\n{"production_written":false}\n'
    assert runner._parse_worker_report(stdout, "fixture") is None
    assert runner._validate_worker_result(0, stdout, "", "fixture")[0] == 2


def test_last_complete_report_is_authoritative(runner):
    stdout = '{"production_written":false}\n{"production_written":true,"nested":{}}\n'
    assert runner._validate_worker_result(0, stdout, "", "fixture")[0] == 3


def test_shared_staging_lock_prevents_cross_worker_overlap(runner, monkeypatch):
    monkeypatch.setitem(runner.WORKER_MAP, "outreach_draft", lambda: pytest.fail("overlap"))
    with runner._worker_lock("staging_db"):
        assert runner.handle_worker("outreach_draft") == 75
    monkeypatch.setitem(runner.WORKER_MAP, "outreach_draft", lambda: (0, "", ""))
    assert runner.handle_worker("outreach_draft") == 0


def test_worker_lock_released_after_exception(runner, monkeypatch):
    def fail():
        raise ValueError("fixture crash")

    monkeypatch.setitem(runner.WORKER_MAP, "fixture", fail)
    assert runner.handle_worker("fixture") == 2
    monkeypatch.setitem(runner.WORKER_MAP, "fixture", lambda: (0, "", ""))
    assert runner.handle_worker("fixture") == 0


def test_kernel_releases_lock_after_owner_process_dies(runner, tmp_path):
    lock_directory = runner.AUDIT_LOG.parent / "locks"
    lock_directory.mkdir()
    lock_path = lock_directory / "staging-artifacts.lock"
    ready_path = tmp_path / "ready"
    program = (
        "import fcntl,pathlib,sys,time; "
        "handle=open(sys.argv[1],'a'); "
        "fcntl.flock(handle,fcntl.LOCK_EX); "
        "pathlib.Path(sys.argv[2]).touch(); time.sleep(60)"
    )
    owner = subprocess.Popen([sys.executable, "-c", program, str(lock_path), str(ready_path)])
    try:
        deadline = time.monotonic() + 5
        while not ready_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready_path.exists()
        with pytest.raises(BlockingIOError), runner._worker_lock("staging_db"):
            pytest.fail("duplicate owner admitted")
        owner.kill()
        owner.wait(timeout=5)
        with runner._worker_lock("outreach_draft"):
            assert lock_path.exists()
    finally:
        if owner.poll() is None:
            owner.kill()
            owner.wait(timeout=5)


def test_module_timeout_kills_descendants(runner, tmp_path, monkeypatch):
    worker_path = tmp_path / "ops/hermes_zero_token/staging_db.py"
    worker_path.parent.mkdir(parents=True)
    child_pid = tmp_path / "child.pid"
    child_stopped = tmp_path / "child-stopped"
    child_program = f"import time,pathlib;time.sleep(1);pathlib.Path({str(child_stopped)!r}).touch()"
    worker_path.write_text(
        "import pathlib,subprocess,sys,time\n"
        f"child=subprocess.Popen([sys.executable,'-c',{child_program!r}])\n"
        f"pathlib.Path({str(child_pid)!r}).write_text(str(child.pid))\n"
        "time.sleep(60)\n"
    )
    monkeypatch.setattr(runner, "MODULE_TIMEOUT_SECONDS", 0.4)
    started = time.monotonic()
    assert runner.handle_worker("staging_db") == 124
    assert time.monotonic() - started < 5
    record = json.loads(runner.AUDIT_LOG.read_text().splitlines()[-1])
    assert record["status"] == "timeout"
    assert child_pid.exists()
    time.sleep(1.1)
    assert not child_stopped.exists()


def test_module_success_uses_subprocess_contract(runner, tmp_path):
    worker_path = tmp_path / "ops/hermes_zero_token/demo_blueprint.py"
    worker_path.parent.mkdir(parents=True)
    worker_path.write_text('print(\'{"production_written":false,"nested":{}}\')\n')
    assert runner._run_module_worker("demo_blueprint")[0] == 0


def test_sigterm_cancels_worker_descendants_and_releases_lock(runner, tmp_path):
    ready = tmp_path / "ready"
    orphaned = tmp_path / "orphaned"
    worker_path = tmp_path / "ops/hermes_zero_token/staging_db.py"
    worker_path.parent.mkdir(parents=True)
    child_program = f"import pathlib,time;time.sleep(1);pathlib.Path({str(orphaned)!r}).touch()"
    worker_path.write_text(
        "import pathlib,subprocess,sys,time\n"
        f"subprocess.Popen([sys.executable,'-c',{child_program!r}])\n"
        f"pathlib.Path({str(ready)!r}).touch()\n"
        "time.sleep(60)\n"
    )
    program = (
        "import importlib.util,pathlib,sys;"
        "spec=importlib.util.spec_from_file_location('runner',sys.argv[1]);"
        "module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);"
        "module.PROJECT_ROOT=pathlib.Path(sys.argv[2]);"
        "module.AUDIT_LOG=pathlib.Path(sys.argv[2])/'audit.jsonl';"
        "sys.exit(module.handle_worker('staging_db'))"
    )
    process = subprocess.Popen([sys.executable, "-c", program, runner.__file__, str(tmp_path)])
    try:
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists()
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=5) == 143
        with runner._worker_lock("staging_db"):
            assert True
        time.sleep(1.1)
        assert not orphaned.exists()
        assert json.loads(runner.AUDIT_LOG.read_text().splitlines()[-1])["status"] == "cancelled"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)

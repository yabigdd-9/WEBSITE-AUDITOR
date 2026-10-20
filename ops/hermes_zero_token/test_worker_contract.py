"""Real worker subprocess contracts on synthetic databases and isolated output paths.

Only the browser transport is a labelled synthetic fixture. Actual worker entry
points, ownership handoff, SQLite staging, blueprint/draft output and audit logging
execute. Real Chromium rendering has its own separate browser acceptance suite.
"""

import importlib.util
import json
import os
import shutil
import sqlite3
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def runner(tmp_path, monkeypatch):
    project = tmp_path / "isolated-project"
    workers = project / "ops/hermes_zero_token"
    workers.mkdir(parents=True)
    for name in ["runner", "worker_ownership", "staging_db", "screenshot_worker",
                 "demo_blueprint", "outreach_draft"]:
        shutil.copyfile(Path(__file__).with_name(name + ".py"), workers / (name + ".py"))
    mm = project / "money-machine"
    mm.mkdir()
    for name in ["mm_core", "mm_experience_ledger", "mm_evidence_ops"]:
        shutil.copyfile(ROOT / "money-machine" / (name + ".py"), mm / (name + ".py"))
    monkeypatch.syspath_prepend(str(mm))
    database = project / "database/money_machine.db"
    database.parent.mkdir()
    with sqlite3.connect(database) as conn:
        conn.executescript((ROOT / "money-machine/database/schema.sql").read_text())
    core_spec = importlib.util.spec_from_file_location("contract_core", mm / "mm_core.py")
    core = importlib.util.module_from_spec(core_spec)
    core_spec.loader.exec_module(core)
    backup = core.backup(project)
    with core.connect(database) as conn:
        core.migrate(conn, backup)
        for bid in (1, 2):
            conn.execute("INSERT INTO businesses(id,name,source,discovered_at,current_status,is_dummy,public_website) "
                         "VALUES(?,?,?,?,'discovered',0,?)",
                         (bid, f'Synthetic contract business {bid}', 'fixture', core.now(),
                          f'https://contract-{bid}.example.invalid'))
            conn.execute("INSERT INTO mm_deals(business_id,stage,updated_at) VALUES(?,'DISCOVERED',?)", (bid, core.now()))
        capture = project / "fixture-capture.txt"
        capture.write_text("Synthetic contract observation; not real website evidence")
        core.record_evidence(conn, 1, 'https://contract-1.example.invalid',
                             'Synthetic observation', 'Contract fixture only', capture,
                             'unverified', 'fixture', 0.0)
        conn.execute("INSERT INTO audits(business_id,evidence,opportunity_score,created_at) VALUES(1,?,25,?)",
                     ('Synthetic contract evidence', core.now()))
        conn.execute("CREATE TABLE IF NOT EXISTS outreach_send_ledger(id INTEGER PRIMARY KEY,status TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS pipeline_items(id INTEGER PRIMARY KEY,state TEXT)")
    fake_browser = project / "auditor_toolkit"
    fake_browser.mkdir()
    (fake_browser / "__init__.py").write_text('"""Isolated browser transport fixture only."""\n')
    (fake_browser / "browser.py").write_text(
        "import base64;from pathlib import Path\n"
        "def run_browser_checks(url,output_dir,enabled=True):\n"
        " p=Path(output_dir)/'screenshot.png';p.parent.mkdir(parents=True,exist_ok=True)\n"
        " p.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='))\n"
        " return {'status':'ok','evidence':{'screenshot':str(p),'mode':'synthetic_contract_fixture'}}\n"
    )
    (project / "sitecustomize.py").write_text(
        "import socket,urllib.request,urllib.error\n"
        "def blocked(*args,**kwargs): raise urllib.error.URLError('synthetic offline contract')\n"
        "socket.socket.connect=blocked;socket.create_connection=blocked;socket.getaddrinfo=blocked\n"
        "urllib.request.urlopen=blocked\n"
    )
    spec = importlib.util.spec_from_file_location("isolated_contract_runner", workers / "runner.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    allowed = {key: value for key, value in os.environ.items()
               if key in {"PATH", "HOME", "TMPDIR", "LANG", "LC_ALL"}}
    allowed.update(PYTHONPATH=str(project), MM_ROOT=str(project), MM_EXTERNAL_SEND_DISABLED="1")
    with patch.dict(os.environ, allowed, clear=True):
        yield module


def run_worker_and_capture(runner, worker_id):
    stdout, stderr = StringIO(), StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        try:
            code = runner.handle_worker(worker_id)
        except SystemExit as error:
            code = error.code
    return code, stdout.getvalue(), stderr.getvalue()


def source_dump(runner):
    path = runner.PROJECT_ROOT / "database/money_machine.db"
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as conn:
        return list(conn.iterdump())


@pytest.mark.parametrize("worker_id,field", [
    ("staging_db", "batch_size_actual"), ("screenshot_worker", "screenshots_captured"),
    ("demo_blueprint", "blueprints_created"), ("outreach_draft", "drafts_created"),
])
def test_real_worker_subprocess_contract_preserves_entire_source_database(runner, worker_id, field):
    before = source_dump(runner)
    code, stdout, stderr = run_worker_and_capture(runner, worker_id)
    assert code == 0, stderr
    assert stderr == ""
    report = json.loads(stdout)
    assert report["production_written"] is False
    assert report["phase"] == "P2"
    assert report[field] > 0
    assert source_dump(runner) == before
    if worker_id == "staging_db":
        assert report["staging_state"]["total_processed"] == 1
        assert report["audit_result"]["results"][0]["status"] == "unverified"


def test_deprecated_aliases_fail_closed(runner):
    for worker_id in ["screenshot_worker_real", "demo_blueprint_real", "outreach_draft_real", "weekly_review_real"]:
        code, stdout, stderr = run_worker_and_capture(runner, worker_id)
        assert code == 3
        assert worker_id.removesuffix("_real") in stdout
        assert "placeholder removed" in stdout
        assert stderr == ""


def test_live_mutating_workers_blocked(runner):
    for worker_id in ["discovery-cycle", "discover-batch", "queue_dispatcher", "identity_resolution",
                      "site_auditor", "discover_nz_businesses"]:
        code, stdout, stderr = run_worker_and_capture(runner, worker_id)
        assert (code, stdout, stderr) == (3, "", "")


def test_unknown_worker_returns_error(runner):
    code, stdout, stderr = run_worker_and_capture(runner, "bogus_worker")
    assert code == 1
    assert stdout == ""
    assert "Unknown worker: bogus_worker" in stderr


def test_kill_switch_blocks_before_creating_any_audit_log(runner, monkeypatch):
    monkeypatch.setenv("HERMES_ZERO_TOKEN_DISABLE_ALL", "1")
    assert not runner.AUDIT_LOG.exists()
    code, stdout, stderr = run_worker_and_capture(runner, "staging_db")
    assert code == 3
    assert stdout == ""
    assert "HERMES_ZERO_TOKEN_DISABLE_ALL=1" in stderr
    assert not runner.AUDIT_LOG.exists()


def test_worker_run_updates_audit_log(runner):
    code, stdout, stderr = run_worker_and_capture(runner, "staging_db")
    assert code == 0, stderr
    report = json.loads(stdout)
    assert report["production_written"] is False
    entry = json.loads(runner.AUDIT_LOG.read_text().splitlines()[-1])
    assert entry["worker_id"] == "staging_db"
    assert entry["status"] == "completed"
    assert entry["exit_code"] == 0
    assert type(entry["duration_ms"]) is int and entry["duration_ms"] >= 0
    assert entry["cost_nzd"] == 0
    for name in ["timestamp", "job_id", "task_id", "event"]:
        assert name in entry


def test_worker_failure_updates_audit_log(runner):
    code, _, _ = run_worker_and_capture(runner, "screenshot_worker_real")
    assert code == 3
    entry = json.loads(runner.AUDIT_LOG.read_text().splitlines()[-1])
    assert entry["worker_id"] == "screenshot_worker_real"
    assert entry["status"] == "failed"
    assert entry["exit_code"] == 3
    assert entry["cost_nzd"] == 0

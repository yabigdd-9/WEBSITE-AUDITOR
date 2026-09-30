"""Disposable runtime fixtures; no live service, network, model calls or sends."""
import copy
import datetime as dt
import json
import sqlite3

import mm_core as core
import mm_pipeline as pipeline
import mm_runtime_guards as guards
import mm_soak as soak
import mm_workers
import pytest


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setenv("MM_ROOT", str(tmp_path))
    (tmp_path / "database").mkdir()
    path = tmp_path / "database/money_machine.db"
    with sqlite3.connect(path) as d:
        d.executescript("""
        CREATE TABLE businesses(id INTEGER PRIMARY KEY, name TEXT);
        INSERT INTO businesses VALUES(1,'Synthetic only');
        CREATE TABLE mm_model_invocations(cost_usd REAL);
        CREATE TABLE mm_messages(sent_at TEXT, send_receipt TEXT);
        CREATE TABLE mm_proposals(sent_at TEXT, send_receipt TEXT);
        """)
    return path


def test_accounting_is_measured_and_includes_partial_send_records(database):
    assert guards.accounting_snapshot()["paid_calls"] == 0
    with sqlite3.connect(database) as d:
        d.execute("INSERT INTO mm_model_invocations VALUES(1.25)")
        d.execute("INSERT INTO mm_messages VALUES('2026-01-01',NULL)")
        d.execute("INSERT INTO mm_messages VALUES(NULL,'receipt')")
    result = guards.accounting_snapshot()
    assert result["status"] == "measured"
    assert result["paid_calls"] == 1
    assert result["model_cost_usd"] == 1.25
    assert result["external_sends"] == 2
    assert result["sent_timestamps"] == result["send_receipts"] == 1


def test_missing_accounting_never_becomes_zero(database):
    with sqlite3.connect(database) as d:
        d.execute("DROP TABLE mm_messages")
    result = guards.accounting_snapshot()
    assert result["status"] == "error"
    assert result["paid_calls"] is None
    assert result["external_sends"] is None


def test_proposal_receipt_also_counts_as_a_send(database):
    with sqlite3.connect(database) as d:
        d.execute("INSERT INTO mm_proposals VALUES(NULL,'synthetic receipt')")
    result = guards.accounting_snapshot()
    assert result["external_sends"] == result["proposal_sends"] == 1


def test_process_reader_detects_other_python_supervisor_and_ignores_unrelated_quotes(monkeypatch):
    monkeypatch.setattr(soak, "run", lambda command: (
        "42 S /project/.venv/bin/python -m supervisor.cli _run-foreground\n"
        "43 S /usr/bin/python3 -m supervisor.cli _run-foreground\n"
        "44 S unrelated 'unclosed quote\n"))
    assert [process["pid"] for process in soak.supervisor_processes()] == [42, 43]


@pytest.mark.parametrize("value", [None, -1, "unknown"])
def test_invalid_cost_records_fail_accounting(database, value):
    with sqlite3.connect(database) as d:
        d.execute("INSERT INTO mm_model_invocations VALUES(?)", (value,))
    assert guards.accounting_snapshot()["status"] == "error"


def test_cli_processes_bounded_work_commits_and_closes(database, monkeypatch):
    connection = core.connect(database)
    monkeypatch.setattr(core, "connect", lambda: connection)
    monkeypatch.setattr(mm_workers, "WORKERS", {
        "synthetic": (("DISCOVERED",),
                      lambda d, it, worker: ("IDENTITY_PENDING", "synthetic", {}))})
    pipeline.migrate(connection)
    pipeline.enqueue(connection, 1)
    connection.commit()
    assert pipeline.run_pipelineloop_cli(
        ["--workers", "synthetic", "--cycles", "1", "--sleep", "0"]) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")
    with sqlite3.connect(database) as persisted:
        assert persisted.execute("SELECT state FROM pipeline_items").fetchone()[0] == "IDENTITY_PENDING"


def test_cli_closes_connection_on_loop_failure(database, monkeypatch):
    connection = core.connect(database)
    monkeypatch.setattr(core, "connect", lambda: connection)

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic loop failure")

    monkeypatch.setattr(pipeline, "run_pipelineloop", fail)
    with pytest.raises(RuntimeError):
        pipeline.run_pipelineloop_cli(["--cycles", "1"])
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


@pytest.mark.parametrize("args", [
    ["--workers", "missing"], ["--cycles", "0"], ["--report-every", "0"],
    ["--sleep", "-1"], ["--sleep", "nan"], ["--sleep", "inf"],
    ["--sleep", "0"], ["--unknown"]])
def test_cli_rejects_bad_arguments_before_opening_database(monkeypatch, args):
    def forbidden():
        raise AssertionError("invalid arguments opened the database")

    monkeypatch.setattr(core, "connect", forbidden)
    with pytest.raises(SystemExit) as error:
        pipeline.run_pipelineloop_cli(args)
    assert error.value.code == 2


def test_loop_sleeps_between_cycles_and_writes_requested_metrics(database, monkeypatch, tmp_path):
    pauses = []
    monkeypatch.setattr(pipeline.time, "sleep", pauses.append)
    with core.connect(database) as d:
        assert pipeline.run_pipelineloop(
            d, [], max_cycles=3, sleep_seconds=0.25, report_every=2,
            log_destination=tmp_path / "metrics") == 3
    assert pauses == [0.25, 0.25]
    rows = [json.loads(row) for row in
            (tmp_path / "metrics/pipeline-loop.jsonl").read_text().splitlines()]
    assert [r["kind"] for r in rows].count("loop_cycle") == 3
    assert rows[-1]["kind"] == "loop_ended"
    assert pipeline.BlockedCost is pipeline.BlockedCostError


def sample(seconds=0):
    timestamp = (dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
                 + dt.timedelta(seconds=seconds)).isoformat()
    return {
        "collected_at_utc": timestamp, "errors": {},
        "git": {"sha": "a" * 40, "branch": "synthetic", "working_tree_clean": True},
        "supervisor_processes": [{"pid": 42, "interpreter": soak.PY}],
        "pidfile": 42, "launchd_running": True,
        "config": {"external_send_disabled": "1", "program": soak.PY,
                   "root": str(soak.ROOT), "working_directory": str(soak.ROOT / "money-machine")},
        "heartbeat": {"at": timestamp, "pid": 42, "status": "running"},
        "accounting": {"status": "measured", "paid_calls": 0, "model_cost_usd": 0,
                       "external_sends": 0, "invalid_cost_records": 0},
        "db": {"integrity_check": "ok", "foreign_key_errors": [], "dead_lettered": 0,
               "expired_leases": 0},
        "disk": {"ok": True}, "network_probe": {"ok": True}}


@pytest.mark.parametrize("change,fragment", [
    ({"accounting": None}, "accounting unavailable"),
    ({"heartbeat": None}, "heartbeat evidence"),
    ({"heartbeat": {"at": "2025-12-31T23:50:00+00:00", "pid": 42, "status": "running"}},
     "heartbeat stale"),
    ({"supervisor_processes": [{"pid": 42}, {"pid": 43}]}, "supervisor count"),
    ({"disk": {"ok": False}}, "disk below"),
    ({"network_probe": {"ok": None}}, "network probe"),
    ({"db": {"integrity_check": "ok", "foreign_key_errors": []}}, "dead-letter evidence"),
])
def test_soak_missing_or_bad_evidence_fails(change, fragment):
    current = sample()
    current.update(change)
    assert any(fragment in error for error in soak.detect_violations(current))


def test_soak_detects_revision_config_gaps_and_transient_dlq_growth():
    baseline = sample()
    current = sample(600)
    current["git"]["sha"] = "b" * 40
    current["config"]["external_send_disabled"] = "0"
    current["db"]["dead_lettered"] = 1
    errors = soak.detect_violations(current, baseline, baseline)
    assert any("revision" in error for error in errors)
    assert any("configuration changed" in error for error in errors)
    assert any("dead-letter count grew" in error for error in errors)
    assert any("sample gap" in error for error in errors)
    finish = sample(86400)
    summary = soak.summarize([baseline, current, finish], [], 86400, True)
    assert summary["soak_passed"] is False
    assert summary["acceptance"]["evidence_valid"] is False


def test_interruption_and_old_uptime_cannot_pass():
    baseline, finish = sample(), sample(300)
    assert soak.detect_violations(baseline) == []
    assert not soak.summarize([baseline, finish], [], 86400, False)["soak_passed"]
    assert not soak.summarize([baseline, finish], [], 300, True)["soak_passed"]


def test_short_monitor_preserves_start_and_periodic_samples(tmp_path, monkeypatch):
    monkeypatch.setattr(soak, "ROOT", tmp_path)
    baseline, finish = sample(), sample(1)
    readings = iter([copy.deepcopy(baseline), copy.deepcopy(finish)])
    monkeypatch.setattr(soak, "collect_sample", lambda label: next(readings))
    clock = iter([0, 0, 0, 1])
    monkeypatch.setattr(soak.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(soak.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(soak.signal, "signal", lambda *args: None)
    directory = tmp_path / "evidence"
    assert soak.main(["--directory", str(directory), "--duration", "1",
                      "--interval", "1", "--max-gap", "2"]) == 1
    rows = (directory / "soak-samples.jsonl").read_text().splitlines()
    assert len(rows) == 2
    summary = json.loads((directory / "soak-summary.json").read_text())
    assert summary["status"] == "completed"
    assert summary["soak_passed"] is False
    assert summary["actual_elapsed_seconds"] == 1


def test_heartbeat_advancing_during_collection_is_not_falsely_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(soak, "ROOT", tmp_path)
    valid = sample(3)
    state = tmp_path / "state"
    state.mkdir()
    (state / "supervisor.heartbeat").write_text(json.dumps(sample(2)["heartbeat"]))
    (state / "supervisor.pid").write_text("42")
    for name, field in (
        ("git_info", "git"), ("supervisor_processes", "supervisor_processes"),
        ("service_config", "config"), ("database_diagnostics", "db"),
    ):
        monkeypatch.setattr(soak, name, lambda key=field: valid[key])
    monkeypatch.setattr(soak, "run", lambda command: "state = running\npid = 42")
    monkeypatch.setattr(guards, "accounting_snapshot", lambda root: valid["accounting"])
    monkeypatch.setattr(guards, "disk_guard", lambda root: valid["disk"])
    monkeypatch.setattr(guards, "network_guard", lambda **kw: valid["network_probe"])
    readings = iter([sample(0)["collected_at_utc"], valid["collected_at_utc"]])
    monkeypatch.setattr(core, "now", lambda: next(readings))
    result = soak.collect_sample()
    assert result["sampling_started_at_utc"] == sample(0)["collected_at_utc"]
    assert result["collected_at_utc"] == valid["collected_at_utc"]
    assert soak.detect_violations(result) == []

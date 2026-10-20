"""Durable snapshot generations, committed progress and bounded recovery on fixtures."""

import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def staging(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("progress_staging", Path(__file__).with_name("staging_db.py"))
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    source = tmp_path / "production.db"
    with sqlite3.connect(source) as conn:
        conn.executescript("""
            CREATE TABLE businesses(id INTEGER PRIMARY KEY, name TEXT, public_website TEXT, is_dummy INTEGER);
            CREATE TABLE mm_evidence(id INTEGER PRIMARY KEY, business_id INTEGER REFERENCES businesses(id));
            INSERT INTO businesses VALUES(1,'No URL',NULL,0);
            INSERT INTO businesses VALUES(2,'Synthetic A','https://a.example.invalid',0);
            INSERT INTO businesses VALUES(3,'Synthetic B','https://b.example.invalid',0);
        """)
    directory = tmp_path / "staging"
    for name, value in {"PROJECT_ROOT": tmp_path, "PROD_DB": source,
                        "STAGING_DIR": directory, "STAGING_DB": directory / "staging.db",
                        "STATE_FILE": directory / "state.json", "REPORT_PATH": directory / "report.json",
                        "BATCH_SIZE": 1}.items():
        monkeypatch.setattr(worker, name, value)

    def audit(ids):
        with sqlite3.connect(worker.STAGING_DB) as conn:
            conn.executemany("INSERT INTO mm_evidence(business_id) VALUES(?)", [(bid,) for bid in ids])
        return 0, json.dumps({"backfilled": len(ids), "model_calls": 0, "external_sends": 0}), ""

    worker._real_audit_batch = worker.run_audit_batch_staging
    monkeypatch.setattr(worker, "run_audit_batch_staging", audit)
    return worker


def test_restarts_preserve_generation_progress_and_do_not_starve_on_missing_url(staging):
    original = staging.PROD_DB.read_bytes()
    assert staging.main() == 0
    first = json.loads(staging.REPORT_PATH.read_text())
    assert first["batch_ids"] == [2]
    assert staging.main() == 0
    second = json.loads(staging.REPORT_PATH.read_text())
    assert second["batch_ids"] == [3]
    assert second["snapshot_generation"] == first["snapshot_generation"]
    assert second["staging_state"]["total_processed"] == 2
    assert staging.main() == 0
    assert json.loads(staging.REPORT_PATH.read_text())["batch_ids"] == []
    assert staging.PROD_DB.read_bytes() == original


def test_commit_survives_a_crash_before_state_export(staging, monkeypatch):
    save = staging.save_state
    monkeypatch.setattr(staging, "save_state", lambda state: (_ for _ in ()).throw(RuntimeError("fixture crash")))
    with pytest.raises(RuntimeError, match="fixture crash"):
        staging.main()
    with sqlite3.connect(staging.STAGING_DB) as conn:
        assert conn.execute("SELECT business_id FROM mm_evidence").fetchall() == [(2,)]
    monkeypatch.setattr(staging, "save_state", save)
    assert staging.main() == 0
    state = json.loads(staging.STATE_FILE.read_text())
    assert state["total_processed"] == 2
    assert json.loads(staging.REPORT_PATH.read_text())["batch_ids"] == [3]


def test_unmanifested_legacy_staging_is_never_reset(staging):
    staging.STAGING_DB.parent.mkdir()
    with sqlite3.connect(staging.STAGING_DB) as conn:
        conn.execute("CREATE TABLE keep_me(value TEXT)")
        conn.execute("INSERT INTO keep_me VALUES('preserved')")
    before = staging.STAGING_DB.read_bytes()
    with pytest.raises(ValueError, match="no generation manifest"):
        staging.snapshot_db()
    assert staging.STAGING_DB.read_bytes() == before


def test_pending_publication_is_resumed_without_a_new_snapshot(staging, monkeypatch):
    publish = staging._publish_snapshot
    monkeypatch.setattr(staging, "_publish_snapshot", lambda *args: (_ for _ in ()).throw(RuntimeError("interrupted publish")))
    with pytest.raises(RuntimeError, match="interrupted publish"):
        staging.snapshot_db()
    pending = staging._snapshot_metadata_path().with_suffix(".json.pending")
    prepared = json.loads(pending.read_text())
    monkeypatch.setattr(staging, "_publish_snapshot", publish)
    assert staging.snapshot_db() == staging.STAGING_DB
    assert staging.snapshot_metadata()["generation"] == prepared["generation"]
    assert not pending.exists()
    assert not Path(prepared["prepared_path"]).exists()


def test_source_schema_drift_blocks_audit_without_losing_progress(staging, monkeypatch):
    assert staging.main() == 0
    before = staging.STAGING_DB.read_bytes()
    with sqlite3.connect(staging.PROD_DB) as conn:
        conn.execute("ALTER TABLE businesses ADD COLUMN changed TEXT")
    monkeypatch.setattr(staging, "run_audit_batch_staging", lambda ids: pytest.fail("drift dispatched work"))
    assert staging.main() == 1
    assert staging.STAGING_DB.read_bytes() == before


def test_malformed_progress_is_held_before_any_audit(staging, monkeypatch):
    staging.snapshot_db()
    staging.STATE_FILE.write_text("not valid JSON")
    monkeypatch.setattr(staging, "run_audit_batch_staging", lambda ids: pytest.fail("invalid state ran"))
    with pytest.raises(ValueError, match="malformed"):
        staging.main()
    assert staging.STATE_FILE.read_text() == "not valid JSON"


def test_timed_out_backup_does_not_publish_or_destroy_any_snapshot(staging, monkeypatch):
    original = staging.PROD_DB.read_bytes()
    ticks = iter([0.0, 100.0])
    monkeypatch.setattr(staging.time, "monotonic", lambda: next(ticks, 100.0))
    with pytest.raises(TimeoutError):
        staging.snapshot_db(timeout_seconds=0.01)
    assert not staging.STAGING_DB.exists()
    assert not staging._snapshot_metadata_path().exists()
    assert not list(staging.STAGING_DIR.glob(".snapshot-*.db"))
    assert staging.PROD_DB.read_bytes() == original


def test_real_busy_source_backup_has_a_deadline(staging):
    program = (
        "import importlib.util,pathlib,sys;"
        "s=importlib.util.spec_from_file_location('s',sys.argv[1]);"
        "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
        "m.PROJECT_ROOT=pathlib.Path(sys.argv[2]);m.PROD_DB=pathlib.Path(sys.argv[3]);"
        "m.STAGING_DIR=pathlib.Path(sys.argv[4]);m.STAGING_DB=m.STAGING_DIR/'busy.db';"
        "\ntry: m.snapshot_db(timeout_seconds=0.05)"
        "\nexcept TimeoutError: sys.exit(0)"
        "\nsys.exit(42)"
    )
    env = {key: value for key, value in os.environ.items() if key in {"PATH", "HOME", "TMPDIR", "LANG"}}
    with sqlite3.connect(staging.PROD_DB) as source:
        source.execute("BEGIN EXCLUSIVE")
        started = time.monotonic()
        result = subprocess.run([sys.executable, "-B", "-c", program, staging.__file__,
                                 str(staging.PROJECT_ROOT), str(staging.PROD_DB), str(staging.STAGING_DIR)],
                                env=env, capture_output=True, text=True, timeout=3)
    assert result.returncode == 0, result.stderr
    assert time.monotonic() - started < 3


def test_subprocess_paths_and_ids_are_arguments_with_staging_root(staging, monkeypatch):
    captured = []

    def run(command, **kwargs):
        captured.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr(staging.subprocess, "run", run)
    staging._real_audit_batch([2])
    command, options = captured[0]
    assert command[0] == sys.executable
    assert str(staging.STAGING_DB) not in command[2]
    assert command[4] == str(staging.STAGING_DB)
    assert json.loads(command[5]) == [2]
    assert options["env"]["MM_ROOT"] == str(staging.STAGING_DB.parent)
    assert options["env"]["MM_EXTERNAL_SEND_DISABLED"] == "1"


def test_quoted_table_names_and_reserved_path_characters_are_data(staging, monkeypatch, tmp_path):
    folder = tmp_path / "quoted' #folder"
    folder.mkdir()
    path = folder / "data.db"
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE "quoted""table"(id INTEGER)')
        conn.execute('INSERT INTO "quoted""table" VALUES(1)')
    assert staging.table_counts(str(path)) == {'quoted"table': 1}


@pytest.mark.parametrize("label", ["../escape", "/absolute", "bad label", "a" * 65])
def test_generation_label_cannot_escape_staging_paths(label):
    env = {key: value for key, value in os.environ.items() if key in {"PATH", "HOME", "TMPDIR", "LANG"}}
    env["ZA_STAGING_GENERATION"] = label
    result = subprocess.run([sys.executable, "-B", str(Path(__file__).with_name("staging_db.py"))],
                            env=env, capture_output=True, text=True, timeout=5)
    assert result.returncode != 0
    assert "ZA_STAGING_GENERATION" in result.stderr

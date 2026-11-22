import hashlib
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import cloud_prospect_pipeline as pipeline
from scripts.operational_ledger import OperationalLedger
from scripts.pipeline_store import VERSION, PipelineStore
from toolkit_tests.platform_helpers import (
    assert_committed_attempt_allows_retry,
    assert_replay_sends_no_requests,
    interrupt_reserved_transaction,
)


def sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as directory:
        result = PipelineStore(Path(directory) / "pipeline.sqlite3")
        with result.transaction(bootstrap=True):
            pass
        yield result


def test_failed_queue_transactions_do_not_refund_request_reservations(store):
    for attempt in range(3):
        prospect_id, audit_id = sha(f"prospect-{attempt}"), sha(str(attempt))
        with pytest.raises(RuntimeError):
            interrupt_reserved_transaction(store, prospect_id, audit_id)
    with store.transaction():
        assert not store.reserve_attempt(sha("prospect-0"), sha("fourth"), now=0, daily_limit=6)
    summary = OperationalLedger(store.operations_path).summary()
    assert summary["reservations"] == 3
    assert sum(j["status"] == "failed" for j in summary["jobs"]) == 3
    assert store.read() == pipeline.empty_state()


def test_committed_queue_marker_repairs_interrupted_final_job_status(store):
    with patch.object(OperationalLedger, "finish", return_value=None):
        with store.transaction():
            pass
    job = OperationalLedger(store.operations_path).summary()["jobs"][0]
    assert job["status"] == "running"
    with store.transaction():
        pass
    repaired = next(
        j
        for j in OperationalLedger(store.operations_path).summary()["jobs"]
        if j["id"] == job["id"]
    )
    assert repaired["status"] == "succeeded"


def test_killed_process_reservation_survives_and_next_writer_records_interruption(store):
    command = [
        sys.executable,
        "-c",
        """
import os,sys,hashlib
from pathlib import Path
from scripts.pipeline_store import PipelineStore
store=PipelineStore(Path(sys.argv[1]))
with store.transaction() as state:
    assert store.reserve_attempt(hashlib.sha256(b'example.com').hexdigest(), hashlib.sha256(b'a').hexdigest(), now=0, daily_limit=6)
    state['events'].append({'uncommitted': True})
    os._exit(19)
""",
        str(store.path),
    ]
    assert subprocess.run(command, check=False).returncode == 19
    assert store.read()["events"] == []
    assert OperationalLedger(store.operations_path).summary()["jobs"][0]["status"] == "running"
    with store.transaction():
        assert not store.reserve_attempt(sha("example.com"), sha("a"), now=0, daily_limit=6)
    assert_replay_sends_no_requests(store, store.path.parent)
    report = OperationalLedger(store.operations_path).summary()
    assert report["reservations"] == 1
    assert any(j["status"] == "interrupted" for j in report["jobs"])


def test_committed_attempt_allows_retry_after_backoff(store):
    assert_committed_attempt_allows_retry(store, store.path.parent)


def test_daily_and_per_run_caps_include_legacy_state_and_failed_jobs(store):
    with store.transaction() as state:
        for index in range(3):
            pipeline.event(state, 0, "legacy", sha(str(index)), "audit", "failed", "audit_failed")
    for attempt in range(3):
        prospect_id, audit_id = sha("new" + str(attempt)), sha(str(attempt))
        with pytest.raises(RuntimeError):
            interrupt_reserved_transaction(store, prospect_id, audit_id)
    with store.transaction():
        assert not store.reserve_attempt(sha("other"), sha("other"), now=0, daily_limit=6)
        for i in range(3):
            assert store.reserve_attempt(
                sha("tomorrow" + str(i)), sha("tomorrow" + str(i)), now=86400, daily_limit=6
            )
        assert not store.reserve_attempt(sha("fourth"), sha("fourth"), now=86400, daily_limit=6)


def test_paired_backup_restores_quotas_and_missing_ledger_fails_closed(store):
    with store.transaction():
        assert store.reserve_attempt(sha("p"), sha("a"), now=0, daily_limit=6)
    destination = store.path.with_name("backup.sqlite3")
    store.backup(destination)
    restored = PipelineStore(destination)
    assert restored.read() == store.read()
    assert OperationalLedger(restored.operations_path).summary()["reservations"] == 1
    assert restored.operations_path.stat().st_mode & 0o777 == 0o600
    store.operations_path.unlink()
    with pytest.raises(ValueError, match="Operational ledger missing"):
        store.read()
    assert not store.operations_path.exists()


def test_reservation_denial_prevents_robots_and_audit_requests(store):
    rows = [dict(domain="example.com", url="https://example.com")]

    def forbidden(*args):
        pytest.fail("Budget-blocked queue issued a request")

    with store.transaction() as state:
        pipeline.process(
            state,
            rows,
            now=0,
            run_id="blocked",
            workspace=store.path.parent,
            attempt_reserver=lambda *args, **kwargs: False,
            robots=forbidden,
            audit=forbidden,
        )
    saved = store.read()
    assert next(iter(saved["prospects"].values()))["attempts"] == 0
    assert saved["audit_runs"] == []
    assert saved["events"][-1]["sanitized_error"] == "quota_exhausted"


def test_cli_wires_reservations_before_mock_audit(store):
    original = pipeline.process
    rows = [dict(domain="example.com", url="https://example.com")]

    def process(state, rows, **kwargs):
        assert callable(kwargs["attempt_reserver"])
        return original(
            state,
            rows,
            **kwargs,
            robots=lambda _: True,
            audit=lambda *args: [{"status": "INCOMPLETE"}],
        )

    flags = {
        "MM_PAID_ALLOWED": "0",
        "MM_ALLOW_EXTERNAL_FREE_MODELS": "0",
        "MM_EXTERNAL_SEND_ALLOWED": "0",
        "WA_RECOVERY_RUN": "",
        "WA_OUTCOMES_ENCRYPTED": "",
    }
    with (
        patch.dict(os.environ, flags),
        patch.object(pipeline, "policy_rows", return_value=rows),
        patch.object(pipeline, "process", process),
    ):
        assert pipeline.main(["--database", str(store.path)]) == 0
    assert OperationalLedger(store.operations_path).summary()["reservations"] == 1


def test_first_bootstrap_failure_cannot_silently_recreate_lost_quota_history(store):
    fresh = PipelineStore(store.path.with_name("fresh.sqlite3"))
    prospect_id, audit_id = sha("p"), sha("a")
    with pytest.raises(RuntimeError):
        interrupt_reserved_transaction(fresh, prospect_id, audit_id, bootstrap=True)
    assert fresh.read() is None
    fresh.operations_path.unlink()
    with pytest.raises(ValueError, match="Operational ledger missing"):
        fresh.read()
    assert not fresh.operations_path.exists()


def test_legacy_prospect_attempts_still_count_after_rollback(store):
    identity = sha("example.com")
    with store.transaction() as state:
        state["prospects"][identity] = dict(
            domain="example.com", attempts=2, status="retry", draft=None
        )
    audit_id = sha("third")
    with pytest.raises(RuntimeError):
        interrupt_reserved_transaction(store, identity, audit_id)
    with store.transaction():
        assert not store.reserve_attempt(identity, sha("fourth"), now=0, daily_limit=6)


def test_committed_attempts_are_not_double_charged(store):
    rows = [dict(domain=f"s{i}.example.com", url=f"https://s{i}.example.com") for i in range(8)]
    calls = []

    def audit(*args):
        calls.append(True)
        return [{"status": "INCOMPLETE"}]

    for now in (0, 1, 4000, 86400):
        with store.transaction() as state:
            pipeline.process(
                state,
                rows,
                now=now,
                run_id=f"run-{now}",
                workspace=store.path.parent,
                attempt_reserver=store.reserve_attempt,
                robots=lambda _: True,
                audit=audit,
            )
        assert len(calls) == (3 if now == 0 else 9 if now == 86400 else 6)
    assert OperationalLedger(store.operations_path).summary()["reservations"] == 9


def test_private_database_rejects_replaceable_parent_directory(store):
    directory = store.path.parent / "shared"
    directory.mkdir()
    directory.chmod(0o777)
    with pytest.raises(ValueError, match="not be writable"):
        PipelineStore(directory / "private.sqlite3")


def test_v2_migration_preserves_state_and_commits_required_ledger_marker(store):
    with sqlite3.connect(store.path) as db:
        db.execute("DROP TABLE audit_artifact_links")
        db.execute("DROP TABLE report_artifacts")
        db.execute("PRAGMA user_version=2")
        db.execute("UPDATE metadata SET body=json_remove(body,'$._store_operations_required')")
    before = store.read()
    assert before == pipeline.empty_state()
    with sqlite3.connect(store.path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == VERSION
        assert (
            db.execute(
                "SELECT json_extract(body,'$._store_operations_required') FROM metadata"
            ).fetchone()[0]
            == 1
        )


def test_pause_skips_stages_and_cli_caps_fail_before_work(store):
    flags = {
        "MM_PAID_ALLOWED": "0",
        "MM_ALLOW_EXTERNAL_FREE_MODELS": "0",
        "MM_EXTERNAL_SEND_ALLOWED": "0",
        "WA_RECOVERY_RUN": "",
        "WA_OUTCOMES_ENCRYPTED": "",
    }
    with (
        patch.dict(os.environ, flags),
        patch.object(pipeline, "policy_rows", return_value=[]),
        patch.object(pipeline, "process", side_effect=AssertionError("Paused job processed work")),
    ):
        assert pipeline.main(["--database", str(store.path), "--paused"]) == 0
        for options in (["--max-audits", "4"], ["--daily-limit", "7"], ["--daily-limit", "-1"]):
            assert pipeline.main(["--database", str(store.path), *options]) == 2
    assert store.read()["events"][-1]["action"] == "pause"
    assert OperationalLedger(store.operations_path).summary()["reservations"] == 0

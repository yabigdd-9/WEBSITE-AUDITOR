import contextlib
import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import cloud_prospect_pipeline as pipeline
from scripts.pipeline_store import PipelineStore
from toolkit_tests.platform_helpers import commit_mutation


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as directory:
        yield PipelineStore(Path(directory) / "pipeline.sqlite3")


def prospect():
    domain = "example.com"
    return hashlib.sha256(domain.encode()).hexdigest(), {
        "domain": domain,
        "draft": None,
        "status": "queued",
    }


def test_independent_process_restore_and_backup(store):
    identity, row = prospect()
    with store.transaction(bootstrap=True) as state:
        state["prospects"][identity] = row
    command = [
        sys.executable,
        "-c",
        "from scripts.pipeline_store import PipelineStore; from pathlib import Path; "
        "import sys,json; print(json.dumps(PipelineStore(Path(sys.argv[1])).read()))",
        str(store.path),
    ]
    restored = json.loads(subprocess.check_output(command, text=True))
    assert restored["prospects"][identity] == row
    assert store.path.stat().st_mode & 0o777 == 0o600
    backup = store.path.with_name("backup.sqlite3")
    store.backup(backup)
    assert PipelineStore(backup).read() == restored
    with pytest.raises(FileExistsError):
        store.backup(backup)


def test_transaction_rollback_and_foreign_key_failure(store):
    with store.transaction(bootstrap=True):
        pass
    before = store.read()
    identity, row = prospect()

    def interrupted(state):
        state["prospects"][identity] = row
        raise RuntimeError("interrupted")

    with pytest.raises(RuntimeError):
        commit_mutation(store, interrupted)
    assert store.read() == before
    with pytest.raises(sqlite3.IntegrityError):
        with store.transaction() as state:
            state["business_events"] = [{"event_id": "e1", "entity_id": "missing"}]
    assert store.read() == before


def test_crashed_process_preserves_previous_commit(store):
    with store.transaction(bootstrap=True):
        pass
    command = [
        sys.executable,
        "-c",
        """
import os,sys
from pathlib import Path
from scripts.pipeline_store import PipelineStore
with PipelineStore(Path(sys.argv[1])).transaction() as state:
    state['events'].append({'interrupted': True})
    os._exit(19)
""",
        str(store.path),
    ]
    assert subprocess.run(command, check=False).returncode == 19
    assert store.read()["events"] == []


def test_competing_worker_cannot_select_or_audit(store):
    with store.transaction(bootstrap=True):
        pass
    competing = PipelineStore(store.path)
    with store.transaction():
        with pytest.raises(sqlite3.OperationalError):
            commit_mutation(competing, lambda state: None)


def test_reader_sees_last_committed_state_while_audit_writer_is_active(store):
    with store.transaction(bootstrap=True):
        pass
    before = store.read()
    with store.transaction() as state:
        state["prospects"][prospect()[0]] = prospect()[1]
        assert PipelineStore(store.path).read() == before
    assert len(store.read()["prospects"]) == 1


def test_installed_adapter_rejects_other_git_checkouts(store):
    checkout = store.path.parent / "other-checkout"
    checkout.mkdir()
    (checkout / ".git").write_text("gitdir: /private/git/metadata")
    with pytest.raises(ValueError):
        PipelineStore(checkout / "records.sqlite3")


def test_bootstrap_schema_and_path_controls(store):
    with pytest.raises(ValueError):
        with store.transaction():
            pass
    with store.transaction(bootstrap=True):
        pass
    with pytest.raises(ValueError):
        with store.transaction(bootstrap=True):
            pass
    with sqlite3.connect(store.path) as db:
        db.execute("PRAGMA user_version=999")
    with pytest.raises(ValueError):
        store.read()
    os.chmod(store.path, 0o644)
    with pytest.raises(ValueError):
        PipelineStore(store.path)
    public_path = Path(__file__).resolve().parents[1] / "secret.sqlite3"
    with pytest.raises(ValueError):
        PipelineStore(public_path)
    link = store.path.with_name("symlink.sqlite3")
    link.symlink_to(store.path)
    with pytest.raises(ValueError):
        PipelineStore(link)


def test_reject_existing_other_schema_and_noncanonical_identity(store):
    with sqlite3.connect(store.path) as db:
        db.execute("CREATE TABLE legacy(value)")
    store.path.chmod(0o600)
    with pytest.raises(ValueError):
        store.read()
    with tempfile.TemporaryDirectory() as directory:
        other = PipelineStore(Path(directory) / "other.sqlite3")
        row = prospect()[1]

        def invalid_identity(state):
            state["prospects"]["wrong"] = row

        with pytest.raises(ValueError):
            commit_mutation(other, invalid_identity, bootstrap=True)
        assert other.read() is None


def test_cli_database_roundtrip_without_checkpoint_secret(store):
    env = {
        "MM_PAID_ALLOWED": "0",
        "MM_ALLOW_EXTERNAL_FREE_MODELS": "0",
        "MM_EXTERNAL_SEND_ALLOWED": "0",
        "WA_OUTCOMES_ENCRYPTED": "",
        "WA_RECOVERY_RUN": "",
        "WA_PIPELINE_STATE_KEY": "",
    }
    output = io.StringIO()
    with (
        patch.dict(os.environ, env),
        patch.object(pipeline, "policy_rows", return_value=[]),
        patch.dict(sys.modules, {"cryptography": None}),
    ):
        with contextlib.redirect_stdout(output):
            assert pipeline.main(["--database", str(store.path), "--bootstrap"]) == 0
            assert pipeline.main(["--database", str(store.path)]) == 0
            assert pipeline.main(["--database", str(store.path), "--bootstrap"]) == 2
    assert len(store.read()["events"]) == 2
    assert "example.com" not in output.getvalue()


def test_history_suppression_and_pagination(store):
    identity, row = prospect()
    row["status"] = "suppressed"
    with store.transaction(bootstrap=True) as state:
        state["prospects"][identity] = row
        state["events"].append({"action": "suppression"})
    before = store.read()
    for mutate in (
        lambda s: s["events"].clear(),
        lambda s: s["prospects"].clear(),
        lambda s: s["prospects"][identity].update(status="queued"),
    ):
        with pytest.raises(ValueError):
            commit_mutation(store, mutate)
        assert store.read() == before
    assert store.prospects(query="EXAMPLE", limit=1) == [row]
    assert store.prospects(offset=1) == []
    assert store.prospects(query="%' OR 1=1 --") == []
    with pytest.raises(ValueError):
        store.prospects(limit=101)


def test_pipeline_history_quota_and_idempotency_across_database_runs(store):
    rows = [dict(domain=f"s{i}.example.com", url=f"https://s{i}.example.com/") for i in range(8)]
    calls = []

    def audit(sites, workspace, entries):
        calls.append(sites)
        return [{"status": "INCOMPLETE"}]

    def run(bootstrap, now):
        with store.transaction(bootstrap=bootstrap) as state:
            pipeline.process(
                state,
                rows,
                now=now,
                run_id=f"run-{now}",
                workspace=store.path.parent,
                robots=lambda _: True,
                audit=audit,
            )

    run(True, 0)
    run(False, 1)
    run(False, 4000)
    assert len(calls) == 6
    saved = store.read()
    assert len(saved["audit_runs"]) == 6
    assert len(saved["prospects"]) == 8
    assert all(r["status"] == "partial" for r in saved["audit_runs"])
    assert all(r["failure_category"] == "audit_incomplete" for r in saved["audit_runs"])
    assert all(p["draft"] is None for p in saved["prospects"].values())
    run(False, 86400)
    assert len(calls) == 9
    assert len(store.read()["audit_runs"]) == 9


def test_completed_evidence_and_source_survive_restart_without_duplicate_audit(store):
    rows = [
        dict(
            domain="example.com",
            url="https://example.com/",
            business_name="Fixture Business",
            region="Christchurch",
            source="curated",
            source_url="https://example.com/about",
        )
    ]
    evidence = dict(
        run_id="canonical-1",
        internal_scope_draft="INTERNAL SCOPE DRAFT - DO NOT SEND\nFixture",
        checks_completed=["fetch", "html"],
        findings=[dict(severity="medium", evidence_ref="html", finding_id="fixture-1")],
    )

    def audit(sites, workspace, entries):
        entries.append(evidence)
        return [{"status": "complete"}]

    with store.transaction(bootstrap=True) as state:
        pipeline.process(
            state,
            rows,
            now=0,
            run_id="first",
            workspace=store.path.parent,
            audit=audit,
            robots=lambda _: True,
        )
    with PipelineStore(store.path).transaction() as state:
        pipeline.process(
            state,
            rows,
            now=86400,
            run_id="second",
            workspace=store.path.parent,
            audit=lambda *args: pytest.fail("Completed audit repeated"),
            robots=lambda _: pytest.fail("Completed site fetched"),
        )
    state = store.read()
    assert len(state["audit_runs"]) == 1
    run = state["audit_runs"][0]
    assert run["canonical_run_id"] == "canonical-1"
    assert run["evidence_references"] == ["html"]
    assert run["finding_counts"]["medium"] == 1
    assert run["encrypted_artifact_reference"] is None
    assert run["retry_count"] == 0
    assert run["checks_completed"] == ["fetch", "html"]
    p = next(iter(state["prospects"].values()))
    assert p["discovery"]["source_url"] == rows[0]["source_url"]
    assert p["discovery"]["business_name"] == "Fixture Business"
    assert p["audit"] == evidence
    assert p["draft"] == evidence["internal_scope_draft"]


def test_daily_pause_and_invalid_budgets_never_request(store):
    with store.transaction(bootstrap=True) as state:
        kwargs = dict(
            now=0,
            run_id="paused",
            workspace=store.path.parent,
            robots=lambda _: pytest.fail("Paused queue fetched a URL"),
        )
        pipeline.process(
            state,
            [dict(domain="example.com", url="https://example.com/")],
            daily_limit=0,
            **kwargs,
        )
        for settings in ({"daily_limit": 7}, {"daily_limit": True}, {"limit": True}):
            with pytest.raises(ValueError):
                pipeline.process(state, [], **kwargs, **settings)
    assert store.read()["audit_runs"] == []

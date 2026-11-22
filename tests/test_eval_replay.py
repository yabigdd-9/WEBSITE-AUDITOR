"""Tests for evaluation replay runner."""

import json

from auditor_toolkit.evaluation.replay import ReplayRunner
from auditor_toolkit.evaluation.runner import EvalRunner
from auditor_toolkit.evaluation.schema import EvalCase


class _FakeReplayAdapter:
    """Deterministic fake for replay testing."""

    def run(self, case, run_id=""):
        from auditor_toolkit.evaluation.schema import EvalResult
        return EvalResult(
            case_id=case.case_id,
            run_id=run_id,
            claims=[{"finding_id": fid, "severity": "high"} for fid in case.expected_findings],
            agent_output=json.dumps(case.expected_findings),
            agent_model="fake-replay",
        )


def _make_case(cid="test_001", **kw):
    defaults = {
        "case_id": cid,
        "category": "accessibility",
        "task": "test task",
        "fixture_id": "fixture_001",
        "expected_behavior": "finding",
    }
    defaults.update(kw)
    return EvalCase(**defaults)


def test_create_snapshot(tmp_path):
    runner = EvalRunner(adapter=_FakeReplayAdapter())
    replay = ReplayRunner(runner, snapshot_dir=tmp_path)

    fixtures = {"fixture_001": tmp_path / "fixture.json"}
    fixtures["fixture_001"].write_text('{"data": "test"}')

    cases = [_make_case(cid="c1")]

    snapshot = replay.create_snapshot(
        snapshot_id="snap_001",
        fixtures=fixtures,
        cases=cases,
    )

    assert snapshot.snapshot_id == "snap_001"
    assert snapshot.content_hash
    assert len(snapshot.case_ids) == 1


def test_load_snapshot(tmp_path):
    runner = EvalRunner(adapter=_FakeReplayAdapter())
    replay = ReplayRunner(runner, snapshot_dir=tmp_path)

    fixtures = {"fixture_001": tmp_path / "fixture.json"}
    fixtures["fixture_001"].write_text('{"data": "test"}')
    cases = [_make_case(cid="c1")]

    replay.create_snapshot(
        snapshot_id="snap_002",
        fixtures=fixtures,
        cases=cases,
    )

    # Load from disk
    loaded = replay.load_snapshot("snap_002")
    assert loaded is not None
    assert loaded.snapshot_id == "snap_002"


def test_load_missing_snapshot(tmp_path):
    runner = EvalRunner(adapter=_FakeReplayAdapter())
    replay = ReplayRunner(runner, snapshot_dir=tmp_path)

    loaded = replay.load_snapshot("nonexistent")
    assert loaded is None


def test_verify_snapshot_match(tmp_path):
    runner = EvalRunner(adapter=_FakeReplayAdapter())
    replay = ReplayRunner(runner)

    fixtures = {"fixture_001": tmp_path / "fixture.json"}
    fixtures["fixture_001"].write_text('{"data": "unchanged"}')
    cases = [_make_case(cid="c1")]

    snapshot = replay.create_snapshot(
        snapshot_id="snap_verify",
        fixtures=fixtures,
        cases=cases,
    )

    ok, mismatches = replay.verify_snapshot(snapshot, fixtures)
    assert ok
    assert mismatches == []


def test_verify_snapshot_mismatch(tmp_path):
    runner = EvalRunner(adapter=_FakeReplayAdapter())
    replay = ReplayRunner(runner)

    fixtures = {"fixture_001": tmp_path / "fixture.json"}
    fixtures["fixture_001"].write_text('{"data": "original"}')
    cases = [_make_case(cid="c1")]

    snapshot = replay.create_snapshot(
        snapshot_id="snap_mismatch",
        fixtures=fixtures,
        cases=cases,
    )

    # Modify the fixture after snapshot creation
    fixtures["fixture_001"].write_text('{"data": "modified"}')

    ok, mismatches = replay.verify_snapshot(snapshot, fixtures)
    assert not ok
    assert "fixture_001" in mismatches


def test_verify_snapshot_missing_file(tmp_path):
    runner = EvalRunner(adapter=_FakeReplayAdapter())
    replay = ReplayRunner(runner)

    fixtures = {"fixture_001": tmp_path / "fixture.json"}
    fixtures["fixture_001"].write_text('{"data": "test"}')
    cases = [_make_case(cid="c1")]

    snapshot = replay.create_snapshot(
        snapshot_id="snap_missing",
        fixtures=fixtures,
        cases=cases,
    )

    # Delete the fixture
    fixtures["fixture_001"].unlink()

    ok, mismatches = replay.verify_snapshot(snapshot, fixtures)
    assert not ok


def test_run_replay_verified(tmp_path):
    runner = EvalRunner(adapter=_FakeReplayAdapter())
    replay = ReplayRunner(runner, snapshot_dir=tmp_path)

    fixtures = {"fixture_001": tmp_path / "fixture.json"}
    fixtures["fixture_001"].write_text('{"data": "test"}')
    cases = [_make_case(cid="c1", expected_findings=["f1"])]

    replay.create_snapshot(
        snapshot_id="snap_run",
        fixtures=fixtures,
        cases=cases,
    )

    run = replay.run_replay(
        snapshot_id="snap_run",
        fixtures=fixtures,
        cases=cases,
    )

    # Should succeed since fixtures match
    assert run.status == "COMPLETE"


def test_run_replay_hash_mismatch(tmp_path):
    runner = EvalRunner(adapter=_FakeReplayAdapter())
    replay = ReplayRunner(runner, snapshot_dir=tmp_path)

    fixtures = {"fixture_001": tmp_path / "fixture.json"}
    fixtures["fixture_001"].write_text('{"data": "original"}')
    cases = [_make_case(cid="c1")]

    replay.create_snapshot(
        snapshot_id="snap_fail",
        fixtures=fixtures,
        cases=cases,
    )

    # Modify fixture to cause hash mismatch
    fixtures["fixture_001"].write_text('{"data": "tampered"}')

    run = replay.run_replay(
        snapshot_id="snap_fail",
        fixtures=fixtures,
        cases=cases,
    )

    # Should fail due to hash mismatch
    assert run.status == "FAILED"


def test_replay_deterministic(tmp_path):
    runner = EvalRunner(adapter=_FakeReplayAdapter())
    replay = ReplayRunner(runner)

    cases = [_make_case(cid="c1", expected_findings=["f1"])]

    variance = replay.replay_deterministic(cases, run_count=3)

    assert "c1" in variance
    assert len(variance["c1"]) == 3


def test_replay_snapshot_to_dict(tmp_path):
    runner = EvalRunner(adapter=_FakeReplayAdapter())
    replay = ReplayRunner(runner)

    fixtures = {"f1": tmp_path / "f.json"}
    fixtures["f1"].write_text("test")
    cases = [_make_case(cid="c1")]

    snapshot = replay.create_snapshot(
        snapshot_id="snap_dict",
        fixtures=fixtures,
        cases=cases,
    )

    d = snapshot.to_dict()
    assert d["snapshot_id"] == "snap_dict"
    assert "c1" in d["case_ids"]
    assert d["content_hash"]

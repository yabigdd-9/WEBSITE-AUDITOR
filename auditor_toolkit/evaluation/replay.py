"""Replay runner — deterministic replay of evaluation cases from frozen fixtures.

Supports replaying against:
- Frozen fixture files
- Existing golden corpus cases
- Recorded evidence snapshots

Ensures fixture hashes are verified before run and that replays are
reproducible.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .runner import EvalRunner, hash_fixture, hash_fixture_content
from .schema import EvalCase, EvalExpectedResult, EvalRun


@dataclass
class ReplaySnapshot:
    """A frozen snapshot of fixture state for deterministic replay."""

    snapshot_id: str
    fixture_path: str
    content_hash: str
    case_ids: list[str] = field(default_factory=list)
    expected_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ReplayRunner:
    """Manages frozen replay snapshots and verifies hashes before execution."""

    def __init__(
        self,
        runner: EvalRunner,
        snapshot_dir: Path | None = None,
    ):
        self.runner = runner
        self.snapshot_dir = snapshot_dir
        self._snapshots: dict[str, ReplaySnapshot] = {}

    def create_snapshot(
        self,
        snapshot_id: str,
        fixtures: dict[str, Path],
        cases: list[EvalCase],
        expected_map: dict[str, EvalExpectedResult] | None = None,
    ) -> ReplaySnapshot:
        """Create a frozen snapshot from fixture files and cases."""
        hashes: dict[str, str] = {}
        for fid, fpath in fixtures.items():
            hashes[fid] = hash_fixture(fpath)

        expected_results = {}
        if expected_map:
            for cid, exp in expected_map.items():
                expected_results[cid] = asdict(exp)

        from datetime import UTC, datetime

        snapshot = ReplaySnapshot(
            snapshot_id=snapshot_id,
            fixture_path=str(next(iter(fixtures.values())))
            if fixtures
            else "",
            content_hash=hash_fixture_content(
                json.dumps(hashes, sort_keys=True)
            ),
            case_ids=[c.case_id for c in cases],
            expected_results=expected_results,
            created_at=datetime.now(UTC).isoformat(),
        )

        if self.snapshot_dir:
            self.snapshot_dir.mkdir(parents=True, exist_ok=True)
            snap_path = self.snapshot_dir / f"{snapshot_id}.json"
            snap_path.write_text(json.dumps(snapshot.to_dict(), indent=2))

        self._snapshots[snapshot_id] = snapshot
        return snapshot

    def load_snapshot(self, snapshot_id: str) -> ReplaySnapshot | None:
        """Load a previously saved snapshot."""
        if snapshot_id in self._snapshots:
            return self._snapshots[snapshot_id]

        if self.snapshot_dir:
            snap_path = self.snapshot_dir / f"{snapshot_id}.json"
            if snap_path.exists():
                data = json.loads(snap_path.read_text())
                snapshot = ReplaySnapshot(**data)
                self._snapshots[snapshot_id] = snapshot
                return snapshot

        return None

    def verify_snapshot(
        self,
        snapshot: ReplaySnapshot,
        fixtures: dict[str, Path],
    ) -> tuple[bool, list[str]]:
        """Verify that fixture files match snapshot hashes.

        Returns (all_match, list_of_mismatched_fixture_ids).
        """
        missing = [fid for fid, fpath in fixtures.items() if not fpath.exists()]
        if missing:
            return False, [f"{fid} (file missing)" for fid in missing]

        current_hashes = {fid: hash_fixture(fpath) for fid, fpath in fixtures.items()}
        current_content_hash = hash_fixture_content(json.dumps(current_hashes, sort_keys=True))
        if current_content_hash == snapshot.content_hash:
            return True, []

        # Older snapshots store only the aggregate hash, so they cannot identify
        # the exact changed fixture. Report all inputs rather than claiming a match.
        return False, list(fixtures)

    def run_replay(
        self,
        snapshot_id: str,
        fixtures: dict[str, Path],
        cases: list[EvalCase],
        expected_map: dict[str, EvalExpectedResult] | None = None,
    ) -> EvalRun:
        """Run evaluation against a verified snapshot.

        Fails fast if fixture hashes don't match.
        """
        snapshot = self.load_snapshot(snapshot_id)
        if snapshot:
            ok, _ = self.verify_snapshot(snapshot, fixtures)
            if not ok:
                # Create a failed run rather than silently continuing
                run = EvalRun(
                    run_id=f"replay-{snapshot_id}-FAILED",
                    candidate_id="replay",
                    baseline_id=snapshot_id,
                    model_name="replay",
                    agent_version="replay",
                    repository_commit="unknown",
                    policy_version=self.runner.policy.version,
                    status="FAILED",
                )
                return run

        return self.runner.run_suite(
            cases,
            candidate_id="replay",
            baseline_id=snapshot_id,
            model_name="replay",
            agent_version="replay",
            expected_map=expected_map,
            fixture_hashes={
                fid: hash_fixture(fpath)
                for fid, fpath in fixtures.items()
            },
        )

    def replay_deterministic(
        self,
        cases: list[EvalCase],
        expected_map: dict[str, EvalExpectedResult] | None = None,
        run_count: int = 3,
    ) -> dict[str, list[str]]:
        """Run the same cases multiple times and collect verdict variance.

        Returns a mapping of case_id -> list of verdicts across runs.
        """
        variance: dict[str, list[str]] = {
            c.case_id: [] for c in cases
        }

        for _ in range(run_count):
            run = self.runner.run_suite(
                cases,
                candidate_id="deterministic-replay",
                baseline_id="deterministic-replay",
                model_name="deterministic",
                expected_map=expected_map,
            )
            for result in run.results:
                variance[result.case_id].append(result.overall)

        return variance

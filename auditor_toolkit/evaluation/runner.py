"""Evaluation runner — orchestrates case execution, grading, and result aggregation.

Supports frozen fixtures, golden corpus cases, recorded evidence snapshots,
and browser fixture sites.  Captures agent output, claims, evidence selected,
tool calls, tool arguments, screenshots, browser trace, console output,
network activity, runtime, memory, and candidate configuration.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from .graders import run_all_graders
from .policy import DEFAULT_POLICY, EvalPolicy
from .schema import (
    EvalCase,
    EvalExpectedResult,
    EvalMetrics,
    EvalResult,
    EvalRun,
)


class EvalRunner:
    """Runs evaluation cases through an agent adapter and grades results."""

    def __init__(
        self,
        adapter,
        policy: EvalPolicy = DEFAULT_POLICY,
        grader_names: list[str] | None = None,
        output_dir: Path | None = None,
    ):
        self.adapter = adapter
        self.policy = policy
        self.grader_names = grader_names
        self.output_dir = output_dir

    def run_case(
        self,
        case: EvalCase,
        run_id: str,
        expected: EvalExpectedResult | None = None,
    ) -> EvalResult:
        """Execute a single evaluation case and grade the result."""
        # Execute agent
        try:
            result = self.adapter.run(case, run_id=run_id)
        except Exception as exc:
            result = EvalResult(
                case_id=case.case_id,
                run_id=run_id,
                overall="FAIL",
                agent_output=f"RUNNER_ERROR: {exc}",
            )
            result.add_grader("JSON_VALIDITY", "FAIL")

        # Grade with deterministic graders
        run_all_graders(
            result, case, expected, self.policy, self.grader_names
        )
        return result

    def run_suite(
        self,
        cases: list[EvalCase],
        candidate_id: str = "",
        baseline_id: str = "",
        model_name: str = "local",
        agent_version: str = "",
        expected_map: dict[str, EvalExpectedResult] | None = None,
        fixture_hashes: dict[str, str] | None = None,
    ) -> EvalRun:
        """Run a full evaluation suite and return an EvalRun."""
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        run = EvalRun(
            run_id=run_id,
            candidate_id=candidate_id or "candidate",
            baseline_id=baseline_id or "baseline",
            model_name=model_name,
            agent_version=agent_version or "unknown",
            repository_commit=_current_commit(),
            policy_version=self.policy.version,
            started_at=_now_iso(),
            fixture_hashes=fixture_hashes or {},
            tool_versions=_tool_versions(),
        )

        for case in cases:
            expected = (expected_map or {}).get(case.case_id)
            result = self.run_case(case, run_id, expected)
            run.add_result(result)

        run.finished_at = _now_iso()
        run.status = "COMPLETE"
        return run

    def compute_metrics(self, run: EvalRun) -> EvalMetrics:
        """Compute aggregated metrics from an EvalRun."""
        metrics = EvalMetrics(run_id=run.run_id)
        metrics.total_cases = run.total
        metrics.pass_count = run.pass_count
        metrics.fail_count = run.fail_count
        metrics.abstain_count = sum(
            1 for r in run.results if r.overall == "ABSTAIN"
        )
        metrics.na_count = sum(
            1 for r in run.results if r.overall == "N/A"
        )

        if metrics.total_cases > 0:
            metrics.completion_rate = metrics.pass_count / metrics.total_cases

        # Compute detailed metrics from results
        total_claims = 0
        supported_claims = 0
        unsupported_claims = 0
        correct_abstentions = 0
        incorrect_abstentions = 0
        total_duration = 0

        for result in run.results:
            total_claims += len(result.claims)
            total_duration += result.duration_ms

            # Unsupported claims
            for claim in result.claims:
                if claim.get("evidence_id") or claim.get("finding_id"):
                    supported_claims += 1
                else:
                    unsupported_claims += 1

            # Abstention analysis
            if not result.claims and result.evidence_selected:
                correct_abstentions += 1
            elif not result.claims and not result.evidence_selected:
                incorrect_abstentions += 1

        if total_claims > 0:
            metrics.unsupported_claim_rate = unsupported_claims / total_claims

        total_abstentions = correct_abstentions + incorrect_abstentions
        if total_abstentions > 0:
            metrics.correct_abstention_rate = (
                correct_abstentions / total_abstentions
            )
            metrics.incorrect_abstention_rate = (
                incorrect_abstentions / total_abstentions
            )

        if metrics.total_cases > 0:
            metrics.avg_latency_ms = total_duration / metrics.total_cases

        # Count failures by type
        for result in run.results:
            for failure in result.failures:
                if failure.failure_class == "GOLDEN_CORPUS_REGRESSION":
                    metrics.golden_corpus_retention = max(
                        0, metrics.golden_corpus_retention - 0.01
                    )
                if failure.failure_class == "FORBIDDEN_ACTION":
                    metrics.prohibited_action_count += 1
                if failure.failure_class == "TOOL_POLICY_VIOLATION":
                    metrics.tool_policy_violation_count += 1

        return metrics

    def save_run(self, run: EvalRun, metrics: EvalMetrics) -> Path | None:
        """Persist run artifacts to the output directory."""
        if not self.output_dir:
            return None

        run_dir = self.output_dir / run.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # manifest.json
        (run_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "run_id": run.run_id,
                    "candidate_id": run.candidate_id,
                    "model_name": run.model_name,
                    "agent_version": run.agent_version,
                    "policy_version": run.policy_version,
                    "started_at": run.started_at,
                    "finished_at": run.finished_at,
                    "total_cases": run.total,
                    "status": run.status,
                },
                indent=2,
            )
        )

        # results.json
        (run_dir / "results.json").write_text(
            json.dumps([r.to_dict() for r in run.results], indent=2)
        )

        # metrics.json
        (run_dir / "metrics.json").write_text(
            json.dumps(metrics.to_dict(), indent=2)
        )

        # failures.json
        all_failures = []
        for r in run.results:
            for f in r.failures:
                all_failures.append(
                    {
                        "case_id": r.case_id,
                        "failure_class": f.failure_class,
                        "grader": f.grader,
                        "message": f.message,
                        "severity": f.severity,
                    }
                )
        (run_dir / "failures.json").write_text(
            json.dumps(all_failures, indent=2)
        )

        # tool_calls.jsonl
        with (run_dir / "tool_calls.jsonl").open("w") as f:
            for r in run.results:
                for tc in r.tool_calls:
                    f.write(
                        json.dumps(
                            {
                                "case_id": r.case_id,
                                "tool_name": tc.tool_name,
                                "args": tc.args,
                                "blocked": tc.blocked,
                                "block_reason": tc.block_reason,
                            }
                        )
                        + "\n"
                    )

        return run_dir


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def _current_commit() -> str:
    """Try to read the current git commit."""
    import subprocess

    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"


def _tool_versions() -> dict[str, str]:
    """Record versions of key evaluation dependencies."""
    versions: dict[str, str] = {}
    try:
        import playwright

        versions["playwright"] = getattr(playwright, "__version__", "unknown")
    except ImportError:
        pass

    try:
        import inspect_ai

        versions["inspect_ai"] = getattr(inspect_ai, "__version__", "unknown")
    except ImportError:
        pass

    try:
        versions["python"] = f"{__import__('sys').version_info.major}.{__import__('sys').version_info.minor}.{__import__('sys').version_info.micro}"
    except Exception:
        pass

    return versions


def hash_fixture(path: Path) -> str:
    """Compute SHA-256 hash of a fixture file for replay verification."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_fixture_content(content: str) -> str:
    """Compute SHA-256 hash of fixture content string."""
    return hashlib.sha256(content.encode()).hexdigest()

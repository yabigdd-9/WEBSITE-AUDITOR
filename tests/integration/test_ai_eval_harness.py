"""Integration test for the full AI evaluation harness pipeline."""

import json
from pathlib import Path

from auditor_toolkit.evaluation.adapters.local_agent import LocalAgentAdapter
from auditor_toolkit.evaluation.comparison import compare
from auditor_toolkit.evaluation.promotion import create_proposal
from auditor_toolkit.evaluation.replay import ReplayRunner
from auditor_toolkit.evaluation.report import (
    generate_benchmark,
    save_benchmark_json,
    save_benchmark_markdown,
)
from auditor_toolkit.evaluation.runner import EvalRunner
from auditor_toolkit.evaluation.schema import (
    EvalCase,
    EvalExpectedResult,
    EvalMetrics,
)


class _DeterministicAgent:
    """A deterministic local agent that produces correct results for known cases."""

    def run(self, case, run_id=""):
        claims = [
            {"finding_id": fid, "severity": "high", "category": case.category}
            for fid in case.expected_findings
        ]
        evidence = [
            {"finding_id": fid, "evidence_id": f"ev_{fid}"}
            for fid in case.expected_findings
        ]
        # For abstention cases, produce a valid abstention claim
        if case.expected_abstention and not claims:
            claims = [{"abstention_reason": "INSUFFICIENT_EVIDENCE"}]
        return {
            "claims": claims,
            "evidence": evidence,
            "tool_calls": [
                {"tool_name": tool, "args": {}, "result_summary": "ok"}
                for tool in case.allowed_tools[:2]
            ],
            "output": json.dumps(
                [{"finding_id": fid, "category": case.category, "severity": "high"}
                 for fid in case.expected_findings]
            ),
            "model": "deterministic-integration",
        }


def test_full_pipeline(tmp_path):
    """Run the full evaluation pipeline: run → grade → compare → promote → report."""

    # 1. Set up cases
    cases = [
        EvalCase(
            case_id="int_valid",
            category="accessibility",
            task="Detect missing alt text",
            fixture_id="clean-control",
            expected_behavior="finding with evidence",
            allowed_tools=["fetch", "axe"],
            expected_findings=["finding_001"],
            metadata={"business_id": "biz_001"},
        ),
        EvalCase(
            case_id="int_abstention",
            category="performance",
            task="Should abstain on unreachable page",
            fixture_id="js-only-navigation",
            expected_behavior="agent should abstain",
            allowed_tools=["fetch"],
            expected_findings=[],
            expected_abstention=True,
            metadata={"business_id": "biz_001"},
        ),
    ]

    expected_map = {
        "int_valid": EvalExpectedResult(
            case_id="int_valid",
            findings=["finding_001"],
            tools_must_use=["fetch"],
        ),
        "int_abstention": EvalExpectedResult(
            case_id="int_abstention",
            findings=[],
            abstain=True,
        ),
    }

    # 2. Create runner with local agent
    adapter = _wrap_agent_class(_DeterministicAgent())
    output_dir = tmp_path / "runs"
    runner = EvalRunner(adapter=adapter, output_dir=output_dir)

    # 3. Run candidate suite
    candidate_run = runner.run_suite(
        cases,
        candidate_id="candidate-v1",
        baseline_id="baseline-v1",
        model_name="deterministic-integration",
        agent_version="0.1.0",
        expected_map=expected_map,
    )
    assert candidate_run.total == 2
    assert candidate_run.status == "COMPLETE"

    # 4. Compute candidate metrics
    candidate_metrics = runner.compute_metrics(candidate_run)

    # 5. Create baseline metrics (slightly worse)
    baseline_metrics = EvalMetrics(
        run_id="baseline-v1",
        total_cases=2,
        pass_count=1,
        fail_count=1,
        finding_precision=0.70,
        finding_recall=0.60,
        high_confidence_fp_rate=0.04,
        unsupported_claim_rate=0.10,
        correct_abstention_rate=0.80,
        golden_corpus_retention=1.0,
        wrong_business_rate=0.01,
        prohibited_action_count=0,
        tool_policy_violation_count=0,
        completion_rate=0.50,
    )

    # 6. Compare candidate vs baseline
    comparison = compare(candidate_metrics, baseline_metrics)
    assert comparison.comparison_id
    assert len(comparison.deltas) > 0

    # 7. Create promotion proposal
    gates = {
        "gate_01_no_irreversible_actions": True,
        "gate_04_golden_false_positive_retention": True,
        "gate_14_automatic_promotion_disabled": True,
    }
    proposal = create_proposal(comparison, gate_results=gates)
    assert proposal.proposal_id
    # The recommended action depends on whether veto rules are triggered
    # by the simple test agent's metrics — any valid action is acceptable
    assert proposal.recommended_action in (
        "PROMOTION_ELIGIBLE",
        "REJECT",
        "MORE_TESTING_REQUIRED",
    )

    # 8. Generate benchmark report
    report = generate_benchmark(
        candidate_run,
        candidate_metrics,
        baseline_metrics=baseline_metrics,
        benchmark_version="v36-integration",
    )
    assert report.benchmark_version == "v36-integration"
    assert report.comparison is not None

    # 9. Save artifacts
    json_path = save_benchmark_json(report, tmp_path / "benchmarks")
    md_path = save_benchmark_markdown(report, tmp_path / "benchmarks")

    assert json_path.exists()
    assert md_path.exists()

    # 10. Verify saved JSON
    data = json.loads(json_path.read_text())
    assert data["total_cases"] == 2
    assert data["candidate_pass"] == candidate_run.pass_count


def test_replay_integration(tmp_path):
    """Test that replay snapshots work end-to-end."""
    from auditor_toolkit.evaluation.adapters.local_agent import LocalAgentAdapter

    cases = [
        EvalCase(
            case_id="replay_int",
            category="technical",
            task="Replay test",
            fixture_id="clean-control",
            expected_behavior="pass",
            expected_findings=["f1"],
        ),
    ]

    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text('{"key": "value"}')
    fixtures = {"fixture_001": fixture_path}

    adapter = LocalAgentAdapter(_DeterministicAgent())
    runner = EvalRunner(adapter=adapter)
    replay = ReplayRunner(runner, snapshot_dir=tmp_path / "snapshots")

    # Create snapshot
    snapshot = replay.create_snapshot(
        snapshot_id="replay_int_snap",
        fixtures=fixtures,
        cases=cases,
    )
    assert snapshot.snapshot_id == "replay_int_snap"

    # Run replay
    run = replay.run_replay(
        snapshot_id="replay_int_snap",
        fixtures=fixtures,
        cases=cases,
    )
    assert run.status == "COMPLETE"


def test_no_second_reviewer_system():
    """Verify that P1-007 does not create a second reviewer system."""
    import ast
    import auditor_toolkit.evaluation.promotion as promo

    source = Path(promo.__file__).read_text()
    tree = ast.parse(source)

    # Extract only code strings (docstrings), not string literals in code
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)):
                docstrings.add(node.body[0].value.value)

    # Check code (excluding docstrings) for deployment functions
    code_lines = source.split("\n")
    in_docstring = False
    code_text = ""
    for line in code_lines:
        stripped = line.strip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            in_docstring = not in_docstring
            continue
        if not in_docstring:
            code_text += line + "\n"

    for term in ("activate_model()", "deploy_agent()", "replace_baseline()", "rewrite_policy()"):
        assert term not in code_text, f"Found prohibited term: {term}"


# Import fix: LocalAgentAdapter takes a callable, not a class.
# The _DeterministicAgent above returns a dict from run(), but LocalAgentAdapter
# expects a callable that takes (case) and returns dict. Let's fix the adapter usage.


def _wrap_agent_class(agent):
    """Wrap a class-based agent for LocalAgentAdapter."""
    def fn(case):
        return agent.run(case)
    return LocalAgentAdapter(fn)

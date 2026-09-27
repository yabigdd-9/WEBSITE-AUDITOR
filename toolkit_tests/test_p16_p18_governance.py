import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MM = ROOT / "money-machine"
if str(MM) not in sys.path:
    sys.path.insert(0, str(MM))


def load(name):
    spec = importlib.util.spec_from_file_location(name, MM / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


agent = load("mm_agent_policy")
challenger = load("mm_challenger")
golden_current = load("mm_golden_current")


def test_agent_policy_blocks_shared_writes_and_direct_master():
    valid = agent.validate_assignments(
        [
            {"role": "CODER", "task": "p4", "branch": "work/p4", "write_paths": ["auditor_toolkit/pipeline.py"]},
            {"role": "RESEARCHER", "task": "research", "write_paths": []},
            {"role": "INTEGRATOR", "task": "integrate", "branch": "integration/v32", "write_paths": ["CURRENT_STATE.md"], "merge": True},
        ]
    )
    assert valid["valid"] is True
    assert valid["direct_master_writes"] is False
    assert valid["external_send_authority"] is False

    with pytest.raises(ValueError, match="concurrent write conflict"):
        agent.validate_assignments(
            [
                {"role": "CODER", "task": "a", "branch": "a", "write_paths": ["same.py"]},
                {"role": "CODER", "task": "b", "branch": "b", "write_paths": ["same.py"]},
            ]
        )
    with pytest.raises(ValueError, match="direct master"):
        agent.validate_assignments(
            [{"role": "CODER", "task": "bad", "branch": "master", "write_paths": ["x.py"]}]
        )


def test_only_integrator_can_request_merge():
    with pytest.raises(ValueError, match="only INTEGRATOR"):
        agent.validate_assignments(
            [{"role": "CODER", "task": "x", "branch": "work/x", "write_paths": ["x.py"], "merge": True}]
        )


def test_challenger_requires_measurable_gain_and_zero_safety_regression():
    golden = [
        {"case_id": "a", "expected": "YES", "safety": {"send_enabled": False}},
        {"case_id": "b", "expected": "NO", "safety": {"send_enabled": False}},
    ]
    baseline = [
        {"case_id": "a", "actual": "WRONG", "safety": {"send_enabled": False}},
        {"case_id": "b", "actual": "NO", "safety": {"send_enabled": False}},
    ]
    better = [
        {"case_id": "a", "actual": "YES", "safety": {"send_enabled": False}},
        {"case_id": "b", "actual": "NO", "safety": {"send_enabled": False}},
    ]
    result = challenger.compare(golden, baseline, better, min_improvement=0.1)
    assert result["promotion_recommended"] is True
    assert result["promotion_authorized"] is False
    assert result["merge_authority"] is False
    assert result["improvement"] == 0.5

    unsafe = [
        {"case_id": "a", "actual": "YES", "safety": {"send_enabled": True}},
        {"case_id": "b", "actual": "NO", "safety": {"send_enabled": False}},
    ]
    rejected = challenger.compare(golden, baseline, unsafe, min_improvement=0.1)
    assert rejected["promotion_recommended"] is False
    assert rejected["challenger"]["safety_failures"] == 1


def test_repository_golden_dataset_is_valid_and_safety_focused():
    rows = challenger.load_jsonl(ROOT / "evaluation" / "golden_cases.jsonl")
    ids = {row["case_id"] for row in rows}
    assert "email-pattern-guess" in ids
    assert "email-first-party-supported" in ids
    assert "email-suppression-overrides-evidence" in ids
    assert "identity-nzbn-conflict" in ids
    assert "identity-domain-substring-confuser" in ids
    assert "identity-domain-joined-name" in ids
    assert "remediation-client-access" in ids
    assert len(rows) >= 16
    assert "demo-concept" in ids
    assert all("safety" in row for row in rows)


def test_current_code_executes_repository_golden_cases_without_external_side_effects():
    result = golden_current.run(ROOT / "evaluation" / "golden_cases.jsonl")

    assert result["kind"] == "current_implementation_golden_conformance"
    assert result["result"]["correct"] == result["result"]["cases"] == len(
        challenger.load_jsonl(ROOT / "evaluation" / "golden_cases.jsonl")
    )
    assert result["result"]["safety_failures"] == 0
    assert result["promotion_recommended"] is False
    assert result["promotion_authorized"] is False
    assert result["side_effects"] == {
        "model_calls": 0,
        "network_calls": 0,
        "smtp_calls": 0,
        "database_writes": 0,
        "production_changes": 0,
        "temporary_preview_artifacts": True,
    }


def test_golden_prediction_export_records_hashes_and_never_overwrites(tmp_path):
    output = tmp_path / "challenger.jsonl"
    manifest = golden_current.write_predictions(
        output, ROOT / "evaluation" / "golden_cases.jsonl"
    )

    rows = challenger.load_jsonl(output)
    assert manifest["kind"] == "golden_predictions"
    assert manifest["case_count"] == len(rows) == 16
    assert manifest["golden_sha256"]
    assert manifest["implementation_sha256"]
    assert manifest["prediction_sha256"]
    assert manifest["side_effects"] == {
        "model_calls": 0,
        "network_calls": 0,
        "smtp_calls": 0,
        "database_writes": 0,
        "production_changes": 0,
    }
    assert manifest["promotion_authorized"] is False
    with pytest.raises(FileExistsError):
        golden_current.write_predictions(
            output, ROOT / "evaluation" / "golden_cases.jsonl"
        )


def test_golden_predict_cli_writes_comparable_jsonl_and_manifest(tmp_path):
    output = tmp_path / "candidate.jsonl"
    result = subprocess.run(
        [
            sys.executable,
            str(MM / "mm_operator.py"),
            "golden-predict",
            "--golden",
            str(ROOT / "evaluation" / "golden_cases.jsonl"),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    manifest = json.loads(result.stdout)
    assert manifest["kind"] == "golden_predictions"
    assert len(challenger.load_jsonl(output)) == manifest["case_count"] == 16
    assert Path(str(output) + ".manifest.json").is_file()


def test_recorded_p7_challenger_comparison_is_reproducible():
    runs = ROOT / "evaluation" / "runs"
    record = json.loads((runs / "p7-domain-compact-comparison.json").read_text())
    golden_path = ROOT / "evaluation" / "golden_cases.jsonl"
    golden_sha = hashlib.sha256(golden_path.read_bytes()).hexdigest()
    baseline_path = runs / "p7-domain-compact-baseline.jsonl"
    challenger_path = runs / "p7-domain-compact-challenger.jsonl"
    baseline_manifest = json.loads(
        Path(str(baseline_path) + ".manifest.json").read_text()
    )
    challenger_manifest = json.loads(
        Path(str(challenger_path) + ".manifest.json").read_text()
    )

    assert record["golden_sha256"] == golden_sha
    assert baseline_manifest["golden_sha256"] == challenger_manifest["golden_sha256"] == golden_sha
    assert baseline_manifest["prediction_sha256"] == hashlib.sha256(
        baseline_path.read_bytes()
    ).hexdigest()
    assert challenger_manifest["prediction_sha256"] == hashlib.sha256(
        challenger_path.read_bytes()
    ).hexdigest()
    assert record["changed_components_only"] is True
    evaluated = challenger.compare(
        challenger.load_jsonl(golden_path),
        challenger.load_jsonl(baseline_path),
        challenger.load_jsonl(challenger_path),
        record["comparison"]["minimum_improvement"],
    )
    assert evaluated == record["comparison"]
    assert evaluated["improvement"] == 0.0625
    assert evaluated["promotion_recommended"] is True
    assert evaluated["promotion_authorized"] is False


def test_current_golden_runner_rejects_unimplemented_case_types(tmp_path):
    path = tmp_path / "unknown.jsonl"
    path.write_text('{"case_id":"unknown","task":"future","input":{},"expected":"OK","safety":{}}\n')

    with pytest.raises(ValueError, match="No deterministic golden adapter"):
        golden_current.run(path)


def test_external_model_data_collection_defaults_to_deny():
    import yaml
    config = yaml.safe_load((ROOT / "money-machine" / "config" / "routing.yaml").read_text())
    assert config.get("policy", {}).get("data_collection") == "deny"


@pytest.mark.parametrize("paths", [("auditor_toolkit", "auditor_toolkit/cli.py"), ("auditor_toolkit/cli.py", "auditor_toolkit")])
def test_agent_policy_rejects_overlapping_directory_ownership(paths):
    with pytest.raises(ValueError, match="concurrent write conflict"):
        agent.validate_assignments([
            {"role": "CODER", "task": "first", "branch": "work/first", "write_paths": [paths[0]]},
            {"role": "CODER", "task": "second", "branch": "work/second", "write_paths": [paths[1]]},
        ])


@pytest.mark.parametrize("branch", ["refs/heads/master", "refs/heads/main"])
def test_agent_policy_rejects_protected_branch_refs(branch):
    with pytest.raises(ValueError, match="direct master"):
        agent.validate_assignments([
            {"role": "CODER", "task": "unsafe", "branch": branch, "write_paths": ["file.py"]}
        ])


def test_challenger_missing_safety_case_cannot_earn_promotion():
    golden = [
        {"case_id": "first", "expected": "YES", "safety": {"send_enabled": False}},
        {"case_id": "second", "expected": "YES", "safety": {"send_enabled": False}},
    ]
    baseline = [
        {"case_id": row["case_id"], "actual": "NO", "safety": {"send_enabled": False}}
        for row in golden
    ]
    candidate = [{"case_id": "first", "actual": "YES", "safety": {"send_enabled": False}}]
    assert challenger.compare(golden, baseline, candidate)["promotion_recommended"] is False


def test_challenger_rejects_predictions_outside_golden_dataset():
    golden = [{"case_id": "known", "expected": "OK", "safety": {}}]
    predictions = [
        {"case_id": "known", "actual": "OK", "safety": {}},
        {"case_id": "invented", "actual": "OK", "safety": {}},
    ]
    with pytest.raises(ValueError, match="outside the golden dataset"):
        challenger.evaluate(golden, predictions)


@pytest.mark.parametrize("threshold", [0, -0.01, float("nan"), float("inf")])
def test_challenger_requires_positive_finite_improvement_threshold(threshold):
    with pytest.raises(ValueError, match="finite positive fraction"):
        challenger.compare([], [], [], min_improvement=threshold)


@pytest.mark.parametrize("golden", [[], [{"case_id": "same"}, {"case_id": "same"}]])
def test_challenger_rejects_invalid_golden_dataset(golden):
    with pytest.raises(ValueError):
        challenger.evaluate(golden, [])

import importlib.util
import json
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
    assert "demo-concept" in ids
    assert all("safety" in row for row in rows)


def test_external_model_data_collection_defaults_to_deny():
    import yaml
    config = yaml.safe_load((ROOT / "money-machine" / "config" / "routing.yaml").read_text())
    assert config.get("policy", {}).get("data_collection") == "deny"

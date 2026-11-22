import json

from auditor_toolkit.schema_validation import (
    validate_agency_config,
    validate_all_configs,
    validate_master_plan,
)


def test_project_schema_reports_valid_and_missing_configs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "agency_config.json").write_text(json.dumps({
        "agency_name": "Fixture agency",
        "clients": [{"name": "Fixture client", "domain": "example.test"}],
    }))
    (tmp_path / ".env.example").write_text("# Example\nWA_PROFILE=default\n")

    valid, errors, agency = validate_agency_config("agency_config.json")
    assert valid and not errors
    assert agency.clients[0].active
    results = validate_all_configs()
    assert results["agency_config.json"]["valid"]
    assert results[".env.example"]["variable_count"] == 1
    assert not validate_master_plan("MASTER_PLAN.yaml")[0]


def test_schema_rejects_invalid_documents(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    plan = tmp_path / "MASTER_PLAN.yaml"
    plan.write_text("plan: [")
    assert "YAML parse error" in validate_master_plan(plan)[1][0]
    plan.write_text("{}")
    assert "plan" in validate_master_plan(plan)[1][0]

    agency = tmp_path / "agency_config.json"
    agency.write_text("{")
    assert "JSON parse error" in validate_agency_config(agency)[1][0]
    agency.write_text('{"agency_name": "Fixture", "settings": {"default_hourly_rate_nzd": -1}}')
    assert "default_hourly_rate_nzd" in validate_agency_config(agency)[1][0]


def test_schema_refuses_file_outside_workspace(tmp_path, monkeypatch):
    outside = tmp_path / "external.json"
    outside.write_text('{"agency_name": "External"}')
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "agency_config.json").symlink_to(outside)
    monkeypatch.chdir(workspace)

    valid, errors, result = validate_agency_config("agency_config.json")
    assert not valid and result is None
    assert "inside the current workspace" in errors[0]

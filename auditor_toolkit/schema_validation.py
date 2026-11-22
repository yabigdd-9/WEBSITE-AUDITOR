"""Schema validation for configuration files.

Provides validation for MASTER_PLAN.yaml, agency_config.json, and other
configuration files using JSON Schema / Pydantic models.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


# MASTER_PLAN.yaml schema
class MasterPlanPhase(BaseModel):
    """A single phase in the master plan."""

    name: str = Field(..., description="Phase name")
    priority: str = Field(default="", description="Phase priority")
    goal: str = Field(default="", description="Phase goal")
    gate: list[str] | str = Field(default_factory=list, description="Gate criteria")
    tasks: list[str] = Field(default_factory=list, description="Tasks in this phase")
    transport_enabled: bool | None = Field(default=None, description="Transport enabled")
    send_enabled: bool | None = Field(default=None, description="Send enabled")
    external_send_authorization: str | None = Field(default=None, description="Send authorization")
    rule: str | None = Field(default=None, description="Rule")
    route: list[str] | None = Field(default=None, description="Route")
    max_cost_usd: int | None = Field(default=None, description="Max cost")
    max_large_local_models_concurrent: int | None = Field(default=None, description="Max large models")
    preferred_small_local_models_concurrent: int | None = Field(default=None, description="Preferred small models")


class MasterPlanPlan(BaseModel):
    """Plan section of MASTER_PLAN.yaml."""

    name: str = Field(..., description="Plan name")
    version: str = Field(..., description="Plan version")
    status: str = Field(default="", description="Plan status")
    primary_workspace: str | None = Field(default=None, description="Primary workspace path")
    experimental_cline_workspace: str | None = Field(default=None, description="Experimental workspace")
    execution_mode: str = Field(default="", description="Execution mode")
    paid_allowed: bool = Field(default=False, description="Whether paid services allowed")
    max_cost_usd: int = Field(default=0, description="Maximum cost in USD")
    outreach_default_enabled: bool = Field(default=False, description="Outreach default enabled")
    destructive_actions_default_allowed: bool = Field(
        default=False, description="Destructive actions allowed"
    )


class MasterPlanNonNegotiables(BaseModel):
    """Non-negotiables section."""

    zero_cost: dict[str, Any] = Field(default_factory=dict)
    repository_safety: dict[str, Any] = Field(default_factory=dict)
    outreach_safety: dict[str, Any] = Field(default_factory=dict)
    production_change_policy: dict[str, Any] = Field(default_factory=dict)


class MasterPlanCanonicalDirection(BaseModel):
    """Canonical direction section."""

    repository: str = Field(default="", description="Canonical repository path")
    audit_engine: str = Field(default="", description="Audit engine")
    operator_cli: str = Field(default="", description="Operator CLI")
    operator_python_default: str = Field(default="", description="Default Python")
    python_override_rule: str = Field(default="", description="Python override rule")
    operator_entrypoint: str = Field(default="", description="Operator entrypoint")
    runtime_state: str = Field(default="", description="Runtime state")
    queue: str = Field(default="", description="Queue")
    supervisor: str = Field(default="", description="Supervisor")
    supervisor_package: str = Field(default="", description="Supervisor package")
    orchestrator: str = Field(default="", description="Orchestrator")
    human_workspace: str = Field(default="", description="Human workspace")
    obsidian_authoritative: bool = Field(default=False, description="Obsidian authoritative")
    n8n_default_runtime: bool = Field(default=False, description="N8n default runtime")
    optional_local_tools: dict[str, Any] = Field(default_factory=dict)
    deterministic_work_requires_model: bool = Field(default=False, description="Model required")


class MasterPlanYaml(BaseModel):
    """MASTER_PLAN.yaml structure."""

    plan: MasterPlanPlan = Field(..., description="Plan configuration")
    non_negotiables: MasterPlanNonNegotiables = Field(
        default_factory=MasterPlanNonNegotiables, description="Non-negotiables"
    )
    canonical_direction: MasterPlanCanonicalDirection = Field(
        default_factory=MasterPlanCanonicalDirection, description="Canonical direction"
    )
    phases: dict[str, MasterPlanPhase] = Field(
        default_factory=dict, description="Plan phases keyed by phase ID"
    )


# Agency config schema
class AgencyClient(BaseModel):
    """Agency client configuration."""

    name: str = Field(..., description="Client name")
    domain: str = Field(..., description="Client domain")
    contact_email: str | None = Field(default=None, description="Contact email")
    hourly_rate_nzd: float | None = Field(default=None, ge=0, description="Hourly rate in NZD")
    active: bool = Field(default=True, description="Whether client is active")


class AgencySettings(BaseModel):
    """Agency-wide settings."""

    default_hourly_rate_nzd: float = Field(default=150.0, ge=0, description="Default hourly rate")
    currency: str = Field(default="NZD", description="Currency code")
    timezone: str = Field(default="Pacific/Auckland", description="Timezone")


class AgencyConfig(BaseModel):
    """agency_config.json structure."""

    agency_name: str = Field(..., description="Agency name")
    settings: AgencySettings = Field(default_factory=AgencySettings)
    clients: list[AgencyClient] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def load_yaml_file(path: str | Path) -> dict[str, Any]:
    """Load a YAML file safely.

    Args:
        path: Path to YAML file.

    Returns:
        Parsed YAML content as dictionary.

    Raises:
        FileNotFoundError: If file doesn't exist.
        yaml.YAMLError: If YAML is invalid.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_json_file(path: str | Path) -> dict[str, Any]:
    """Load a JSON file safely.

    Args:
        path: Path to JSON file.

    Returns:
        Parsed JSON content as dictionary.

    Raises:
        FileNotFoundError: If file doesn't exist.
        json.JSONDecodeError: If JSON is invalid.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def validate_master_plan(path: str | Path) -> tuple[bool, list[str], MasterPlanYaml | None]:
    """Validate MASTER_PLAN.yaml against schema.

    Args:
        path: Path to MASTER_PLAN.yaml.

    Returns:
        Tuple of (is_valid, error_messages, parsed_model).
    """
    try:
        data = load_yaml_file(path)
        model = MasterPlanYaml(**data)
        return True, [], model
    except FileNotFoundError as e:
        return False, [str(e)], None
    except yaml.YAMLError as e:
        return False, [f"YAML parse error: {e}"], None
    except ValidationError as e:
        errors = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
        return False, errors, None
    except Exception as e:
        return False, [f"Unexpected error: {e}"], None


def validate_agency_config(path: str | Path) -> tuple[bool, list[str], AgencyConfig | None]:
    """Validate agency_config.json against schema.

    Args:
        path: Path to agency_config.json.

    Returns:
        Tuple of (is_valid, error_messages, parsed_model).
    """
    try:
        data = load_json_file(path)
        model = AgencyConfig(**data)
        return True, [], model
    except FileNotFoundError as e:
        return False, [str(e)], None
    except json.JSONDecodeError as e:
        return False, [f"JSON parse error: {e}"], None
    except ValidationError as e:
        errors = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
        return False, errors, None
    except Exception as e:
        return False, [f"Unexpected error: {e}"], None


def validate_all_configs(project_root: str | Path = ".") -> dict[str, Any]:
    """Validate all known configuration files in the project.

    Args:
        project_root: Root directory of the project.

    Returns:
        Dictionary with validation results for each config file.
    """
    project_root = Path(project_root)
    results = {}

    # MASTER_PLAN.yaml
    master_plan_path = project_root / "MASTER_PLAN.yaml"
    if master_plan_path.exists():
        valid, errors, model = validate_master_plan(master_plan_path)
        results["MASTER_PLAN.yaml"] = {
            "valid": valid,
            "errors": errors,
            "phase_count": len(model.phases) if model else 0,
        }
    else:
        results["MASTER_PLAN.yaml"] = {"valid": False, "errors": ["File not found"]}

    # agency_config.json (optional)
    agency_config_path = project_root / "agency_config.json"
    if agency_config_path.exists():
        valid, errors, model = validate_agency_config(agency_config_path)
        results["agency_config.json"] = {
            "valid": valid,
            "errors": errors,
            "client_count": len(model.clients) if model else 0,
        }
    else:
        results["agency_config.json"] = {
            "valid": True,
            "errors": [],
            "optional": True,
            "note": "File not found (optional)",
        }

    # .env.example (check it exists and has basic structure)
    env_example_path = project_root / ".env.example"
    if env_example_path.exists():
        try:
            content = env_example_path.read_text()
            lines = [l.strip() for l in content.splitlines() if l.strip() and not l.startswith("#")]
            results[".env.example"] = {
                "valid": True,
                "errors": [],
                "variable_count": len(lines),
            }
        except Exception as e:
            results[".env.example"] = {"valid": False, "errors": [str(e)]}
    else:
        results[".env.example"] = {"valid": False, "errors": ["File not found"]}

    # Overall validity (exclude optional files)
    required_files = [k for k, v in results.items() if not v.get("optional", False)]
    all_valid = all(results[k].get("valid", False) for k in required_files)
    results["_summary"] = {
        "all_valid": all_valid,
        "total_files": len(results),
        "valid_files": sum(1 for r in results.values() if r.get("valid", False)),
        "required_files": len(required_files),
    }

    return results


# CLI entry point
def main() -> int:
    """Validate all configs and print results."""
    import json
    import sys

    project_root = Path.cwd()
    results = validate_all_configs(project_root)
    print(json.dumps(results, indent=2))
    return 0 if results["_summary"]["all_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
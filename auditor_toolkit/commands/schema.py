"""Schema command implementation."""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path

from auditor_toolkit.schema_validation import (
    validate_agency_config,
    validate_all_configs,
    validate_master_plan,
)

from .base import Command, register_command


class SchemaCommand(Command):
    """Validate configuration file schemas."""

    name = "schema"
    help = "Validate configuration file schemas"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "action",
            choices=["validate"],
            help="Validate configuration file schemas",
        )
        parser.add_argument(
            "--file",
            type=Path,
            help="Specific file to validate (master_plan, agency_config, or path)",
        )

    def execute(self, args: Namespace) -> int:
        import json
        if args.file:
            file_str = str(args.file)
            if file_str in ("master_plan", "MASTER_PLAN.yaml"):
                valid, errors, _ = validate_master_plan("MASTER_PLAN.yaml")
                result = {"file": "MASTER_PLAN.yaml", "valid": valid, "errors": errors}
            elif file_str in ("agency_config", "agency_config.json"):
                valid, errors, _ = validate_agency_config("agency_config.json")
                result = {"file": "agency_config.json", "valid": valid, "errors": errors}
            else:
                path = Path(file_str)
                if path.suffix in (".yaml", ".yml"):
                    valid, errors, _ = validate_master_plan(path)
                    result = {"file": file_str, "valid": valid, "errors": errors}
                elif path.suffix == ".json":
                    valid, errors, _ = validate_agency_config(path)
                    result = {"file": file_str, "valid": valid, "errors": errors}
                else:
                    print(json.dumps({"error": f"Unknown file type: {file_str}"}, indent=2))
                    return 1
            print(json.dumps(result, indent=2))
            return 0 if result["valid"] else 1
        else:
            results = validate_all_configs()
            print(json.dumps(results, indent=2))
            return 0 if results["_summary"]["all_valid"] else 1


register_command(SchemaCommand())

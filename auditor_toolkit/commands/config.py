"""Config command implementation."""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path

from auditor_toolkit.config import get_settings, validate_startup

from .base import Command, register_command


class ConfigCommand(Command):
    """Validate or show configuration."""

    name = "config"
    help = "Validate configuration or show current settings"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "action",
            choices=["validate", "show"],
            help="Validate configuration or show current settings",
        )

    def execute(self, args: Namespace) -> int:
        def _serialize(obj):
            if isinstance(obj, Path):
                return str(obj)
            if isinstance(obj, dict):
                return {k: _serialize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_serialize(v) for v in obj]
            return obj

        import json
        if args.action == "validate":
            result = validate_startup()
            print(json.dumps(_serialize(result), indent=2))
            return 0 if result["valid"] else 1
        elif args.action == "show":
            settings = get_settings()
            data = _serialize(settings.model_dump())
            for key in ["pagespeed_api_key", "alert_webhook_url"]:
                if key in data and data[key]:
                    data[key] = "***"
            print(json.dumps(data, indent=2))
            return 0
        return 1


register_command(ConfigCommand())

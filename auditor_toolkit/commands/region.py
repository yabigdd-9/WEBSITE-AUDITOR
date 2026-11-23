"""Region management CLI commands for multi-region portal support."""

from __future__ import annotations

import getpass
import json
from argparse import ArgumentParser, Namespace
from pathlib import Path

from auditor_toolkit.common import atomic_write_json
from auditor_toolkit.portal import setup_password

from .base import Command, register_command


class RegionCommand(Command):
    """Manage multi-region portal configurations."""

    name = "region"
    help = "Manage multi-region portal configurations"

    def add_arguments(self, parser: ArgumentParser) -> None:
        sub = parser.add_subparsers(dest="region_command", required=True)

        # list subcommand
        list_parser = sub.add_parser("list", help="List all configured regions")
        list_parser.add_argument("--output-root", default="outputs/toolkit", type=Path)

        # create subcommand
        create_parser = sub.add_parser("create", help="Create a new region")
        create_parser.add_argument("--output-root", default="outputs/toolkit", type=Path)
        create_parser.add_argument("--region", required=True, help="Region identifier")
        create_parser.add_argument("--password", help="Portal password (will prompt if not provided)")
        create_parser.add_argument("--config", type=Path, help="Region-specific configuration JSON")

        # config subcommand
        config_parser = sub.add_parser("config", help="View or update region configuration")
        config_parser.add_argument("--output-root", default="outputs/toolkit", type=Path)
        config_parser.add_argument("--region", required=True, help="Region identifier")
        config_parser.add_argument("--set", type=Path, help="JSON file with configuration to set")
        config_parser.add_argument("--show", action="store_true", help="Show current configuration")

        # delete subcommand
        delete_parser = sub.add_parser("delete", help="Delete a region")
        delete_parser.add_argument("--output-root", default="outputs/toolkit", type=Path)
        delete_parser.add_argument("--region", required=True, help="Region identifier")
        delete_parser.add_argument("--force", action="store_true", help="Skip confirmation")

    def execute(self, args: Namespace) -> int:
        if args.region_command == "list":
            return self._cmd_list(args)
        elif args.region_command == "create":
            return self._cmd_create(args)
        elif args.region_command == "config":
            return self._cmd_config(args)
        elif args.region_command == "delete":
            return self._cmd_delete(args)
        return 1

    def _cmd_list(self, args: Namespace) -> int:
        output_root = args.output_root.resolve()
        regions_dir = output_root / "regions"

        if not regions_dir.is_dir():
            print("No regions configured (single-region mode)")
            return 0

        regions = []
        for region_dir in regions_dir.iterdir():
            if region_dir.is_dir():
                auth_file = region_dir / "portal-auth.json"
                config_file = region_dir / "region-config.json"
                has_auth = auth_file.is_file()
                has_config = config_file.is_file()
                regions.append({
                    "name": region_dir.name,
                    "auth_configured": has_auth,
                    "config_configured": has_config,
                })

        if not regions:
            print("No regions configured")
            return 0

        print("Configured regions:")
        for r in sorted(regions, key=lambda x: x["name"]):
            status = []
            if r["auth_configured"]:
                status.append("auth")
            if r["config_configured"]:
                status.append("config")
            print(f"  {r['name']} [{', '.join(status) if status else 'empty'}]")
        return 0

    def _cmd_create(self, args: Namespace) -> int:
        output_root = args.output_root.resolve()
        regions_dir = output_root / "regions"
        region_dir = regions_dir / args.region

        if region_dir.exists():
            print(f"Region '{args.region}' already exists")
            return 1

        region_dir.mkdir(parents=True, exist_ok=True)

        # Set password
        password = args.password or getpass.getpass(f"Portal password for region '{args.region}' (12+ characters): ")
        setup_password(region_dir, password)

        # Write config if provided
        if args.config:
            config = json.loads(args.config.read_text())
            atomic_write_json(region_dir / "region-config.json", config)
            print(f"Applied region configuration from {args.config}")

        print(f"Created region '{args.region}' at {region_dir}")
        print("Run 'wa dashboard --region {args.region}' to serve")
        return 0

    def _cmd_config(self, args: Namespace) -> int:
        output_root = args.output_root.resolve()
        region_dir = output_root / "regions" / args.region
        config_file = region_dir / "region-config.json"

        if not region_dir.is_dir():
            print(f"Region '{args.region}' does not exist")
            return 1

        if args.set:
            config = json.loads(args.set.read_text())
            atomic_write_json(config_file, config)
            print(f"Updated region '{args.region}' configuration")
            return 0

        if args.show or not args.set:
            if config_file.is_file():
                config = json.loads(config_file.read_text())
                print(json.dumps(config, indent=2))
            else:
                print(f"No configuration file for region '{args.region}'")
            return 0

        return 0

    def _cmd_delete(self, args: Namespace) -> int:
        output_root = args.output_root.resolve()
        region_dir = output_root / "regions" / args.region

        if not region_dir.is_dir():
            print(f"Region '{args.region}' does not exist")
            return 1

        if not args.force:
            confirm = input(f"Delete region '{args.region}'? This cannot be undone. (yes/no): ")
            if confirm.lower() != "yes":
                print("Cancelled")
                return 1

        import shutil
        shutil.rmtree(region_dir)
        print(f"Deleted region '{args.region}'")
        return 0


register_command(RegionCommand())

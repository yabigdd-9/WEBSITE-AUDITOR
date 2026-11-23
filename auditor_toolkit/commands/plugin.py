"""Plugin management CLI commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .base import Command, register_command
from auditor_toolkit.plugins import (
    get_registry,
    load_plugins_from_directory,
    load_plugins_from_entry_points,
)


class PluginCommand(Command):
    """Manage check plugins."""

    name = "plugin"
    help = "Manage audit check plugins"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        sub = parser.add_subparsers(dest="plugin_command", required=True)

        # list subcommand
        list_parser = sub.add_parser("list", help="List all registered plugins")
        list_parser.add_argument(
            "--category",
            help="Filter by category",
        )
        list_parser.add_argument(
            "--enabled-only",
            action="store_true",
            help="Show only enabled plugins",
        )
        list_parser.add_argument(
            "--json",
            action="store_true",
            help="Output as JSON",
        )

        # enable subcommand
        enable_parser = sub.add_parser("enable", help="Enable a plugin")
        enable_parser.add_argument("plugin_id", help="Plugin ID to enable")

        # disable subcommand
        disable_parser = sub.add_parser("disable", help="Disable a plugin")
        disable_parser.add_argument("plugin_id", help="Plugin ID to disable")

        # load-entry-points subcommand
        ep_parser = sub.add_parser("load-entry-points", help="Load plugins from entry points")
        ep_parser.add_argument(
            "--group",
            default="auditor_toolkit.checks",
            help="Entry point group name",
        )

        # load-directory subcommand
        dir_parser = sub.add_parser("load-directory", help="Load plugins from a directory")
        dir_parser.add_argument("directory", type=Path, help="Directory containing plugin modules")

        # info subcommand
        info_parser = sub.add_parser("info", help="Show detailed info for a plugin")
        info_parser.add_argument("plugin_id", help="Plugin ID to show info for")

    def execute(self, args: argparse.Namespace) -> int:
        registry = get_registry()

        if args.plugin_command == "list":
            return self._cmd_list(registry, args)
        elif args.plugin_command == "enable":
            return self._cmd_enable(registry, args)
        elif args.plugin_command == "disable":
            return self._cmd_disable(registry, args)
        elif args.plugin_command == "load-entry-points":
            return self._cmd_load_entry_points(args)
        elif args.plugin_command == "load-directory":
            return self._cmd_load_directory(args)
        elif args.plugin_command == "info":
            return self._cmd_info(registry, args)

        return 1

    def _cmd_list(self, registry, args) -> int:
        plugins = registry.get_enabled() if args.enabled_only else [
            registry.get(pid) for pid in registry._plugins
        ]

        if args.category:
            plugins = [p for p in plugins if p.metadata.category == args.category]

        if args.json:
            output = []
            for p in plugins:
                output.append({
                    "id": p.metadata.id,
                    "name": p.metadata.name,
                    "version": p.metadata.version,
                    "category": p.metadata.category,
                    "mode": p.metadata.mode,
                    "description": p.metadata.description,
                    "limitation": p.metadata.limitation,
                    "requires_external": p.metadata.requires_external,
                    "author": p.metadata.author,
                    "enabled": p.metadata.id in registry._enabled,
                })
            print(json.dumps(output, indent=2))
        else:
            for p in plugins:
                status = "enabled" if p.metadata.id in registry._enabled else "disabled"
                print(f"  {p.metadata.id} ({status})")
                print(f"    Name: {p.metadata.name}")
                print(f"    Version: {p.metadata.version}")
                print(f"    Category: {p.metadata.category}")
                print(f"    Mode: {p.metadata.mode}")
                if p.metadata.description:
                    print(f"    Description: {p.metadata.description}")
                if p.metadata.limitation:
                    print(f"    Limitation: {p.metadata.limitation}")
                if p.metadata.requires_external:
                    print(f"    Requires external: yes")
                if p.metadata.author:
                    print(f"    Author: {p.metadata.author}")
                print()
        return 0

    def _cmd_enable(self, registry, args) -> int:
        if registry.enable(args.plugin_id):
            print(f"Enabled plugin: {args.plugin_id}")
            return 0
        else:
            print(f"Plugin not found: {args.plugin_id}")
            return 1

    def _cmd_disable(self, registry, args) -> int:
        if registry.disable(args.plugin_id):
            print(f"Disabled plugin: {args.plugin_id}")
            return 0
        else:
            print(f"Plugin not found: {args.plugin_id}")
            return 1

    def _cmd_load_entry_points(self, args) -> int:
        count = load_plugins_from_entry_points(args.group)
        print(f"Loaded {count} plugins from entry points")
        return 0

    def _cmd_load_directory(self, args) -> int:
        if not args.directory.is_dir():
            print(f"Directory not found: {args.directory}")
            return 1

        count = load_plugins_from_directory(args.directory)
        print(f"Loaded {count} plugin modules from {args.directory}")
        return 0

    def _cmd_info(self, registry, args) -> int:
        plugin = registry.get(args.plugin_id)
        if not plugin:
            print(f"Plugin not found: {args.plugin_id}")
            return 1

        meta = plugin.metadata
        print(f"ID: {meta.id}")
        print(f"Name: {meta.name}")
        print(f"Version: {meta.version}")
        print(f"Category: {meta.category}")
        print(f"Mode: {meta.mode}")
        print(f"Description: {meta.description or 'N/A'}")
        print(f"Limitation: {meta.limitation or 'N/A'}")
        print(f"Requires external: {'yes' if meta.requires_external else 'no'}")
        print(f"Author: {meta.author or 'N/A'}")
        print(f"Enabled: {'yes' if meta.id in registry._enabled else 'no'}")

        # Show definition
        definition = plugin.get_definition()
        print(f"\nCheckDefinition:")
        print(f"  ID: {definition.id}")
        print(f"  Category: {definition.category}")
        print(f"  Mode: {definition.mode}")
        print(f"  Version: {definition.version}")
        print(f"  Evidence required: {definition.evidence_required}")
        print(f"  Limitation: {definition.limitation or 'N/A'}")

        return 0


# Register the command
register_command(PluginCommand())
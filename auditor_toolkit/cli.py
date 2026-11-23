"""Main CLI entry point using command pattern."""

from __future__ import annotations

import argparse
import logging

from auditor_toolkit.agency_cli import add_commands, run_command
from auditor_toolkit.commands import registry
from auditor_toolkit.logging_config import setup_logging


def create_parser() -> argparse.ArgumentParser:
    """Create the main argument parser with all commands."""
    parser = argparse.ArgumentParser(prog="wa")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set logging level",
    )
    parser.add_argument(
        "--json-log",
        action="store_true",
        help="Output logs as JSON lines",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # Register all commands from the registry
    for cmd in registry.all().values():
        cmd_parser = sub.add_parser(cmd.name, help=cmd.help)
        cmd.add_arguments(cmd_parser)

    # Add agency commands (they have their own structure)
    add_commands(sub)

    return parser


def main(argv=None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv)

    # Configure logging
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    setup_logging(level=log_level, json_output=args.json_log)

    # Handle agency commands
    if args.command in {"revenue", "monthly"}:
        try:
            return run_command(args)
        except (ValueError, OSError, KeyError) as exc:
            parser.error(str(exc))
            return 1

    # Get and execute the command
    cmd = registry.get(args.command)
    if cmd is None:
        parser.error(f"Unknown command: {args.command}")
        return 1

    try:
        return cmd.execute(args)
    except SystemExit as e:
        return e.code
    except Exception as exc:
        parser.error(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

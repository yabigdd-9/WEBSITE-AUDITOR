"""Command registry for mm_operator.

Each command module registers its subcommands with the central registry.
The main operator then dispatches to registered handlers.
"""

from __future__ import annotations

import argparse
from typing import Any, Callable

# Command handler type
CommandHandler = Callable[[argparse.Namespace], Any]

# Registry of command handlers
_command_handlers: dict[str, CommandHandler] = {}
_subcommand_parsers: dict[str, argparse.ArgumentParser] = {}

# Subcommand groups that share a parent parser
_subcommand_groups: dict[str, dict[str, CommandHandler]] = {}


def register_command(name: str, handler: CommandHandler, *, help: str | None = None):
    """Register a top-level command handler."""
    _command_handlers[name] = handler


def register_subcommand_group(
    group_name: str,
    parent_parser: argparse.ArgumentParser,
    subcommands: dict[str, CommandHandler],
):
    """Register a group of subcommands under a parent parser."""
    _subcommand_groups[group_name] = subcommands


def get_handler(name: str) -> CommandHandler | None:
    """Get a command handler by name."""
    return _command_handlers.get(name)


def get_subcommand_handler(group: str, subcommand: str) -> CommandHandler | None:
    """Get a subcommand handler."""
    return _subcommand_groups.get(group, {}).get(subcommand)


def list_commands() -> list[str]:
    """List all registered top-level commands."""
    return list(_command_handlers.keys())


def list_subcommands(group: str) -> list[str]:
    """List all registered subcommands for a group."""
    return list(_subcommand_groups.get(group, {}).keys())


def build_parser() -> argparse.ArgumentParser:
    """Build the complete argument parser with all registered commands."""
    p = argparse.ArgumentParser(
        description="WEBSITES/BUISNESSaudits: deterministic local operator. Never sends or calls a model."
    )
    s = p.add_subparsers(dest="cmd", required=True)

    # Register all commands from modules
    from . import (
        core,
        observability,
        data_quarantine,
        obsidian,
        smart_reply,
        transport,
        outcomes,
        polish_module,
        audit_workflow,
        outreach,
        email,
        discovery,
        evidence,
        reporting,
        brain,
        supervisor_cmd,
        model,
        agent_policy,
        challenger,
        deploy,
        pipeline_cmd,
        approval,
        price,
    )

    # Core commands
    core.register(s)

    # Observability commands
    observability.register(s)

    # Data quarantine
    data_quarantine.register(s)

    # Obsidian
    obsidian.register(s)

    # Smart reply
    smart_reply.register(s)

    # Transport
    transport.register(s)

    # Outcomes
    outcomes.register(s)

    # Polish/Module status
    polish_module.register(s)

    # Audit workflow
    audit_workflow.register(s)

    # Outreach
    outreach.register(s)

    # Email
    email.register(s)

    # Discovery
    discovery.register(s)

    # Evidence
    evidence.register(s)

    # Reporting
    reporting.register(s)

    # Brain
    brain.register(s)

    # Supervisor
    supervisor_cmd.register(s)

    # Model
    model.register(s)

    # Agent policy
    agent_policy.register(s)

    # Challenger
    challenger.register(s)

    # Deploy
    deploy.register(s)

    # Pipeline
    pipeline_cmd.register(s)

    # Approval
    approval.register(s)

    # Price
    price.register(s)

    return p
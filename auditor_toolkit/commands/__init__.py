"""Command pattern implementation for CLI commands."""

from __future__ import annotations

from .base import Command, CommandRegistry, register_command, registry

# Import all command modules to register them
# These imports trigger the register_command() calls in each module
from . import (  # noqa: F401
    actions,
    audit,
    config,
    dashboard,
    demo,
    doctor,
    eval,
    health,
    history,
    metrics,
    packet,
    plugin,
    quote,
    region,
    remediate,
    schema,
    secret,
    secret_rotation,
    tracing,
    watchdog,
)

__all__ = [
    "Command",
    "CommandRegistry",
    "register_command",
    "registry",
]
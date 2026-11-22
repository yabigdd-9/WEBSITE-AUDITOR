"""Base classes for CLI commands."""

from __future__ import annotations

from abc import ABC, abstractmethod
from argparse import ArgumentParser, Namespace


class Command(ABC):
    """Base class for CLI commands."""

    name: str = ""
    help: str = ""

    @abstractmethod
    def add_arguments(self, parser: ArgumentParser) -> None:
        """Add command-specific arguments to the parser."""
        pass

    @abstractmethod
    def execute(self, args: Namespace) -> int:
        """Execute the command with parsed arguments."""
        pass


class CommandRegistry:
    """Registry for CLI commands."""

    def __init__(self):
        self._commands: dict[str, Command] = {}

    def register(self, command: Command) -> None:
        """Register a command."""
        self._commands[command.name] = command

    def get(self, name: str) -> Command | None:
        """Get a command by name."""
        return self._commands.get(name)

    def all(self) -> dict[str, Command]:
        """Get all registered commands."""
        return self._commands.copy()


# Global registry instance
registry = CommandRegistry()


def register_command(command: Command) -> None:
    """Register a command in the global registry."""
    registry.register(command)
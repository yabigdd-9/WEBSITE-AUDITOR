"""Eval command implementation."""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
import subprocess

from auditor_toolkit.commands.base import Command, register_command


class EvalCommand(Command):
    """Run promptfoo evaluation."""

    name = "eval"
    help = "Run promptfoo evaluation"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--config", default="money-machine/promptfoo.yaml", help="Path to promptfoo config")
        parser.add_argument("--quiet", action="store_true", help="Quiet mode")

    def execute(self, args: Namespace) -> int:
        cmd = ["promptfoo", "eval", "--config", args.config]
        if args.quiet:
            cmd.append("--quiet")
        subprocess.run(cmd, check=True)
        return 0


register_command(EvalCommand())
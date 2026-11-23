"""Obsidian commands for mm_operator."""

from __future__ import annotations

import argparse


def register(subparsers: argparse._SubParsersAction):
    """Register obsidian commands."""
    for cmd in ("obsidian-sync", "obsidian-status"):
        subparsers.add_parser(cmd)


def handle(a: argparse.Namespace) -> dict:
    """Handle obsidian commands."""
    import mm_obsidian

    if a.cmd == "obsidian-sync":
        return mm_obsidian.sync()
    elif a.cmd == "obsidian-status":
        return mm_obsidian.status()
    else:
        raise ValueError(f"Unknown obsidian command: {a.cmd}")
"""Doctor command implementation."""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
import importlib.util
import os
import sys
from pathlib import Path

from auditor_toolkit.commands.base import Command, register_command
from auditor_toolkit.ai import generate_drafts, verify_model
from auditor_toolkit.external_tools import installed_tools


class DoctorCommand(Command):
    """Run diagnostics."""

    name = "doctor"
    help = "Run diagnostic checks on the environment"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--smoke", action="store_true", help="Run smoke tests (launch browser, test generation)")
        parser.add_argument("--output-root", default="outputs/toolkit", help="Output directory root")

    def execute(self, args: Namespace) -> int:
        root = Path(args.output_root)
        result = {
            "interpreter": sys.executable,
            "dependencies": {
                name: importlib.util.find_spec(name) is not None
                for name in ("httpx", "bs4", "dns", "fastapi", "argon2", "playwright", "llama_cpp")
            },
            "model": verify_model(),
            "output_writable": os.access(root if root.exists() else root.parent, os.W_OK),
            "generation": {"status": "not_tested"},
            "browser": {"status": "not_tested"},
            "external_tools": installed_tools(),
        }
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                result["browser"] = {
                    "executable": p.chromium.executable_path,
                    "installed": Path(p.chromium.executable_path).is_file(),
                    "status": "not_launched",
                }
                if args.smoke:
                    browser = p.chromium.launch(headless=True)
                    browser.close()
                    result["browser"]["status"] = "ok"
        except Exception as exc:
            result["browser"] = {"status": "error", "reason": str(exc)}
        if args.smoke:
            result["generation"] = generate_drafts(
                {"url": "https://example.com", "defects": []}, enabled=True
            )

        import json
        print(json.dumps(result, indent=2))
        return (
            2
            if args.smoke
            and (result["browser"]["status"] != "ok" or result["generation"]["status"] != "ok")
            else 0
        )


register_command(DoctorCommand())
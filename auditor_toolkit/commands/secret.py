"""Secret command implementation."""

from __future__ import annotations

import subprocess
import sys
from argparse import ArgumentParser, Namespace

from .base import Command, register_command


class SecretCommand(Command):
    """Manage secrets in the keychain."""

    name = "secret"
    help = "Manage secrets in the keychain"

    def add_arguments(self, parser: ArgumentParser) -> None:
        sub = parser.add_subparsers(dest="secret_command", required=True)
        # set
        secret_set = sub.add_parser("set", help="Store a secret in the keychain")
        secret_set.add_argument("name", help="Secret name")
        secret_set.add_argument("value", help="Secret value")
        # get
        secret_get = sub.add_parser("get", help="Retrieve a secret from the keychain")
        secret_get.add_argument("name", help="Secret name")
        # list
        sub.add_parser("list", help="List secret names")
        # delete
        secret_delete = sub.add_parser("delete", help="Delete a secret from the keychain")
        secret_delete.add_argument("name", help="Secret name")

    def execute(self, args: Namespace) -> int:
        if args.secret_command == "set":
            subprocess.run([
                "security", "add-generic-password",
                "-s", "website-auditor",
                "-a", args.name,
                "-w", args.value,
                "-U"
            ], check=True)
            print(f"Secret '{args.name}' stored.")
        elif args.secret_command == "get":
            try:
                result = subprocess.run([
                    "security", "find-generic-password",
                    "-s", "website-auditor",
                    "-a", args.name,
                    "-w"
                ], capture_output=True, text=True, check=True)
                print(result.stdout.strip())
            except subprocess.CalledProcessError:
                print(f"Error: Secret '{args.name}' not found.", file=sys.stderr)
                return 1
        elif args.secret_command == "list":
            try:
                result = subprocess.run([
                    "security", "find-generic-password", "-s", "website-auditor", "-g"
                ], capture_output=True, text=True, check=True)
                print("Listing secrets is not yet implemented in this version.")
            except subprocess.CalledProcessError:
                print("No secrets found.")
        elif args.secret_command == "delete":
            subprocess.run([
                "security", "delete-generic-password",
                "-s", "website-auditor",
                "-a", args.name
            ], check=True)
            print(f"Secret '{args.name}' deleted.")
        else:
            print("error: Invalid secret command", file=sys.stderr)
            return 1
        return 0


register_command(SecretCommand())

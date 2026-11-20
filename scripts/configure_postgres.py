"""Trusted-device credential check/install; never accepts a secret as an argument.

Only explicitly requested GitHub secret installation writes externally. Database
verification is read-only and never starts pipeline jobs, audits or sending.
"""

from __future__ import annotations

import argparse
import getpass
import subprocess
import sys
import warnings

from scripts.postgres_store import PostgresPipelineStore

REPOSITORY = "github.com/yabigdd-9/WEBSITE-AUDITOR"
SECRET_NAME = "WA_POSTGRES_DSN"


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally echoes unrecognized arguments, which may be secrets.
        self.exit(2, "Invalid setup options. Enter credentials only at the hidden prompt.\n")


def github_command(arguments, *, secret=None):
    # The credential travels over stdin, never process arguments or an env file.
    subprocess.run(
        ["gh", *arguments], input=secret, text=True, capture_output=True,
        check=True, timeout=30,
    )


def configure(*, install_github_secret=False):
    if not sys.stdin.isatty():
        raise ValueError("Use a trusted interactive terminal")
    if install_github_secret:
        github_command(["auth", "status", "--hostname", "github.com"])
    # Refuse getpass's echoing fallback if terminal echo cannot be disabled.
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        dsn = getpass.getpass("Private moneymachine runner connection string (hidden): ")
    if not dsn.strip():
        raise ValueError("A dedicated runtime connection is required")
    store = PostgresPipelineStore(dsn)
    if store.read() is None:
        raise ValueError("Initialize the reviewed private pipeline before credential setup")
    store.operational_summary()  # Verify the durable quota schema too, read-only.
    if install_github_secret:
        github_command(["secret", "set", SECRET_NAME, "--repo", REPOSITORY], secret=dsn)


def main(argv=None):
    parser = PrivateArgumentParser(description="Privately verify the selected project's runner credential")
    parser.add_argument(
        "--install-github-secret", action="store_true",
        help="After verification, create/replace WA_POSTGRES_DSN in yabigdd-9/WEBSITE-AUDITOR",
    )
    args = parser.parse_args(argv)
    try:
        configure(install_github_secret=args.install_github_secret)
    except (KeyboardInterrupt, EOFError):
        print("Setup interrupted. Verify private configuration before retrying.")
        return 2
    except Exception:
        # Driver/gh errors may echo connection arguments; never print them.
        print("Credential setup blocked. Check the trusted terminal, connection and repository permissions privately.")
        return 2
    if args.install_github_secret:
        print("Credential verified and GitHub secret installed. No workflow, audit or send was started.")
    else:
        print("Credential verified. No secret was installed and no workflow, audit or send was started.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

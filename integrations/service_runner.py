"""LaunchAgent entrypoint; loads webhook secrets from macOS Keychain into env only."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def keychain_secret(service: str) -> str:
    result = subprocess.run(
        ["/usr/bin/security", "find-generic-password", "-s", service, "-w"],
        capture_output=True,
        text=True,
        check=True,
    )
    value = result.stdout.strip()
    if not value:
        raise RuntimeError(f"Keychain item is empty: {service}")
    return value


def main() -> None:
    os.environ["WA_ROOT"] = str(ROOT)
    os.environ["PYTHONPATH"] = str(ROOT)
    os.environ["GITHUB_WEBHOOK_SECRET"] = keychain_secret("WEBSITE-AUDITOR-GITHUB-WEBHOOK")
    os.environ["WA_WEBHOOK_TOKEN"] = keychain_secret("WEBSITE-AUDITOR-WA-API-TOKEN")
    os.chdir(ROOT)
    os.execv(
        sys.executable,
        [sys.executable, "-m", "integrations", "serve", "--host", "127.0.0.1", "--port", "8091"],
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Casino Auditor: allowlisted operator-site audit launcher.

Scans run only when the operator supplies a target manifest, an explicit
written-authorization reference, a future expiration date and --run.
This deliberately reuses the existing 'wa audit' CLI without attempting
exploitation, login, payment, or session manipulation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import urlsplit

HOST_RE = re.compile(r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")


def validate_target(entry: dict, now: datetime | None = None) -> tuple[str, str]:
    if not isinstance(entry, dict):
        raise ValueError("Each target must be an object")
    url = entry.get("url")
    if not isinstance(url, str) or not url:
        raise ValueError("A target URL is required")
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().rstrip(".")
    if (parts.scheme != "https" or not host or not HOST_RE.fullmatch(host)
            or "." not in host or parts.port is not None or parts.username
            or parts.password or parts.query or parts.fragment
            or parts.path not in ("", "/")
            or host.endswith((".local", ".internal", ".localhost"))
            or host.startswith(("localhost.", "127."))
            or all(char.isdigit() or char == "." for char in host)):
        raise ValueError(f"Unsafe or unsupported site URL: {url!r}. Use https://domain.tld only.")
    approved_by = entry.get("approved_by")
    reference = entry.get("authorization_reference")
    if not isinstance(approved_by, str) or len(approved_by.strip()) < 3:
        raise ValueError(f"{host}: approved_by must identify the approving site owner")
    if not isinstance(reference, str) or len(reference.strip()) < 3:
        raise ValueError(f"{host}: authorization_reference is required")
    if entry.get("scope") != "public-site-audit":
        raise ValueError(f"{host}: only 'public-site-audit' scope is supported")
    expiry = entry.get("expires_utc")
    try:
        if not isinstance(expiry, str):
            raise ValueError("expiry must be ISO-8601")
        expiry_dt = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
        if expiry_dt.tzinfo is None:
            raise ValueError("expiry timezone must be explicit")
    except ValueError as error:
        raise ValueError(f"{host}: invalid expires_utc: {error}") from error
    if expiry_dt <= (now or datetime.now(timezone.utc)):
        raise ValueError(f"{host}: written authorization has expired")
    return host, url


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Casino Auditor (authorized websites only)")
    parser.add_argument("--manifest", type=Path, required=True, help="JSON list of approved sites")
    parser.add_argument("--output-dir", type=Path, default=Path("casino-audit-reports"))
    parser.add_argument("--run", action="store_true", help="Actually invoke the existing wa audit CLI")
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.manifest.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("targets"), list) or not data["targets"]:
            raise ValueError("Manifest needs a nonempty targets list")
        targets = [validate_target(item) for item in data["targets"]]
        if len(set(host for host, _ in targets)) != len(targets):
            raise ValueError("Duplicate host in manifest")
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error))

    for host, url in targets:
        print(f"Approved target manifest: {host} — scope public-site-audit")
    if not args.run:
        print("DRY RUN ONLY. Supply --run after independently verifying written owner consent.")
        return 0

    command = shutil.which("wa")
    if command is None:
        parser.error("The canonical 'wa' executable is not installed. See the main README.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    failures = 0
    for host, url in targets:
        print(f"Auditing approved site: {host}", flush=True)
        try:
            result = subprocess.run([command, "audit", url, "--profile", "nz"],
                                    capture_output=True, text=True, timeout=600, check=False)
            (args.output_dir / f"{host}.stdout.txt").write_text(result.stdout, encoding="utf-8")
            (args.output_dir / f"{host}.stderr.txt").write_text(result.stderr, encoding="utf-8")
            failures += result.returncode != 0
        except subprocess.TimeoutExpired:
            print(f"{host}: audit timed out", file=sys.stderr)
            failures += 1
    print(f"Completed {len(targets)} approved-site audit(s); failed: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Fail-closed cloud startup check for the Website Auditor supervisor.

A missing persistent mount, missing/invalid database or enabled mail transport
blocks startup. This check does not create/migrate files or access the network.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path


def validate(root: Path, data_mount: Path) -> list[str]:
    errors: list[str] = []
    root = root.resolve()
    data_mount = data_mount.resolve()

    if not data_mount.is_mount():
        errors.append(f"Persistent data disk is not mounted: {data_mount}")
    if root == data_mount or not root.is_relative_to(data_mount):
        errors.append(f"MM_ROOT must be inside the persistent disk: {root}")

    state_dir = root / "state"
    database_dir = root / "database"
    db_path = database_dir / "money_machine.db"
    if not state_dir.is_dir() or not os.access(state_dir, os.W_OK):
        errors.append(f"Writable state directory required: {state_dir}")
    if not database_dir.is_dir() or not os.access(database_dir, os.W_OK):
        errors.append(f"Writable database directory required: {database_dir}")

    if not db_path.is_file() or db_path.stat().st_size == 0:
        errors.append(f"Nonempty restored SQLite database required: {db_path}")
    else:
        try:
            with closing(sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True, timeout=5)) as connection:
                result = connection.execute("PRAGMA quick_check").fetchone()
                if not result or result[0] != "ok":
                    errors.append("SQLite integrity check failed")
                tables = {row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
                if "businesses" not in tables:
                    errors.append("Database missing the required businesses table")
        except (sqlite3.DatabaseError, OSError) as error:
            errors.append(f"SQLite database cannot be read: {type(error).__name__}")

    transport = root / "money-machine" / "config" / "transport.json"
    try:
        config = json.loads(transport.read_text(encoding="utf-8"))
        if (config.get("enabled") is not False or
                config.get("external_send_allowed") is not False or
                config.get("daily_cap") != 0):
            errors.append("Mail transport must remain disabled (zero daily sends)")
    except (OSError, ValueError) as error:
        errors.append(f"Mail transport policy missing or invalid: {type(error).__name__}")
    return errors


def main() -> int:
    root = Path(os.environ.get("MM_ROOT", "/mnt/wa-data/WEBSITE-AUDITOR"))
    mount = Path(os.environ.get("WA_DATA_MOUNT", "/mnt/wa-data"))
    errors = validate(root, mount)
    for error in errors:
        print(f"BLOCKED_CLOUD_PREFLIGHT: {error}", file=sys.stderr)
    if errors:
        return 2
    print("Cloud preflight passed: persistent disk, database and mail policy verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

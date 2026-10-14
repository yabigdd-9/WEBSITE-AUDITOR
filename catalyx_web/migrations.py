"""Explicit application schema migration command for a configured database."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import os
from pathlib import Path

from .db import Database


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize or upgrade the Catalyx application schema")
    parser.add_argument(
        "--database",
        default=os.getenv("CATALYX_DATABASE_URL") or os.getenv("CATALYX_DB_PATH", "state/catalyx-app.sqlite3"),
        help="Database URL or local SQLite path; secrets should come from the environment",
    )
    parser.add_argument(
        "--postgres-backup",
        help="Path to a pg_dump custom or plain SQL backup made before this migration",
    )
    parser.add_argument(
        "--postgres-backup-sha256",
        help="Expected SHA-256 for --postgres-backup",
    )
    arguments = parser.parse_args()
    is_postgres = arguments.database.startswith(("postgres://", "postgresql://"))
    if bool(arguments.postgres_backup) != bool(arguments.postgres_backup_sha256):
        parser.error("--postgres-backup and --postgres-backup-sha256 must be provided together")
    backup_verified = False
    if arguments.postgres_backup:
        backup_path = Path(arguments.postgres_backup).expanduser()
        try:
            with backup_path.open("rb") as backup_file:
                signature = backup_file.read(64)
                backup_file.seek(0)
                digest = hashlib.file_digest(backup_file, "sha256").hexdigest()
        except OSError:
            parser.error("The PostgreSQL backup artifact could not be read")
        if not (signature.startswith(b"PGDMP") or signature.startswith(b"-- PostgreSQL database dump")):
            parser.error("The backup artifact is not a recognized pg_dump custom or plain SQL file")
        if not hmac.compare_digest(digest, arguments.postgres_backup_sha256.lower()):
            parser.error("The PostgreSQL backup SHA-256 did not match")
        backup_verified = True
    if arguments.postgres_backup and not is_postgres:
        parser.error("PostgreSQL backup options apply only to a PostgreSQL database")
    Database(arguments.database, initialize=True, postgres_backup_verified=backup_verified)
    print("Catalyx application database schema is ready.")


if __name__ == "__main__":
    main()

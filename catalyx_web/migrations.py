"""Explicit application schema migration command for a configured database."""

from __future__ import annotations

import argparse
import os

from .db import Database


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize or upgrade the Catalyx application schema")
    parser.add_argument(
        "--database",
        default=os.getenv("CATALYX_DATABASE_URL") or os.getenv("CATALYX_DB_PATH", "state/catalyx-app.sqlite3"),
        help="Database URL or local SQLite path; secrets should come from the environment",
    )
    arguments = parser.parse_args()
    Database(arguments.database, initialize=True)
    print("Catalyx application database schema is ready.")


if __name__ == "__main__":
    main()

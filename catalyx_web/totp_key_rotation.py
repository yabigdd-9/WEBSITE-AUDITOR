"""Offline, dry-run-first rotation for administrator TOTP encryption keys."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .db import Database, DatabaseError
from .security import parse_totp_encryption_key


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate or rotate administrator TOTP encryption keys."
    )
    parser.add_argument(
        "--database",
        default=os.getenv("CATALYX_DATABASE_URL")
        or os.getenv("CATALYX_DB_PATH", "state/catalyx-app.sqlite3"),
        help="Database URL or local SQLite path; credentials should come from the environment",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the re-encryption after the default read-only validation pass",
    )
    arguments = parser.parse_args()

    try:
        if not arguments.database.startswith(("postgres://", "postgresql://")):
            local_database = Path(arguments.database).expanduser()
            if not local_database.is_file():
                parser.exit(2, "error: local database file does not exist\n")
        old_encoded = os.environ["CATALYX_TOTP_ROTATION_OLD_KEY"]
        new_encoded = os.environ["CATALYX_TOTP_ROTATION_NEW_KEY"]
        old_key = parse_totp_encryption_key(old_encoded)
        new_key = parse_totp_encryption_key(new_encoded)
        database = Database(
            arguments.database,
            initialize=False,
            totp_encryption_key=new_key,
        )
        result = database.rotate_totp_secrets(old_key, new_key, apply=arguments.apply)
    except KeyError as exc:
        missing = str(exc).strip("'")
        parser.exit(2, f"error: required environment variable {missing} is not set\n")
    except (ValueError, DatabaseError) as exc:
        parser.exit(2, f"error: {exc}\n")

    action = "rotated" if result["applied"] else "validated"
    print(
        f"{action} total={result['total']} would_rotate={result['would_rotate']} "
        f"already_current={result['already_current']} applied={str(result['applied']).lower()}"
    )


if __name__ == "__main__":
    main()

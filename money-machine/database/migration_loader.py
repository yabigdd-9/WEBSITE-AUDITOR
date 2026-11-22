"""Migration loader for MoneyMachine.

Loads SQL schema and triggers from versioned migration files.
"""

from __future__ import annotations

from pathlib import Path


MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def load_schema() -> str:
    """Load the schema SQL from migration file."""
    schema_path = MIGRATIONS_DIR / "001_schema.sql"
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema migration not found: {schema_path}")
    return schema_path.read_text(encoding="utf-8")


def load_triggers() -> str:
    """Load the triggers SQL from migration file."""
    triggers_path = MIGRATIONS_DIR / "002_triggers.sql"
    if not triggers_path.exists():
        raise FileNotFoundError(f"Triggers migration not found: {triggers_path}")
    return triggers_path.read_text(encoding="utf-8")


def load_migration(version: int) -> str:
    """Load a specific migration by version number."""
    migrations = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if version <= 0 or version > len(migrations):
        raise ValueError(f"Invalid migration version: {version}")
    return migrations[version - 1].read_text(encoding="utf-8")


def list_migrations() -> list[dict[str, any]]:
    """List all available migrations."""
    migrations = sorted(MIGRATIONS_DIR.glob("*.sql"))
    result = []
    for i, path in enumerate(migrations, 1):
        result.append({
            "version": i,
            "name": path.stem,
            "path": str(path),
            "size": path.stat().st_size,
        })
    return result
"""Fresh and legacy SQLite schema checks for the Money Machine operator."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import mm_core


def test_legacy_messages_gain_invalidation_field_before_guards(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parent
    database = tmp_path / "database" / "money_machine.db"
    database.parent.mkdir()
    with sqlite3.connect(database) as connection:
        connection.executescript((root / "database" / "schema.sql").read_text())
        triggers = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='mm_messages'"
        ).fetchall()
        for (name,) in triggers:
            escaped = name.replace('"', '""')
            connection.execute(f'DROP TRIGGER "{escaped}"')
        connection.execute("ALTER TABLE mm_messages DROP COLUMN invalidated_reason")

    monkeypatch.setenv("MM_ROOT", str(tmp_path))
    backup = mm_core.backup(tmp_path)
    with mm_core.connect(database) as connection:
        mm_core.migrate(connection, backup)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(mm_messages)")}
        guards = connection.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='trigger' AND tbl_name='mm_messages'"
        ).fetchone()[0]

    assert "invalidated_reason" in columns
    assert guards > 0

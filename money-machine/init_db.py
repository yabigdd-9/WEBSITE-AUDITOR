#!/usr/bin/env python3
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "database" / "money_machine.db"
SCHEMA = ROOT / "database" / "schema.sql"

DB.parent.mkdir(parents=True, exist_ok=True)
with sqlite3.connect(DB) as connection:
    connection.executescript(SCHEMA.read_text())
    connection.execute("PRAGMA foreign_keys = ON")
print(f"initialized: {DB}")


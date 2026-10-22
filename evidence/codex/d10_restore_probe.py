"""Run an isolated synthetic WAL backup/restore drill with existing mm_core."""

import hashlib
import importlib.util
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parents[2]
    fixture = root / "work/codex-r00/d10-fixture"
    if fixture.exists():
        raise SystemExit("Fixture exists; use a new reviewed location, never overwrite")
    fixture.mkdir(parents=True)
    database = fixture / "database/money_machine.db"
    database.parent.mkdir()
    source_path = root / "money-machine/mm_core.py"
    spec = importlib.util.spec_from_file_location("isolated_mm_core", source_path)
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)
    started = datetime.now(timezone.utc).isoformat()
    timer = time.monotonic()
    source = sqlite3.connect(database)
    source.execute("PRAGMA journal_mode=WAL")
    source.execute("PRAGMA wal_autocheckpoint=0")
    source.executescript("""
        CREATE TABLE businesses(id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE pending_work(id INTEGER PRIMARY KEY, business_id INTEGER
          REFERENCES businesses(id), state TEXT NOT NULL);
        CREATE TABLE suppression(business_id INTEGER PRIMARY KEY
          REFERENCES businesses(id), reason TEXT NOT NULL);
        INSERT INTO businesses VALUES(1, 'Synthetic fixture');
        INSERT INTO pending_work VALUES(1, 1, 'UNKNOWN_NEEDS_RECONCILIATION');
        INSERT INTO suppression VALUES(1, 'operator hold');
    """)
    source.commit()
    before = list(source.iterdump())
    wal_present = database.with_name(database.name + "-wal").stat().st_size > 0
    backup = core.backup(fixture)
    manifest = json.loads((backup / "manifest.json").read_text())
    assert all(digest(Path(item["path"])) == item["sha256"] for item in manifest["items"])
    saved = backup / "money_machine.db"
    with sqlite3.connect(saved.as_uri() + "?mode=ro", uri=True) as snapshot:
        restored = fixture / "restore/money_machine.db"
        restored.parent.mkdir()
        with sqlite3.connect(restored) as destination:
            snapshot.backup(destination)
            assert destination.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            assert not destination.execute("PRAGMA foreign_key_check").fetchall()
            assert list(destination.iterdump()) == before
    # A partial restore is quarantined; never rename it over the source or good restore.
    preserved = digest(restored)
    interrupted = fixture / "restore/interrupted.partial"
    interrupted.write_bytes(saved.read_bytes()[:64])
    try:
        with sqlite3.connect(interrupted.as_uri() + "?mode=ro", uri=True) as broken:
            assert broken.execute("PRAGMA integrity_check").fetchone() != ("ok",)
    except sqlite3.DatabaseError:
        pass
    else:
        raise AssertionError("Truncated restore was unexpectedly accepted")
    assert digest(restored) == preserved
    assert list(source.iterdump()) == before
    source.close()
    result = {
        "status": "PASS_SYNTHETIC_ONLY",
        "started_at_utc": started,
        "duration_seconds": round(time.monotonic() - timer, 3),
        "core_source_sha256": digest(source_path),
        "wal_present_during_backup": wal_present,
        "backup_manifest_hashes_match": True,
        "restored_schema_and_rows_match": True,
        "pending_and_suppression_preserved": True,
        "partial_restore_rejected": True,
        "source_logical_contents_unchanged": True,
        "production_database_opened": False,
        "limitations": [
            "Synthetic schema only; no production schema restoration claim",
            "Partial-file fault injection, not process-kill recovery",
            "Not independent acceptance; no production restore or runtime activation",
        ],
    }
    output = root / "evidence/codex/d10-restore-receipt.json"
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

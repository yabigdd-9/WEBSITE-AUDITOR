"""Compatible append-only experience ledger for V44 rejections and V45 outcomes."""
TABLE = """
CREATE TABLE IF NOT EXISTS experience_ledger(
  id INTEGER PRIMARY KEY,
  outcome_id INTEGER REFERENCES prospect_outcomes(id),
  business_id INTEGER NOT NULL,
  outcome TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  actor TEXT NOT NULL,
  evidence_path TEXT NOT NULL DEFAULT '',
  evidence_hash TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  ledger_at TEXT NOT NULL DEFAULT '')
"""
OPTIONAL_COLUMNS = {
    "outcome_id": "INTEGER REFERENCES prospect_outcomes(id)",
    "evidence_path": "TEXT NOT NULL DEFAULT ''",
    "note": "TEXT NOT NULL DEFAULT ''",
    "ledger_at": "TEXT NOT NULL DEFAULT ''",
}
POPULATE = """
CREATE TRIGGER experience_ledger_populate
AFTER INSERT ON prospect_outcomes BEGIN
  INSERT INTO experience_ledger(
    outcome_id,business_id,outcome,observed_at,actor,
    evidence_path,evidence_hash,note,created_at,ledger_at)
  VALUES(
    NEW.id,NEW.business_id,NEW.outcome,NEW.observed_at,NEW.actor,
    NEW.evidence_path,NEW.evidence_hash,NEW.note,NEW.created_at,
    strftime('%Y-%m-%dT%H:%M:%fZ','now'));
END
"""


def migrate(d):
    """Preserve either existing layout and install exactly one outcome trigger.

    V44 gains nullable metadata columns. V45's mandatory outcome FK is broadened
    for terminal rejection experiences. Its original table is archived intact
    and immutable; all existing columns are copied into the active ledger.
    Everything is one savepoint, including trigger changes.
    """
    d.execute("SAVEPOINT experience_compatibility")
    try:
        for trigger in ("experience_ledger_on_outcome", "experience_ledger_populate",
                        "experience_ledger_on_outcomeAFTER", "experience_ledger_populateAFTER"):
            d.execute("DROP TRIGGER IF EXISTS " + trigger)
        columns = {row[1]: row for row in d.execute("PRAGMA table_info(experience_ledger)")}
        if "outcome_id" in columns and columns["outcome_id"][3]:
            archive = "experience_ledger_v45_archive"
            if d.execute("SELECT 1 FROM sqlite_master WHERE name=?", (archive,)).fetchone():
                raise ValueError("experience ledger archive already exists; review required")
            for (table,) in d.execute("SELECT name FROM sqlite_master WHERE type='table'"):
                if any(row[2] == "experience_ledger" for row in d.execute(
                        'PRAGMA foreign_key_list("' + table.replace('"', '""') + '")')):
                    raise ValueError("experience ledger has external FK references; review required")
            d.execute("ALTER TABLE experience_ledger RENAME TO " + archive)
            for operation in ("UPDATE", "DELETE"):
                d.execute(f"CREATE TRIGGER experience_archive_no_{operation.lower()} "
                          f"BEFORE {operation} ON {archive} BEGIN "
                          "SELECT RAISE(ABORT,'experience archive is append-only'); END")
            d.execute(TABLE)
            active = {row[1] for row in d.execute("PRAGMA table_info(experience_ledger)")}
            if set(columns) - active:
                raise ValueError("unknown experience columns; review required before migration")
            names = ",".join('"' + name + '"' for name in columns)
            d.execute(f"INSERT INTO experience_ledger({names}) SELECT {names} FROM {archive}")
            if d.execute("SELECT count(*) FROM experience_ledger").fetchone()[0] != d.execute(
                    "SELECT count(*) FROM " + archive).fetchone()[0]:
                raise ValueError("experience ledger row-count mismatch")
        else:
            d.execute(TABLE)
        columns = {row[1] for row in d.execute("PRAGMA table_info(experience_ledger)")}
        for name, declaration in OPTIONAL_COLUMNS.items():
            if name not in columns:
                d.execute(f"ALTER TABLE experience_ledger ADD COLUMN {name} {declaration}")
        d.execute("CREATE INDEX IF NOT EXISTS experience_ledger_business_v2 "
                  "ON experience_ledger(business_id,observed_at DESC)")
        for operation in ("UPDATE", "DELETE"):
            d.execute(f"DROP TRIGGER IF EXISTS experience_ledger_no_{operation.lower()}_v2")
            d.execute(f"CREATE TRIGGER experience_ledger_no_{operation.lower()}_v2 "
                      f"BEFORE {operation} ON experience_ledger BEGIN "
                      "SELECT RAISE(ABORT,'experience ledger is append-only'); END")
        if d.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                     "AND name='prospect_outcomes'").fetchone():
            d.execute(POPULATE)
        d.execute("RELEASE experience_compatibility")
    except Exception:
        d.execute("ROLLBACK TO experience_compatibility")
        d.execute("RELEASE experience_compatibility")
        raise

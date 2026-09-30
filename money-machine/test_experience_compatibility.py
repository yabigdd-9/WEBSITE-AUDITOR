"""Merge regressions: retain both ledger formats, all rows and append-only gates."""
import sqlite3

import mm_experience_ledger as experience
import mm_outcomes as outcomes
import mm_rejection as rejection
import pytest


def database():
    d = sqlite3.connect(":memory:")
    d.row_factory = sqlite3.Row
    d.execute("PRAGMA foreign_keys=ON")
    d.executescript("""
    CREATE TABLE businesses(id INTEGER PRIMARY KEY);
    INSERT INTO businesses VALUES(1);
    """)
    d.executescript(outcomes.DDL)
    d.execute("INSERT INTO prospect_outcomes VALUES(1,1,'REPLIED','2026-01-01',"
              "'human','/synthetic/evidence','hash','note','2026-01-01')")
    return d


def append_outcome(d, row_id=2):
    d.execute("INSERT INTO prospect_outcomes VALUES(?,1,'PENDING','2026-01-02',"
              "'human','/synthetic/next','next-hash','next-note','2026-01-02')", (row_id,))


@pytest.mark.parametrize("trigger", ["experience_ledger_on_outcome",
                                    "experience_ledger_on_outcomeAFTER"])
def test_v44_rows_preserved_and_one_outcome_produces_one_experience(trigger):
    d = database()
    d.executescript("""
    CREATE TABLE experience_ledger(id INTEGER PRIMARY KEY,outcome TEXT NOT NULL,
        actor TEXT NOT NULL,observed_at TEXT NOT NULL,business_id INTEGER NOT NULL,
        evidence_hash TEXT NOT NULL,created_at TEXT NOT NULL);
    INSERT INTO experience_ledger VALUES(1,'REPLIED','human','2026-01-01',1,'hash','2026-01-01');
    CREATE TRIGGER TRIGGER_NAME AFTER INSERT ON prospect_outcomes BEGIN
        INSERT INTO experience_ledger(outcome,actor,observed_at,business_id,evidence_hash,created_at)
        VALUES(NEW.outcome,NEW.actor,NEW.observed_at,NEW.business_id,NEW.evidence_hash,NEW.created_at);
    END;
    """.replace("TRIGGER_NAME", trigger))
    before = dict(d.execute("SELECT * FROM experience_ledger").fetchone())
    experience.migrate(d)
    experience.migrate(d)
    after = dict(d.execute("SELECT * FROM experience_ledger WHERE id=1").fetchone())
    assert all(after[key] == value for key, value in before.items())
    assert after["outcome_id"] is None
    append_outcome(d)
    assert d.execute("SELECT count(*) FROM experience_ledger").fetchone()[0] == 2
    latest = dict(d.execute("SELECT * FROM experience_ledger WHERE outcome_id=2").fetchone())
    assert latest["evidence_path"] == "/synthetic/next"
    assert latest["note"] == "next-note"
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        d.execute("UPDATE experience_ledger SET actor='changed'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        d.execute("DELETE FROM experience_ledger")
    assert d.execute("PRAGMA foreign_key_check").fetchall() == []


def legacy_v45(d):
    d.executescript("""
    CREATE TABLE experience_ledger(
        id INTEGER PRIMARY KEY,outcome_id INTEGER NOT NULL REFERENCES prospect_outcomes(id),
        business_id INTEGER NOT NULL,outcome TEXT NOT NULL,observed_at TEXT NOT NULL,
        actor TEXT NOT NULL,evidence_path TEXT NOT NULL,evidence_hash TEXT NOT NULL,
        note TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,ledger_at TEXT NOT NULL);
    INSERT INTO experience_ledger VALUES(
        1,1,1,'REPLIED','2026-01-01','human','/synthetic/evidence','hash','note',
        '2026-01-01','2026-01-01');
    """)


def test_v45_metadata_archived_and_terminal_rejections_remain_supported():
    d = database()
    legacy_v45(d)
    before = dict(d.execute("SELECT * FROM experience_ledger").fetchone())
    experience.migrate(d)
    experience.migrate(d)
    assert dict(d.execute("SELECT * FROM experience_ledger WHERE id=1").fetchone()) == before
    assert dict(d.execute("SELECT * FROM experience_ledger_v45_archive").fetchone()) == before
    append_outcome(d)
    rejection.migrate(d)
    rejection.record(d, 1, "REJECTED", "insufficient evidence", "qualification")
    rows = d.execute("SELECT * FROM experience_ledger ORDER BY id").fetchall()
    assert len(rows) == 3
    assert rows[1]["outcome_id"] == 2
    assert rows[2]["outcome"] == "terminal_rejection:REJECTED"
    assert rows[2]["outcome_id"] is None
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        d.execute("DELETE FROM experience_ledger_v45_archive")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        d.execute("UPDATE experience_ledger SET note='changed'")
    assert d.execute("PRAGMA foreign_key_check").fetchall() == []


def test_unexpected_archive_collision_rolls_back_without_losing_rows():
    d = database()
    legacy_v45(d)
    d.execute("CREATE TABLE experience_ledger_v45_archive(id INTEGER)")
    with pytest.raises(ValueError, match="archive already exists"):
        experience.migrate(d)
    assert d.execute("SELECT count(*) FROM experience_ledger").fetchone()[0] == 1
    columns = {row[1]: row for row in d.execute("PRAGMA table_info(experience_ledger)")}
    assert columns["outcome_id"][3] == 1

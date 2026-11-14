"""Build a disposable, customer-free source for legacy MoneyMachine tests."""

import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[2]
    sys.path[:0] = [str(root / "money-machine"), str(root)]
    import mm_approval
    import mm_core
    import mm_email_store
    import mm_pipeline

    fixture = root / "work/codex-r00/money-source-legacy-final"
    source = fixture / "database/money_machine.db"
    if source.exists():
        raise SystemExit("Fixture already exists; preserve prior evidence")
    source.parent.mkdir(parents=True)
    schema = root / "money-machine/database/schema.sql"
    # Model historical claims predating the guards. Install every original
    # trigger before migrations/tests; never disable a live or installed guard.
    triggers = []
    with sqlite3.connect(source) as database:
        statement = ""
        for line in schema.read_text().splitlines(keepends=True):
            statement += line
            if sqlite3.complete_statement(statement):
                if re.search(r"\bCREATE\s+TRIGGER\b", statement, re.I):
                    triggers.append(statement)
                else:
                    database.executescript(statement)
                statement = ""
        if statement.strip():
            database.executescript(statement)
        for _ in range(3):
            database.execute(
                "INSERT INTO outreach(draft,approved_by_human,sent_at) VALUES(?,0,?)",
                ("Synthetic pre-guard legacy claim; no actual delivery", mm_core.now()),
            )
        database.commit()
        for statement in triggers:
            database.executescript(statement)
    backup = mm_core.backup(fixture)
    database = mm_core.connect(source)
    mm_core.migrate(database, backup)
    mm_email_store.migrate_email(database, backup)
    mm_pipeline.migrate(database)
    mm_approval.migrate(database)
    stamp = mm_core.now()
    database.execute(
        "INSERT INTO businesses(id,name,source,discovered_at,current_status,is_dummy) "
        "VALUES(8000,'Synthetic history fixture','fixture',?,'discovered',1)", (stamp,)
    )
    database.execute(
        "INSERT INTO mm_evidence(id,business_id,url,observation,limitation,checked_at) "
        "VALUES(8000,8000,'https://fixture.example.invalid','Synthetic archive',"
        "'No live observation',?)", (stamp,)
    )
    database.execute(
        "INSERT INTO mm_score_history(business_id,evidence_id,inputs_json,computed_json,"
        "calculated_at) VALUES(8000,8000,'{}','{}',?)", (stamp,)
    )
    database.commit()
    try:
        database.execute(
            "INSERT INTO outreach(draft,approved_by_human,sent_at) VALUES(?,0,?)",
            ("Synthetic forbidden new send claim", stamp),
        )
    except sqlite3.IntegrityError:
        database.rollback()
    else:
        raise AssertionError("Installed send guard was not enforced")
    assert database.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert not database.execute("PRAGMA foreign_key_check").fetchall()
    receipt = {
        "source": "Versioned schema, real canonical migrations and synthetic historical rows",
        "fixture_path": str(source),
        "schema_sha256": hashlib.sha256(schema.read_bytes()).hexdigest(),
        "customer_records_copied": 0,
        "actual_external_sends": 0,
        "synthetic_unverified_legacy_claims": 3,
        "synthetic_archive_rows": 1,
        "all_base_triggers_installed_before_migrations": True,
        "new_unapproved_send_claim_rejected": True,
        "reason": "Existing tests assume three historical claims and an archived score; all data is fabricated fixture data, never business evidence",
        "integrity_check": "ok",
        "foreign_key_violations": 0,
    }
    database.close()
    (root / "evidence/codex/q10-money-source-final.json").write_text(
        json.dumps(receipt, indent=2) + "\n"
    )
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()

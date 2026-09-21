#!/usr/bin/env python3
import sqlite3
from pathlib import Path
import os
from mm_core import SCHEMA, TRIGGERS, now

ROOT = Path(__file__).resolve().parent
DB = ROOT / ".." / "database" / "money_machine.db"

print(f"Creating missing tables in {DB}")

# Execute the schema to create missing tables
with sqlite3.connect(DB) as conn:
    # Older canonical snapshots contain a compact mm_deals table. Add the
    # queue columns required by the current operator without replacing data.
    deal_columns = {row[1] for row in conn.execute("PRAGMA table_info(mm_deals)")}
    if deal_columns and "next_action" not in deal_columns:
        conn.execute("ALTER TABLE mm_deals ADD COLUMN next_action TEXT NOT NULL DEFAULT 'Verify website and contact permission'")
    if deal_columns and "due" not in deal_columns:
        conn.execute("ALTER TABLE mm_deals ADD COLUMN due TEXT")
    proposal_columns = {row[1] for row in conn.execute("PRAGMA table_info(mm_proposals)")}
    for name in ("evidence_id", "body", "digest", "price_cents", "approved_hash",
                 "approved_by", "approval_ref", "permission_basis", "sent_at",
                 "send_receipt", "invalidated_reason"):
        if proposal_columns and name not in proposal_columns:
            conn.execute(f"ALTER TABLE mm_proposals ADD COLUMN {name} TEXT")
    # Execute SCHEMA
    conn.executescript(SCHEMA)
    print("Executed SCHEMA")

    # Execute TRIGGERS
    conn.executescript(TRIGGERS)
    conn.execute("CREATE INDEX IF NOT EXISTS mm_deal_queue ON mm_deals(stage,due)")
    print("Executed TRIGGERS")

    # Insert initial migration record
    conn.execute(
        "INSERT OR IGNORE INTO mm_migrations VALUES(?,?,?)",
        (2, now(), str(ROOT / "state"))
    )
    print("Inserted migration record")

    conn.commit()

print("Done!")

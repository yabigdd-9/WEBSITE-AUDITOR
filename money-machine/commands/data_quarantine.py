"""Data quarantine command for mm_operator."""

from __future__ import annotations

import argparse
import contextlib
import json

from mm_operator import (
    OperationalError,
    backup,
    root,
    now,
    ensure_business_columns,
)


def register(subparsers: argparse._SubParsersAction):
    """Register data quarantine command."""
    q = subparsers.add_parser("data-quarantine")
    q.add_argument("--source", required=True)


def handle(a: argparse.Namespace) -> dict:
    """Handle data quarantine command."""
    from mm_pipeline import migrate as mm_pipeline_migrate

    backup_result = backup()
    quarantined = []
    already_quarantined = 0

    with contextlib.closing(connect()) as d, d:
        ensure_business_columns(d)
        mm_pipeline_migrate(d)
        ts = now()
        rows = d.execute(
            "SELECT id, name FROM businesses WHERE source=? ORDER BY id",
            (a.source,),
        ).fetchall()

        for row in rows:
            bid = row["id"]
            cur = d.execute(
                "UPDATE businesses SET is_dummy=1, suppression_reason='test_fixture' "
                "WHERE id=? AND is_dummy=0",
                (bid,),
            )
            if cur.rowcount == 0:
                already_quarantined += 1
                continue

            item = d.execute(
                "SELECT state FROM pipeline_items WHERE business_id=?", (bid,)
            ).fetchone()

            if item and item["state"] != "SUPPRESSED":
                d.execute(
                    "UPDATE pipeline_items SET state='SUPPRESSED', next_retry_at=NULL, "
                    "lease_owner=NULL, lease_until=NULL, updated_at=? WHERE business_id=?",
                    (ts, bid),
                )
                d.execute(
                    "INSERT INTO pipeline_events(business_id,from_state,to_state,"
                    "actor,reason,evidence,event_at) VALUES(?,?,?,?,?,?,?)",
                    (
                        bid,
                        item["state"],
                        "SUPPRESSED",
                        "mm-data-quarantine",
                        "test_fixture",
                        json.dumps({"source": a.source, "is_dummy": True}, sort_keys=True),
                        ts,
                    ),
                )

            quarantined.append({"business_id": bid, "name": row["name"]})

    return {
        "status": "completed",
        "source": a.source,
        "quarantined": len(quarantined),
        "already_quarantined": already_quarantined,
        "items": quarantined,
        "deleted": 0,
        "external_sends": 0,
        "paid_calls": 0,
        "backup": str(backup_result),
    }


def connect():
    """Get database connection."""
    from mm_core import connect
    r = root()
    if not r.exists():
        raise OperationalError(f"MM_ROOT directory does not exist: {r}")
    if not (r / "database").exists():
        raise OperationalError("Database directory missing")
    return connect(r / "database" / "money_machine.db")


from mm_operator import OperationalError
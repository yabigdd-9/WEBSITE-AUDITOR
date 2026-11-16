"""Private crash-durable job/quota bookkeeping, independent of queue rollback."""

from __future__ import annotations

import os
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from scripts.review_ledger import _is_safe_db_location

MAX_HISTORY = 10000
SCHEMA = (
    "CREATE TABLE jobs (id TEXT PRIMARY KEY, started REAL NOT NULL, finished REAL, "
    "status TEXT NOT NULL CHECK(status IN ('running','succeeded','failed','interrupted')))",
    "CREATE TABLE reservations (job_id TEXT NOT NULL REFERENCES jobs(id), audit_id TEXT NOT NULL, "
    "prospect_id TEXT NOT NULL, day TEXT NOT NULL, PRIMARY KEY(job_id,audit_id))",
    "CREATE INDEX reservation_day ON reservations(day)",
    "CREATE INDEX reservation_prospect ON reservations(prospect_id)",
)


class OperationalLedger:
    def __init__(self, path: Path, *, allow_create=False):
        self.path = _is_safe_db_location(path)
        self.allow_create = allow_create
        if not self.path.is_file() and not allow_create:
            raise ValueError("Operational ledger missing; restore the private backup pair")

    @contextmanager
    def connect(self):
        _is_safe_db_location(self.path)
        if not self.path.exists():
            if not self.allow_create:
                raise ValueError("Operational ledger missing; restore the private backup pair")
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
            os.close(fd)
        db = sqlite3.connect(self.path, timeout=1)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                if db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                    raise ValueError("Unrecognized operational database")
                for statement in SCHEMA:
                    db.execute(statement)
                db.execute("PRAGMA user_version=1")
            elif version != 1:
                raise ValueError("Unsupported operational schema")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def start(self, committed_job_id=None):
        # Caller MUST hold the main queue writer lock. Therefore prior running
        # jobs cannot still own the queue and may be classified as interrupted.
        job_id = uuid.uuid4().hex
        with self.connect() as db:
            if db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] >= MAX_HISTORY:
                raise ValueError("Archive operational history before continuing")
            db.execute(
                "UPDATE jobs SET status='succeeded',finished=? WHERE status='running' AND id=?",
                (time.time(), committed_job_id),
            )
            db.execute("UPDATE jobs SET status='interrupted',finished=? WHERE status='running'", (time.time(),))
            db.execute("INSERT INTO jobs VALUES(?,?,NULL,'running')", (job_id, time.time()))
        return job_id

    def finish(self, job_id, status):
        if status not in {"succeeded", "failed"}:
            raise ValueError("Invalid final job status")
        with self.connect() as db:
            db.execute("UPDATE jobs SET status=?,finished=? WHERE id=? AND status='running'", (status, time.time(), job_id))

    @staticmethod
    def daily_usage(db, day, baseline):
        rows = db.execute("SELECT audit_id FROM reservations WHERE day=?", (day,)).fetchall()
        known = {a["audit_id"] for a in baseline.get("audit_runs", []) if a["execution_timestamp"][:10] == day}
        count = sum(e.get("action") == "audit" and e.get("timestamp_utc", "")[:10] == day
                    for e in baseline.get("events", []))
        return max(0, count - len(known & {r[0] for r in rows})) + len(rows)

    def reserve(self, job_id, prospect_id, audit_id, *, now, daily_limit, baseline):
        if type(daily_limit) is not int or not 0 <= daily_limit <= 6:
            raise ValueError("Invalid daily cap")
        if not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
                   for value in (prospect_id, audit_id)):
            raise ValueError("Hashed prospect and audit references required")
        day = datetime.fromtimestamp(now, timezone.utc).isoformat()[:10]
        with self.connect() as db:
            if db.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone() != ("running",):
                raise ValueError("Active queue job required")
            if db.execute("SELECT 1 FROM reservations WHERE job_id=? AND audit_id=?", (job_id, audit_id)).fetchone():
                return True
            # Count legacy committed events too, subtracting only committed
            # audit IDs represented in this ledger. Aborted reservations remain
            # charged even when the queue transaction rolls back.
            if self.daily_usage(db, day, baseline) >= daily_limit:
                return False
            if db.execute("SELECT COUNT(*) FROM reservations WHERE job_id=?", (job_id,)).fetchone()[0] >= 3:
                return False
            prospect_rows = {r[0] for r in db.execute(
                "SELECT audit_id FROM reservations WHERE prospect_id=?", (prospect_id,)
            )}
            count = db.execute("SELECT COUNT(*) FROM reservations WHERE prospect_id=?", (prospect_id,)).fetchone()[0]
            known_prospect = {a["audit_id"] for a in baseline.get("audit_runs", []) if a["prospect_id"] == prospect_id}
            legacy_attempts = max(0, baseline["prospects"].get(prospect_id, {}).get("attempts", 0)
                                  - len(known_prospect & prospect_rows))
            if legacy_attempts + count >= 3:
                return False
            if db.execute("SELECT COUNT(*) FROM reservations").fetchone()[0] >= MAX_HISTORY:
                raise ValueError("Archive reservations before continuing")
            db.execute("INSERT INTO reservations VALUES(?,?,?,?)", (job_id, audit_id, prospect_id, day))
        return True

    def summary(self, baseline=None):
        with self.connect() as db:
            return dict(
                jobs=[dict(id=row[0], started=row[1], finished=row[2], status=row[3])
                      for row in db.execute("SELECT id,started,finished,status FROM jobs ORDER BY started DESC LIMIT 25")],
                reservations=db.execute("SELECT COUNT(*) FROM reservations").fetchone()[0],
                charged_today=self.daily_usage(
                    db, datetime.now(timezone.utc).isoformat()[:10], baseline or {}
                ),
            )

    def backup(self, destination):
        target = _is_safe_db_location(destination)
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        source = None
        output = None
        try:
            source = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
            output = sqlite3.connect(target)
            source.backup(output)
            if output.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Operational backup integrity failed")
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        finally:
            if output is not None:
                output.close()
            if source is not None:
                source.close()

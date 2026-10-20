"""Transactional history; old runs and their evidence are immutable."""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .comparison import compare_finding_history, utc_timestamp, verification_evidence

STATES = {
    "detected",
    "acknowledged",
    "scheduled",
    "in_progress",
    "patched",
    "verified",
    "regressed",
    "accepted_risk",
    "false_positive",
}


def finding_id(finding):
    key = [
        finding.get("check"),
        finding.get("defect_key"),
        finding.get("source_url"),
        finding.get("selector", ""),
    ]
    return hashlib.sha256(json.dumps(key).encode()).hexdigest()[:24]


class History:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "history.sqlite3"
        with self.connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise ValueError("History schema is newer than this toolkit")
            db.executescript("""
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, url TEXT, timestamp TEXT, report TEXT);
            CREATE TABLE IF NOT EXISTS remediations(id TEXT PRIMARY KEY, state TEXT, metadata TEXT);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                kind TEXT, payload TEXT);
            CREATE INDEX IF NOT EXISTS idx_runs_url_timestamp ON runs(url, timestamp DESC);
            PRAGMA user_version=1;
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.create_function("audit_instant_utc", 1, utc_timestamp, deterministic=True)
            with db:
                yield db
        finally:
            db.close()

    def list(self, query="", limit=100):
        with self.connect() as db:
            rows = db.execute(
                "SELECT report FROM runs WHERE url LIKE ? ORDER BY timestamp DESC LIMIT ?",
                ("%" + query + "%", min(max(limit, 1), 1000)),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def get_latest_valid_audit(self, domain, max_age_days=7):
        """
        Get the latest valid (complete) audit for a domain, if it exists and is not too old.

        Args:
            domain (str): The domain to lookup
            max_age_days (int): Maximum age in days for audit to be considered valid

        Returns:
            dict: The audit report if found and valid, None otherwise
        """
        with self.connect() as db:
            # Calculate cutoff timestamp
            cutoff = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ) - timedelta(days=max_age_days)
            cutoff_str = cutoff.isoformat()

            # Get the latest complete audit for this domain that's newer than cutoff
            row = db.execute("""
                SELECT report FROM runs
                WHERE url LIKE ?
                  AND timestamp >= ?
                  AND json_extract(report, '$.status') = 'complete'
                ORDER BY timestamp DESC
                LIMIT 1
            """, (f"%{domain}%", cutoff_str)).fetchone()

            if row:
                return json.loads(row[0])
            return None

    def get(self, run_id):
        with self.connect() as db:
            row = db.execute("SELECT report FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return json.loads(row[0])

    def prior_observations(self, report, limit=99):
        """Exact URL/profile, bounded older rows; never a domain substring match."""
        if not 1 <= limit <= 99:
            raise ValueError("History chart accepts 1–99 previous observations")
        with self.connect() as db:
            rows = db.execute(
                "SELECT report FROM runs WHERE url=? AND id!=? AND json_extract(report, '$.profile')=? "
                "AND (audit_instant_utc(timestamp)<=audit_instant_utc(?) OR audit_instant_utc(timestamp) IS NULL) "
                "ORDER BY audit_instant_utc(timestamp) DESC, id DESC LIMIT ?",
                (report["url"], report["run_id"], report["profile"], report["timestamp"], limit),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def _finding_observations(self, report):
        with self.connect() as db:
            rows = db.execute(
                "SELECT report FROM runs WHERE url=? AND audit_instant_utc(timestamp)<audit_instant_utc(?) AND id!=? "
                "AND json_extract(report, '$.profile')=? ORDER BY audit_instant_utc(timestamp) DESC, id DESC LIMIT 1000",
                (report["url"], report["timestamp"], report["run_id"], report["profile"]),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def compare(self, report):
        return compare_finding_history(report, self._finding_observations(report))

    def save(self, report):
        with self.connect() as db:
            db.execute(
                "INSERT INTO runs VALUES(?,?,?,?)",
                (report["run_id"], report["url"], report["timestamp"], json.dumps(report)),
            )
            for d in report["defects"]:
                db.execute(
                    "INSERT OR IGNORE INTO remediations VALUES(?,?,?)",
                    (d["finding_id"], "detected", "{}"),
                )

    def transition(self, identity, state, metadata=None):
        if state not in STATES:
            raise ValueError("Unknown remediation state")
        metadata = dict(metadata or {})
        if state == "verified":
            run = self.get(metadata.get("verification_run", ""))
            metadata.update(verification_evidence(run, self._finding_observations(run), identity))
        metadata.pop("id", None)
        metadata.pop("state", None)
        with self.connect() as db:
            if (
                db.execute(
                    "UPDATE remediations SET state=?, metadata=? WHERE id=?",
                    (state, json.dumps(metadata), identity),
                ).rowcount
                != 1
            ):
                raise KeyError(identity)
            db.execute(
                "INSERT INTO events(kind,payload) VALUES(?,?)",
                ("remediation", json.dumps({**metadata, "id": identity, "state": state})),
            )

    def artifact(self, run_id, kind):
        report = self.get(run_id)
        path = Path(report["artifacts"][kind]).resolve()
        run_dir = self.root / run_id
        if not path.is_relative_to(run_dir) or not path.is_file():
            raise ValueError("Unregistered artifact path")
        expected = report.get("manifest", {}).get(kind, {}).get("sha256")
        if expected and hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Artifact integrity check failed")
        return path

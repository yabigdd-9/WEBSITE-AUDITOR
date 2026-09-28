"""Transactional history; old runs and their evidence are immutable."""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

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

    def compare(self, report):
        previous = [r for r in self.list(report["url"], 1000) if r["url"] == report["url"]]
        # A partial scan cannot establish resolution or a regression baseline.
        baseline = next(
            (
                r
                for r in previous
                if r["status"] == "complete" and r["profile"] == report["profile"]
            ),
            None,
        )
        current = {d["finding_id"] for d in report["defects"]}
        old = {d["finding_id"] for d in baseline["defects"]} if baseline else set()
        historic = {
            d["finding_id"] for r in previous if r["status"] == "complete" for d in r["defects"]
        }
        return {
            "baseline": baseline["run_id"] if baseline else None,
            "new": sorted(current - old - historic),
            "persistent": sorted(current & old),
            "regressed": sorted((current - old) & historic),
            "resolved": sorted(old - current) if report["status"] == "complete" else [],
            "resolution_assessed": report["status"] == "complete" and baseline is not None,
        }

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

    def _validate_false_positive_review(self, identity, metadata):
        if not isinstance(metadata, dict):
            raise ValueError("False-positive review metadata must be an object")
        reviewer_id = metadata.get("reviewer_id")
        rationale = metadata.get("rationale")
        review_run_id = metadata.get("review_run")
        if not isinstance(reviewer_id, str) or not reviewer_id.strip():
            raise ValueError("False-positive review needs a reviewer_id")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("False-positive review needs a rationale")
        if not isinstance(review_run_id, str) or not review_run_id.strip():
            raise ValueError("False-positive review needs a review_run")
        review_run = self.get(review_run_id)
        includes_finding = any(
            finding.get("finding_id") == identity
            for finding in review_run.get("defects", [])
        )
        if review_run.get("status") != "complete" or not includes_finding:
            raise ValueError(
                "False-positive review needs a complete run containing the finding"
            )

    def _validate_verification(self, identity, metadata):
        run = self.get(metadata.get("verification_run", ""))
        finding_remains = any(
            defect["finding_id"] == identity for defect in run["defects"]
        )
        if run["status"] != "complete" or finding_remains:
            raise ValueError("Verification needs a complete run without the finding")
        with self.connect() as db:
            originals = [json.loads(row[0]) for row in db.execute("SELECT report FROM runs")]
        detection_precedes = any(
            report["url"] == run["url"]
            and report["profile"] == run["profile"]
            and report["timestamp"] < run["timestamp"]
            and any(defect["finding_id"] == identity for defect in report["defects"])
            for report in originals
        )
        if not detection_precedes:
            raise ValueError(
                "Verification must cover the same site and profile after detection"
            )

    def transition(self, identity, state, metadata=None):
        if state not in STATES:
            raise ValueError("Unknown remediation state")
        metadata = metadata or {}
        if state == "false_positive":
            self._validate_false_positive_review(identity, metadata)
        elif state == "verified":
            self._validate_verification(identity, metadata)
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
                ("remediation", json.dumps({"id": identity, "state": state, **metadata})),
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

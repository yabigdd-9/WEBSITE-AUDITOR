"""Transactional history; old runs and their evidence are immutable.

This module provides persistent storage for audit runs, findings, and remediation
state using SQLite. All historical data is immutable once written.
"""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Valid remediation states for findings
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


def finding_id(finding: dict) -> str:
    """Generate a stable, unique identifier for a finding.

    The ID is derived from the check name, defect key, source URL, and selector.
    This allows tracking the same finding across multiple audit runs.

    Args:
        finding: Finding dictionary with keys "check", "defect_key",
            "source_url", and optionally "selector".

    Returns:
        24-character hexadecimal string (SHA256 truncated).
    """
    key = [
        finding.get("check"),
        finding.get("defect_key"),
        finding.get("source_url"),
        finding.get("selector", ""),
    ]
    return hashlib.sha256(json.dumps(key).encode()).hexdigest()[:24]


class History:
    """Persistent audit history using SQLite.

    Manages audit runs, findings, remediation tracking, and artifact integrity.
    Each audit run is stored with its full report JSON for complete reproducibility.

    Database schema:
        - runs: Audit runs (id, url, timestamp, report JSON)
        - remediations: Finding remediation state (id, state, metadata JSON)
        - events: Audit trail events (timestamp, kind, payload JSON)

    Args:
        root: Root directory for history database and artifacts.
    """

    def __init__(self, root: str | Path):
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
        """Context manager for database connections.

        Yields:
            sqlite3.Connection: Database connection with auto-commit on success,
            rollback on exception.

        Raises:
            sqlite3.Error: Database connection or query errors.
        """
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def list(self, query: str = "", limit: int = 100) -> list[dict]:
        """List audit runs matching a query.

        Args:
            query: Substring to match against URLs (wildcard search).
            limit: Maximum number of results (1-1000).

        Returns:
            List of audit report dictionaries, newest first.
        """
        with self.connect() as db:
            rows = db.execute(
                "SELECT report FROM runs WHERE url LIKE ? ORDER BY timestamp DESC LIMIT ?",
                ("%" + query + "%", min(max(limit, 1), 1000)),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def get_latest_valid_audit(self, domain: str, max_age_days: int = 7) -> dict | None:
        """Get the latest valid (complete) audit for a domain.

        Args:
            domain: The domain to lookup.
            max_age_days: Maximum age in days for audit to be considered valid.

        Returns:
            The audit report if found and valid, None otherwise.
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

    def get(self, run_id: str) -> dict:
        """Retrieve a specific audit run by ID.

        Args:
            run_id: Unique run identifier.

        Returns:
            Full audit report dictionary.

        Raises:
            KeyError: If run_id not found.
        """
        with self.connect() as db:
            row = db.execute("SELECT report FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return json.loads(row[0])

    def compare(self, report: dict) -> dict:
        """Compare a report against historical audits for the same URL.

        Identifies new, persistent, regressed, and resolved findings by comparing
        finding_ids across runs. Uses optimized SQL queries to avoid N+1 loading.

        Args:
            report: Current audit report to compare.

        Returns:
            Dictionary with keys:
            - baseline: Run ID of the comparison baseline (most recent complete
              run with same URL and profile).
            - new: Finding IDs in current but not in baseline or history.
            - persistent: Finding IDs in both current and baseline.
            - regressed: Finding IDs in current and history but not baseline.
            - resolved: Finding IDs in baseline but not current (only if complete).
            - resolution_assessed: Whether resolution could be assessed.
        """
        # Use exact URL match in SQL to avoid N+1 loading of full reports
        with self.connect() as db:
            # Find baseline (most recent complete run with same URL and profile)
            baseline_row = db.execute(
                """SELECT run_id, report FROM runs
                   WHERE url = ? AND profile = ? AND json_extract(report, '$.status') = 'complete'
                   ORDER BY timestamp DESC LIMIT 1""",
                (report["url"], report["profile"]),
            ).fetchone()

            baseline = json.loads(baseline_row[1]) if baseline_row else None
            baseline_id = baseline_row[0] if baseline_row else None

            # Get all finding_ids from historical complete runs with same URL and profile
            # in a single query using JSON extraction
            historic_rows = db.execute(
                """SELECT json_extract(report, '$.defects') FROM runs
                   WHERE url = ? AND profile = ? AND json_extract(report, '$.status') = 'complete'
                   AND run_id != ?""",
                (report["url"], report["profile"], report.get("run_id", "")),
            ).fetchall()

        current = {d["finding_id"] for d in report["defects"]}
        old = {d["finding_id"] for d in baseline["defects"]} if baseline else set()
        historic = set()
        for row in historic_rows:
            try:
                defects = json.loads(row[0])
                for d in defects:
                    historic.add(d["finding_id"])
            except (json.JSONDecodeError, KeyError, TypeError):
                continue

        return {
            "baseline": baseline_id,
            "new": sorted(current - old - historic),
            "persistent": sorted(current & old),
            "regressed": sorted((current - old) & historic),
            "resolved": sorted(old - current) if report["status"] == "complete" else [],
            "resolution_assessed": report["status"] == "complete" and baseline is not None,
        }

    def save(self, report: dict) -> None:
        """Save an audit run and initialize remediation tracking.

        Args:
            report: Complete audit report dictionary.
        """
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

    def transition(self, identity: str, state: str, metadata: dict | None = None) -> None:
        """Transition a finding's remediation state.

        Args:
            identity: Finding ID (from finding_id()).
            state: New state (must be in STATES).
            metadata: Optional metadata for the transition.

        Raises:
            ValueError: If state is invalid or verification preconditions fail.
            KeyError: If finding ID not found.
        """
        if state not in STATES:
            raise ValueError("Unknown remediation state")
        metadata = metadata or {}
        if state == "verified":
            run = self.get(metadata.get("verification_run", ""))
            if run["status"] != "complete" or any(
                d["finding_id"] == identity for d in run["defects"]
            ):
                raise ValueError("Verification needs a complete run without the finding")
            with self.connect() as db:
                originals = [json.loads(r[0]) for r in db.execute("SELECT report FROM runs")]
            if not any(
                r["url"] == run["url"]
                and r["profile"] == run["profile"]
                and r["timestamp"] < run["timestamp"]
                and any(d["finding_id"] == identity for d in r["defects"])
                for r in originals
            ):
                raise ValueError(
                    "Verification must cover the same site and profile after detection"
                )
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

    def artifact(self, run_id: str, kind: str) -> Path:
        """Retrieve a validated artifact path for a run.

        Verifies the artifact is registered in the manifest and its SHA256
        matches the expected hash.

        Args:
            run_id: Audit run identifier.
            kind: Artifact kind (e.g., "json", "html", "pdf", "screenshot").

        Returns:
            Path to the artifact file.

        Raises:
            KeyError: If run_id not found.
            ValueError: If artifact is unregistered or integrity check fails.
        """
        report = self.get(run_id)
        path = Path(report["artifacts"][kind]).resolve()
        run_dir = self.root / run_id
        if not path.is_relative_to(run_dir) or not path.is_file():
            raise ValueError("Unregistered artifact path")
        expected = report.get("manifest", {}).get(kind, {}).get("sha256")
        if expected and hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Artifact integrity check failed")
        return path

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

    def transition(self, identity, state, metadata=None):
        if state not in STATES:
            raise ValueError("Unknown remediation state")
        metadata = metadata or {}
        if state == "verified":
            run = self.get(metadata.get("verification_run", ""))
            if run["status"] != "complete" or any(
                d["finding_id"] == identity for d in run["defects"]
            ):
                raise ValueError("Verification needs a complete run without the finding")
            with self.connect() as db:
                originals = [json.loads(r[0]) for r in db.execute("SELECT report FROM runs")]
            if not any(
                r["url"] == run["url"]
                and r["profile"] == run["profile"]
                and r["timestamp"] < run["timestamp"]
                and any(d["finding_id"] == identity for d in r["defects"])
                for r in originals
            ):
                raise ValueError(
                    "Verification must cover the same site and profile after detection"
                )
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

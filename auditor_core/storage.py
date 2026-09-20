"""SQLite-backed audit history and regression records."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _health_score(audit: dict[str, Any]) -> float | None:
    scores = audit.get("site_category_scores") or audit.get("category_scores") or {}
    value = scores.get("overall_health_score") if isinstance(scores, dict) else None
    return float(value) if isinstance(value, (int, float)) else None


def _audit_id(audit: dict[str, Any]) -> str:
    domain = str(audit.get("domain") or "")
    timestamp = str(audit.get("timestamp") or utc_now())
    payload = json.dumps(audit, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(f"{domain}|{timestamp}|{payload}".encode("utf-8")).hexdigest()[:20]
    return f"audit_{digest}"


class AuditHistoryStore:
    def __init__(self, path: str | Path = "outputs/history/audits.sqlite3"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS audits (
                    audit_id TEXT PRIMARY KEY,
                    domain TEXT NOT NULL,
                    url TEXT,
                    captured_at TEXT NOT NULL,
                    opportunity_score REAL,
                    health_score REAL,
                    schema_version INTEGER,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_audits_domain_time
                    ON audits(domain, captured_at DESC);

                CREATE TABLE IF NOT EXISTS findings (
                    audit_id TEXT NOT NULL,
                    check_id TEXT NOT NULL,
                    page_url TEXT,
                    severity TEXT,
                    category TEXT,
                    message TEXT,
                    PRIMARY KEY (audit_id, check_id, page_url),
                    FOREIGN KEY (audit_id) REFERENCES audits(audit_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_findings_check
                    ON findings(check_id);

                CREATE TABLE IF NOT EXISTS verifications (
                    verification_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    domain TEXT NOT NULL,
                    before_audit_id TEXT NOT NULL,
                    after_audit_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    introduced_count INTEGER NOT NULL,
                    resolved_count INTEGER NOT NULL,
                    report_json TEXT NOT NULL,
                    FOREIGN KEY (before_audit_id) REFERENCES audits(audit_id),
                    FOREIGN KEY (after_audit_id) REFERENCES audits(audit_id)
                );
                CREATE INDEX IF NOT EXISTS idx_verifications_domain_time
                    ON verifications(domain, created_at DESC);
                """
            )

    def save_audit(self, audit: dict[str, Any]) -> str:
        audit_id = _audit_id(audit)
        domain = str(audit.get("domain") or "").lower()
        if not domain:
            raise ValueError("audit domain is required")
        captured_at = str(audit.get("timestamp") or utc_now())
        payload_json = json.dumps(audit, sort_keys=True, default=str)
        findings = audit.get("site_findings") or audit.get("findings") or []

        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO audits (
                    audit_id, domain, url, captured_at, opportunity_score,
                    health_score, schema_version, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit_id,
                    domain,
                    audit.get("url"),
                    captured_at,
                    audit.get("score"),
                    _health_score(audit),
                    audit.get("schema_version"),
                    payload_json,
                ),
            )
            for index, finding in enumerate(findings if isinstance(findings, list) else []):
                if not isinstance(finding, dict):
                    continue
                check_id = str(finding.get("check_id") or f"legacy:{index}")
                page_url = str(finding.get("page_url") or audit.get("url") or "")
                conn.execute(
                    """
                    INSERT OR REPLACE INTO findings (
                        audit_id, check_id, page_url, severity, category, message
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        audit_id,
                        check_id,
                        page_url,
                        finding.get("severity"),
                        finding.get("category"),
                        finding.get("message") or finding.get("defect"),
                    ),
                )
        return audit_id

    def latest(self, domain: str, *, exclude_audit_id: str | None = None) -> dict[str, Any] | None:
        query = "SELECT * FROM audits WHERE domain = ?"
        params: list[Any] = [domain.lower()]
        if exclude_audit_id:
            query += " AND audit_id <> ?"
            params.append(exclude_audit_id)
        query += " ORDER BY captured_at DESC, rowid DESC LIMIT 1"
        with self.connect() as conn:
            row = conn.execute(query, params).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload_json"])
        payload["_history_audit_id"] = row["audit_id"]
        return payload

    def count(self, domain: str | None = None) -> int:
        with self.connect() as conn:
            if domain:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM audits WHERE domain = ?", (domain.lower(),)
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) AS n FROM audits").fetchone()
        return int(row["n"])

    def record_verification(
        self,
        domain: str,
        before_audit_id: str,
        after_audit_id: str,
        report: dict[str, Any],
    ) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO verifications (
                    domain, before_audit_id, after_audit_id, created_at,
                    introduced_count, resolved_count, report_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    domain.lower(),
                    before_audit_id,
                    after_audit_id,
                    utc_now(),
                    int(report.get("introduced_count", 0)),
                    int(report.get("resolved_count", 0)),
                    json.dumps(report, sort_keys=True, default=str),
                ),
            )
            return int(cursor.lastrowid)

    def recent_regressions(self, domain: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        query = "SELECT * FROM verifications WHERE introduced_count > 0"
        params: list[Any] = []
        if domain:
            query += " AND domain = ?"
            params.append(domain.lower())
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, int(limit)))
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "verification_id": row["verification_id"],
                "domain": row["domain"],
                "before_audit_id": row["before_audit_id"],
                "after_audit_id": row["after_audit_id"],
                "created_at": row["created_at"],
                "introduced_count": row["introduced_count"],
                "resolved_count": row["resolved_count"],
                "report": json.loads(row["report_json"]),
            }
            for row in rows
        ]

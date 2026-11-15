"""Private, offline SQLite ledger for decrypted MoneyMachine review archives.

No network requests, prospect contact lookup, model calls, outreach or payments.
Only the owner explicitly imports a locally decrypted, bounded vault bundle.
Never run against the existing MoneyMachine production database.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

KIND = "website_auditor_encrypted_review_bundle"
MAX_SOURCE_BYTES = 1_000_000
MAX_SITES = 10
MAX_FINDINGS_PER_SITE = 20
HOST = re.compile(r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
SCHEMA = """
CREATE TABLE IF NOT EXISTS imports (
    source_hash TEXT PRIMARY KEY,
    imported_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sites (
    domain TEXT PRIMARY KEY,
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    last_run_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scan_runs (
    domain TEXT NOT NULL REFERENCES sites(domain),
    run_id TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    PRIMARY KEY (domain, run_id)
);
CREATE TABLE IF NOT EXISTS findings (
    domain TEXT NOT NULL REFERENCES sites(domain),
    finding_id TEXT NOT NULL,
    defect_key TEXT NOT NULL,
    severity TEXT NOT NULL,
    observation TEXT NOT NULL,
    remediation_action TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    observed_scans INTEGER NOT NULL DEFAULT 1 CHECK(observed_scans >= 1),
    review_state TEXT NOT NULL DEFAULT 'PENDING_REVIEW'
       CHECK(review_state IN ('PENDING_REVIEW','ACKNOWLEDGED','DISMISSED')),
    PRIMARY KEY(domain, finding_id)
);
CREATE TABLE IF NOT EXISTS internal_drafts (
    domain TEXT NOT NULL,
    run_id TEXT NOT NULL,
    body TEXT NOT NULL,
    approval_state TEXT NOT NULL DEFAULT 'HUMAN_REVIEW_REQUIRED'
       CHECK(approval_state = 'HUMAN_REVIEW_REQUIRED'),
    sent INTEGER NOT NULL DEFAULT 0 CHECK(sent = 0),
    PRIMARY KEY(domain, run_id),
    FOREIGN KEY(domain, run_id) REFERENCES scan_runs(domain, run_id)
);
CREATE INDEX IF NOT EXISTS idx_findings_review ON findings(review_state);
CREATE INDEX IF NOT EXISTS idx_scans_date ON scan_runs(observed_at);
"""


def _is_safe_db_location(path: Path) -> Path:
    """Never put a private plaintext database inside the public Git checkout."""
    path = Path(path).expanduser().absolute()
    if path.suffix != ".sqlite3":
        raise ValueError("Use an explicit private .sqlite3 database path")
    if path.is_symlink():
        raise ValueError("Refusing symlink database paths")
    if not path.parent.is_dir():
        raise ValueError("Create the private destination directory first")
    # Follow and check every ancestor to block a symlink redirect into source.
    path = path.parent.resolve() / path.name
    project = Path(__file__).resolve().parents[1]
    if path == project or project in path.parents:
        raise ValueError("Database must be outside the public source checkout")
    if path.exists() and (not path.is_file() or path.stat().st_mode & 0o077):
        raise ValueError("Existing private database must be a 0600 file")
    return path


def _open_database(path: Path) -> sqlite3.Connection:
    path = _is_safe_db_location(path)
    if not path.exists():
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
        os.close(fd)
    db = sqlite3.connect(str(path), timeout=15)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=15000")
    db.executescript(SCHEMA)
    if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        db.close()
        raise ValueError("Local ledger integrity check failed")
    return db


def _timestamp(value: object) -> str:
    if not isinstance(value, str) or len(value) > 80:
        raise ValueError("Invalid audit timestamp")
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if date.tzinfo is None:
            raise ValueError("Timezone required")
        return date.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid audit timestamp") from exc


def _short(value: object, limit: int, label: str) -> str:
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError("Invalid " + label)
    return value


def _validated_sites(bundle: object) -> list[dict]:
    if (not isinstance(bundle, dict) or bundle.get("schema_version") != 1
            or bundle.get("kind") != KIND
            or bundle.get("allowlist_only") is not True
            or bundle.get("owner_review_required") is not True
            or bundle.get("external_sends") != 0
            or bundle.get("paid_calls") != 0):
        raise ValueError("Invalid or non-review-only vault bundle")
    sites = bundle.get("sites")
    if not isinstance(sites, list) or len(sites) > MAX_SITES:
        raise ValueError("Invalid bounded site list")
    validated = []
    seen_runs = set()
    for site in sites:
        if not isinstance(site, dict) or site.get("outbound_sent") != 0:
            raise ValueError("An unsent site record is required")
        domain = _short(site.get("domain"), 253, "site domain")
        if not (HOST.fullmatch(domain) and "." in domain
                and not domain.endswith((".local", ".internal", ".localhost"))):
            raise ValueError("Invalid public domain")
        status = site.get("status")
        if status not in {"COMPLETE", "INCOMPLETE", "ERROR"}:
            raise ValueError("Invalid audit status")
        if status != "COMPLETE":
            if site.get("findings") not in ([], None):
                raise ValueError("Incomplete scans cannot supply findings")
            validated.append({"domain": domain, "status": status})
            continue
        run_id = _short(site.get("run_id"), 120, "run ID")
        if not run_id or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", run_id):
            raise ValueError("Invalid run ID")
        identity = (domain, run_id)
        if identity in seen_runs:
            raise ValueError("Duplicate run in same archive")
        seen_runs.add(identity)
        observed_at = _timestamp(site.get("timestamp"))
        findings = site.get("findings")
        if not isinstance(findings, list) or len(findings) > MAX_FINDINGS_PER_SITE:
            raise ValueError("Invalid bounded finding list")
        clean = []
        ids = set()
        for item in findings:
            if not isinstance(item, dict):
                raise ValueError("Invalid finding")
            finding_id = _short(item.get("finding_id"), 100, "finding ID")
            defect_key = _short(item.get("defect_key"), 80, "defect key")
            if not IDENTIFIER.fullmatch(finding_id) or not IDENTIFIER.fullmatch(defect_key):
                raise ValueError("Invalid finding identifier")
            if finding_id in ids:
                raise ValueError("Duplicate finding identifier in a run")
            ids.add(finding_id)
            severity = item.get("severity")
            if severity not in {"low", "medium", "high", "critical"}:
                raise ValueError("Invalid severity")
            clean.append({
                "finding_id": finding_id,
                "defect_key": defect_key,
                "severity": severity,
                "observation": _short(item.get("observed"), 500, "observation"),
                "remediation_action": _short(
                    item.get("remediation_action"), 500, "remediation action"
                ),
            })
        draft = site.get("internal_scope_draft")
        if draft is not None:
            draft = _short(draft, 9000, "internal scope draft")
            if (not draft.startswith("INTERNAL SCOPE DRAFT - DO NOT SEND")
                    or site.get("approval_status") != "HUMAN_REVIEW_REQUIRED"):
                raise ValueError("Only unapproved internal drafts may be imported")
        validated.append({
            "domain": domain, "status": "COMPLETE", "run_id": run_id,
            "observed_at": observed_at, "findings": clean, "draft": draft,
        })
    return validated


def import_bundle(bundle: dict, db_path: Path) -> dict:
    """Idempotent, atomic import; never infer resolved issues from missing rows."""
    sites = _validated_sites(bundle)  # Validate everything before changing DB.
    fingerprint = hashlib.sha256(
        json.dumps(bundle, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    imported_at = datetime.now(timezone.utc).isoformat()
    counts = {"new_runs": 0, "new_findings": 0, "updated_findings": 0,
              "internal_drafts": 0, "incomplete": 0, "duplicate_archive": False}
    db = _open_database(db_path)
    try:
        with db:
            duplicate = db.execute(
                "SELECT 1 FROM imports WHERE source_hash=?", (fingerprint,)
            ).fetchone()
            if duplicate:
                counts["duplicate_archive"] = True
                return counts
            for site in sites:
                if site["status"] != "COMPLETE":
                    counts["incomplete"] += 1
                    continue
                host, run_id, observed = (
                    site["domain"], site["run_id"], site["observed_at"]
                )
                existing = db.execute(
                    "SELECT 1 FROM scan_runs WHERE domain=? AND run_id=?",
                    (host, run_id),
                ).fetchone()
                if existing:
                    continue  # Reimporting a run from another archive is safe.
                db.execute(
                    """INSERT INTO sites(domain,first_observed_at,last_observed_at,last_run_id)
                       VALUES(?,?,?,?)
                       ON CONFLICT(domain) DO UPDATE SET
                       first_observed_at=MIN(sites.first_observed_at,excluded.first_observed_at),
                       last_observed_at=MAX(sites.last_observed_at,excluded.last_observed_at),
                       last_run_id=CASE WHEN excluded.last_observed_at >= sites.last_observed_at
                                        THEN excluded.last_run_id ELSE sites.last_run_id END""",
                    (host, observed, observed, run_id),
                )
                db.execute(
                    "INSERT INTO scan_runs(domain,run_id,observed_at) VALUES(?,?,?)",
                    (host, run_id, observed),
                )
                counts["new_runs"] += 1
                for item in site["findings"]:
                    row = db.execute(
                        "SELECT 1 FROM findings WHERE domain=? AND finding_id=?",
                        (host, item["finding_id"]),
                    ).fetchone()
                    if row:
                        db.execute(
                            """UPDATE findings SET
                               last_seen_at=MAX(last_seen_at,?),
                               observed_scans=observed_scans+1,
                               observation=CASE WHEN ? >= last_seen_at
                                   THEN ? ELSE observation END,
                               remediation_action=CASE WHEN ? >= last_seen_at
                                   THEN ? ELSE remediation_action END,
                               severity=CASE WHEN ? >= last_seen_at
                                   THEN ? ELSE severity END
                               WHERE domain=? AND finding_id=?""",
                            (observed, observed, item["observation"],
                             observed, item["remediation_action"],
                             observed, item["severity"], host, item["finding_id"]),
                        )
                        counts["updated_findings"] += 1
                    else:
                        db.execute(
                            """INSERT INTO findings(domain,finding_id,defect_key,severity,
                               observation,remediation_action,first_seen_at,last_seen_at)
                               VALUES(?,?,?,?,?,?,?,?)""",
                            (host, item["finding_id"], item["defect_key"],
                             item["severity"], item["observation"],
                             item["remediation_action"], observed, observed),
                        )
                        counts["new_findings"] += 1
                if site["draft"]:
                    db.execute(
                        """INSERT INTO internal_drafts(domain,run_id,body)
                           VALUES(?,?,?)""", (host, run_id, site["draft"]),
                    )
                    counts["internal_drafts"] += 1
            db.execute(
                "INSERT INTO imports(source_hash,imported_at) VALUES(?,?)",
                (fingerprint, imported_at),
            )
    finally:
        db.close()
    return counts


def summarize(db_path: Path) -> dict:
    if not Path(db_path).exists():
        raise ValueError("No local private database exists yet")
    db = _open_database(db_path)
    try:
        return {
            "sites": db.execute("SELECT count(*) FROM sites").fetchone()[0],
            "distinct_runs": db.execute("SELECT count(*) FROM scan_runs").fetchone()[0],
            "distinct_findings": db.execute("SELECT count(*) FROM findings").fetchone()[0],
            "pending_review": db.execute(
                "SELECT count(*) FROM findings WHERE review_state='PENDING_REVIEW'"
            ).fetchone()[0],
            "internal_drafts": db.execute(
                "SELECT count(*) FROM internal_drafts").fetchone()[0],
        }
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Owner-only offline review ledger")
    sub = parser.add_subparsers(dest="command", required=True)
    incoming = sub.add_parser("import", help="Import a locally decrypted vault bundle")
    incoming.add_argument("--input", type=Path, required=True)
    incoming.add_argument("--db", type=Path, required=True)
    status = sub.add_parser("summary", help="Show counts only, no client details")
    status.add_argument("--db", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "import":
        source = args.input.expanduser()
        if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_SOURCE_BYTES:
            raise ValueError("Invalid or oversized private input")
        bundle = json.loads(source.read_text(encoding="utf-8"))
        result = import_bundle(bundle, args.db)
    else:
        result = summarize(args.db)
    # No site URLs, individual findings, customer information or drafts in stdout.
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

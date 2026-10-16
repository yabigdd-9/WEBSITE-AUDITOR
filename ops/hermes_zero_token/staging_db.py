#!/usr/bin/env python3
"""
HERMES_ZERO_TOKEN Staging Database Worker (P2)

Safety: this module NEVER writes to the production database.
It creates a staging copy, runs a BOUNDED batch of audit-backfill against the
staging copy, validates schema + integrity, and produces a before/after diff.
Promotion to production requires explicit human approval.
"""

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

PROD_DB = PROJECT_ROOT / "database" / "money_machine.db"
STAGING_DIR = PROJECT_ROOT / "state" / "hermes_zero_token" / "staging"
STAGING_DB = STAGING_DIR / "money_machine_staging.db"
STATE_FILE = STAGING_DIR / "staging_state.json"
REPORT_PATH = STAGING_DIR / "staging_report.json"

BATCH_SIZE = int(os.environ.get("ZA_STAGING_BATCH", "5"))

os.environ["HERMES_ZERO_TOKEN_MODE"] = "ZERO_LLM"
os.environ["HERMES_ALLOW_HOSTED_LLM"] = "0"
os.environ["HERMES_ALLOW_PAID_FALLBACK"] = "0"
os.environ["WEBSITE_AUDITOR_OUTREACH_SEND"] = "0"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _validate_staging_path():
    production = PROD_DB.resolve()
    staging = STAGING_DB.resolve()
    if staging == production or not staging.is_relative_to(STAGING_DIR.resolve()):
        raise ValueError("Staging database must be isolated from production")
    for suffix in ("", "-wal", "-shm"):
        candidate = STAGING_DB.with_name(STAGING_DB.name + suffix)
        if candidate.is_symlink() or (candidate.exists() and production.exists()
                                      and os.path.samefile(candidate, production)):
            raise ValueError("Staging database aliases production")


def snapshot_db():
    _validate_staging_path()
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        p = STAGING_DB.with_name(STAGING_DB.name + suffix)
        if p.exists():
            p.unlink()
    src = sqlite3.connect(f"file:{PROD_DB}?mode=ro", uri=True)
    dst = sqlite3.connect(str(STAGING_DB))
    src.backup(dst)
    dst.close()
    src.close()
    return STAGING_DB


def table_counts(db_path):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )]
    counts = {}
    for t in tables:
        try:
            counts[t] = conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        except Exception as e:
            counts[t] = f"error: {e}"
    conn.close()
    return counts


def validate_schema(db_path):
    def get_schema(path):
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        schema = {r[0]: r[1] for r in conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
        )}
        conn.close()
        return schema

    prod = get_schema(str(PROD_DB))
    stage = get_schema(str(db_path))
    missing = [t for t in prod if t not in stage]
    extra = [t for t in stage if t not in prod]
    mismatched = [t for t in prod if t in stage and prod[t] != stage[t]]
    return {
        "ok": not missing and not extra and not mismatched,
        "missing_tables": missing,
        "extra_tables": extra,
        "mismatched_schema": mismatched,
    }


def get_next_batch(db_path, batch_size):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, name, public_website FROM businesses "
        "WHERE is_dummy=0 AND NOT EXISTS("
        "  SELECT 1 FROM mm_evidence e WHERE e.business_id=businesses.id) "
        "ORDER BY id LIMIT ?",
        (batch_size,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def run_audit_batch_staging(ids):
    _validate_staging_path()
    code = (
        "import sys; sys.path.insert(0, r'%s/money-machine')" % PROJECT_ROOT
        + "\nfrom mm_core import connect\n"
        + "from mm_evidence_ops import audit_backfill\n"
        + "import json\n"
        + "with connect(r'%s') as d:\n" % str(STAGING_DB)
        + "    result = audit_backfill(d, ids=%s, politeness=0.0)\n" % json.dumps(ids)
        + "    d.commit()\n"
        + "    print(json.dumps(result, default=str))\n"
    )
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv-email" / "bin" / "python"), "-c", code],
        capture_output=True, text=True, timeout=180,
    )
    return result.returncode, result.stdout, result.stderr


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            pass
    return {"batches_run": 0, "total_processed": 0, "last_run": None}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


def main():
    report = {
        "generated_at": _now(),
        "phase": "P2",
        "staging_db": str(STAGING_DB),
        "production_db": str(PROD_DB),
        "production_written": False,
        "batch_size": BATCH_SIZE,
    }

    snapshot_db()
    report["staging_size_bytes"] = STAGING_DB.stat().st_size
    report["before_counts"] = table_counts(str(STAGING_DB))
    report["schema_validation"] = validate_schema(str(STAGING_DB))

    batch = get_next_batch(str(STAGING_DB), BATCH_SIZE)
    report["batch_size_actual"] = len(batch)
    report["batch_ids"] = [b["id"] for b in batch]
    report["batch_names"] = [b["name"] for b in batch]

    if batch:
        rc, stdout, stderr = run_audit_batch_staging([b["id"] for b in batch])
        report["audit_returncode"] = rc
        try:
            report["audit_result"] = json.loads(stdout.strip().split("\n")[-1])
        except (json.JSONDecodeError, IndexError):
            report["audit_result"] = {"raw_stdout": stdout[:500], "raw_stderr": stderr[:500]}
    else:
        report["audit_result"] = {"message": "no businesses pending audit"}

    report["after_counts"] = table_counts(str(STAGING_DB))
    report["before_after_diff"] = {
        t: {
            "before": report["before_counts"].get(t, 0),
            "after": report["after_counts"].get(t, 0),
            "delta": report["after_counts"].get(t, 0) - report["before_counts"].get(t, 0),
        }
        for t in set(report["before_counts"]) | set(report["after_counts"])
        if report["before_counts"].get(t, 0) != report["after_counts"].get(t, 0)
    }

    conn = sqlite3.connect(f"file:{STAGING_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    report["staging_integrity"] = conn.execute("PRAGMA integrity_check").fetchone()[0]
    report["staging_foreign_key_violations"] = [dict(r) for r in conn.execute("PRAGMA foreign_key_check").fetchall()]
    conn.close()

    state = load_state()
    state["batches_run"] += 1
    state["total_processed"] += len(batch)
    state["last_run"] = _now()
    save_state(state)
    report["staging_state"] = state

    REPORT_PATH.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))
    return 0 if (report.get("audit_returncode", 0) == 0
                 and report["schema_validation"]["ok"]
                 and report["staging_integrity"] == "ok"
                 and not report["staging_foreign_key_violations"]) else 1


if __name__ == "__main__":
    sys.exit(main())

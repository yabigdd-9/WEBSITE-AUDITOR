#!/usr/bin/env python3
"""
HERMES_ZERO_TOKEN Staging Database Worker (P2)

Safety: this module NEVER writes to the production database.
It creates a staging copy, runs a BOUNDED batch of audit-backfill against the
staging copy, validates schema + integrity, and produces a before/after diff.
Promotion to production requires explicit human approval.
"""

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from ops.hermes_zero_token.worker_ownership import (  # noqa: E402
    ZERO_TOKEN_ENV,
    run_owned_worker,
    worker_lock,
)

PROD_DB = PROJECT_ROOT / "database" / "money_machine.db"
STAGING_DIR = PROJECT_ROOT / "state" / "hermes_zero_token" / "staging"
GENERATION_LABEL = os.environ.get("ZA_STAGING_GENERATION")
if GENERATION_LABEL is not None and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", GENERATION_LABEL):
    raise ValueError("ZA_STAGING_GENERATION must be a short, safe generation label")
WORK_DIR = STAGING_DIR / "generations" / GENERATION_LABEL if GENERATION_LABEL else STAGING_DIR
STAGING_DB = WORK_DIR / "money_machine_staging.db"
STATE_FILE = WORK_DIR / "staging_state.json"
REPORT_PATH = WORK_DIR / "staging_report.json"

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


def _atomic_json(path, document):
    descriptor, name = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(document, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _hash_file(path, deadline=None):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("Staging snapshot deadline exceeded")
            digest.update(chunk)
    return digest.hexdigest()


def _read_only(path):
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)


def _check_database(path, deadline=None):
    with closing(_read_only(path)) as conn:
        if deadline is not None:
            conn.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
        try:
            if conn.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise ValueError("Staging database integrity failed; existing files preserved")
            if conn.execute("PRAGMA foreign_key_check").fetchone():
                raise ValueError("Staging database foreign-key check failed; existing files preserved")
        except sqlite3.OperationalError as exc:
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("Staging database validation deadline exceeded") from exc
            raise


def _snapshot_metadata_path():
    return STAGING_DB.with_suffix(".snapshot.json")


def _source_identity():
    source = PROD_DB.resolve(strict=True)
    info = source.stat()
    return {"path": str(source), "device": info.st_dev, "inode": info.st_ino}


def snapshot_metadata():
    metadata_path = _snapshot_metadata_path()
    if metadata_path.is_symlink():
        raise ValueError("Snapshot metadata cannot be a symlink")
    record = json.loads(metadata_path.read_text())
    if (not isinstance(record, dict) or record.get("source") != _source_identity()
            or record.get("target") != str(STAGING_DB.resolve())
            or not isinstance(record.get("generation"), str)
            or not re.fullmatch(r"[0-9a-f]{32}", record["generation"])):
        raise ValueError("Snapshot generation/source identity mismatch; select a new generation")
    return record


def _publish_snapshot(record, pending, deadline=None):
    prepared = Path(record["prepared_path"])
    if (prepared.parent.resolve() != STAGING_DB.parent.resolve()
            or not prepared.name.startswith(".snapshot-") or prepared.is_symlink()):
        raise ValueError("Invalid prepared snapshot path")
    if record.get("source") != _source_identity() or record.get("target") != str(STAGING_DB.resolve()):
        raise ValueError("Prepared snapshot identity mismatch")
    if not STAGING_DB.exists():
        if _hash_file(prepared, deadline) != record["initial_sha256"]:
            raise ValueError("Prepared snapshot changed")
        # link is atomic and refuses an existing target; never overwrite progress.
        os.link(prepared, STAGING_DB)
    if _hash_file(STAGING_DB, deadline) != record["initial_sha256"]:
        raise ValueError("Unpublished staging database changed; retain for review")
    _check_database(STAGING_DB, deadline)
    os.replace(pending, _snapshot_metadata_path())
    if prepared.exists() and os.path.samefile(prepared, STAGING_DB):
        prepared.unlink()


def snapshot_db(timeout_seconds=30):
    with worker_lock(PROJECT_ROOT / "state/hermes_zero_token/locks", "staging_db"):
        return _snapshot_db(timeout_seconds)


def _snapshot_db(timeout_seconds):
    """Create once, then reuse a generation; never reset an existing snapshot.

    A fresh generation is an explicit ZA_STAGING_GENERATION label. Legacy
    unlabelled databases without a manifest stay intact and require review.
    """
    if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
            or not 0 < timeout_seconds <= 300):
        raise ValueError("Snapshot timeout must be finite and between 0 and 300 seconds")
    deadline = time.monotonic() + timeout_seconds
    _validate_staging_path()
    STAGING_DB.parent.mkdir(parents=True, exist_ok=True)
    metadata = _snapshot_metadata_path()
    if metadata.is_symlink():
        raise ValueError("Snapshot metadata cannot be a symlink")
    pending = metadata.with_suffix(".json.pending")
    if pending.is_symlink():
        raise ValueError("Pending snapshot metadata cannot be a symlink")
    if not metadata.exists() and pending.exists():
        _publish_snapshot(json.loads(pending.read_text()), pending, deadline)
    if STAGING_DB.exists():
        if not metadata.is_file():
            raise ValueError("Existing staging data has no generation manifest; preserve it and select a new generation")
        snapshot_metadata()
        _check_database(STAGING_DB, deadline)
        return STAGING_DB
    if metadata.exists():
        raise ValueError("Snapshot generation database is missing; preserve metadata for review")
    descriptor, name = tempfile.mkstemp(prefix=".snapshot-", suffix=".db", dir=STAGING_DB.parent)
    os.close(descriptor)
    prepared = Path(name)
    record_published = False

    def progress(*_args):
        if time.monotonic() >= deadline:
            raise TimeoutError("Staging snapshot deadline exceeded")

    try:
        source = _source_identity()
        with closing(_read_only(PROD_DB)) as src, closing(sqlite3.connect(prepared)) as dst:
            src.backup(dst, pages=128, progress=progress, sleep=0.01)
        _check_database(prepared, deadline)
        with closing(_read_only(prepared)) as conn:
            has_evidence = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='mm_evidence'").fetchone()
            initial_max = conn.execute("SELECT coalesce(max(id),0) FROM mm_evidence").fetchone()[0] if has_evidence else 0
        record = {"generation": uuid.uuid4().hex, "created_at": _now(),
                  "source": source, "target": str(STAGING_DB.resolve()),
                  "prepared_path": str(prepared), "initial_sha256": _hash_file(prepared, deadline),
                  "initial_evidence_max_id": initial_max}
        _atomic_json(pending, record)
        record_published = True
        _publish_snapshot(record, pending, deadline)
    finally:
        # A published pending record is recovery evidence, not disposable scratch.
        if prepared.exists() and not record_published:
            prepared.unlink()
    return STAGING_DB


def table_counts(db_path):
    conn = _read_only(Path(db_path))
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )]
    counts = {}
    for t in tables:
        try:
            quoted = '"' + t.replace('"', '""') + '"'
            counts[t] = conn.execute(f"SELECT count(*) FROM {quoted}").fetchone()[0]
        except Exception as e:
            counts[t] = f"error: {e}"
    conn.close()
    return counts


def validate_schema(db_path):
    def get_schema(path):
        conn = _read_only(Path(path))
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
    conn = _read_only(Path(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, name, public_website FROM businesses "
        "WHERE is_dummy=0 AND public_website IS NOT NULL "
        "AND trim(public_website) != '' AND NOT EXISTS("
        "  SELECT 1 FROM mm_evidence e WHERE e.business_id=businesses.id) "
        "ORDER BY id LIMIT ?",
        (batch_size,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def run_audit_batch_staging(ids):
    _validate_staging_path()
    code = (
        "import sys; sys.path.insert(0, sys.argv[1])"
        + "\nfrom mm_core import connect\n"
        + "from mm_evidence_ops import audit_backfill\n"
        + "import json\n"
        + "with connect(sys.argv[2]) as d:\n"
        + "    result = audit_backfill(d, ids=json.loads(sys.argv[3]), "
        + "capture_dir=sys.argv[4], politeness=0.0)\n"
        + "    d.commit()\n"
        + "    print(json.dumps(result, default=str))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(PROJECT_ROOT / "money-machine"),
         str(STAGING_DB), json.dumps(ids), str(STAGING_DB.parent / "captures")],
        capture_output=True, text=True, timeout=180,
        env={**os.environ, **ZERO_TOKEN_ENV, "MM_ROOT": str(STAGING_DB.parent)},
    )
    return result.returncode, result.stdout, result.stderr


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError as exc:
            raise ValueError("Existing staging state is malformed; preserve it for review") from exc
    return {"batches_run": 0, "total_processed": 0, "last_run": None}


def save_state(state):
    _atomic_json(STATE_FILE, state)


def _main():
    report = {
        "generated_at": _now(),
        "phase": "P2",
        "staging_db": str(STAGING_DB),
        "production_db": str(PROD_DB),
        "production_written": False,
        "batch_size": BATCH_SIZE,
    }

    snapshot_db()
    generation = snapshot_metadata()
    report["snapshot_generation"] = generation["generation"]
    report["staging_size_bytes"] = STAGING_DB.stat().st_size
    report["before_counts"] = table_counts(str(STAGING_DB))
    report["schema_validation"] = validate_schema(str(STAGING_DB))
    if not report["schema_validation"]["ok"]:
        report["error"] = "Source schema changed; select an explicit new staging generation"
        _atomic_json(REPORT_PATH, report)
        print(json.dumps(report, indent=2))
        return 1
    state = load_state()
    if not isinstance(state, dict):
        raise ValueError("Existing staging state must be an object")
    if state.get("generation") == generation["generation"] and (
        type(state.get("batches_run")) is not int or state["batches_run"] < 0
    ):
        raise ValueError("Staging batch counter is malformed; preserve state for review")

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

    conn = _read_only(STAGING_DB)
    conn.row_factory = sqlite3.Row
    report["staging_integrity"] = conn.execute("PRAGMA integrity_check").fetchone()[0]
    report["staging_foreign_key_violations"] = [dict(r) for r in conn.execute("PRAGMA foreign_key_check").fetchall()]
    conn.close()

    if state.get("generation") != generation["generation"]:
        state = {"generation": generation["generation"], "batches_run": 0,
                 "total_processed": 0, "last_run": None, "prior_state": state}
    state["batches_run"] += 1
    with closing(_read_only(STAGING_DB)) as conn:
        state["total_processed"] = conn.execute(
            "SELECT count(DISTINCT business_id) FROM mm_evidence WHERE id > ?",
            (generation["initial_evidence_max_id"],)).fetchone()[0]
    state["progress_scope"] = "Distinct businesses with staging evidence added since this snapshot; not verified live audit acceptance"
    state["last_run"] = _now()
    save_state(state)
    report["staging_state"] = state

    _atomic_json(REPORT_PATH, report)
    print(json.dumps(report, indent=2, default=str))
    return 0 if (report.get("audit_returncode", 0) == 0
                 and report["schema_validation"]["ok"]
                 and report["staging_integrity"] == "ok"
                 and not report["staging_foreign_key_violations"]) else 1


def main():
    return run_owned_worker(PROJECT_ROOT, 'staging_db', _main)


if __name__ == "__main__":
    sys.exit(main())

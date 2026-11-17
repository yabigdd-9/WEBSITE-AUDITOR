"""Optional, owner-controlled PostgreSQL backup of sealed MoneyMachine checkpoints.

IMPORTANT: This is NOT automatically connected to GitHub Actions. This module
never writes plaintext to PostgreSQL, logs credentials, or performs outreach.
Use only after a reviewed migration, least-privilege login and restore drill.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

MIN_BLOB_BYTES = 100
MAX_BLOB_BYTES = 8_000_000
MAX_REVISIONS = 24
CHECKPOINT_ID = "money_machine"
LOCK_CLASS = 20261118
LOCK_ID = 1


def verify_encrypted_checkpoint(blob: bytes, state_key: str) -> None:
    """Decrypt only in trusted process memory to reject unrelated/corrupt tokens."""
    if not isinstance(blob, bytes) or not MIN_BLOB_BYTES <= len(blob) <= MAX_BLOB_BYTES:
        raise ValueError("Invalid bounded encrypted checkpoint")
    from cryptography.fernet import Fernet

    raw = Fernet(state_key.encode("ascii")).decrypt(blob)
    if len(raw) > 5_000_000:
        raise ValueError("Plaintext state exceeds worker bound")
    from scripts.pipeline_store import validate

    state = json.loads(raw)
    validate(state)


def _private_output(path: Path, blob: bytes) -> None:
    target = Path(path).expanduser()
    if target.is_symlink() or not target.parent.is_dir():
        raise ValueError("Output must be a new regular file")
    fd = os.open(
        target, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(blob)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def validate_supabase_dsn(dsn: str, *, expected_ref: str) -> None:
    """Refuse insecure transports, generic hosts, and the wrong Supabase project."""
    from psycopg.conninfo import conninfo_to_dict

    if not isinstance(expected_ref, str) or not expected_ref.isalnum() or len(expected_ref) != 20:
        raise ValueError("Expected Supabase project reference required")
    if not dsn or len(dsn) > 4096:
        raise ValueError("Database connection is missing or oversized")
    options = conninfo_to_dict(dsn)
    host = options.get("host", "").lower().rstrip(".")
    if not host or "," in host or "/" in host or options.get("hostaddr"):
        raise ValueError("A single named remote host is required")
    direct = host == f"db.{expected_ref}.supabase.co"
    pooled = host.endswith(".pooler.supabase.com") and (
        options.get("user", "").endswith("." + expected_ref)
    )
    if not (direct or pooled):
        raise ValueError("Database host or pool user does not match intended Supabase project")
    if options.get("sslmode") != "verify-full":
        raise ValueError("TLS certificate verification (sslmode=verify-full) is required")
    if options.get("user", "").split(".")[0] in {"postgres", "supabase_admin"}:
        raise ValueError("Use an approved dedicated database login, not the administrator")


class SealedCheckpointStore:
    """Transactional compare-and-swap checkpoint mirror with complete history.

    Every put requires the revision the owner just read. No initial write can
    silently replace existing content. The lock and current/history writes
    share a single transaction; rollback preserves the old checkpoint.
    """

    def __init__(self, connect):
        self.connect = connect

    def put(self, blob: bytes, key: str, *, expected_revision: int) -> int:
        verify_encrypted_checkpoint(blob, key)
        if type(expected_revision) is not int or not 0 <= expected_revision < MAX_REVISIONS:
            raise ValueError("Expected revision must be an integer between 0 and 23")
        checksum = hashlib.sha256(blob).hexdigest()
        with self.connect() as db:
            with db.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(%s,%s)", (LOCK_CLASS, LOCK_ID))
                cur.execute(
                    "SELECT revision,ciphertext,sha256 FROM mm_internal.encrypted_checkpoints "
                    "WHERE id=%s FOR UPDATE", (CHECKPOINT_ID,),
                )
                existing = cur.fetchone()
                actual = existing[0] if existing else 0
                if actual != expected_revision:
                    raise ValueError("Checkpoint revision conflict; owner recovery required")
                if existing:
                    old_blob = bytes(existing[1])
                    if hashlib.sha256(old_blob).hexdigest() != existing[2]:
                        raise ValueError("Existing checkpoint checksum invalid")
                    # Never overwrite history encrypted under a different/lost
                    # key. Key rotation needs explicit decrypt/re-encrypt plan.
                    verify_encrypted_checkpoint(old_blob, key)
                next_revision = actual + 1
                if next_revision > MAX_REVISIONS:
                    raise ValueError("Revision limit reached; archive and review retention")
                cur.execute(
                    "INSERT INTO mm_internal.encrypted_checkpoint_history "
                    "(revision,ciphertext,sha256) VALUES (%s,%s,%s)",
                    (next_revision, blob, checksum),
                )
                if existing:
                    cur.execute(
                        "UPDATE mm_internal.encrypted_checkpoints SET "
                        "revision=%s,ciphertext=%s,sha256=%s,saved_at=clock_timestamp() "
                        "WHERE id=%s AND revision=%s",
                        (next_revision, blob, checksum, CHECKPOINT_ID, actual),
                    )
                else:
                    cur.execute(
                        "INSERT INTO mm_internal.encrypted_checkpoints "
                        "(id,revision,ciphertext,sha256) VALUES (%s,%s,%s,%s)",
                        (CHECKPOINT_ID, next_revision, blob, checksum),
                    )
                if cur.rowcount != 1:
                    raise ValueError("Checkpoint write conflict; state left unchanged")
        return next_revision

    def read(self, key: str) -> tuple[int, bytes]:
        with self.connect() as db:
            with db.cursor() as cur:
                cur.execute(
                    "SELECT revision,ciphertext,sha256 "
                    "FROM mm_internal.encrypted_checkpoints WHERE id=%s",
                    (CHECKPOINT_ID,),
                )
                result = cur.fetchone()
        if not result:
            raise ValueError("No saved checkpoint; explicit initial import required")
        revision, blob, digest = result
        blob = bytes(blob)
        if type(revision) is not int or not 1 <= revision <= MAX_REVISIONS:
            raise ValueError("Invalid saved checkpoint revision")
        if hashlib.sha256(blob).hexdigest() != digest:
            raise ValueError("Checkpoint integrity check failed")
        verify_encrypted_checkpoint(blob, key)
        return revision, blob


def _connect_from_environment():
    import psycopg

    url = os.environ["WA_PG_DATABASE_URL"]
    validate_supabase_dsn(
        url, expected_ref=os.environ["WA_SUPABASE_PROJECT_REF"],
    )
    # Driver returns a transaction-scoped connection; no autocommit.
    return psycopg.connect(url, connect_timeout=8, application_name="mm-checkpoint-only")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Optional encrypted Postgres checkpoint mirror")
    sub = parser.add_subparsers(dest="operation", required=True)
    save = sub.add_parser("put")
    save.add_argument("--sealed-file", type=Path, required=True)
    save.add_argument("--expected-revision", type=int, required=True)
    restore = sub.add_parser("get")
    restore.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        from scripts.cloud_review_only_opportunities import _verify_safety

        _verify_safety(Path(__file__).resolve().parents[1])
        state_key = os.environ["WA_PIPELINE_STATE_KEY"]
        store = SealedCheckpointStore(_connect_from_environment)
        if args.operation == "put":
            sealed = args.sealed_file
            if (
                sealed.is_symlink() or not sealed.is_file()
                or not MIN_BLOB_BYTES <= sealed.stat().st_size <= MAX_BLOB_BYTES
            ):
                raise ValueError("Invalid encrypted input")
            version = store.put(
                sealed.read_bytes(), state_key, expected_revision=args.expected_revision,
            )
            print(json.dumps({"checkpoint_revision": version, "encrypted_only": True}))
        else:
            revision, blob = store.read(state_key)
            _private_output(args.output, blob)
            print(json.dumps({"checkpoint_revision": revision, "encrypted_only": True}))
        return 0
    except Exception:
        # No exception text: driver messages can contain hostnames or credentials.
        print("CHECKPOINT OPERATION BLOCKED; no plaintext or connection details logged.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Trusted-device paired exports; no cloud upload, encryption or key handling."""
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path

from scripts.pipeline_store import validate
from scripts.postgres_store import WRITER_LOCK
from scripts.review_ledger import _is_safe_db_location

MAX_BACKUP = 20_000_000
FORMAT = "wa-postgres-backup-v1"


@contextmanager
def locked(store):
    with store.connection() as db:
        if not db.execute("SELECT pg_try_advisory_lock(%s)", (WRITER_LOCK,)).fetchone()[0]:
            raise ValueError("Pause the writer before paired export/recovery")
        try:
            yield db
        finally:
            db.execute("SELECT pg_advisory_unlock(%s)", (WRITER_LOCK,))


def private_location(path):
    result = Path(path).expanduser().absolute()
    _is_safe_db_location(result.with_suffix(".sqlite3"))
    return result


def encode(document):
    return json.dumps(document, sort_keys=True, allow_nan=False).encode()


def export_private(store, destination):
    target = private_location(destination)
    with locked(store) as db, db.transaction():
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        marker = db.execute("SELECT last_committed_job FROM moneymachine.metadata WHERE singleton=1").fetchone()
        content = dict(
            state=store.load(db), last_committed_job=marker[0] if marker else None,
            jobs=db.execute("SELECT id,started,finished,status FROM moneymachine.jobs ORDER BY id").fetchall(),
            reservations=db.execute("SELECT job_id,audit_id,prospect_id,day FROM moneymachine.reservations ORDER BY job_id,audit_id").fetchall())
    envelope = encode(dict(format=FORMAT, content=content, sha256=hashlib.sha256(encode(content)).hexdigest()))
    if len(envelope) > MAX_BACKUP:
        raise ValueError("Backup exceeds bounded local export size")
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(envelope)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def read_private(source):
    path = private_location(source)
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError("Private regular backup required")
    with path.open("rb") as stream:
        raw = stream.read(MAX_BACKUP + 1)
    if len(raw) > MAX_BACKUP:
        raise ValueError("Oversized recovery input")
    document = json.loads(raw)
    if not isinstance(document, dict) or set(document) != {"format", "content", "sha256"} or document["format"] != FORMAT:
        raise ValueError("Invalid paired export")
    content = document["content"]
    if hashlib.sha256(encode(content)).hexdigest() != document["sha256"]:
        raise ValueError("Backup checksum changed")
    if (not isinstance(content, dict) or set(content) != {"state", "last_committed_job", "jobs", "reservations"}
            or not isinstance(content["jobs"], list) or len(content["jobs"]) > 10000
            or not isinstance(content["reservations"], list) or len(content["reservations"]) > 10000):
        raise ValueError("Invalid bounded operational export")
    validate(content["state"])
    return content


def restore_empty(store, source):
    content = read_private(source)
    with locked(store) as db, db.transaction():
        if (store.load(db) is not None
                or db.execute("SELECT count(*) FROM moneymachine.jobs").fetchone()[0]
                or db.execute("SELECT count(*) FROM moneymachine.reservations").fetchone()[0]):
            raise ValueError("Recovery requires an empty migrated destination")
        for row in content["jobs"]:
            db.execute("INSERT INTO moneymachine.jobs VALUES(%s,%s,%s,%s)", row)
        for row in content["reservations"]:
            db.execute("INSERT INTO moneymachine.reservations VALUES(%s,%s,%s,%s)", row)
        store.save(db, content["state"], None, content["last_committed_job"])

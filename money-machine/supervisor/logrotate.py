"""Coordinated JSONL append, bounded-memory compression and owned retention.

Only matching archives created by this module or the legacy rotator expire.
Append and rotation share a directory lock, acquired before opening the log.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import gzip
import json
import math
import os
import re
import shutil
import stat
import tempfile
import uuid
from pathlib import Path

_ARCHIVE = re.compile(r"^(.+\.jsonl)\.\d{8}_\d{6}(?:_[0-9a-f]{8})?\.gz$")


@contextlib.contextmanager
def directory_lock(directory: Path, lock_name: str = ".log-rotation.lock"):
    directory = Path(directory)
    if Path(lock_name).name != lock_name or not lock_name.endswith(".lock"):
        raise ValueError("Lock basename required")
    if directory.is_symlink():
        raise ValueError("Log directory symlinks are unsupported")
    directory.mkdir(parents=True, exist_ok=True)
    fd = os.open(directory / lock_name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("Regular rotation lock required")
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def append_jsonl(path: Path, record: dict) -> None:
    path = Path(path)
    text = json.dumps(record, sort_keys=True, default=str) + "\n"
    with directory_lock(path.parent):
        if path.is_symlink():
            raise ValueError("Log symlinks are unsupported")
        fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())


def maintain_logs(log_dir: Path, max_size_mb: float = 50, retention_days: int = 30,
                  names: set[str] | None = None) -> dict:
    if isinstance(max_size_mb, bool) or not isinstance(max_size_mb, (int, float)) or not math.isfinite(max_size_mb) or max_size_mb <= 0:
        raise ValueError("Positive finite log-size limit required")
    if type(retention_days) is not int or not 1 <= retention_days <= 365:
        raise ValueError("Archive retention must be 1–365 days")
    if names is not None and (not isinstance(names, set) or not names or any(not isinstance(n, str) or Path(n).name != n or not n.endswith(".jsonl") for n in names)):
        raise ValueError("Explicit JSONL basenames required")
    log_dir = Path(log_dir)
    result = {"rotated": [], "expired_removed": [], "retention_days": retention_days,
              "max_size_mb": max_size_mb}
    if not log_dir.exists():
        return result
    now = dt.datetime.now(dt.timezone.utc)
    with directory_lock(log_dir):
        for path in sorted(log_dir.glob("*.jsonl")):
            if names is not None and path.name not in names:
                continue
            if path.is_symlink() or not path.is_file():
                continue
            original = path.stat()
            if original.st_size <= max_size_mb * 1024 * 1024:
                continue
            stamp = now.strftime("%Y%m%d_%H%M%S")
            archive = path.with_name(f"{path.name}.{stamp}_{uuid.uuid4().hex[:8]}.gz")
            fd, temporary = tempfile.mkstemp(prefix=".rotation-", dir=log_dir)
            try:
                with os.fdopen(fd, "wb") as raw:
                    with path.open("rb") as source, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
                        shutil.copyfileobj(source, compressed, length=64 * 1024)
                    raw.flush()
                    os.fsync(raw.fileno())
                current = path.stat()
                if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) != (original.st_dev, original.st_ino, original.st_size, original.st_mtime_ns):
                    raise RuntimeError("Uncoordinated log writer changed the source; original retained")
                os.replace(temporary, archive)
                path.unlink()
                result["rotated"].append(str(archive))
            finally:
                Path(temporary).unlink(missing_ok=True)
        cutoff = now.timestamp() - retention_days * 86400
        for path in sorted(log_dir.glob("*.gz")):
            match = _ARCHIVE.fullmatch(path.name)
            if not match or (names is not None and match.group(1) not in names):
                continue
            if not path.is_symlink() and path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
                result["expired_removed"].append(str(path))
    return result


def rotate_logs(log_dir: Path, max_size_mb: float = 50, retention_days: int = 30) -> list[str]:
    """Retain the existing supervisor-facing list return contract."""
    return maintain_logs(log_dir, max_size_mb, retention_days)["rotated"]

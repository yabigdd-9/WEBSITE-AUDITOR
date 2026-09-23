"""Tests for runtime quarantine and idempotency."""

from pathlib import Path

from auditor_toolkit.runtime.idempotency import IdempotencyStore, make_idempotency_key
from auditor_toolkit.runtime.quarantine import (
    DLQEntry,
    DLQStore,
    QuarantineEntry,
    QuarantineStore,
    quarantine_or_dlq,
)


def test_quarantine_store(tmp_path):
    store = QuarantineStore(tmp_path)
    entry = QuarantineEntry(job_id="job_001", reason="parser error", error_type="PARSER_BUG")
    path = store.add(entry)
    assert path.exists()
    assert len(store.list()) == 1


def test_dlq_store(tmp_path):
    store = DLQStore(tmp_path)
    entry = DLQEntry(job_id="job_002", reason="max retries", retries_exhausted=5)
    path = store.add(entry)
    assert path.exists()
    assert store.count() == 1


def test_quarantine_or_dlq_deterministic(tmp_path):
    qd = tmp_path / "q"
    dd = tmp_path / "dlq"
    result = quarantine_or_dlq(
        job_id="job_003",
        error=Exception("bad data"),
        error_type="POISON_JOB",
        is_deterministic=True,
        retry_count=0,
        max_retries=3,
        quarantine_dir=qd,
        dlq_dir=dd,
    )
    assert isinstance(result, Path)


def test_quarantine_or_dlq_retries_exhausted(tmp_path):
    qd = tmp_path / "q"
    dd = tmp_path / "dlq"
    result = quarantine_or_dlq(
        job_id="job_004",
        error=Exception("timeout"),
        error_type="TIMEOUT",
        is_deterministic=False,
        retry_count=5,
        max_retries=3,
        quarantine_dir=qd,
        dlq_dir=dd,
    )
    # Returns a Path (entry was saved)
    assert isinstance(result, Path)


def test_idempotency_key_stable():
    k1 = make_idempotency_key("biz_001", "snap_001", "audit")
    k2 = make_idempotency_key("biz_001", "snap_001", "audit")
    assert k1 == k2
    assert len(k1) == 16


def test_idempotency_key_different():
    k1 = make_idempotency_key("biz_001", "snap_001", "audit")
    k2 = make_idempotency_key("biz_002", "snap_001", "audit")
    assert k1 != k2


def test_idempotency_store(tmp_path):
    store = IdempotencyStore(tmp_path)
    key = make_idempotency_key("biz_001", "snap_001", "audit")
    assert not store.is_completed(key)
    store.mark_completed(key)
    assert store.is_completed(key)
    assert store.count() == 1

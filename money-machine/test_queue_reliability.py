"""Disposable queue regressions: no providers, real prospects or sends."""
import sqlite3

import mm_pipeline as p
import pytest


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("MM_ROOT", str(tmp_path))
    d = sqlite3.connect(tmp_path / "queue.db")
    d.row_factory = sqlite3.Row
    d.execute("CREATE TABLE businesses(id INTEGER PRIMARY KEY)")
    p.migrate(d)
    for bid in (1, 2):
        d.execute("INSERT INTO businesses VALUES(?)", (bid,))
        p.enqueue(d, bid)
    d.commit()
    yield d
    d.close()


def test_active_lease_does_not_hide_next_eligible_item(db):
    assert p.claim(db, ("DISCOVERED",), "first")[0]["business_id"] == 1
    db.execute("UPDATE pipeline_items SET updated_at='2000-01-01T00:00:00+00:00' WHERE business_id=1")
    claimed = p.claim(db, ("DISCOVERED",), "second")
    assert [r["business_id"] for r in claimed] == [2]


def test_rejected_completion_does_not_increment_success_metric(db):
    p.claim(db, ("DISCOVERED",), "first")
    with pytest.raises(ValueError):
        p.complete(db, 1, "first", "APPROVED")
    assert db.execute("SELECT value FROM mm_metrics WHERE name='pipeline.items.completed'").fetchone() is None
    assert p.item(db, 1)["lease_owner"] == "first"


@pytest.mark.parametrize("operation", ["complete", "fail"])
def test_stale_worker_cannot_change_new_owners_item(db, operation):
    p.claim(db, ("DISCOVERED",), "old")
    db.execute("UPDATE pipeline_items SET lease_until='2000-01-01T00:00:00+00:00', updated_at='2000-01-01T00:00:00+00:00' WHERE business_id=1")
    assert p.claim(db, ("DISCOVERED",), "new")[0]['business_id'] == 1
    assert p.item(db, 1)['lease_owner'] == 'new'
    before = dict(p.item(db, 1))
    with pytest.raises(ValueError):
        if operation == "complete":
            p.complete(db, 1, "old", "IDENTITY_PENDING")
        else:
            p.fail(db, 1, "old", p.RetryableError("late result"))
    assert dict(p.item(db, 1)) == before


def test_expired_worker_outcome_is_not_counted(db):
    def expired(d, row, worker):
        d.execute("UPDATE pipeline_items SET lease_until='2000-01-01T00:00:00+00:00' WHERE business_id=?", (row['business_id'],))
        return 'IDENTITY_PENDING', 'late', None
    assert p.Worker('late', ('DISCOVERED',), expired).run_once(db) == 0
    assert p.item(db, 1)['state'] == 'DISCOVERED'
    p.drain_expired_leases(db)
    assert p.item(db, 1)['lease_owner'] is None


def test_health_is_readonly_and_separates_idle_from_stale_workers(db):
    import mm_queue_health
    p.register_worker(db, 'idle', 'DISCOVERED')
    db.execute("UPDATE pipeline_items SET state='NEEDS_REVIEW'")
    db.execute("UPDATE worker_registry SET heartbeat_at='2000-01-01T00:00:00+00:00'")
    db.commit()
    db.execute('PRAGMA query_only=ON')
    snap = mm_queue_health.snapshot(db)
    assert snap['activity'] == 'idle_no_eligible_work'
    assert snap['eligible'] == 0
    assert snap['held_or_terminal'] == 2
    assert snap['workers'][0]['stale'] is True


def test_health_counts_due_retries_and_expired_leases(db):
    import mm_queue_health
    p.register_worker(db, 'worker', 'DISCOVERED')
    db.execute("UPDATE pipeline_items SET next_retry_at='2999-01-01T00:00:00+00:00' WHERE business_id=2")
    db.execute("UPDATE pipeline_items SET lease_until='2000-01-01T00:00:00+00:00' WHERE business_id=1")
    snap = mm_queue_health.snapshot(db)
    assert (snap['eligible'], snap['expired_leases'], snap['waiting_retry']) == (1, 1, 1)

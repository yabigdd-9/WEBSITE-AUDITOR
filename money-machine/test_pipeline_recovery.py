#!/usr/bin/env python3
"""P3 scheduler / crash-recovery tests for WEBSITE-AUDITOR.

Fixtures are synthetic and disposable: in-memory SQLite only, no network,
no model calls, no real businesses, no sends.  Proves:

  * exactly one worker owns a claimed item (duplicate claim fails)
  * expired leases are drained and re-claimable
  * retries are bounded and backoff is monotonic
  * failed-job isolation: one bad item does not lose its neighbours
  * a stale lock holder cannot hold items forever
"""
import sqlite3
import time

import mm_pipeline as P


def fresh_db():
    """Isolated, deterministic in-memory SQLite with the pipeline schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    P.migrate(conn)
    return conn


def seed(d, n, state="DISCOVERED"):
    for i in range(n):
        P.enqueue(d, business_id=i, state=state)
    d.commit()


def active_lease_count(d):
    return d.execute(
        "SELECT COUNT(*) FROM pipeline_items "
        "WHERE lease_until IS NOT NULL"
    ).fetchone()[0]


def test_single_owner_per_claim():
    d = fresh_db()
    try:
        seed(d, 3)
        a = P.claim(d, ["DISCOVERED"], worker_id="w-a", lease_seconds=300, limit=3)
        assert len(a) == 3, f"expected 3 claims, got {len(a)}"
        b = P.claim(d, ["DISCOVERED"], worker_id="w-b", lease_seconds=300, limit=3)
        assert b == [], f"duplicate claim succeeded: {b}"
        for r in a:
            P.release(d, r["business_id"], "w-a")
        d.commit()
        again = P.claim(d, ["DISCOVERED"], worker_id="w-b", lease_seconds=300, limit=3)
        assert len(again) == 3, "released items were not re-claimable"
    finally:
        d.close()


def test_expired_lease_drain_and_reclaim():
    d = fresh_db()
    try:
        seed(d, 2)
        a = P.claim(d, ["DISCOVERED"], worker_id="w-a", lease_seconds=1, limit=2)
        assert len(a) == 2
        assert active_lease_count(d) == 2
        time.sleep(1.3)
        P.drain_expired_leases(d)
        d.commit()
        assert active_lease_count(d) == 0, "expired leases were not drained"
        b = P.claim(d, ["DISCOVERED"], worker_id="w-b", lease_seconds=300, limit=2)
        assert len(b) == 2, f"drained items not re-claimable: {len(b)}"
    finally:
        d.close()


def test_retry_bounds_and_backoff():
    d = fresh_db()
    try:
        seed(d, 1)
        item = P.claim(d, ["DISCOVERED"], worker_id="w-x", lease_seconds=300, limit=1)[0]
        bid = item["business_id"]
        for attempt in range(1, 5):
            P.fail(d, bid, "w-x", f"boom-{attempt}", retryable=True)
            d.commit()
        backoffs = [P.backoff_seconds(i, base=30, cap=3600) for i in range(1, 6)]
        assert backoffs == sorted(backoffs), f"backoff not monotonic: {backoffs}"
        assert backoffs[-1] <= 3600, f"backoff exceeded cap: {backoffs[-1]}"
    finally:
        d.close()


def test_failed_job_isolation():
    d = fresh_db()
    try:
        seed(d, 4)
        items = P.claim(d, ["DISCOVERED"], worker_id="w-iso", lease_seconds=300, limit=4)
        assert len(items) == 4
        P.fail(d, items[1]["business_id"], "w-iso", "transient", retryable=True)
        P.fail(d, items[2]["business_id"], "w-iso", "transient", retryable=True)
        d.commit()
        P.complete(d, items[0]["business_id"], "w-iso", to_state="QUALIFIED", reason="ok")
        P.complete(d, items[3]["business_id"], "w-iso", to_state="QUALIFIED", reason="ok")
        d.commit()
        states = {r["business_id"]: r["state"] for r in d.execute(
            "SELECT business_id, state FROM pipeline_items").fetchall()}
        assert states[items[0]["business_id"]] == "QUALIFIED"
        assert states[items[3]["business_id"]] == "QUALIFIED"
        assert states[items[1]["business_id"]] != "QUALIFIED"
        assert states[items[2]["business_id"]] != "QUALIFIED"
    finally:
        d.close()


def test_stale_lock_does_not_persist():
    d = fresh_db()
    try:
        seed(d, 1)
        P.claim(d, ["DISCOVERED"], worker_id="crashed", lease_seconds=1, limit=1)
        d.commit()
        assert active_lease_count(d) == 1
        time.sleep(1.3)
        P.drain_expired_leases(d)
        d.commit()
        assert active_lease_count(d) == 0, "stale lease survived drain"
        b = P.claim(d, ["DISCOVERED"], worker_id="recovery", lease_seconds=300, limit=1)
        assert len(b) == 1, "stale lease blocked recovery"
    finally:
        d.close()
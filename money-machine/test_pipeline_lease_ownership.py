"""Synthetic regressions for queue eligibility and fenced worker writes."""
import datetime as dt
import sqlite3

import mm_pipeline as p
import pytest
from test_pipeline import add_business, fresh_db


@pytest.fixture
def queue(tmp_path, monkeypatch):
    monkeypatch.setenv("MM_ROOT", str(tmp_path))
    d = fresh_db(tmp_path)
    bid = add_business(d)
    p.enqueue(d, bid)
    try:
        yield d, bid
    finally:
        d.close()


def owned(d, bid, owner="owner", seconds=300):
    token = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=seconds)).isoformat()
    d.execute("UPDATE pipeline_items SET lease_owner=?,lease_until=?,attempts=3 WHERE business_id=?",
              (owner, token, bid))
    return token


def snapshot(d):
    return list(d.iterdump())


def test_active_lease_does_not_consume_claim_limit(queue):
    d, bid = queue
    owned(d, bid)
    other = add_business(d, name="Second fixture")
    p.enqueue(d, other)
    d.execute("UPDATE pipeline_items SET updated_at='2000-01-01' WHERE business_id=?", (bid,))
    assert [x["business_id"] for x in p.claim(d, ("DISCOVERED",), "new", limit=1)] == [other]


@pytest.mark.parametrize("operation", ["complete", "fail"])
@pytest.mark.parametrize("reason", ["other_owner", "expired", "same_owner_new_token", "released"])
def test_stale_mutation_preserves_every_database_row(queue, operation, reason):
    d, bid = queue
    token = owned(d, bid, owner="worker", seconds=-10 if reason == "expired" else 300)
    supplied = token
    if reason == "other_owner":
        d.execute("UPDATE pipeline_items SET lease_owner='other' WHERE business_id=?", (bid,))
    if reason == "same_owner_new_token":
        supplied = "2000-01-01T00:00:00+00:00"
    if reason == "released":
        d.execute("UPDATE pipeline_items SET lease_owner=NULL,lease_until=NULL WHERE business_id=?", (bid,))
    before = snapshot(d)
    with pytest.raises(p.LeaseLostError):
        if operation == "complete":
            p.complete(d, bid, "worker", "IDENTITY_PENDING", expected_lease=supplied)
        else:
            p.fail(d, bid, "worker", p.RetryableError("stale"), expected_lease=supplied)
    assert snapshot(d) == before


def test_rejected_completion_rolls_back_metrics_lease_and_events(queue):
    d, bid = queue
    token = owned(d, bid)
    before = snapshot(d)
    with pytest.raises(ValueError):
        p.complete(d, bid, "owner", "SENT", expected_lease=token)
    assert snapshot(d) == before


def test_mid_transition_failure_rolls_back_all_writes(queue, monkeypatch):
    d, bid = queue
    token = owned(d, bid)
    before = snapshot(d)
    def unavailable(*args):
        raise RuntimeError("synthetic event failure")
    monkeypatch.setattr(p, "_record", unavailable)
    with pytest.raises(RuntimeError):
        p.complete(d, bid, "owner", "IDENTITY_PENDING", expected_lease=token)
    assert snapshot(d) == before


@pytest.mark.parametrize("failure", [False, True])
def test_worker_lease_loss_never_overwrites_reassigned_owner(queue, monkeypatch, failure):
    d, bid = queue
    monkeypatch.setattr("mm_brain.safe_mode", lambda: {"enabled": False})
    def handler(d, it, worker):
        owned(d, bid, owner="replacement")
        if failure:
            raise p.RetryableError("stale result")
        return "IDENTITY_PENDING", "stale success", None
    assert p.Worker("worker", ("DISCOVERED",), handler).run_once(d) == 0
    row = p.item(d, bid)
    assert row["lease_owner"] == "replacement"
    assert row["state"] == "DISCOVERED"
    assert row["attempts"] == 3


def test_competing_connections_do_not_claim_same_item(queue, tmp_path):
    d, bid = queue
    other = add_business(d, name="Other fixture")
    p.enqueue(d, other)
    d.commit()
    second = sqlite3.connect(tmp_path / "t.db")
    second.row_factory = sqlite3.Row
    try:
        first = p.claim(d, ("DISCOVERED",), "first", limit=1)
        d.commit()
        next_items = p.claim(second, ("DISCOVERED",), "second", limit=1)
        assert {x["business_id"] for x in first}.isdisjoint(x["business_id"] for x in next_items)
        assert len(first) == len(next_items) == 1
    finally:
        second.close()


def test_success_returns_cleared_lease_and_preserves_outer_transaction(queue):
    d, bid = queue
    token = owned(d, bid)
    d.commit()
    before = snapshot(d)
    d.execute("UPDATE pipeline_items SET last_error='outer transaction' WHERE business_id=?", (bid,))
    result = p.complete(d, bid, "owner", "IDENTITY_PENDING", expected_lease=token)
    assert result["lease_owner"] is None
    assert result["state"] == "IDENTITY_PENDING"
    assert d.in_transaction
    d.rollback()
    assert snapshot(d) == before


def test_worker_cost_block_preserves_typed_classification(queue, monkeypatch):
    d, bid = queue
    monkeypatch.setattr("mm_brain.safe_mode", lambda: {"enabled": False})
    def handler(*args):
        raise p.BlockedCost("synthetic unavailable route")
    assert p.Worker("worker", ("DISCOVERED",), handler).run_once(d) == 0
    row = p.item(d, bid)
    assert row["classification"] == "blocked_cost"
    assert row["last_error"].startswith("BLOCKED_COST:")
    assert row["lease_owner"] is None

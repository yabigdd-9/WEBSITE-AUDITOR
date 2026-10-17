"""Provider outages retain typed metadata through real worker handling."""
import json
from unittest.mock import patch

import mm_discovery as discovery
import mm_pipeline as pipeline
from test_pipeline import add_business, fresh_db


def test_search_outage_survives_worker_retry_and_dead_letter(tmp_path, monkeypatch):
    monkeypatch.setenv("MM_ROOT", str(tmp_path))
    d = fresh_db(tmp_path)
    try:
        bid = add_business(d)
        pipeline.enqueue(d, bid)
        d.execute("UPDATE pipeline_items SET max_attempts=2 WHERE business_id=?", (bid,))

        def unavailable(*args):
            raise discovery.SearchBlocked("BLOCKED_SEARCH_TIMEOUT", "fixture", "timeout")

        worker = pipeline.Worker("fixture-worker", ("DISCOVERED",), unavailable)
        with patch("mm_brain.safe_mode", return_value={"enabled": False}):
            assert worker.run_once(d) == 0
            row = pipeline.item(d, bid)
            assert row["attempts"] == 1
            assert row["state"] == "DISCOVERED"
            assert json.loads(row["payload"])["lane"] == "search"
            d.execute("UPDATE pipeline_items SET next_retry_at=NULL WHERE business_id=?", (bid,))
            assert worker.run_once(d) == 0
        row = pipeline.item(d, bid)
        assert row["state"] == "RETRYABLE_FAILURE"
        assert json.loads(row["payload"])["provider_state"] == "BLOCKED_SEARCH_TIMEOUT"
        assert row["classification"] == "transient"
    finally:
        d.close()


def test_source_collection_preserves_outage_without_creating_prospect(monkeypatch):
    error = discovery.SearchBlocked("BLOCKED_SEARCH_SERVICE_ABSENT", "fixture", "absent")
    monkeypatch.setattr(discovery, "searxng_candidates", lambda *a: (_ for _ in ()).throw(error))
    candidates, report, rejected = discovery._collect_search_source("fixture", "NZ", "fixture", 1)
    assert candidates == rejected == []
    assert report["provider_state"] == error.code
    assert report["lane"] == "search"

"""Synthetic recovery regressions; no network, model calls or external sends."""
import json
from unittest.mock import Mock

import mm_discovery_quality as quality
import mm_pipeline as pipeline
import mm_workers as workers
import pytest
from test_pipeline import add_business, fresh_db


@pytest.mark.parametrize("host", ["yelp.com", "www.yelp.com", "m.yelp.com", "uk.yelp.com"])
def test_yelp_directory_and_subdomains_reject(host):
    result = quality.classify_candidate({"source_url": f"https://{host}/search?cflt=plumbing"})
    assert result["classification"] == quality.DIRECTORY
    assert result["disposition"] == quality.REJECT
    assert result["confidence"] >= 0.9


@pytest.mark.parametrize("host", ["notyelp.com", "yelp.com.example.co.nz"])
def test_directory_matching_does_not_match_lookalikes(host):
    result = quality.classify_candidate({"source_url": f"https://{host}/"})
    assert result["classification"] != quality.DIRECTORY


def test_yelp_filtered_before_pipeline_intake():
    result = quality.filter_candidates([{"source_url": "https://m.yelp.com/search"}])
    assert result["counts"] == {"accepted": 0, "rejected": 1, "review": 0}
    assert result["paid_calls"] == result["external_sends"] == 0


@pytest.fixture
def disposable_db(tmp_path, monkeypatch):
    monkeypatch.setenv("MM_ROOT", str(tmp_path))
    monkeypatch.setenv("MM_EXTERNAL_SEND_DISABLED", "1")
    d = fresh_db(tmp_path)
    yield d
    d.close()


def test_recovery_holds_review_and_retains_failure_history(disposable_db, monkeypatch):
    d = disposable_db
    bid = add_business(d, site="https://m.yelp.com/")
    review = {"classification": "UNKNOWN", "disposition": "REVIEW", "confidence": 0.35}
    pipeline.enqueue(d, bid, payload={"discovery_quality": review})
    pipeline.transition(d, bid, "RETRYABLE_FAILURE", "w-audit", "HTTP 403 after five attempts")
    d.execute("UPDATE pipeline_items SET attempts=5, repeat_count=5 WHERE business_id=?", (bid,))
    previous = [tuple(r) for r in d.execute("SELECT * FROM pipeline_events ORDER BY id")]
    pipeline.transition(d, bid, "IDENTITY_PENDING", "operator", "authorized identity recovery")
    forbidden = Mock(side_effect=AssertionError("held candidate must not execute audit or shadow work"))
    monkeypatch.setattr(workers, "audit_handler", forbidden)
    monkeypatch.setattr("mm_opportunity_intelligence.shadow_assessment", forbidden)
    monkeypatch.setattr("socket.socket.connect", forbidden)
    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    monkeypatch.setattr("requests.Session.request", forbidden)
    worker = pipeline.Worker("recovery-identity", ("IDENTITY_PENDING",), workers.identity_handler)
    assert worker.run_once(d) == 1
    assert worker.run_once(d) == 0
    item = pipeline.item(d, bid)
    assert item["state"] == "NEEDS_REVIEW"
    assert item["lease_owner"] is None and item["lease_until"] is None
    assert item["attempts"] == 0 and item["max_attempts"] == 5
    events = [tuple(r) for r in d.execute("SELECT * FROM pipeline_events ORDER BY id")]
    assert events[:len(previous)] == previous
    assert len(events) == len(previous) + 2
    ledger = d.execute("SELECT * FROM intelligence_ledger WHERE prospect_id=?", (bid,)).fetchone()
    assert ledger["decision"] == "NEEDS_REVIEW" and ledger["disposition"] == "REVIEW"
    assert ledger["primary_reason"] == "DISCOVERY_IDENTITY_REVIEW_REQUIRED"
    evidence = json.loads(ledger["derived_evidence"])
    assert evidence["discovery_quality"] == review
    assert evidence["audit_run"] is False and evidence["external_sends"] == 0
    assert ledger["processing_cost"] == 0
    assert d.execute("SELECT COUNT(*) FROM mm_model_invocations").fetchone()[0] == 0
    assert d.execute("SELECT COUNT(*) FROM mm_messages").fetchone()[0] == 0
    assert d.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert list(d.execute("PRAGMA foreign_key_check")) == []
    forbidden.assert_not_called()


@pytest.mark.parametrize("raw_payload", [
    None, "{broken", "[]", "null", "{}", '{"discovery_quality": "REVIEW"}',
    '{"discovery_quality": null}', '{"discovery_quality": {"disposition": "ACCEPT"}}',
])
def test_missing_malformed_and_accepted_metadata_keep_existing_identity_behavior(disposable_db, raw_payload):
    d = disposable_db
    bid = add_business(d)
    nxt, _, evidence = workers.identity_handler(d, {"business_id": bid, "payload": raw_payload}, None)
    assert nxt == "AUDIT_PENDING"
    assert evidence["canonical_host"] == "fixture.example.co.nz"


def test_review_rejects_private_website_before_holding(disposable_db):
    d = disposable_db
    bid = add_business(d, site="http://127.0.0.1/")
    with pytest.raises(ValueError, match="Private IP"):
        workers.identity_handler(d, {
            "business_id": bid,
            "payload": json.dumps({"discovery_quality": {"disposition": "REVIEW"}}),
        }, None)

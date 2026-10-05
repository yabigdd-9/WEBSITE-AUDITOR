"""Offline task/cache/consumer contracts and single-child integration checks."""
# ruff: noqa: F811 -- pytest fixture imports intentionally share argument names.
import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import mm_contact_review_cache as cache
import mm_contact_review_consumer as consumer
import mm_contact_review_tasks as tasks
import mm_recurring_contact_review as recurring
import pytest
from test_contact_review_workers import (  # noqa: F401
    CONFIG,
    HASHES,
    business,
    fake_row,
    isolated,
    job,
    scheduler,
    write_json,
)


def test_immediate_child_publication_is_never_overwritten(scheduler, monkeypatch):
    def start(command, **kwargs):
        path = Path(command[-1])
        request = recurring.read_json(path / "JOB.json")
        for entry in request["cases"]:
            bid = entry["business"]["live_business_id"]
            current = recurring.read_json(scheduler.root / f"state/contact-review/latest/{bid}.json")
            assert current["status"] == "SCHEDULED"
            write_json(scheduler.root / f"state/contact-review/latest/{bid}.json",
                       {**current, "status": "COMPLETE", "finished_before_popen_return": True})
        return scheduler.proc
    monkeypatch.setattr(recurring.subprocess, "Popen", start)
    recurring.tick(None)
    for bid in (1, 2):
        assert recurring.read_json(scheduler.root / f"state/contact-review/latest/{bid}.json")["status"] == "COMPLETE"


def test_failed_launch_restores_all_missing_and_existing_receipts(scheduler):
    prior = {"fingerprint": "old", "reviewed_at": "2000-01-01T00:00:00+00:00"}
    write_json(scheduler.root / "state/contact-review/latest/1.json", prior)
    scheduler.launches.side_effect = OSError("synthetic")
    with pytest.raises(OSError):
        recurring.tick(None)
    assert recurring.read_json(scheduler.root / "state/contact-review/latest/1.json") == prior
    assert not (scheduler.root / "state/contact-review/latest/2.json").exists()
    assert not (scheduler.root / "state/contact-review/latest/3.json").exists()


@pytest.mark.parametrize("attempt,seconds", [(0, 60), (1, 300), (2, 1800), (3, 86400)])
def test_transient_backoff_is_bounded(attempt, seconds):
    at = datetime(2026, 10, 6, tzinfo=timezone.utc)
    receipt = {"status": "INCOMPLETE", "fingerprint": "same", "reviewed_at": at.isoformat(),
               "retry_attempts": attempt}
    assert not tasks.schedule(receipt, "same", at + timedelta(seconds=seconds - 1))["due"]
    assert tasks.schedule(receipt, "same", at + timedelta(seconds=seconds))["due"]


def test_completed_hold_is_fresh_but_changed_business_runs_immediately():
    at = datetime.now(timezone.utc)
    receipt = {"status": "COMPLETE", "fingerprint": "same", "reviewed_at": at.isoformat(),
               "row": {"judge": {"route": "IDENTITY_EXCEPTION"}}}
    assert not tasks.schedule(receipt, "same", at + timedelta(hours=1))["due"]
    assert tasks.schedule(receipt, "changed", at)["due"]


def test_robots_failure_is_not_retried_each_minute():
    at = datetime.now(timezone.utc)
    receipt = {"status": "REVIEW_ERROR", "fingerprint": "same", "reviewed_at": at.isoformat(),
               "error": "ACCESS_RESTRICTED_OR_ROBOTS_UNAVAILABLE"}
    result = tasks.schedule(receipt, "same", at + timedelta(minutes=30))
    assert result["reason"] == "ACCESS_HOLD" and not result["due"]


def test_task_fingerprint_and_authority_are_idempotent():
    b = business()
    receipt = {"status": "COMPLETE", "live_business_id": 1, "fingerprint": "fixed", "row": fake_row(b, True)}
    task = tasks.task_for(receipt)
    assert task == tasks.task_for(receipt)
    assert task["required_worker"] == "DRAFT_PREPARATION"
    assert task["authority"] == "DRAFT_ONLY"
    receipt["status"] = "STALE_LIVE_STATE"
    assert tasks.task_for(receipt)["status"] == "HELD"


def test_error_case_is_in_total_and_offline_html(job, monkeypatch):
    monkeypatch.setattr(recurring, "collect_case", lambda *args: (_ for _ in ()).throw(ValueError("synthetic capture error")))
    recurring.process_job(job.path)
    result = recurring.read_json(job.path / "RESULT.json")
    assert result["summary"]["attempted"] == result["summary"]["cases"] == result["summary"]["errors"] == 1
    assert result["summary"]["machine_supported"] == 0
    html = (job.path / "REVIEW.html").read_text()
    assert "synthetic capture error" in html and "Clear Plumbing" in html


def test_slow_first_case_does_not_omit_second_case(job, monkeypatch):
    second = business(2)
    request = job.request
    request["cases"].append({"business": second, "fingerprint": recurring.fingerprint(second, HASHES)})
    write_json(job.path / "JOB.json", request)
    monkeypatch.setattr(recurring, "candidates", lambda db: [job.business, second])
    def collect(b, *args):
        if b["live_business_id"] == 1:
            raise TimeoutError("CONTACT_REVIEW_CASE_DEADLINE")
        return job.path, {}, "SYNTHETIC"
    monkeypatch.setattr(recurring, "collect_case", collect)
    monkeypatch.setattr(recurring, "review_case", lambda b, *args: fake_row(b))
    recurring.process_job(job.path)
    result = recurring.read_json(job.path / "RESULT.json")
    assert [r["status"] for r in result["cases"]] == ["TIMEOUT", "COMPLETE"]
    assert result["summary"]["cases"] == 2


def cached_capture(tmp_path):
    b = business()
    path = tmp_path / "state/contact-review/runs/old/business-1"
    capture = path / "evidence/capture.html"
    capture.parent.mkdir(parents=True)
    capture.write_bytes(b"<h1>Clear Plumbing</h1>")
    sha = hashlib.sha256(capture.read_bytes()).hexdigest()
    at = datetime.now(timezone.utc).isoformat()
    doc = {"business": b, "pages": [{"path": "capture.html", "sha256": sha, "captured_at": at}],
           "dns": {"clear.nz": {"checked_at": at}}, "errors": []}
    write_json(path / "COLLECTION.json", doc)
    parent = path.parent
    write_json(parent / "MANIFEST.json", {str(p.relative_to(parent)): cache.sha(p)
                                           for p in parent.rglob("*") if p.is_file()})
    entry = cache.cache_entry(parent, path, doc, "same")
    return b, path, entry


def test_rule_only_refresh_reuses_pages_without_any_request(isolated):
    b, path, entry = cached_capture(isolated.root)
    packet, doc, method = cache.reuse(entry, b, "same", isolated.root)
    assert packet == path and doc["business"] == b
    assert method == "HASH_VERIFIED_CAPTURE_REUSED"
    assert cache.reuse(entry, b, "changed-network-policy", isolated.root) is None


@pytest.mark.parametrize("target", ["capture", "collection", "manifest"])
def test_cache_tamper_fails_closed(isolated, target):
    b, path, entry = cached_capture(isolated.root)
    p = path / "evidence/capture.html" if target == "capture" else path / "COLLECTION.json" if target == "collection" else path.parent / "MANIFEST.json"
    p.write_text("tampered")
    with pytest.raises(ValueError):
        cache.reuse(entry, b, "same", isolated.root)


def test_cache_cannot_change_business_unit(isolated):
    b, path, entry = cached_capture(isolated.root)
    with pytest.raises(ValueError, match="another business/unit"):
        cache.reuse(entry, {**b, "region": "Otago"}, "same", isolated.root)


def consumer_db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
      CREATE TABLE businesses(id INTEGER PRIMARY KEY,name TEXT,normalized_name TEXT,region TEXT,public_website TEXT,is_dummy INTEGER,suppression_reason TEXT,current_status TEXT);
      CREATE TABLE pipeline_items(business_id INTEGER PRIMARY KEY,state TEXT,lease_owner TEXT);
      CREATE TABLE mm_events(event_at TEXT,action TEXT,business_id INTEGER,detail TEXT);
      INSERT INTO businesses VALUES(1,'clear.co.nz','clear','Auckland','https://clear.nz/',0,'','DISCOVERED');
      INSERT INTO pipeline_items VALUES(1,'NEEDS_REVIEW',NULL);
    """)
    return db


def proposal_for(b, path):
    path.write_bytes(b"validated evidence")
    return {"permitted_action": "APPLY_VALIDATED_IDENTITY_NAME", "changed_fields": ["name"],
            "business": {**b, "name": "Clear Plumbing"}, "row": {"identity": {"status": "HIGH"},
            "verifier": {"identity": {"status": "HIGH", "reasons": [],
            "page_evidence": [{"capture_path": str(path), "capture_hash": cache.sha(path)}]}}}}


def test_machine_name_resolution_is_audited_and_idempotent(isolated, monkeypatch):
    monkeypatch.setattr(consumer.email_store, "is_suppressed", lambda *args: False)
    b = {**business(), "name": "clear.co.nz"}
    proposal = proposal_for(b, isolated.root / "capture")
    db = consumer_db()
    assert consumer.apply_identity(db, b, proposal, isolated.root)["applied"]
    assert db.execute("SELECT name FROM businesses").fetchone()[0] == "Clear Plumbing"
    assert db.execute("SELECT region FROM businesses").fetchone()[0] == "Auckland"
    assert db.execute("SELECT count(*) FROM mm_events").fetchone()[0] == 1
    assert not consumer.apply_identity(db, b, proposal, isolated.root)["applied"]
    db.close()


@pytest.mark.parametrize("guard", ["human", "suppressed", "leased", "rejected", "tamper", "unit"])
def test_machine_resolution_preserves_all_holds(isolated, monkeypatch, guard):
    monkeypatch.setattr(consumer.email_store, "is_suppressed", lambda *args: guard == "suppressed")
    b = {**business(), "name": "clear.co.nz"}
    proposal = proposal_for(b, isolated.root / "capture")
    db = consumer_db()
    if guard == "human":
        db.execute("INSERT INTO mm_events VALUES('now','human_identity_name_applied',1,'{}')")
    if guard == "leased":
        db.execute("UPDATE pipeline_items SET lease_owner='other-owner'")
    if guard == "rejected":
        db.execute("UPDATE pipeline_items SET state='REJECTED'")
    if guard == "tamper":
        (isolated.root / "capture").write_text("changed")
    if guard == "unit":
        proposal["business"]["region"] = "Otago"
    assert not consumer.apply_identity(db, b, proposal, isolated.root)["applied"]
    assert db.execute("SELECT name FROM businesses").fetchone()[0] == "clear.co.nz"
    db.close()


def test_identity_application_failure_releases_finished_child(scheduler, monkeypatch):
    config = {**CONFIG, "automatic_identity_resolution": True}
    monkeypatch.setattr(recurring, "load_config", lambda: config)
    recurring.tick(None)
    scheduler.proc.poll.return_value = 0
    def broken(*args):
        raise ValueError("synthetic changed manifest")
    monkeypatch.setattr(recurring, "consume_identity", broken)
    result = recurring.tick(None)
    assert result["reason"] == "worker_finished"
    assert recurring._owned is None and recurring._lock is None
    assert list((scheduler.root / "state/contact-review/runs").rglob("*.identity-application.json"))


def test_relative_identity_capture_consumes_only_unchanged_full_snapshot(isolated, monkeypatch):
    monkeypatch.setattr(consumer.email_store, "is_suppressed", lambda *args: False)
    monkeypatch.setattr(recurring, "source_hashes", lambda: HASHES)
    b = {**business(), "name": "clear.co.nz"}
    monkeypatch.setattr(recurring, "candidates", lambda d: [b])
    job = isolated.root / "state/contact-review/runs/identity-job"
    folder = job / b["id"]
    capture = folder / "evidence/page.html"
    capture.parent.mkdir(parents=True)
    proposal = proposal_for(b, capture)
    proposal["row"]["verifier"]["identity"]["page_evidence"][0]["capture_path"] = "page.html"
    result = {"status":"COMPLETE", "fingerprint":recurring.fingerprint(b,HASHES),
              "identity_proposal":proposal, "collection_reference":str(folder)}
    case = write_json(job / "1.json", result)
    write_json(job / "MANIFEST.json", {"1.json":cache.sha(case), str(capture.relative_to(job)):cache.sha(capture)})
    entry = {"business":b, "fingerprint":result["fingerprint"]}
    db = consumer_db()
    recurring.consume_identity(db, entry, job, {"source_hashes":HASHES})
    assert db.execute("SELECT name FROM businesses").fetchone()[0] == "Clear Plumbing"
    assert recurring.read_json(job / "1.identity-application.json")["applied"]
    db.close()


def test_identity_consumption_rechecks_changed_branch_snapshot(isolated, monkeypatch):
    monkeypatch.setattr(recurring, "source_hashes", lambda: HASHES)
    b = {**business(), "name":"clear.co.nz", "branch":"Recorded branch"}
    monkeypatch.setattr(recurring, "candidates", lambda d: [{**b,"branch":"Changed branch"}])
    job = isolated.root / "state/contact-review/runs/changed-branch"
    case = write_json(job / "1.json", {"status":"COMPLETE", "fingerprint":recurring.fingerprint(b,HASHES),"identity_proposal":{"synthetic":True}})
    write_json(job / "MANIFEST.json", {"1.json":cache.sha(case)})
    db = consumer_db()
    recurring.consume_identity(db, {"business":b,"fingerprint":recurring.fingerprint(b,HASHES)},job,{"source_hashes":HASHES})
    assert db.execute("SELECT name FROM businesses").fetchone()[0] == "clear.co.nz"
    assert recurring.read_json(job / "1.identity-application.json")["reason"] == "STALE_IDENTITY_HANDOFF"
    db.close()

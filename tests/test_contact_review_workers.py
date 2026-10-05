"""Offline contract tests for the advisory contact-review workers only.

All writable state lives under tmp_path. Network, model calls, process launches
and process signals fail unless a test explicitly replaces them with a fake.
"""
import hashlib
import json
import socket
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "money-machine"))
import mm_contact_review_pathway as pathway  # noqa: E402
import mm_recurring_contact_review as recurring  # noqa: E402

CONFIG = {
    "enabled": True, "scan_interval_seconds": 60, "refresh_hours": 24,
    "max_businesses_per_job": 2, "job_timeout_seconds": 180,
    "max_pages": 3, "max_requests": 5, "max_dns_domains": 5,
    "model_execution_enabled": False,
}
HASHES = {"synthetic-source.py": "frozen-source"}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return path


def business(bid=1):
    return {
        "id": f"business-{bid}", "live_business_id": bid,
        "name": "Clear Plumbing", "region": "Auckland",
        "public_website": "https://clear.nz/", "source": "synthetic",
        "pipeline_state_at_freeze": "NEEDS_REVIEW", "pipeline_updated_at": "frozen",
        "unit_scope": "Recorded business and region",
    }


def fake_row(b, supported=False):
    return {
        "case_id": b["id"], "live_business_id": b["live_business_id"],
        "company": b["name"], "website": b["public_website"],
        "identity": {"status": "HIGH", "reasons": [], "name_suggestions": []},
        "verifier": {"selected": {"email": "info@clear.nz"} if supported else None},
        "proofer": {"passed": supported, "checks": {}, "sources": []},
        "judge": {
            "route": "MACHINE_SUPPORTED_RECOMMENDATION" if supported else "CONTACT_EXCEPTION",
            "next_worker": "JUDGE" if supported else "CONTACT_VERIFIER",
            "reason": "Synthetic", "pipeline_state_at_capture": "NEEDS_REVIEW",
            "pipeline_action": "NONE", "outreach_eligible": False,
            "precision_release_authority": False, "human_precision_label": None,
        },
    }


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail("Unexpected network, model, live database or process operation")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    real_sqlite_connect = sqlite3.connect
    def isolated_sqlite_connect(database, *args, **kwargs):
        address = str(database).removeprefix("file:").split("?", 1)[0]
        if address != ":memory:" and not Path(address).resolve().is_relative_to(tmp_path):
            forbidden()
        return real_sqlite_connect(database, *args, **kwargs)
    monkeypatch.setattr(sqlite3, "connect", isolated_sqlite_connect)
    monkeypatch.setattr(recurring, "get_public", forbidden)
    monkeypatch.setattr(recurring, "connect", forbidden)
    monkeypatch.setattr(recurring.subprocess, "Popen", forbidden)
    monkeypatch.setattr(recurring.os, "kill", forbidden)
    monkeypatch.setitem(sys.modules, "mm_model_router", SimpleNamespace(local_complete=forbidden))
    monkeypatch.setattr(recurring, "ROOT", tmp_path)
    monkeypatch.setattr(recurring, "root", lambda: tmp_path)
    monkeypatch.setenv("MM_ROOT", str(tmp_path))
    monkeypatch.setenv("MM_EXTERNAL_SEND_DISABLED", "1")
    monkeypatch.setattr(recurring, "_owned", None)
    monkeypatch.setattr(recurring, "_lock", None)
    monkeypatch.setattr(recurring, "_job", None)
    monkeypatch.setattr(recurring, "_last_scan", 0.0)
    monkeypatch.setattr(recurring.time, "monotonic", lambda: 1000.0)
    monkeypatch.setattr(recurring, "source_hashes", lambda: dict(HASHES))
    config_path = tmp_path / "money-machine/config/contact_review_schedule.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(yaml.safe_dump(CONFIG))
    alarm = Mock()
    handler = Mock()
    monkeypatch.setattr(recurring.signal, "alarm", alarm)
    monkeypatch.setattr(recurring.signal, "signal", handler)
    yield SimpleNamespace(root=tmp_path, config_path=config_path, alarm=alarm, handler=handler)
    if recurring._lock is not None:
        recurring._lock.close()


@pytest.fixture
def scheduler(monkeypatch, isolated):
    items = [business(i) for i in range(1, 4)]
    monkeypatch.setattr(recurring, "candidates", lambda db: items)
    proc = Mock(pid=987654)
    proc.poll.return_value = None
    launches = Mock(return_value=proc)
    monkeypatch.setattr(recurring.subprocess, "Popen", launches)
    return SimpleNamespace(items=items, proc=proc, launches=launches, root=isolated.root)


@pytest.fixture
def job(monkeypatch, isolated):
    b = business()
    path = isolated.root / "state/contact-review/runs/synthetic"
    request = {"cases": [{"business": b, "fingerprint": recurring.fingerprint(b, HASHES)}],
               "source_hashes": HASHES, "config": CONFIG, "seed_packets": []}
    write_json(path / "JOB.json", request)
    monkeypatch.setattr(recurring, "seed_case", lambda *args: None)
    monkeypatch.setattr(recurring, "collect_case", lambda *args: (path, {}, "SYNTHETIC"))
    monkeypatch.setattr(recurring, "review_case", lambda *args: fake_row(b))
    monkeypatch.setattr(recurring, "candidates", lambda db: [b])

    @contextmanager
    def readonly(*, readonly):
        assert readonly is True
        yield object()

    monkeypatch.setattr(recurring, "connect", readonly)
    return SimpleNamespace(path=path, business=b, request=request, alarm=isolated.alarm)


def test_default_config_is_bounded_and_models_disabled():
    assert recurring.load_config() == CONFIG


@pytest.mark.parametrize("field,value", [
    ("model_execution_enabled", True), ("model_execution_enabled", None),
    ("scan_interval_seconds", 29), ("scan_interval_seconds", 3601),
    ("refresh_hours", 0), ("refresh_hours", 169),
    ("max_businesses_per_job", 0), ("max_businesses_per_job", 6),
    ("job_timeout_seconds", 29), ("job_timeout_seconds", 301),
    ("max_pages", 0), ("max_pages", 6),
    ("max_requests", 0), ("max_requests", 9),
    ("max_dns_domains", 0), ("max_dns_domains", 6),
    ("max_pages", True), ("max_businesses_per_job", "2"),
])
def test_invalid_config_fails_closed(isolated, field, value):
    config = {**CONFIG, field: value}
    isolated.config_path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError):
        recurring.load_config()


def test_request_cap_must_cover_page_cap(isolated):
    isolated.config_path.write_text(yaml.safe_dump({**CONFIG, "max_requests": 2}))
    with pytest.raises(ValueError, match="cover page limit"):
        recurring.load_config()


def test_candidate_selection_excludes_rejected_suppressed_and_dummy():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE businesses(id INTEGER, name TEXT, region TEXT, public_website TEXT,
          source TEXT, is_dummy INTEGER, suppression_reason TEXT, current_status TEXT);
        CREATE TABLE pipeline_items(business_id INTEGER,state TEXT,payload TEXT,updated_at TEXT);
    """)
    rows = [
        (1, "NEEDS_REVIEW", 0, "", "discovered", "https://clear.nz/"),
        (2, "REJECTED", 0, "", "discovered", "https://clear.nz/"),
        (3, "CONTACT_PENDING", 1, "", "discovered", "https://clear.nz/"),
        (4, "IDENTITY_PENDING", 0, "opted out", "discovered", "https://clear.nz/"),
        (5, "NEEDS_REVIEW", 0, "", "SUPPRESSED", "https://clear.nz/"),
        (6, "NEEDS_REVIEW", 0, "", "discovered", ""),
    ]
    for bid, state, dummy, suppression, status, website in rows:
        db.execute("INSERT INTO businesses VALUES(?,?,?,?,?,?,?,?)",
                   (bid, "Clear Plumbing", "Auckland", website, "synthetic", dummy, suppression, status))
        db.execute("INSERT INTO pipeline_items VALUES(?,?,?,?)",
                   (bid, state, json.dumps({"legal_name": "Clear Plumbing Ltd"}), "frozen"))
    writes = db.total_changes
    result = recurring.candidates(db)
    assert [r["live_business_id"] for r in result] == [1]
    assert result[0]["legal_name"] == "Clear Plumbing Ltd"
    assert db.total_changes == writes
    db.close()


def test_running_owned_child_does_not_spawn_or_wait(scheduler, monkeypatch):
    monkeypatch.setattr(recurring, "_owned", scheduler.proc)
    assert recurring.tick(None)["reason"] == "worker_running"
    scheduler.launches.assert_not_called()
    scheduler.proc.wait.assert_not_called()


def test_schedule_starts_one_child_with_two_cases_and_preserves_prior(scheduler):
    prior = {"status": "COMPLETE", "fingerprint": "old", "reviewed_at": "2000-01-01T00:00:00+00:00"}
    write_json(scheduler.root / "state/contact-review/latest/1.json", prior)
    result = recurring.tick(None)
    assert result["business_ids"] == [2, 3]  # missing cases are oldest
    scheduler.launches.assert_called_once()
    args, kwargs = scheduler.launches.call_args
    assert args[0][1:4] == ["-B", "-m", "mm_recurring_contact_review"]
    assert len(kwargs["pass_fds"]) == 1
    assert kwargs["env"]["MM_ROOT"] == str(scheduler.root)
    assert kwargs["env"]["MM_EXTERNAL_SEND_DISABLED"] == "1"
    request = recurring.read_json(Path(result["job_directory"]) / "JOB.json")
    assert len(request["cases"]) == 2
    assert recurring.read_json(scheduler.root / "state/contact-review/latest/1.json") == prior
    assert (scheduler.root / "state/contact-review/status.json").stat().st_mode & 0o777 == 0o600
    assert recurring.tick(None)["reason"] == "worker_running"
    scheduler.launches.assert_called_once()


def test_recent_unchanged_cases_do_not_refresh(scheduler):
    for b in scheduler.items:
        write_json(scheduler.root / f"state/contact-review/latest/{b['live_business_id']}.json",
                   {"status": "COMPLETE", "reviewed_at": recurring.now(),
                    "fingerprint": recurring.fingerprint(b, HASHES)})
    assert recurring.tick(None)["reason"] == "all_current"
    scheduler.launches.assert_not_called()


def test_disabled_schedule_does_not_start_child(scheduler, isolated):
    isolated.config_path.write_text(yaml.safe_dump({**CONFIG, "enabled": False}))
    assert recurring.tick(None)["reason"] == "disabled"
    scheduler.launches.assert_not_called()


def test_changed_name_refreshes_without_requeueing_pipeline(scheduler):
    for b in scheduler.items:
        write_json(scheduler.root / f"state/contact-review/latest/{b['live_business_id']}.json",
                   {"status": "COMPLETE", "reviewed_at": recurring.now(),
                    "fingerprint": recurring.fingerprint(b, HASHES)})
    scheduler.items[0]["name"] = "Confirmed Name"
    result = recurring.tick(None)
    assert result["business_ids"] == [1]
    request = recurring.read_json(Path(result["job_directory"]) / "JOB.json")
    assert request["cases"][0]["business"]["pipeline_state_at_freeze"] == "NEEDS_REVIEW"
    prior = recurring.read_json(Path(result["job_directory"]) / "PRIOR_REVIEWS.json")
    assert prior["1"]["status"] == "COMPLETE"


def test_refresh_after_24_hours_and_scan_throttle(scheduler, monkeypatch):
    old = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    for b in scheduler.items:
        write_json(scheduler.root / f"state/contact-review/latest/{b['live_business_id']}.json",
                   {"status": "COMPLETE", "reviewed_at": old,
                    "fingerprint": recurring.fingerprint(b, HASHES)})
    monkeypatch.setattr(recurring, "_last_scan", 980.0)
    assert recurring.tick(None)["reason"] == "not_due"
    scheduler.launches.assert_not_called()
    monkeypatch.setattr(recurring, "_last_scan", 930.0)
    assert recurring.tick(None)["reason"] == "worker_started"


def test_existing_owner_lock_prevents_duplicate_child(scheduler, monkeypatch):
    def already_owned(*args):
        raise BlockingIOError("Synthetic existing owner")
    monkeypatch.setattr(recurring.fcntl, "flock", already_owned)
    assert recurring.tick(None)["reason"] == "existing_review_owner"
    scheduler.launches.assert_not_called()


def test_real_file_lock_prevents_duplicate_owner(scheduler):
    path = scheduler.root / "state/contact-review/.owner.lock"
    path.parent.mkdir(parents=True)
    with path.open("a") as owner:
        recurring.fcntl.flock(owner, recurring.fcntl.LOCK_EX | recurring.fcntl.LOCK_NB)
        assert recurring.tick(None)["reason"] == "existing_review_owner"
        scheduler.launches.assert_not_called()


def test_spawn_failure_preserves_old_receipt_and_releases_lock(scheduler):
    prior = {"status": "COMPLETE", "reviewed_at": "old", "fingerprint": "prior"}
    write_json(scheduler.root / "state/contact-review/latest/1.json", prior)
    scheduler.launches.side_effect = OSError("Synthetic launch failure")
    with pytest.raises(OSError, match="launch failure"):
        recurring.tick(None)
    assert recurring._owned is None
    assert recurring.read_json(scheduler.root / "state/contact-review/latest/1.json") == prior
    with (scheduler.root / "state/contact-review/.owner.lock").open("a") as lock:
        recurring.fcntl.flock(lock, recurring.fcntl.LOCK_EX | recurring.fcntl.LOCK_NB)


def test_interrupted_child_finalizes_scheduled_case_without_losing_prior(scheduler):
    result = recurring.tick(None)
    job_path = Path(result["job_directory"])
    original = (job_path / "PRIOR_REVIEWS.json").read_bytes()
    scheduler.proc.poll.return_value = 9
    assert recurring.tick(None)["reason"] == "worker_finished"
    latest = recurring.read_json(scheduler.root / "state/contact-review/latest/1.json")
    assert latest["status"] == "INCOMPLETE"
    assert (job_path / "PRIOR_REVIEWS.json").read_bytes() == original
    assert recurring._owned is None and recurring._lock is None
    scheduler.launches.assert_called_once()


def test_shutdown_signals_only_owned_fake_child(scheduler, monkeypatch):
    result = recurring.tick(None)
    assert result["reason"] == "worker_started"
    scheduler.proc.wait.side_effect = [recurring.subprocess.TimeoutExpired("fake", 3), None]
    recurring.shutdown()
    scheduler.proc.terminate.assert_called_once()
    scheduler.proc.kill.assert_called_once()
    assert recurring._owned is None and recurring._lock is None


def test_job_keeps_database_readonly_and_writes_zero_send_receipt(job):
    recurring.process_job(job.path)
    result = recurring.read_json(job.path / "RESULT.json")
    assert result["status"] == "COMPLETE"
    for key in ("external_sends", "model_calls", "paid_ai_cost", "pipeline_writes",
                "independent_human_labels_created"):
        assert result[key] == 0
    assert job.alarm.call_args_list[0].args == (180,)
    assert job.alarm.call_args_list[-1].args == (0,)
    manifest = recurring.read_json(job.path / "MANIFEST.json")
    for rel, expected in manifest.items():
        assert recurring.hash_file(job.path / rel) == expected


@pytest.mark.parametrize("changed", ["source", "configuration"])
def test_job_refuses_configuration_or_source_changed_after_schedule(job, monkeypatch, changed):
    if changed == "source":
        monkeypatch.setattr(recurring, "source_hashes", lambda: {"changed": "yes"})
    else:
        monkeypatch.setattr(recurring, "load_config", lambda: {**CONFIG, "max_pages": 2})
    with pytest.raises(ValueError, match="changed after job scheduling"):
        recurring.process_job(job.path)
    job.alarm.assert_not_called()


def test_current_supported_case_is_counted_and_still_has_no_release_authority(job, monkeypatch):
    monkeypatch.setattr(recurring, "review_case", lambda *args: fake_row(job.business, True))
    recurring.process_job(job.path)
    result = recurring.read_json(job.path / "RESULT.json")
    assert result["summary"] == {"cases": 1, "attempted": 1, "machine_supported": 1, "exceptions": 0, "errors": 0, "stale": 0}
    row = recurring.read_json(job.path / "1.json")["row"]
    assert row["judge"]["outreach_eligible"] is False
    assert row["judge"]["human_precision_label"] is None
    assert 'data-supported="true"' in (job.path / "REVIEW.html").read_text()


def test_job_deadline_preserves_incomplete_receipt_and_cancels_alarm(job, monkeypatch):
    def deadline(*args):
        raise RuntimeError("CONTACT_REVIEW_JOB_DEADLINE")
    monkeypatch.setattr(recurring, "collect_case", deadline)
    with pytest.raises(RuntimeError, match="JOB_DEADLINE"):
        recurring.process_job(job.path)
    assert recurring.read_json(job.path / "RESULT.json")["status"] == "INCOMPLETE"
    assert not (job.path / "1.json").exists()
    assert job.alarm.call_args_list[-1].args == (0,)


def test_job_source_mutation_does_not_publish_case(job, monkeypatch):
    calls = iter([HASHES, {"changed": "yes"}])
    monkeypatch.setattr(recurring, "source_hashes", lambda: next(calls))
    with pytest.raises(ValueError, match="changed during job"):
        recurring.process_job(job.path)
    assert recurring.read_json(job.path / "RESULT.json")["status"] == "INCOMPLETE"
    assert not (job.path / "1.json").exists()


def test_acquisition_failure_becomes_held_error_not_a_supported_contact(job, monkeypatch):
    def restricted(*args):
        raise ValueError("ACCESS_RESTRICTED_OR_ROBOTS_UNAVAILABLE")
    monkeypatch.setattr(recurring, "collect_case", restricted)
    recurring.process_job(job.path)
    result = recurring.read_json(job.path / "RESULT.json")
    assert result["status"] == "COMPLETED_WITH_ERRORS"
    assert result["summary"]["machine_supported"] == 0
    assert recurring.read_json(job.path / "1.json")["status"] == "REVIEW_ERROR"


@pytest.mark.parametrize("current", [[], [{**business(), "name": "Changed after capture"}]])
def test_changed_or_removed_live_case_is_stale(job, monkeypatch, current):
    monkeypatch.setattr(recurring, "candidates", lambda db: current)
    recurring.process_job(job.path)
    assert recurring.read_json(job.path / "1.json")["status"] == "STALE_LIVE_STATE"
    assert recurring.read_json(job.path / "RESULT.json")["status"] == "COMPLETED_WITH_ERRORS"


def test_stale_case_is_not_counted_as_supported_in_operator_report(job, monkeypatch):
    monkeypatch.setattr(recurring, "review_case", lambda *args: fake_row(job.business, True))
    monkeypatch.setattr(recurring, "candidates", lambda db: [])
    recurring.process_job(job.path)
    result = recurring.read_json(job.path / "RESULT.json")
    assert result["summary"]["machine_supported"] == 0
    assert result["summary"]["exceptions"] == 1
    assert 'data-supported="true"' not in (job.path / "REVIEW.html").read_text()
    row = recurring.read_json(job.path / "1.json")["row"]
    assert row["judge_at_capture"]["route"] == "MACHINE_SUPPORTED_RECOMMENDATION"
    assert row["judge"]["route"] == "STALE_LIVE_STATE"
    assert row["judge"]["next_worker"] == "SCOUT"
    assert row["acceptance_current"] is False
    assert row["proofer"]["passed"] is True  # original capture proof is retained


def publication_meta(at=None, url="https://clear.nz/contact"):
    return {"url": url, "sha256": "synthetic", "content_type": "text/html",
            "captured_at": (at or datetime.now(timezone.utc)).isoformat()}


@pytest.mark.parametrize("raw", [
    b"<script>info@clear.nz</script>", b"<div hidden>info@clear.nz</div>",
    b"<div aria-hidden='true'>info@clear.nz</div>",
    b"<textarea>info@clear.nz</textarea>", b"<p>otherinfo@clear.nz</p>",
])
def test_hidden_or_partial_email_is_not_publication(raw):
    assert pathway.publication_proof(publication_meta(), raw, "info@clear.nz") is None


def test_exact_visible_and_encoded_mailto_publication():
    raw = b'<title>Contact</title><a href="mailto:info%40clear.nz?subject=Hello">Email</a><p>info@clear.nz</p>'
    proof = pathway.publication_proof(publication_meta(), raw, "info@clear.nz")
    assert proof["mailto"] and proof["visible_text"] and proof["contact_page"]


def supported_result(at):
    return {"identity": {"status": "HIGH", "canonical_root_domain": "clear.nz"},
            "selected": {"email": "info@clear.nz", "domain_match": True,
                         "business_match": True, "domain_accepts_mail": True,
                         "mx_present": True, "dns_checked_at": at.isoformat(),
                         "role_account": "office", "rejection_reasons": [],
                         "confidence_label": "VERIFIED_HIGH"}}


def test_all_proof_gates_can_pass_without_human_or_sending_authority():
    at = datetime.now(timezone.utc)
    proof = pathway.proofer_worker(business(), supported_result(at),
                                  [(publication_meta(at), b'<p>info@clear.nz</p>')], at)
    assert proof["passed"]
    assert proof["independent_human_review"] is False
    assert proof["mailbox_delivery_proven"] is False


@pytest.mark.parametrize("mutation", ["stale_dns", "foreign_page", "stale_page", "careers",
                                       "medium", "rejected", "wrong_unit", "ambiguous"])
def test_proofer_fails_closed_for_missing_acceptance_gate(mutation):
    at = datetime.now(timezone.utc)
    result = supported_result(at)
    meta = publication_meta(at)
    raw = b'<p>info@clear.nz</p>'
    if mutation == "stale_dns":
        result["selected"]["dns_checked_at"] = (at - timedelta(days=8)).isoformat()
    elif mutation == "foreign_page":
        meta["url"] = "https://other.nz/contact"
    elif mutation == "stale_page":
        meta["captured_at"] = (at - timedelta(days=8)).isoformat()
    elif mutation == "careers":
        result["selected"]["email"] = "jobs@clear.nz"
        raw = b'<p>jobs@clear.nz</p>'
    elif mutation == "medium":
        result["selected"]["confidence_label"] = "VERIFIED_MEDIUM"
    elif mutation == "rejected":
        result["selected"]["rejection_reasons"] = ["Not suitable"]
    elif mutation == "wrong_unit":
        result["selected"]["business_match"] = False
    else:
        result["identity"]["status"] = "AMBIGUOUS"
    assert not pathway.proofer_worker(business(), result, [(meta, raw)], at)["passed"]


def test_judge_routes_supported_contact_without_authorizing_send_or_human_label():
    doc = {"pages": [1], "business": {"pipeline_state_at_freeze": "REJECTED"}}
    result = {"selected": {"email": "info@clear.nz"}, "identity": {"status": "HIGH"}}
    decision = pathway.judge_worker(doc, result, {"passed": True})
    assert decision["route"] == "MACHINE_SUPPORTED_RECOMMENDATION"
    assert decision["pipeline_state_at_capture"] == "REJECTED"
    assert decision["pipeline_action"] == "NONE"
    assert decision["outreach_eligible"] is False
    assert decision["human_precision_label"] is None
    assert decision["precision_release_authority"] is False


@pytest.mark.parametrize("pages,identity,selected,worker", [
    ([], "HIGH", None, "SCOUT"), ([1], "AMBIGUOUS", None, "IDENTITY"),
    ([1], "HIGH", None, "CONTACT_VERIFIER"),
    ([1], "HIGH", {"email": "info@clear.nz"}, "EVIDENCE_PROOFER"),
])
def test_judge_assigns_correct_exception_worker(pages, identity, selected, worker):
    doc = {"pages": pages, "business": {}}
    result = {"selected": selected, "identity": {"status": identity}}
    assert pathway.judge_worker(doc, result, {"passed": False})["next_worker"] == worker


def test_replay_rejects_changed_bytes_and_path_escape(tmp_path):
    b = business()
    raw = tmp_path / "evidence/page.html"
    raw.parent.mkdir()
    raw.write_bytes(b"Changed content")
    doc = {"business": b, "pages": [{"path": "page.html", "sha256": "original"}],
           "dns": {}, "errors": []}
    with pytest.raises(ValueError, match="digest mismatch"):
        pathway.review_case(b, doc, tmp_path, datetime.now(timezone.utc))
    with pytest.raises(ValueError, match="escapes"):
        pathway.safe_child(tmp_path, "../outside")


def test_replay_rejects_oversized_capture(tmp_path):
    path = tmp_path / "too-large.capture"
    path.write_bytes(b"x" * (pathway.MAX_BYTES + 1))
    with pytest.raises(ValueError, match="bounded file size"):
        pathway.read_limited(path)


def test_replay_rejects_mismatched_case_and_excessive_pages(tmp_path):
    b = business()
    doc = {"business": {**b, "name": "Different"}, "pages": []}
    with pytest.raises(ValueError, match="frozen business"):
        pathway.review_case(b, doc, tmp_path, datetime.now(timezone.utc))
    doc = {"business": b, "pages": [None] * 6}
    with pytest.raises(ValueError, match="bounded page count"):
        pathway.review_case(b, doc, tmp_path, datetime.now(timezone.utc))


def seed_packet(tmp_path, *, hours_old=0):
    packet = tmp_path / "seed-packet"
    at = datetime.now(timezone.utc) - timedelta(hours=hours_old)
    b = {**business(), "id": "seed-1"}
    raw = packet / "evidence/page.html"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"<h1>Clear Plumbing</h1>")
    doc = {"business": b, "pages": [{"path": "page.html", "captured_at": at.isoformat(),
                                      "sha256": recurring.hash_file(raw)}],
           "dns": {"clear.nz": {"checked_at": at.isoformat()}}, "errors": []}
    case = write_json(packet / "evidence/cases/seed-1.json", doc)
    sample = write_json(packet / "sample.json", {"cases": [b]})
    manifest = write_json(packet / "PACKET_MANIFEST.json", {"files": {
        str(p.relative_to(packet)): {"sha256": recurring.hash_file(p)}
        for p in [raw, case, sample]}})
    return packet, {"path": str(packet), "manifest_sha256": recurring.hash_file(manifest)}


def test_seed_reuses_fresh_hash_checked_evidence_without_network(tmp_path):
    packet, seed = seed_packet(tmp_path)
    actual, doc, method = recurring.seed_case(business(), [seed])
    assert actual == packet
    assert doc["business"] == business()
    assert method == "SAVED_CAPTURE_REUSED"


@pytest.mark.parametrize("tamper", ["capture", "case", "manifest"])
def test_seed_tampering_stops_review(tmp_path, tamper):
    packet, seed = seed_packet(tmp_path)
    path = {"capture": packet / "evidence/page.html",
            "case": packet / "evidence/cases/seed-1.json",
            "manifest": packet / "PACKET_MANIFEST.json"}[tamper]
    path.write_text("changed")
    with pytest.raises(ValueError, match="changed"):
        recurring.seed_case(business(), [seed])


def test_seed_expired_or_for_old_name_is_not_reused(tmp_path):
    _, seed = seed_packet(tmp_path, hours_old=25)
    assert recurring.seed_case(business(), [seed]) is None
    assert recurring.seed_case({**business(), "name": "New Name"}, [seed]) is None


def synthetic_response(url, raw, content_type="text/html"):
    return {"url": url, "captured_at": datetime.now(timezone.utc).isoformat(),
            "sha256": hashlib.sha256(raw).hexdigest(), "content_type": content_type,
            "redirects": []}, raw


@pytest.mark.parametrize("robots_failure", ["deny", "unavailable"])
def test_public_collection_does_not_bypass_robots(monkeypatch, tmp_path, robots_failure):
    calls = []
    def public(url, **kwargs):
        calls.append(url)
        assert url.endswith("/robots.txt")
        if robots_failure == "unavailable":
            raise OSError("Synthetic telemetry failure")
        return synthetic_response(url, b"User-agent: *\nDisallow: /\n", "text/plain")
    monkeypatch.setattr(recurring, "get_public", public)
    monkeypatch.setattr(recurring.time, "sleep", lambda *args: None)
    packet, doc, method = recurring.collect_case(business(), tmp_path / "job", CONFIG)
    assert method == "PUBLIC_GET_DNS"
    assert doc["pages"] == []
    assert len(calls) == 1
    assert "ACCESS_RESTRICTED" in doc["errors"][0]["reason"]
    assert (packet / "COLLECTION.json").exists()


def test_robots_and_failed_pages_share_total_public_request_cap(monkeypatch, tmp_path):
    calls = []
    def public(url, **kwargs):
        calls.append(url)
        if url.endswith("/robots.txt"):
            return synthetic_response(url, b"User-agent: *\nAllow: /\n", "text/plain")
        if url == business()["public_website"]:
            raw = b'<h1>Clear Plumbing</h1>' + b''.join(
                f'<a href="/contact-{i}">Contact</a>'.encode() for i in range(6))
            return synthetic_response(url, raw)
        raise ValueError("HTTP_404")
    monkeypatch.setattr(recurring, "get_public", public)
    monkeypatch.setattr(recurring.time, "sleep", lambda *args: None)
    _, doc, _ = recurring.collect_case(business(), tmp_path / "job", CONFIG)
    assert len(doc["pages"]) == 1
    assert len(calls) <= CONFIG["max_requests"]


def test_redirect_hops_share_the_same_request_budget(monkeypatch, tmp_path):
    request_hops = []
    def public(url, *, redirects):
        hops = 2 if url.endswith("/robots.txt") else 1
        assert redirects >= hops
        request_hops.append(hops + 1)
        raw = (b"User-agent: *\nAllow: /\n" if url.endswith("/robots.txt") else
               b'<h1>Clear Plumbing</h1><a href="/contact">Contact</a>')
        meta, data = synthetic_response(url, raw)
        meta["redirects"] = [{"from": url, "to": url, "status": 302}] * hops
        return meta, data
    monkeypatch.setattr(recurring, "get_public", public)
    monkeypatch.setattr(recurring.time, "sleep", lambda *args: None)
    packet, doc, _ = recurring.collect_case(business(), tmp_path / "job", CONFIG)
    assert len(doc["pages"]) == 1
    assert sum(request_hops) == CONFIG["max_requests"]
    budget = recurring.read_json(packet / "COLLECTION.json")["request_budget"]
    assert budget == {"limit": 5, "consumed_or_reserved": 5, "remaining": 0}


def test_single_request_budget_cannot_fetch_page_after_robots(monkeypatch, tmp_path):
    calls = []
    def public(url, *, redirects):
        calls.append(url)
        assert redirects == 0 and url.endswith("/robots.txt")
        return synthetic_response(url, b"User-agent: *\nAllow: /\n")
    monkeypatch.setattr(recurring, "get_public", public)
    monkeypatch.setattr(recurring.time, "sleep", lambda *args: None)
    _, doc, _ = recurring.collect_case(
        business(), tmp_path / "job", {**CONFIG, "max_pages": 1, "max_requests": 1})
    assert len(calls) == 1 and doc["pages"] == []
    assert "CONTACT_REVIEW_REQUEST_LIMIT" in doc["errors"][0]["reason"]


def test_dns_checks_are_capped_to_configured_domains(monkeypatch, tmp_path):
    checked = []
    page = {"url": "https://clear.nz/", "observations": [
        {"email": f"info@company{i}.nz", "syntax_error": None} for i in range(9)]}
    class FakeCrawler:
        def __init__(self, evidence, **kwargs):
            assert kwargs["max_pages"] == 3 and kwargs["max_requests"] == 5
        def crawl(self, website):
            return [page], []
    class FakeDNS:
        def __init__(self, path):
            assert path.is_relative_to(tmp_path)
        def check(self, domain):
            checked.append(domain)
            return {"domain_accepts_mail": False}
    monkeypatch.setattr(recurring, "Crawler", FakeCrawler)
    monkeypatch.setattr(recurring, "DNSChecks", FakeDNS)
    _, doc, _ = recurring.collect_case(business(), tmp_path / "job", CONFIG)
    assert len(checked) == len(doc["dns"]) == CONFIG["max_dns_domains"]


def test_standalone_reevaluation_never_calls_model_and_preserves_input(tmp_path):
    packet = tmp_path / "frozen-packet"
    b = business()
    doc = {"business": b, "pages": [], "dns": {}, "errors": []}
    case = write_json(packet / f"evidence/cases/{b['id']}.json", doc)
    frame = {"cases": [b], "application_revision": "8cf06168", "engine_hashes": {}}
    sample = write_json(packet / "sample.json", frame)
    (packet / "FRAME_SHA256.txt").write_text(recurring.hash_file(sample))
    write_json(packet / "PACKET_MANIFEST.json", {"files": {
        str(p.relative_to(packet)): {"sha256": recurring.hash_file(p)} for p in [case, sample]}})
    original = {str(p.relative_to(packet)): recurring.hash_file(p)
                for p in packet.rglob("*") if p.is_file()}
    previous_umask = recurring.os.umask(0o077)
    try:
        summary = pathway.run(packet, tmp_path / "replay-output", enable_ai=False, mode="reevaluate")
    finally:
        recurring.os.umask(previous_umask)
    assert summary["cases"] == 1
    assert summary["model_calls"] == summary["paid_ai_cost"] == summary["external_sends"] == 0
    assert summary["pipeline_writes"] == summary["independent_human_labels_created"] == 0
    assert summary["routes"] == {"EVIDENCE_NEEDED": 1}
    assert {str(p.relative_to(packet)): recurring.hash_file(p)
            for p in packet.rglob("*") if p.is_file()} == original


def test_optional_advisor_cannot_invent_worker_or_override_judge(monkeypatch):
    calls = []
    def fake_model(prompt, **kwargs):
        calls.append((prompt, kwargs))
        return {"text": json.dumps({"business-1": "CONTACT_VERIFIER", "other": "SHELL"}),
                "provider": "synthetic-free", "model": "synthetic", "cost_usd": 0}
    monkeypatch.setitem(sys.modules, "mm_model_router", SimpleNamespace(local_complete=fake_model))
    row = fake_row(business())
    advice = pathway.ai_advice([row])
    assert advice["accepted_assignments"] == {"business-1": "CONTACT_VERIFIER"}
    assert advice["discarded_assignments"] == 1
    assert advice["can_change_judge_decisions"] is False
    assert len(calls) == 1
    assert "Clear Plumbing" not in calls[0][0] and "clear.nz" not in calls[0][0]

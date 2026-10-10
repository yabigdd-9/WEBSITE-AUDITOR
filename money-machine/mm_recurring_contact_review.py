"""One bounded advisory contact-review child owned by the existing supervisor.

The supervisor polls without waiting for network work. This module reads live
businesses, writes separate evidence artifacts, and never transitions pipeline
items, modifies release policy, creates human labels, calls models or sends.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml
from mm_core import connect, root

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import mm_email as email  # noqa: E402
from email_baseline_capture import get_public  # noqa: E402
from mm_contact_review_pathway import (  # noqa: E402
    REQUIRED_ENGINE_FILES,
    report_html,
    review_case,
    safe_child,
)
from mm_email_network import Crawler, DNSChecks  # noqa: E402

VERSION = "recurring-contact-review-v2.0"
ELIGIBLE = {"IDENTITY_PENDING", "CONTACT_PENDING", "NEEDS_REVIEW"}
_owned = None
_lock = None
_job = None
_last_scan = 0.0
_backlog = False


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(path.name + "." + str(os.getpid()) + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        os.chmod(temp, 0o600)
        json.dump(value, handle, indent=2)
        handle.write("\n")
    temp.replace(path)


def read_json(path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes():
    return {rel: hash_file(ROOT / rel) for rel in REQUIRED_ENGINE_FILES}


def fingerprint(business, hashes):
    return hashlib.sha256(json.dumps({"business": business, "source": hashes},
                                     sort_keys=True).encode()).hexdigest()


def load_config():
    config = yaml.safe_load((ROOT / "money-machine/config/contact_review_schedule.yaml").read_text())
    if not isinstance(config, dict):
        raise ValueError("Review schedule must be a mapping")
    if config.get("model_execution_enabled") is not False:
        raise ValueError("Automatic contact review does not authorize model execution")
    for key, low, high in [("scan_interval_seconds", 30, 3600), ("refresh_hours", 1, 168),
                           ("max_businesses_per_job", 1, 5), ("job_timeout_seconds", 30, 180),
                           ("max_pages", 1, 5), ("max_requests", 1, 5), ("max_dns_domains", 1, 5)]:
        value = config.get(key)
        if type(value) is not int or not low <= value <= high:
            raise ValueError("Out-of-bounds review setting: " + key)
    if config["max_requests"] < config["max_pages"]:
        raise ValueError("Request limit must cover page limit")
    for flag in ("evidence_reuse_enabled", "automatic_identity_resolution", "draft_preparation_enabled"):
        if flag in config and type(config[flag]) is not bool:
            raise ValueError("Review feature flag must be boolean: " + flag)
    for field, high in (("case_timeout_seconds", 160), ("collection_timeout_seconds", 120), ("dns_timeout_seconds", 30)):
        if field in config and (type(config[field]) is not int or not 1 <= config[field] <= high):
            raise ValueError("Out-of-bounds review setting: " + field)
    return config


def candidates(d):
    rows = d.execute(
        "SELECT p.business_id,p.state,p.payload,p.updated_at,b.name,b.region,"
        "b.public_website,b.source FROM pipeline_items p JOIN businesses b ON b.id=p.business_id "
        "WHERE p.state IN ('IDENTITY_PENDING','CONTACT_PENDING','NEEDS_REVIEW') "
        "AND b.is_dummy=0 AND COALESCE(b.suppression_reason,'')='' "
        "AND b.current_status<>'SUPPRESSED' AND COALESCE(b.public_website,'')<>''"
    ).fetchall()
    result = []
    for row in rows:
        payload = read_payload(row["payload"])
        business = {"id": "business-" + str(row["business_id"]),
                    "live_business_id": row["business_id"], "name": row["name"],
                    "region": row["region"], "public_website": row["public_website"],
                    "source": row["source"], "pipeline_state_at_freeze": row["state"],
                    "pipeline_updated_at": row["updated_at"],
                    "unit_scope": "Recorded business and region; no unrecorded branch inference"}
        for key in ("legal_name", "trading_name", "nzbn_name", "branch", "address", "phone"):
            if isinstance(payload.get(key), str) and payload[key]:
                business[key] = payload[key]
        result.append(business)
    return result


def read_payload(value):
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}


def tick(d):
    """Short scheduling/consumption tick; all expensive work belongs to one child."""
    global _owned, _lock, _job, _last_scan, _backlog
    from mm_contact_review_tasks import schedule
    state = root() / "state/contact-review"
    if _owned is not None:
        code = _owned.poll()
        if code is None:
            return {"ran": False, "reason": "worker_running", "worker_pid": _owned.pid}
        try:
            result = read_json(_job / "RESULT.json", {"status": "INCOMPLETE", "returncode": code})
            result = {**result, "worker_pid": _owned.pid, "returncode": code, "finished_at": now()}
            atomic(state / "status.json", result)
            request = read_json(_job / "JOB.json", {})
            for entry in request.get("cases", []):
                bid = entry["business"]["live_business_id"]
                latest_path = state / "latest" / (str(bid) + ".json")
                latest = read_json(latest_path, {})
                if request.get("kind") == "DRAFT_PREPARATION":
                    task = read_json(state / "tasks" / (str(bid) + ".json"), {})
                    if task.get("status") == "RUNNING":
                        atomic(state / "tasks" / (str(bid) + ".json"), {**task, "status": "HELD", "reason_code": "DRAFT_INCOMPLETE"})
                    continue
                if latest.get("status") == "SCHEDULED" and latest.get("job_directory") == str(_job):
                    # A completed job is the durable truth if the child exited before latest publication.
                    completed = read_json(_job / (str(bid) + ".json"))
                    atomic(latest_path, completed or {**latest, "status": "INCOMPLETE", "reviewed_at": now(),
                           "error": result.get("error", "Review child did not finish this case")})
                if request.get("config", {}).get("automatic_identity_resolution") and code == 0:
                    try:
                        consume_identity(d, entry, _job, request)
                    except Exception as exc:
                        atomic(_job / (str(bid) + ".identity-application.json"), {
                            "applied": False, "reason": "APPLICATION_HELD",
                            "error": type(exc).__name__ + ": " + str(exc)[:240]})
        finally:
            if _lock is not None:
                _lock.close()
            _owned, _lock, _job = None, None, None
        if _backlog:
            _last_scan = 0.0
        return {"ran": True, "reason": "worker_finished", **result}
    if _last_scan and time.monotonic() - _last_scan < 30:
        return {"ran": False, "reason": "not_due"}
    config = load_config()
    if config.get("enabled") is not True:
        return {"ran": False, "reason": "disabled"}
    if _last_scan and time.monotonic() - _last_scan < config["scan_interval_seconds"]:
        return {"ran": False, "reason": "not_due"}
    _last_scan = time.monotonic()
    hashes = source_hashes()
    pending, drafts = [], []
    at = datetime.now(timezone.utc)
    for business in candidates(d):
        bid = business["live_business_id"]
        latest = read_json(state / "latest" / (str(bid) + ".json"), {})
        key = fingerprint(business, hashes)
        decision = schedule(latest, key, at, config["refresh_hours"])
        if decision["due"]:
            pending.append((latest.get("reviewed_at", ""), bid, business, key, decision))
        elif config.get("draft_preparation_enabled"):
            task = read_json(state / "tasks" / (str(bid) + ".json"), {})
            if task.get("status") == "PENDING" and task.get("required_worker") == "DRAFT_PREPARATION" and task.get("business_fingerprint") == key:
                drafts.append((latest.get("reviewed_at", ""), bid, business, key, latest))
    pending.sort(key=lambda row: (row[0], row[1]))
    drafts.sort(key=lambda row: (row[0], row[1]))
    if not pending and not drafts:
        return {"ran": False, "reason": "all_current"}
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    owner_lock = (state / ".owner.lock").open("a")
    os.chmod(state / ".owner.lock", 0o600)
    try:
        fcntl.flock(owner_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        owner_lock.close()
        return {"ran": False, "reason": "existing_review_owner"}
    job = state / "runs" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    job.mkdir(parents=True, mode=0o700)
    # Finish the due evidence queue first; then prepare one local draft at a time.
    kind = "CONTACT_REVIEW" if pending else "DRAFT_PREPARATION"
    chosen = pending[:config["max_businesses_per_job"]] if pending else drafts[:1]
    _backlog = len(pending) > len(chosen) or bool(drafts) or config.get("draft_preparation_enabled", False)
    selected = [{"business": row[2], "fingerprint": row[3],
                 "retry_attempts": row[4]["attempts"] + int(row[4]["reason"] == "TRANSIENT_RETRY") if pending else 0,
                 "review_receipt": row[4] if not pending else None} for row in chosen]
    policy = read_json(root() / "state/contact-review-policy.json", {})
    request = {"version": VERSION, "kind": kind, "created_at": now(), "supervisor_pid": os.getpid(),
               "config": config, "source_hashes": hashes, "cases": selected,
               "seed_packets": policy.get("seed_packets", [])}
    atomic(job / "JOB.json", request)
    prior = {str(e["business"]["live_business_id"]): read_json(state / "latest" / (str(e["business"]["live_business_id"]) + ".json")) for e in selected}
    atomic(job / "PRIOR_REVIEWS.json", prior)
    # Initialize before Popen: a seed replay may complete before Popen returns.
    for entry in selected:
        bid = entry["business"]["live_business_id"]
        if kind == "CONTACT_REVIEW":
            atomic(state / "latest" / (str(bid) + ".json"), {
                "status": "SCHEDULED", "reviewed_at": now(), "fingerprint": entry["fingerprint"],
                "retry_attempts": entry["retry_attempts"], "job_directory": str(job), "live_business_id": bid})
        else:
            task_path = state / "tasks" / (str(bid) + ".json")
            atomic(task_path, {**read_json(task_path, {}), "status": "RUNNING", "job_directory": str(job)})
    try:
        with (job / "worker.log").open("w") as log:
            os.chmod(job / "worker.log", 0o600)
            proc = subprocess.Popen(
                [sys.executable, "-B", "-m", "mm_recurring_contact_review", "--process-job", str(job)],
                cwd=str(ROOT / "money-machine"), env=os.environ.copy(),
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, pass_fds=(owner_lock.fileno(),))
    except Exception:
        for entry in selected:
            bid = entry["business"]["live_business_id"]
            path = state / "latest" / (str(bid) + ".json")
            if kind == "CONTACT_REVIEW":
                if prior[str(bid)] is None:
                    path.unlink(missing_ok=True)
                else:
                    atomic(path, prior[str(bid)])
            else:
                task_path = state / "tasks" / (str(bid) + ".json")
                atomic(task_path, {**read_json(task_path, {}), "status": "PENDING"})
        owner_lock.close()
        atomic(job / "RESULT.json", {"status": "LAUNCH_FAILED", "cases": [], "external_sends": 0})
        raise
    _owned, _lock, _job = proc, owner_lock, job
    status = {"status": "RUNNING", "kind": kind, "started_at": now(), "supervisor_pid": os.getpid(),
              "worker_pid": proc.pid, "job_directory": str(job),
              "business_ids": [e["business"]["live_business_id"] for e in selected],
              "external_sends": 0, "model_calls": 0, "pipeline_writes": 0}
    atomic(state / "status.json", status)
    return {"ran": True, "reason": "worker_started", **status}


def consume_identity(d, entry, job, request):
    from mm_contact_review_consumer import apply_identity
    manifest = read_json(job / "MANIFEST.json", {})
    bid = entry["business"]["live_business_id"]
    case = job / (str(bid) + ".json")
    if request["source_hashes"] != source_hashes() or manifest.get(case.name) != hash_file(case):
        raise ValueError("Identity result source/manifest changed")
    result = read_json(case, {})
    if result.get("fingerprint") != entry["fingerprint"] or result.get("status") != "COMPLETE":
        return
    proposal = result.get("identity_proposal")
    if not proposal:
        return
    with d:
        # Acquire the SQLite write lock before checking the entire business/unit snapshot.
        d.execute("UPDATE businesses SET name=name WHERE id=?", (bid,))
        current = next((b for b in candidates(d) if b["live_business_id"] == bid), None)
        if current is None or fingerprint(current, request["source_hashes"]) != entry["fingerprint"]:
            atomic(job / (str(bid) + ".identity-application.json"), {"applied": False, "reason": "STALE_IDENTITY_HANDOFF"})
            return
        # Helper paths are relative to their verified collection, not the supervisor cwd.
        folder = Path(result["collection_reference"]).resolve()
        if folder.is_relative_to(root() / "state/contact-review/runs"):
            capture_manifest = read_json(folder.parents[0] / "MANIFEST.json", {})
            capture_root = folder / "evidence"
            capture_job = folder.parent
        else:
            seeds = {str(Path(seed["path"]).resolve()): seed for seed in request.get("seed_packets", [])}
            seed = seeds.get(str(folder))
            if not seed or hash_file(folder / "PACKET_MANIFEST.json") != seed["manifest_sha256"]:
                raise ValueError("Identity capture root unproven")
            capture_manifest = {k: v["sha256"] for k, v in read_json(folder / "PACKET_MANIFEST.json")["files"].items()}
            capture_root, capture_job = folder / "evidence", folder
        proposal = json.loads(json.dumps(proposal))
        for page in proposal["row"]["verifier"]["identity"]["page_evidence"]:
            path = safe_child(capture_root, page["capture_path"])
            if capture_manifest.get(str(path.relative_to(capture_job))) != hash_file(path):
                raise ValueError("Identity capture manifest changed")
            page["capture_path"] = str(path)
        outcome = apply_identity(d, entry["business"], proposal, job)
    atomic(job / (str(bid) + ".identity-application.json"), outcome)
    # The original collection/decision manifest stays immutable; this application has its own receipt.
    if outcome.get("applied"):
        global _last_scan
        _last_scan = 0.0


def shutdown():
    """Stop only this module's owned review child on supervisor shutdown."""
    global _owned, _lock, _job
    if _owned is not None:
        if _owned.poll() is None:
            _owned.terminate()
            try:
                _owned.wait(timeout=3)
            except subprocess.TimeoutExpired:
                _owned.kill()
                _owned.wait(timeout=3)
        if _lock:
            _lock.close()
        _owned, _lock, _job = None, None, None


def seed_case(business, seeds):
    for seed in seeds:
        packet = Path(seed["path"]).resolve()
        manifest_path = packet / "PACKET_MANIFEST.json"
        if hash_file(manifest_path) != seed["manifest_sha256"]:
            raise ValueError("Seed packet manifest changed")
        manifest = read_json(manifest_path)["files"]
        sample = packet / "sample.json"
        if hash_file(sample) != manifest["sample.json"]["sha256"]:
            raise ValueError("Seed frame changed")
        for case in read_json(sample)["cases"]:
            if case.get("live_business_id") != business["live_business_id"]:
                continue
            if any(case.get(key) != business.get(key) for key in ("name", "region", "public_website")):
                continue
            path = "evidence/cases/" + case["id"] + ".json"
            case_path = safe_child(packet, path)
            if hash_file(case_path) != manifest[path]["sha256"]:
                raise ValueError("Seed case changed")
            doc = read_json(case_path)
            if not doc["pages"] or any(not 0 <= email.age_days(p["captured_at"]) <= 1 for p in doc["pages"]):
                continue
            if any(not 0 <= email.age_days(v.get("checked_at")) <= 1 / 24 for v in doc["dns"].values()):
                continue
            for page in doc["pages"]:
                capture = safe_child(packet / "evidence", page["path"])
                rel = str(capture.relative_to(packet))
                if hash_file(capture) != manifest[rel]["sha256"] or hash_file(capture) != page["sha256"]:
                    raise ValueError("Seed capture changed")
            return packet, {**doc, "business": business}, "SAVED_CAPTURE_REUSED"
    return None


def collect_case(business, job, config):
    from mm_contact_review_network import collect_case as collect
    return collect(business, job / business["id"], config, get_public_fn=get_public,
                   crawler_cls=Crawler, dns_cls=DNSChecks,
                   deadline=getattr(collect_case, "deadline", None),
                   dns_cache_path=root() / "state/contact-review/cache/dns.json")


@contextlib.contextmanager
def case_deadline(seconds):
    """One bounded case cannot consume the next case's reserved job share."""
    end = time.monotonic() + seconds
    previous = signal.getsignal(signal.SIGALRM)
    def expired(signum, frame):
        raise TimeoutError("CONTACT_REVIEW_CASE_DEADLINE")
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(max(1, math.ceil(seconds)))
    try:
        yield end
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)




def write_manifest(job):
    atomic(job / "MANIFEST.json", {str(p.relative_to(job)): hash_file(p)
           for p in sorted(job.rglob("*")) if p.is_file() and p.name not in {"MANIFEST.json", "worker.log"}})


def current_business(bid):
    with connect(readonly=True) as d:
        return next((b for b in candidates(d) if b["live_business_id"] == bid), None)


def process_job(job):
    request = read_json(job / "JOB.json")
    if request["source_hashes"] != source_hashes() or request["config"] != load_config():
        raise ValueError("Review source changed after job scheduling")
    if request.get("kind") == "DRAFT_PREPARATION":
        return process_draft_job(job, request)
    from mm_contact_review_cache import acquisition_key, cache_entry, reuse
    from mm_contact_review_tasks import schedule, task_for, timestamp
    config = request["config"]
    def timeout_handler(signum, frame):
        raise RuntimeError("CONTACT_REVIEW_JOB_DEADLINE")
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(config["job_timeout_seconds"])
    job_end = time.monotonic() + config["job_timeout_seconds"]
    rows, outcomes, collections = [], [], []
    started = time.monotonic()
    state = root() / "state/contact-review"
    try:
        for entry in request["cases"]:
            business = entry["business"]
            bid = business["live_business_id"]
            attempt_start = time.monotonic()
            packet, doc, method = None, None, None
            try:
                case_seconds = min(config.get("case_timeout_seconds", 80),
                                   (config["job_timeout_seconds"] - 20) / len(request["cases"]),
                                   job_end - time.monotonic() - 20)
                if case_seconds <= 0:
                    raise TimeoutError("CONTACT_REVIEW_CASE_DEADLINE")
                with case_deadline(case_seconds) as deadline:
                    collect_case.deadline = deadline
                    loaded = None
                    acq_key = acquisition_key(business, request["source_hashes"], config)
                    if config.get("evidence_reuse_enabled"):
                        cached = read_json(state / "cache" / (str(bid) + ".json"))
                        loaded = reuse(cached, business, acq_key, root(),
                                       dns_factory=lambda: DNSChecks(state / "cache/dns.json"), deadline=deadline)
                    if loaded is None:
                        loaded = seed_case(business, request["seed_packets"])
                    packet, doc, method = loaded or collect_case(business, job, config)
                    row = review_case(business, doc, packet, datetime.now(timezone.utc))
                    row["collection_method"] = method
                    rows.append(row)
                    result = {"status": "COMPLETE", "row": row}
                    if config.get("automatic_identity_resolution") and row["identity"]["status"] != "HIGH":
                        from mm_contact_review_pathway import validated_identity_candidate
                        result["identity_proposal"] = validated_identity_candidate(business, doc, packet, datetime.now(timezone.utc))
                    if config.get("evidence_reuse_enabled") and method == "PUBLIC_GET_DNS":
                        collections.append((bid, packet, doc, acq_key))
            except Exception as exc:
                if str(exc) == "CONTACT_REVIEW_JOB_DEADLINE":
                    raise
                result = {"status": "TIMEOUT" if isinstance(exc, TimeoutError) else "REVIEW_ERROR",
                          "error": type(exc).__name__ + ": " + str(exc)[:240]}
            result.update({"reviewed_at": now(), "fingerprint": entry["fingerprint"],
                           "live_business_id": bid, "company": business["name"],
                           "retry_attempts": entry.get("retry_attempts", 0),
                           "job_directory": str(job), "external_sends": 0, "model_calls": 0,
                           "paid_ai_cost": 0, "pipeline_writes": 0, "independent_human_label": None,
                           "timings": {"case_seconds": round(time.monotonic() - attempt_start, 6)},
                           "collection_reference": str(packet) if packet else None})
            queued = timestamp(request.get("created_at"))
            result["metrics"] = {"queue_age_seconds": max(0, (datetime.now(timezone.utc) - queued).total_seconds()) if queued else 0,
                                 "collection_method": method,
                                 "request_counts": (doc or {}).get("request_metrics", {}),
                                 "stage_seconds": (doc or {}).get("stage_timings", {}),
                                 "cache_reused": method in {"HASH_VERIFIED_CAPTURE_REUSED", "SAVED_CAPTURE_REUSED"}}
            errors = json.dumps((doc or {}).get("errors", []))
            result["retryable_acquisition_error"] = any(v in errors for v in
                ("Timeout", "OSError", "Connection", "HTTP_5", "DEADLINE", "REQUEST_LIMIT"))
            if request["source_hashes"] != source_hashes():
                raise ValueError("Review source changed during job")
            current = current_business(bid)
            if current is None or fingerprint(current, request["source_hashes"]) != entry["fingerprint"]:
                result["status"] = "STALE_LIVE_STATE"
                if "row" in result:
                    row["judge_at_capture"] = dict(row["judge"])
                    row["acceptance_current"] = False
                    row["judge"] = {**row["judge"], "route": "STALE_LIVE_STATE", "next_worker": "SCOUT",
                                    "reason_codes": ["STALE_LIVE_STATE"],
                                    "blocking_checks": ["live_business_fingerprint_changed"],
                                    "required_evidence": ["Fresh permitted first-party evidence for the current business"],
                                    "permitted_action": "COLLECT_PERMITTED_PUBLIC_EVIDENCE",
                                    "reason": "Business changed or left the eligible queue during review; current evidence is required"}
            decision = schedule(result, entry["fingerprint"], refresh_hours=config["refresh_hours"])
            result["next_retry_at"] = decision["due_at"]
            atomic(job / (str(bid) + ".json"), result)
            atomic(state / "latest" / (str(bid) + ".json"), result)
            task = task_for(result)
            # Default receipt is advisory in legacy configs; activation is explicit.
            if config.get("draft_preparation_enabled") or config.get("automatic_identity_resolution"):
                atomic(state / "tasks" / (str(bid) + ".json"), task)
            outcomes.append({"business_id": bid, "company": business["name"], "status": result["status"],
                             "error": result.get("error"), "route": (result.get("row") or {}).get("judge", {}).get("route")})
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(max(1, math.ceil(job_end - time.monotonic())))
        supported = sum(o["status"] == "COMPLETE" and o["route"] == "MACHINE_SUPPORTED_RECOMMENDATION" for o in outcomes)
        summary = {"cases": len(outcomes), "attempted": len(request["cases"]), "machine_supported": supported,
                   "exceptions": len(outcomes) - supported,
                   "errors": sum(o["status"] in {"REVIEW_ERROR", "TIMEOUT", "INCOMPLETE"} for o in outcomes),
                   "stale": sum(o["status"] == "STALE_LIVE_STATE" for o in outcomes)}
        (job / "REVIEW.html").write_text(report_html(summary, rows, outcomes), encoding="utf-8")
        status = "COMPLETE" if all(o["status"] == "COMPLETE" for o in outcomes) else "COMPLETED_WITH_ERRORS"
        atomic(job / "RESULT.json", {"status": status, "version": VERSION, "kind": "CONTACT_REVIEW",
               "job_directory": str(job), "cases": outcomes, "summary": summary,
               "timings": {"job_seconds": round(time.monotonic() - started, 6)},
               "source_hashes": request["source_hashes"], "external_sends": 0, "model_calls": 0,
               "paid_ai_cost": 0, "pipeline_writes": 0, "independent_human_labels_created": 0})
        if config.get("draft_preparation_enabled"):
            publish_draft_inbox(state)
        write_manifest(job)
        for bid, folder, doc, acq_key in collections:
            cached = cache_entry(job, folder, doc, acq_key)
            if cached:
                atomic(state / "cache" / (str(bid) + ".json"), cached)
    except Exception as exc:
        attempted_ids = {o["business_id"] for o in outcomes}
        for entry in request["cases"]:
            bid = entry["business"]["live_business_id"]
            if bid not in attempted_ids:
                outcomes.append({"business_id": bid, "company": entry["business"]["name"], "status": "INCOMPLETE", "error": str(exc)[:240]})
        atomic(job / "RESULT.json", {"status": "INCOMPLETE", "job_directory": str(job),
               "cases": outcomes, "error": type(exc).__name__ + ": " + str(exc)[:240]})
        (job / "REVIEW.html").write_text(report_html({"cases": len(outcomes)}, rows, outcomes), encoding="utf-8")
        raise
    finally:
        signal.alarm(0)
        collect_case.deadline = None


def process_draft_job(job, request):
    from mm_contact_draft_bridge import prepare_draft
    from mm_contact_review_consumer import eligible
    state = root() / "state/contact-review"
    config = request["config"]
    def expired(signum, frame):
        raise TimeoutError("CONTACT_DRAFT_JOB_DEADLINE")
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(config["job_timeout_seconds"])
    results = []
    try:
        for entry in request["cases"]:
            business = entry["business"]
            bid = business["live_business_id"]
            task_path = state / "tasks" / (str(bid) + ".json")
            try:
                current = current_business(bid)
                if current is None or fingerprint(current, request["source_hashes"]) != entry["fingerprint"]:
                    raise ValueError("STALE_DRAFT_HANDOFF")
                receipt = entry["review_receipt"]
                origin = Path(receipt["job_directory"]).resolve()
                if not origin.is_relative_to(state.resolve() / "runs"):
                    raise ValueError("Draft review escaped owned runtime")
                manifest = read_json(origin / "MANIFEST.json", {})
                original = origin / (str(bid) + ".json")
                if manifest.get(original.name) != hash_file(original) or read_json(original) != receipt:
                    raise ValueError("DRAFT_REVIEW_MANIFEST_CHANGED")
                recipient = receipt["row"]["verifier"]["selected"]["email"]
                with connect(readonly=True) as d:
                    if not eligible(d, bid, recipient):
                        raise ValueError("DRAFT_INELIGIBLE_OR_SUPPRESSED")
                result = prepare_draft(business, receipt, root(), budget_seconds=config["job_timeout_seconds"] - 20)
                with connect(readonly=True) as d:
                    if not eligible(d, bid, recipient):
                        raise ValueError("DRAFT_ELIGIBILITY_CHANGED")
                current = current_business(bid)
                if current is None or fingerprint(current, request["source_hashes"]) != entry["fingerprint"] or request["source_hashes"] != source_hashes():
                    raise ValueError("DRAFT_HANDOFF_CHANGED")
            except Exception as exc:
                result = {"status": "HELD", "business_id": bid, "technical_holds": [type(exc).__name__ + ": " + str(exc)[:240]], "external_sends": 0}
            result.update(business_fingerprint=entry["fingerprint"], business_snapshot=business,
                          review_source_hashes=request["source_hashes"])
            atomic(state / "drafts" / (str(bid) + ".json"), result)
            task = read_json(task_path, {})
            atomic(task_path, {**task, "business_id": bid, "status": result["status"], "draft_receipt": result,
                               "reason_code": "DRAFT_READY" if result["status"] == "DRAFT_READY" else "DRAFT_HELD",
                               "technical_holds": result.get("technical_holds", [])})
            results.append(result)
        publish_draft_inbox(state)
        atomic(job / "RESULT.json", {"status": "COMPLETE", "kind": "DRAFT_PREPARATION", "cases": results,
               "source_hashes": request["source_hashes"], "external_sends": 0, "model_calls": 0, "paid_ai_cost": 0})
        write_manifest(job)
    finally:
        signal.alarm(0)


def publish_draft_inbox(state):
    from mm_contact_draft_bridge import build_approval_page
    from mm_contact_review_consumer import eligible
    drafts, represented = [], set()
    for path in sorted((state / "drafts").glob("*.json")):
        draft = read_json(path, {})
        bid = draft.get("business_id")
        if not bid:
            continue
        represented.add(bid)
        if draft.get("status") == "DRAFT_READY":
            business = current_business(bid)
            hashes = source_hashes()
            with connect(readonly=True) as d:
                allowed = eligible(d, bid, draft.get("recipient", ""))
            if not allowed or not business or fingerprint(business, hashes) != draft.get("business_fingerprint"):
                draft = {**draft, "status": "HELD", "technical_holds": ["BUSINESS_CHANGED_OR_SUPPRESSED"]}
        drafts.append(draft)
    for path in sorted((state / "tasks").glob("*.json")):
        task = read_json(path, {})
        if not task.get("business_id") or task.get("business_id") in represented:
            continue
        drafts.append({"status": "HELD", "business_id": task.get("business_id"),
                       "technical_holds": task.get("required_evidence", []) or [task.get("reason_code", "Automatic review pending")]})
    return build_approval_page(drafts, state / "DRAFT_APPROVAL.html")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--process-job", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    job = args.process_job.resolve()
    if not job.is_relative_to(root() / "state/contact-review/runs"):
        raise ValueError("Worker job must be in the owned review runtime")
    process_job(job)


if __name__ == "__main__":
    main()

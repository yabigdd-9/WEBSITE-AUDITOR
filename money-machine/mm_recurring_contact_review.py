"""One bounded advisory contact-review child owned by the existing supervisor.

The supervisor polls without waiting for network work. This module reads live
businesses, writes separate evidence artifacts, and never transitions pipeline
items, modifies release policy, creates human labels, calls models or sends.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import yaml

from mm_core import connect, root

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from mm_contact_review_pathway import review_case, report_html, safe_child  # noqa: E402
from mm_email_network import Crawler, DNSChecks  # noqa: E402
import mm_email as email  # noqa: E402
from email_baseline_capture import get_public  # noqa: E402

VERSION = "recurring-contact-review-v1.0"
ELIGIBLE = {"IDENTITY_PENDING", "CONTACT_PENDING", "NEEDS_REVIEW"}
_owned = None
_lock = None
_job = None
_last_scan = 0.0


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
    files = ["money-machine/mm_email.py", "money-machine/mm_email_network.py",
             "money-machine/email_baseline_capture.py", "auditor_toolkit/identity.py",
             "money-machine/mm_contact_review_pathway.py",
             "money-machine/mm_recurring_contact_review.py",
             "money-machine/config/contact_review_schedule.yaml",
             "money-machine/config/disposable_email_blocklist.conf"]
    return {rel: hash_file(ROOT / rel) for rel in files}


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
                           ("max_businesses_per_job", 1, 5), ("job_timeout_seconds", 30, 300),
                           ("max_pages", 1, 5), ("max_requests", 1, 8), ("max_dns_domains", 1, 5)]:
        value = config.get(key)
        if type(value) is not int or not low <= value <= high:
            raise ValueError("Out-of-bounds review setting: " + key)
    if config["max_requests"] < config["max_pages"]:
        raise ValueError("Request limit must cover page limit")
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
    """Called in every supervisor cycle; network work never blocks its heartbeat."""
    global _owned, _lock, _job, _last_scan
    state = root() / "state/contact-review"
    if _owned is not None:
        code = _owned.poll()
        if code is None:
            return {"ran": False, "reason": "worker_running", "worker_pid": _owned.pid}
        result = read_json(_job / "RESULT.json", {"status": "INCOMPLETE", "returncode": code})
        result = {**result, "worker_pid": _owned.pid, "returncode": code, "finished_at": now()}
        atomic(state / "status.json", result)
        request = read_json(_job / "JOB.json", {})
        for entry in request.get("cases", []):
            latest_path = state / "latest" / (str(entry["business"]["live_business_id"]) + ".json")
            latest = read_json(latest_path, {})
            if latest.get("status") == "SCHEDULED" and latest.get("job_directory") == str(_job):
                atomic(latest_path, {**latest, "status": "INCOMPLETE", "reviewed_at": now(),
                                    "error": result.get("error", "Review child did not finish this case")})
        _lock.close()
        _owned, _lock, _job = None, None, None
        return {"ran": True, "reason": "worker_finished", **result}
    if time.monotonic() - _last_scan < 30:
        return {"ran": False, "reason": "not_due"}
    config = load_config()
    if config.get("enabled") is not True:
        return {"ran": False, "reason": "disabled"}
    if _last_scan and time.monotonic() - _last_scan < config["scan_interval_seconds"]:
        return {"ran": False, "reason": "not_due"}
    _last_scan = time.monotonic()
    hashes = source_hashes()
    pending = []
    for business in candidates(d):
        latest = read_json(state / "latest" / (str(business["live_business_id"]) + ".json"), {})
        age = email.age_days(latest.get("reviewed_at")) * 24
        key = fingerprint(business, hashes)
        if latest.get("fingerprint") != key or not 0 <= age < config["refresh_hours"]:
            pending.append((latest.get("reviewed_at", ""), business["live_business_id"], business, key))
    pending.sort(key=lambda row: (row[0], row[1]))
    if not pending:
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
    selected = [{"business": row[2], "fingerprint": row[3]}
                for row in pending[:config["max_businesses_per_job"]]]
    policy = read_json(root() / "state/contact-review-policy.json", {})
    request = {"version": VERSION, "created_at": now(), "supervisor_pid": os.getpid(),
               "config": config, "source_hashes": hashes, "cases": selected,
               "seed_packets": policy.get("seed_packets", [])}
    atomic(job / "JOB.json", request)
    atomic(job / "PRIOR_REVIEWS.json", {str(row["business"]["live_business_id"]):
           read_json(state / "latest" / (str(row["business"]["live_business_id"]) + ".json"))
           for row in selected})
    with (job / "worker.log").open("w") as log:
        os.chmod(job / "worker.log", 0o600)
        try:
            proc = subprocess.Popen(
                [sys.executable, "-B", "-m", "mm_recurring_contact_review", "--process-job", str(job)],
                cwd=str(ROOT / "money-machine"), env=os.environ.copy(),
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                pass_fds=(owner_lock.fileno(),),
            )
        except Exception:
            owner_lock.close()
            raise
    _owned, _lock, _job = proc, owner_lock, job
    for entry in selected:
        atomic(state / "latest" / (str(entry["business"]["live_business_id"]) + ".json"), {
            "status": "SCHEDULED", "reviewed_at": now(), "fingerprint": entry["fingerprint"],
            "job_directory": str(job), "live_business_id": entry["business"]["live_business_id"],
        })
    status = {"status": "RUNNING", "started_at": now(), "supervisor_pid": os.getpid(),
              "worker_pid": proc.pid, "job_directory": str(job),
              "business_ids": [row["business"]["live_business_id"] for row in selected],
              "external_sends": 0, "model_calls": 0, "pipeline_writes": 0}
    atomic(state / "status.json", status)
    return {"ran": True, "reason": "worker_started", **status}


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
            if any(not 0 <= email.age_days(v.get("checked_at")) <= 1 for v in doc["dns"].values()):
                continue
            for page in doc["pages"]:
                capture = safe_child(packet / "evidence", page["path"])
                rel = str(capture.relative_to(packet))
                if hash_file(capture) != manifest[rel]["sha256"] or hash_file(capture) != page["sha256"]:
                    raise ValueError("Seed capture changed")
            return packet, {**doc, "business": business}, "SAVED_CAPTURE_REUSED"
    return None


def collect_case(business, job, config):
    folder = job / business["id"]
    evidence = folder / "evidence"
    evidence.mkdir(parents=True, mode=0o700)
    robots, calls = {}, []
    def fetch(url):
        split = urlsplit(url)
        origin = split.scheme + "://" + split.netloc
        if origin not in robots:
            try:
                meta, raw = get_public(origin + "/robots.txt", redirects=2)
                parser = RobotFileParser()
                parser.parse(raw.decode("utf-8", "replace").splitlines())
                robots[origin] = parser
                (evidence / ("robots-" + meta["sha256"] + ".txt")).write_bytes(raw)
                calls.append({"url": origin + "/robots.txt", "status": "captured"})
            except ValueError as exc:
                robots[origin] = None if str(exc) in {"HTTP_404", "HTTP_410"} else False
                calls.append({"url": origin + "/robots.txt", "status": str(exc)})
            except OSError:
                robots[origin] = False
                calls.append({"url": origin + "/robots.txt", "status": "unavailable"})
        if robots[origin] is False or (robots[origin] and not robots[origin].can_fetch("MoneyMachine-EvidenceReview", url)):
            raise ValueError("ACCESS_RESTRICTED_OR_ROBOTS_UNAVAILABLE")
        meta, raw = get_public(url, redirects=2)
        calls.append({"url": url, "status": "captured", "redirects": meta["redirects"]})
        return meta, raw
    pages, errors = Crawler(evidence, max_pages=config["max_pages"],
                            max_requests=config["max_requests"], fetcher=fetch).crawl(business["public_website"])
    domains = sorted({o["email"].rsplit("@", 1)[-1] for p in pages for o in p["observations"]
                      if not o["syntax_error"]})[:config["max_dns_domains"]]
    dns = DNSChecks(evidence / "dns.json")
    dns_results = {domain: dns.check(domain) for domain in domains}
    meta = [{key: p[key] for key in ("url", "requested_url", "captured_at", "sha256", "path", "content_type", "redirects") if key in p} for p in pages]
    doc = {"business": business, "pages": meta, "dns": dns_results, "errors": errors}
    atomic(folder / "COLLECTION.json", {**doc, "public_fetch_calls": calls})
    return folder, doc, "PUBLIC_GET_DNS"


def process_job(job):
    request = read_json(job / "JOB.json")
    if request["source_hashes"] != source_hashes() or request["config"] != load_config():
        raise ValueError("Review source changed after job scheduling")
    def timeout_handler(signum, frame):
        raise RuntimeError("CONTACT_REVIEW_JOB_DEADLINE")
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(request["config"]["job_timeout_seconds"])
    rows, outcomes = [], []
    try:
        for entry in request["cases"]:
            business = entry["business"]
            bid = business["live_business_id"]
            try:
                loaded = seed_case(business, request["seed_packets"])
                packet, doc, method = loaded or collect_case(business, job, request["config"])
                row = review_case(business, doc, packet, datetime.now(timezone.utc))
                row["collection_method"] = method
                rows.append(row)
                result = {"status": "COMPLETE", "row": row}
            except Exception as exc:
                if str(exc) == "CONTACT_REVIEW_JOB_DEADLINE":
                    raise
                result = {"status": "REVIEW_ERROR", "error": type(exc).__name__ + ": " + str(exc)[:240]}
            result.update({"reviewed_at": now(), "fingerprint": entry["fingerprint"],
                           "live_business_id": bid, "job_directory": str(job),
                           "external_sends": 0, "model_calls": 0, "paid_ai_cost": 0,
                           "pipeline_writes": 0, "independent_human_label": None})
            if request["source_hashes"] != source_hashes():
                raise ValueError("Review source changed during job")
            with connect(readonly=True) as d:
                current = next((b for b in candidates(d) if b["live_business_id"] == bid), None)
            if current is None or fingerprint(current, request["source_hashes"]) != entry["fingerprint"]:
                result["status"] = "STALE_LIVE_STATE"
            atomic(job / (str(bid) + ".json"), result)
            atomic(root() / "state/contact-review/latest" / (str(bid) + ".json"), result)
            outcomes.append({"business_id": bid, "status": result["status"],
                             "route": (result.get("row") or {}).get("judge", {}).get("route")})
        summary = {"cases": len(rows), "machine_supported": sum(r["proofer"]["passed"] for r in rows),
                   "exceptions": sum(not r["proofer"]["passed"] for r in rows)}
        (job / "REVIEW.html").write_text(report_html(summary, rows), encoding="utf-8")
        status = "COMPLETE" if all(r["status"] == "COMPLETE" for r in outcomes) else "COMPLETED_WITH_ERRORS"
        atomic(job / "RESULT.json", {"status": status, "version": VERSION,
               "job_directory": str(job), "cases": outcomes, "summary": summary,
               "source_hashes": request["source_hashes"], "external_sends": 0,
               "model_calls": 0, "paid_ai_cost": 0, "pipeline_writes": 0,
               "independent_human_labels_created": 0})
        atomic(job / "MANIFEST.json", {str(p.relative_to(job)): hash_file(p)
               for p in sorted(job.rglob("*")) if p.is_file() and p.name not in {"MANIFEST.json", "worker.log"}})
    except Exception as exc:
        atomic(job / "RESULT.json", {"status": "INCOMPLETE", "job_directory": str(job),
               "cases": outcomes, "error": type(exc).__name__ + ": " + str(exc)[:240]})
        raise
    finally:
        signal.alarm(0)


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

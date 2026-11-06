"""Reuse immutable collection evidence, never reuse its historical decisions."""
from __future__ import annotations

import copy
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import mm_email as email
from mm_contact_review_pathway import safe_child

ACQUISITION_FILES = ("money-machine/email_baseline_capture.py", "money-machine/mm_email_network.py",
                     "money-machine/mm_contact_review_network.py")
ACQUISITION_FIELDS = ("max_pages", "max_requests", "max_dns_domains",
                      "collection_timeout_seconds", "dns_timeout_seconds")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def acquisition_key(business, hashes, config):
    # Pipeline timestamps and decision rules do not change the captured site.
    fields = {k: v for k, v in business.items() if k not in
              {"pipeline_updated_at", "pipeline_state_at_freeze"}}
    value = {"business": fields, "network": {k: hashes[k] for k in ACQUISITION_FILES if k in hashes},
             "config": {k: config.get(k) for k in ACQUISITION_FIELDS}}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def cache_entry(job, folder, doc, acquisition_fingerprint):
    collection = folder / "COLLECTION.json"
    manifest = job / "MANIFEST.json"
    if not collection.is_file() or not manifest.is_file() or not doc.get("pages"):
        return None
    # Never treat partial acquisition failures as a complete collection cache.
    if doc.get("errors"):
        return None
    return {"acquisition_fingerprint": acquisition_fingerprint, "job": str(job),
            "folder": str(folder), "collection_sha256": sha(collection),
            "manifest_sha256": sha(manifest), "saved_at": datetime.now(timezone.utc).isoformat()}


def reuse(entry, business, acquisition_fingerprint, runtime, *, dns_factory=None, deadline=None):
    started = time.monotonic()
    def check_deadline():
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError("CONTACT_REVIEW_CASE_DEADLINE")
    check_deadline()
    if not entry or entry.get("acquisition_fingerprint") != acquisition_fingerprint:
        return None
    runtime = Path(runtime).resolve()
    job = Path(entry["job"]).resolve()
    folder = Path(entry["folder"]).resolve()
    if not job.is_relative_to(runtime / "state/contact-review/runs") or not folder.is_relative_to(job):
        raise ValueError("Cache escaped owned review runtime")
    manifest_path = job / "MANIFEST.json"
    collection = folder / "COLLECTION.json"
    if sha(manifest_path) != entry["manifest_sha256"] or sha(collection) != entry["collection_sha256"]:
        raise ValueError("Cached collection or manifest changed")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get(str(collection.relative_to(job))) != sha(collection):
        raise ValueError("Collection not covered by cached manifest")
    doc = json.loads(collection.read_text())
    frozen = doc.get("business", {})
    if any(frozen.get(k) != v for k, v in business.items() if k not in
           {"pipeline_updated_at", "pipeline_state_at_freeze"}):
        raise ValueError("Cached evidence belongs to another business/unit")
    at = datetime.now(timezone.utc)
    if not doc.get("pages") or any(not 0 <= email.age_days(p.get("captured_at"), at) <= 1 for p in doc["pages"]):
        return None
    for page in doc["pages"]:
        check_deadline()
        capture = safe_child(folder / "evidence", page["path"])
        if sha(capture) != page["sha256"] or manifest.get(str(capture.relative_to(job))) != page["sha256"]:
            raise ValueError("Cached capture integrity failed")
    doc = copy.deepcopy(doc)
    stale_dns = [domain for domain, result in doc.get("dns", {}).items()
                 if not 0 <= email.age_days(result.get("checked_at"), at) <= 1 / 24]
    if stale_dns:
        if dns_factory is None:
            return None
        checker = dns_factory()
        end = min(deadline or float("inf"), time.monotonic() + 15)
        for domain in stale_dns:
            if time.monotonic() >= end:
                raise TimeoutError("CONTACT_REVIEW_DNS_DEADLINE")
            # DNS checks support a bounded stage deadline; no HTML is fetched.
            doc["dns"][domain] = checker.check(domain, deadline=end)
    check_deadline()
    doc["business"] = business
    doc["historical_acquisition_metrics"] = {
        "stage_timings": doc.get("stage_timings", {}), "request_metrics": doc.get("request_metrics", {})}
    doc["stage_timings"] = {"collection_seconds": 0, "dns_seconds": round(time.monotonic() - started, 6) if stale_dns else 0,
                            "cache_validation_seconds": round(time.monotonic() - started, 6)}
    doc["request_metrics"] = {"public_fetch_calls": 0, "actual_requests": 0, "reserved_requests": 0, "actual_http_attempts": 0,
                              "cache_hit": True, "dns_refreshed_domains": len(stale_dns)}
    return folder, doc, "HASH_VERIFIED_CAPTURE_REUSED"

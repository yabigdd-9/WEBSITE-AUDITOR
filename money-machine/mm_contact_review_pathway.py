"""Advisory scout -> identity -> verifier -> proofer -> judge workers.

Replay a frozen capture packet without network requests or database writes.
An optional, explicitly requested free AI advisor can suggest a worker from
the fixed registry. It cannot change gates, execute commands or label humans.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mm_email as verifier  # noqa: E402

VERSION = "contact-review-pathway-v1.0"
WORKERS = {
    "SCOUT": "Load frozen cases and hash-check original page captures",
    "IDENTITY": "Check company/domain/unit identity and propose evidenced names",
    "CONTACT_VERIFIER": "Re-run the committed email verifier with captured DNS",
    "EVIDENCE_PROOFER": "Separately confirm publication, purpose and capture linkage",
    "JUDGE": "Route supported recommendations and exceptions using fixed gates",
}
CONTACT_PATH = re.compile(r"(?:contact|enquir|quote|touch)", re.I)
BAD_PURPOSE = re.compile(
    r"\b(?:jobs?|careers?|recruitment|privacy|legal|billing|invoices?|webmaster|"
    r"noreply|no-reply|developer)\b", re.I
)
MAX_BYTES = 8 * 1024 * 1024


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_child(base: Path, relative: str) -> Path:
    path = (base / relative).resolve()
    if not path.is_relative_to(base.resolve()) or path == base.resolve():
        raise ValueError("Evidence path escapes its packet")
    return path


def read_limited(path: Path) -> bytes:
    with path.open("rb") as handle:
        data = handle.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Input exceeds bounded file size")
    return data


def load_json(path: Path):
    return json.loads(read_limited(path))


def save_json(path: Path, value):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    path.chmod(0o600)


def compact_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", verifier.normalize_name(value))


def identity_worker(business, pages, result):
    """Suggest domain-linked trading names without rewriting the frozen case."""
    proposed = {}
    root = verifier.root_domain(business["public_website"])
    domain_stem = verifier.PSL(root).domain
    for page in pages:
        if verifier.root_domain(page["url"]) != root:
            continue
        candidates = page["organization_names"] + page["headings"][:4]
        candidates += re.split(r"\s*[|–—]\s*|\s+-\s+", page["title"])
        for name in candidates:
            name = name.strip()
            if not name or len(name) > 100 or ".co.nz" in name:
                continue
            if compact_name(name) != compact_name(domain_stem):
                continue
            if not verifier.name_matches(name, page["text"]):
                continue
            proposed.setdefault(name, set()).add(page["url"])
    suggestions = [
        {"name": name, "source_urls": sorted(urls),
         "basis": "Prominent first-party name agrees with domain stem and visible text",
         "applied_to_frozen_case": False}
        for name, urls in sorted(proposed.items())
        if compact_name(name) != compact_name(business["name"])
    ]
    return {
        "worker": "IDENTITY", "status": result["identity"]["status"],
        "reasons": result["identity"]["reasons"],
        "name_suggestions": suggestions,
        "unit_scope": business.get("unit_scope"),
        "scope_note": "Named business website; no inference of an unrecorded branch",
    }


def publication_proof(meta, raw, address):
    """Independent HTML publication predicates, separate from scoring extraction."""
    if "html" not in meta.get("content_type", ""):
        return None
    soup = BeautifulSoup(raw, "html.parser")
    for node in soup.select("script,style,noscript,svg,template,[hidden],"
                            "[aria-hidden='true'],input,textarea"):
        node.decompose()
    mailto = any(
        unquote(node.get("href", "")[7:].split("?")[0]).strip() == address
        for node in soup.select("a[href]")
        if node["href"].lower().startswith("mailto:")
    )
    visible = bool(re.search(
        r"(?<![\w.+@-])" + re.escape(address) + r"(?![\w.@-])",
        soup.get_text(" ", strip=True)
    ))
    if not (mailto or visible):
        return None
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    contact_page = bool(CONTACT_PATH.search(urlsplit(meta["url"]).path + " " + title))
    return {
        "source_url": meta["url"], "capture_sha256": meta["sha256"],
        "captured_at": meta["captured_at"], "mailto": mailto,
        "visible_text": visible, "contact_page": contact_page,
    }


def proofer_worker(business, result, captures, at):
    selected = result["selected"]
    if not selected:
        return {"worker": "EVIDENCE_PROOFER", "passed": False,
                "checks": {}, "sources": [], "reason": "No selected contact to prove"}
    address = selected["email"]
    root = result["identity"]["canonical_root_domain"]
    sources = []
    for meta, raw in captures:
        if verifier.root_domain(meta["url"]) != root:
            continue
        if not 0 <= verifier.age_days(meta["captured_at"], at) <= 7:
            continue
        proof = publication_proof(meta, raw, address)
        if proof:
            sources.append(proof)
    local_part = address.split("@")[0]
    checks = {
        "strict_company_identity": result["identity"]["status"] == "HIGH",
        "exact_publication_reconfirmed": bool(sources),
        "official_domain_agrees": selected["domain_match"] is True,
        "requested_unit_agrees": selected["business_match"] is True,
        "current_dns_supports_mail": selected["domain_accepts_mail"] is True
            and selected["mx_present"] is True
            and 0 <= verifier.age_days(selected["dns_checked_at"], at) <= 7,
        "appropriate_published_purpose": any(s["contact_page"] for s in sources)
            and not BAD_PURPOSE.search(local_part)
            and selected["role_account"] not in verifier.BAD_ROLES,
        "no_verifier_rejections": not selected["rejection_reasons"],
        "committed_verifier_selected_high": selected["confidence_label"] == "VERIFIED_HIGH",
    }
    return {"worker": "EVIDENCE_PROOFER", "passed": all(checks.values()),
            "checks": checks, "sources": sources,
            "independent_human_review": False,
            "mailbox_delivery_proven": False}


def judge_worker(doc, result, proof):
    if proof["passed"] and result["selected"]:
        route = "MACHINE_SUPPORTED_RECOMMENDATION"
        next_worker = "JUDGE"
        reason = "Company, publication, contact purpose, unit and DNS gates passed"
    elif not doc["pages"]:
        route, next_worker, reason = "EVIDENCE_NEEDED", "SCOUT", "No captured first-party pages"
    elif result["identity"]["status"] != "HIGH":
        route, next_worker, reason = "IDENTITY_EXCEPTION", "IDENTITY", "Strict company or unit identity is unresolved"
    elif not result["selected"]:
        route, next_worker, reason = "CONTACT_EXCEPTION", "CONTACT_VERIFIER", "No contact meets the committed selection gates"
    else:
        route, next_worker, reason = "PROOF_EXCEPTION", "EVIDENCE_PROOFER", "Publication or purpose proof is incomplete"
    return {
        "worker": "JUDGE", "route": route, "next_worker": next_worker, "reason": reason,
        "pipeline_state_at_capture": doc["business"].get("pipeline_state_at_freeze"),
        "pipeline_action": "NONE", "outreach_eligible": False,
        "human_precision_label": None, "precision_release_authority": False,
        "note": "A supported recommendation cannot clear a rejection, suppression or release hold",
    }


def review_case(business, doc, packet, at):
    if doc["business"] != business:
        raise ValueError("Case does not match frozen business")
    captures, pages = [], []
    if len(doc["pages"]) > 5:
        raise ValueError("Case exceeds bounded page count")
    for meta in doc["pages"]:
        raw = read_limited(safe_child(packet / "evidence", meta["path"]))
        if digest(raw) != meta["sha256"]:
            raise ValueError("Raw capture digest mismatch")
        captures.append((meta, raw))
        pages.append(verifier.parse_page(meta, raw))
    result = verifier.evaluate(business, pages, doc["dns"], at=at)
    identity = identity_worker(business, pages, result)
    proof = proofer_worker(business, result, captures, at)
    return {
        "case_id": business["id"], "live_business_id": business.get("live_business_id"),
        "company": business["name"], "website": business["public_website"],
        "scout": {"worker": "SCOUT", "pages_hash_verified": len(pages),
                  "acquisition_errors": doc["errors"], "new_requests": 0},
        "identity": identity, "verifier": result,
        "proofer": proof, "judge": judge_worker(doc, result, proof),
    }


def ai_advice(rows):
    """Explicit opt-in, one bounded free-role request with no contact/page PII."""
    from mm_model_router import local_complete
    assignments = [{"case_id": r["case_id"], "route": r["judge"]["route"],
                    "required_worker": r["judge"]["next_worker"]}
                   for r in rows if r["judge"]["route"] != "MACHINE_SUPPORTED_RECOMMENDATION"]
    prompt = (
        "Suggest worker assignments for this non-confidential routing table, containing "
        "no company names, page text or contacts. Return ONLY a JSON "
        "object mapping case_id to required_worker, using the required worker already shown. "
        "You have no authority to approve contacts, execute tools, or change gates.\n"
        + json.dumps(assignments)
    )
    # Propagate failure. Do not repeatedly retry, silently upgrade routes, or
    # report unsupported cost as a success. Existing router enforces free lanes.
    response = local_complete(prompt, purpose="orchestrator", max_tokens=1000, timeout=45)
    proposed = json.loads(response["text"])
    expected = {r["case_id"]: r["required_worker"] for r in assignments}
    accepted = {key: value for key, value in proposed.items()
                if key in expected and value in WORKERS and value == expected[key]}
    return {"status": "ADVISORY_ONLY", "provider": response["provider"],
            "model": response["model"], "cost_usd": response["cost_usd"],
            "model_calls": 1, "accepted_assignments": accepted,
            "discarded_assignments": len(proposed) - len(accepted),
            "can_change_judge_decisions": False}


def report_html(summary, rows):
    esc = lambda value: html.escape(str(value), quote=True)
    cards = []
    for row in rows:
        selected = row["verifier"]["selected"]
        route = row["judge"]["route"]
        supported = route == "MACHINE_SUPPORTED_RECOMMENDATION"
        reasons = row["identity"]["reasons"] if not supported else []
        failed = [key.replace("_", " ") for key, ok in row["proofer"]["checks"].items() if not ok]
        body = "<p>" + esc(selected["email"] if selected else "No selected contact") + "</p>"
        body += "<p>" + esc(row["judge"]["reason"]) + "</p>"
        body += "<p>Next worker: <strong>" + esc(row["judge"]["next_worker"]) + "</strong></p>"
        body += "<ul>" + "".join("<li>" + esc(r) + "</li>" for r in reasons + failed) + "</ul>"
        if row["identity"]["name_suggestions"]:
            body += "<p>Evidence-backed name suggestions: " + esc(
                ", ".join(s["name"] for s in row["identity"]["name_suggestions"])) + "</p>"
        body += "<p>Captured pipeline state: " + esc(row["judge"]["pipeline_state_at_capture"]) + " — no change made.</p>"
        body += "<ul>" + "".join(
            '<li><a href="' + esc(s["source_url"]) + '">' + esc(s["source_url"]) + '</a><br><small>Capture: '
            + esc(s["capture_sha256"]) + "</small></li>" for s in row["proofer"]["sources"]) + "</ul>"
        cards.append('<details data-supported="' + str(supported).lower() + '"><summary>'
                     + esc(row["company"]) + " · " + esc(route.replace("_", " ").lower())
                     + "</summary>" + body + "</details>")
    return """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<title>Automatic contact review</title><style>body{font:17px system-ui;max-width:1000px;margin:40px auto;padding:0 20px;background:#f4f7fa;color:#192d39}h1{font-size:32px}details{background:white;border:1px solid #bbcbd4;border-radius:10px;margin:12px 0;padding:18px}summary{cursor:pointer;font-weight:650}small{overflow-wrap:anywhere}button{padding:10px 16px;margin:6px;font:inherit}a{color:#14627e}</style>
<h1>Automatic contact review</h1><p>Scout → Identity → Contact verifier → Evidence proofer → Judge</p>
<p>""" + esc(summary["cases"]) + " cases processed · " + esc(summary["machine_supported"]) + " supported recommendations · " + esc(summary["exceptions"]) + " exceptions</p><p>These are machine recommendations. Human precision labels, release approval and sending permission remain separate. Individual mailbox delivery is unproven.</p><button onclick=\"show('all')\">All cases</button><button onclick=\"show('true')\">Supported</button><button onclick=\"show('false')\">Exceptions</button>" + "".join(cards) + "<script>function show(value){document.querySelectorAll('details').forEach(d=>{d.hidden=value!=='all'&&d.dataset.supported!==value})}</script>"


def run(packet: Path, output: Path, enable_ai=False):
    packet, output = packet.resolve(), output.resolve()
    if output == packet or output.is_relative_to(packet) or packet.is_relative_to(output):
        raise ValueError("Output must be separate from the frozen input packet")
    frame_bytes = read_limited(packet / "sample.json")
    frame = json.loads(frame_bytes)
    if digest(frame_bytes) != (packet / "FRAME_SHA256.txt").read_text().strip():
        raise ValueError("Frozen frame hash changed")
    cases = frame["cases"]
    ids = [case["id"] for case in cases]
    if not 1 <= len(ids) <= 50 or len(set(ids)) != len(ids):
        raise ValueError("Require 1–50 unique frozen cases")
    if any(not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", case_id) for case_id in ids):
        raise ValueError("Unsafe case identifier")
    source_root = Path(__file__).resolve().parents[1]
    for rel, expected in frame["engine_hashes"].items():
        if digest(read_limited(safe_child(source_root, rel))) != expected:
            raise ValueError("Frozen engine/configuration changed: " + rel)
    manifest = load_json(packet / "PACKET_MANIFEST.json")
    input_hashes = {}
    for rel, entry in manifest["files"].items():
        if rel == "sample.json" or rel.startswith("evidence/"):
            actual = digest(read_limited(safe_child(packet, rel)))
            if actual != entry["sha256"]:
                raise ValueError("Frozen evidence manifest mismatch: " + rel)
            input_hashes[rel] = actual
    if input_hashes.get("sample.json") != digest(frame_bytes):
        raise ValueError("Frozen manifest does not cover the frame")
    # A separate packet-level lock prevents duplicate simultaneous analysis,
    # even when two callers choose different output folders. It lives outside
    # immutable evidence and never signals or interacts with the soak processes.
    lock_path = packet.parent / ("." + packet.name + ".contact-review.lock")
    os.umask(0o077)
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        output.mkdir(mode=0o700, parents=True, exist_ok=False)
        (output / "cases").mkdir(mode=0o700)
        at = datetime.now(timezone.utc)
        rows = []
        for business in cases:
            rel = "evidence/cases/" + business["id"] + ".json"
            if rel not in input_hashes:
                raise ValueError("Frozen manifest does not cover case")
            doc = load_json(safe_child(packet, rel))
            row = review_case(business, doc, packet, at)
            save_json(output / "cases" / (business["id"] + ".json"), row)
            rows.append(row)
        advisor = {"status": "NOT_REQUESTED", "model_calls": 0, "cost_usd": 0}
        if enable_ai:
            advisor = ai_advice(rows)
        routes = Counter(row["judge"]["route"] for row in rows)
        summary = {
            "version": VERSION, "evaluated_at": at.isoformat(), "mode": "CAPTURE_REPLAY_ADVISORY",
            "input_packet": str(packet), "frame_sha256": digest(frame_bytes),
            "frozen_application_revision": frame["application_revision"],
            "verifier_version": verifier.VERSION, "workers": WORKERS,
            "cases": len(rows), "raw_pages_hash_verified": sum(r["scout"]["pages_hash_verified"] for r in rows),
            "observed_contacts": sum(len(r["verifier"]["results"]) for r in rows),
            "machine_supported": routes["MACHINE_SUPPORTED_RECOMMENDATION"],
            "exceptions": len(rows) - routes["MACHINE_SUPPORTED_RECOMMENDATION"], "routes": dict(routes),
            "identity_name_suggestions": sum(bool(r["identity"]["name_suggestions"]) for r in rows),
            "independent_human_labels_created": 0, "precision": None,
            "release_gate_changed": False, "pipeline_writes": 0, "new_public_requests": 0,
            "external_sends": 0, "model_calls": advisor["model_calls"], "paid_ai_cost": advisor["cost_usd"],
            "ai_advisor": advisor, "outreach_eligible": False,
        }
        save_json(output / "SUMMARY.json", summary)
        save_json(output / "WORKER_ASSIGNMENTS.json", [
            {"case_id": r["case_id"], **r["judge"]} for r in rows])
        save_json(output / "RECOMMENDATIONS.json", [
            r for r in rows if r["judge"]["route"] == "MACHINE_SUPPORTED_RECOMMENDATION"])
        save_json(output / "EXCEPTIONS.json", [
            r for r in rows if r["judge"]["route"] != "MACHINE_SUPPORTED_RECOMMENDATION"])
        (output / "REVIEW.html").write_text(report_html(summary, rows), encoding="utf-8")
        # Detect input mutation during this run as well as at its start.
        for rel, expected in input_hashes.items():
            if digest(read_limited(safe_child(packet, rel))) != expected:
                raise ValueError("Input evidence changed during review")
        for rel, expected in frame["engine_hashes"].items():
            if digest(read_limited(safe_child(source_root, rel))) != expected:
                raise ValueError("Frozen engine changed during review: " + rel)
        (output / "MODULE_SNAPSHOT.py").write_bytes(Path(__file__).read_bytes())
        output_files = {str(p.relative_to(output)): digest(p.read_bytes())
                        for p in sorted(output.rglob("*")) if p.is_file()}
        save_json(output / "MANIFEST.json", {
            "status": "COMPLETE", "input_sha256": input_hashes,
            "module_sha256": digest(Path(__file__).read_bytes()), "output_sha256": output_files,
        })
        return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--free-ai-advice", action="store_true",
                        help="Explicitly opt in to one existing certified free role-router request")
    args = parser.parse_args()
    print(json.dumps(run(args.packet, args.output, args.free_ai_advice), indent=2))


if __name__ == "__main__":
    main()

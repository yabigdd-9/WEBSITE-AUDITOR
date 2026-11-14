"""Advisory scout -> identity -> verifier -> proofer -> judge workers.

Replay a frozen capture packet without network requests or database writes.
An optional, explicitly requested free AI advisor can suggest a worker from
the fixed registry. It cannot change gates, execute commands or label humans.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import html
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup, Comment

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mm_email as verifier  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
VERSION = "contact-review-pathway-v1.1"
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
REQUIRED_ENGINE_FILES = (
    "money-machine/mm_email.py", "money-machine/mm_email_network.py",
    "money-machine/email_baseline_capture.py", "auditor_toolkit/identity.py",
    "money-machine/mm_contact_review_pathway.py",
    "money-machine/mm_recurring_contact_review.py",
    "money-machine/config/contact_review_schedule.yaml",
    "money-machine/config/disposable_email_blocklist.conf",
    "money-machine/mm_contact_review_network.py", "money-machine/mm_contact_review_cache.py",
    "money-machine/mm_contact_review_tasks.py", "money-machine/mm_contact_review_consumer.py",
    "money-machine/mm_contact_draft_bridge.py", "auditor_toolkit/packet.py",
    "money-machine/mm_email_store.py", "money-machine/mm_core.py",
    "money-machine/mm_approval.py",
)
# Draft builders import scoring/checks/configuration transitively. Freeze their
# complete local Python implementation rather than accepting partial receipts.
REQUIRED_ENGINE_FILES = tuple(sorted(set(REQUIRED_ENGINE_FILES) | {
    str(path.relative_to(ROOT)) for path in (ROOT / "auditor_toolkit").rglob("*.py")
}))


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
    """Confirm exact publication in markup without claiming rendered visibility."""
    if "html" not in meta.get("content_type", "").lower():
        return None
    soup = BeautifulSoup(raw, "html.parser")
    unresolved_styles = bool(soup.find("style") or soup.select('link[rel~="stylesheet"]'))
    verifier.trim_hidden_markup(soup)
    mailto_nodes = [node for node in soup.select("a[href]")
                    if node["href"].lower().startswith("mailto:")
                    and unquote(node["href"][7:].split("?")[0]).strip() == address]
    exact = re.compile(r"(?<![\w.+@-])" + re.escape(address) + r"(?![\w.@-])")
    text_nodes = [node for node in soup.find_all(string=exact)
                  if not isinstance(node, Comment) and node.parent and node.parent.name not in {"title", "head"}]
    def css_dependent(node):
        ancestors = list(node.parents)
        if getattr(node, "attrs", None) is not None:
            ancestors.insert(0, node)
        return unresolved_styles or any(parent.get("class") or parent.get("id") or parent.get("style")
                                        for parent in ancestors if parent.attrs is not None)
    visible = any(not css_dependent(node) for node in text_nodes)
    mailto = any(not css_dependent(node) for node in mailto_nodes)
    uncertain = any(css_dependent(node) for node in text_nodes + mailto_nodes)
    if not (mailto or visible):
        return None
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    contact_page = bool(CONTACT_PATH.search(urlsplit(meta["url"]).path + " " + title))
    return {
        "source_url": meta["url"], "capture_sha256": meta["sha256"],
        "captured_at": meta["captured_at"], "mailto": mailto,
        "visible_text": visible, "contact_page": contact_page,
        "publication_basis": "EXACT_MAILTO_MARKUP" if mailto else "TEXT_WITHOUT_KNOWN_CSS_DEPENDENCE",
        "css_visibility_uncertain": uncertain, "rendered_visibility_proven": False,
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
        if not 0 <= verifier.age_days(meta["captured_at"], at) <= 1:
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
            and 0 <= verifier.age_days(selected["dns_checked_at"], at) <= 1 / 24,
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
    required = {
        "EVIDENCE_NEEDED": ["Fresh permitted first-party page captures"],
        "IDENTITY_EXCEPTION": ["Agreement on the recorded company, domain and requested location/unit"],
        "CONTACT_EXCEPTION": ["A suitable exact published contact meeting the committed verifier gates"],
        "PROOF_EXCEPTION": ["Exact publication, appropriate contact purpose and fresh matching DNS evidence"],
        "MACHINE_SUPPORTED_RECOMMENDATION": ["Independent human contact review and separate release permission"],
    }
    permitted = {
        "SCOUT": "COLLECT_PERMITTED_PUBLIC_EVIDENCE", "IDENTITY": "PROPOSE_EVIDENCED_IDENTITY",
        "CONTACT_VERIFIER": "VERIFY_PUBLISHED_CONTACT", "EVIDENCE_PROOFER": "RECONFIRM_CONTACT_EVIDENCE",
        "JUDGE": "REQUEST_HUMAN_REVIEW",
    }
    blocked = [key for key, passed in proof.get("checks", {}).items() if not passed]
    if route == "EVIDENCE_NEEDED":
        blocked.insert(0, "first_party_captures_missing")
    elif route == "IDENTITY_EXCEPTION":
        blocked.insert(0, "strict_company_or_unit_identity_unresolved")
    elif route == "CONTACT_EXCEPTION":
        blocked.insert(0, "committed_verifier_selected_contact_missing")
    return {
        "worker": "JUDGE", "route": route, "next_worker": next_worker, "reason": reason,
        "reason_codes": [route], "blocking_checks": list(dict.fromkeys(blocked)),
        "required_evidence": required[route], "permitted_action": permitted[next_worker],
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


def validated_identity_candidate(business, doc, packet, at):
    """Validate a unique name proposal without applying it or approving contacts."""
    row = review_case(business, doc, packet, at)
    suggestions = row["identity"]["name_suggestions"]
    unique = {compact_name(proposal["name"]): proposal for proposal in suggestions}
    if len(unique) != 1:
        return None
    proposal = next(iter(unique.values()))
    if compact_name(proposal["name"]) == compact_name(business["name"]):
        return None
    proposed = {**business, "name": proposal["name"]}
    rerun = review_case(proposed, {**doc, "business": proposed}, packet, at)
    identity = rerun["verifier"]["identity"]
    if identity["status"] != "HIGH" or identity.get("weighted_confidence", {}).get("conflicts"):
        return None
    if identity.get("reasons"):
        return None
    if identity.get("branch_sensitive"):
        matched = set(identity.get("matched_branches", []))
        if not matched or not set(identity.get("observed_branches", [])) <= matched:
            return None
    return {"business": proposed, "row": rerun, "proposal": proposal,
            "changed_fields": ["name"], "permitted_action": "APPLY_VALIDATED_IDENTITY_NAME",
            "contact_approval": False, "pipeline_transition_authority": False,
            "external_send_authority": False}


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


def report_html(summary, rows, outcomes=None):
    """Show every attempted case, including cases without a successful review."""
    def esc(value):
        return html.escape(str(value), quote=True)
    cards = []
    if outcomes is None:
        outcomes = [{"business_id": row.get("live_business_id"), "case_id": row["case_id"],
                     "status": "STALE_LIVE_STATE" if row["judge"]["route"] == "STALE_LIVE_STATE" else "COMPLETE",
                     "route": row["judge"]["route"]} for row in rows]
    outcomes = list(outcomes)
    def key(value):
        bid = value.get("business_id", value.get("live_business_id"))
        return ("business", str(bid)) if bid is not None else ("case", str(value.get("case_id", "")))
    indexed = {key(outcome): outcome for outcome in outcomes}
    represented, supported_count = set(), 0
    for row in rows:
        row_key = key(row)
        represented.add(row_key)
        outcome = indexed.get(row_key, {"status": "INCOMPLETE"})
        selected = row["verifier"]["selected"]
        route = row["judge"]["route"]
        status = outcome.get("status", "INCOMPLETE")
        supported = route == "MACHINE_SUPPORTED_RECOMMENDATION" and status == "COMPLETE"
        supported_count += int(supported)
        display_route = route if status == "COMPLETE" else status
        reasons = row["identity"]["reasons"] if not supported else []
        failed = [key.replace("_", " ") for key, ok in row["proofer"]["checks"].items() if not ok]
        body = "<p>" + esc(selected["email"] if selected else "No selected contact") + "</p>"
        if status != "COMPLETE":
            body += "<p>Current result held: " + esc(outcome.get("error") or status) + ". Captured evidence is retained.</p>"
        body += "<p>" + esc(row["judge"]["reason"]) + "</p>"
        body += "<p>Next worker: <strong>" + esc(row["judge"]["next_worker"]) + "</strong></p>"
        if row["judge"].get("required_evidence"):
            body += "<p>Evidence needed: " + esc("; ".join(row["judge"]["required_evidence"])) + "</p>"
        body += "<ul>" + "".join("<li>" + esc(r) + "</li>" for r in reasons + failed) + "</ul>"
        if row["identity"]["name_suggestions"]:
            body += "<p>Evidence-backed name suggestions: " + esc(
                ", ".join(s["name"] for s in row["identity"]["name_suggestions"])) + "</p>"
        body += "<p>Captured pipeline state: " + esc(row["judge"]["pipeline_state_at_capture"]) + " — no change made.</p>"
        source_items = []
        for source in row["proofer"]["sources"]:
            url = source["source_url"]
            try:
                parsed = urlsplit(url)
                safe_link = parsed.scheme in {"https", "http"} and bool(parsed.hostname) and not parsed.username and not parsed.password
            except ValueError:
                safe_link = False
            label = '<a href="' + esc(url) + '" rel="noreferrer">' + esc(url) + "</a>" if safe_link else esc(url)
            source_items.append("<li>" + label + "<br><small>Capture: " + esc(source["capture_sha256"]) + "</small></li>")
        body += "<ul>" + "".join(source_items) + "</ul>"
        cards.append('<details data-supported="' + str(supported).lower() + '"><summary>'
                     + esc(row["company"]) + " · " + esc(display_route.replace("_", " ").lower())
                     + "</summary>" + body + "</details>")
    for outcome in outcomes:
        if key(outcome) in represented:
            continue
        title = outcome.get("company") or outcome.get("case_id") or "Business " + str(outcome.get("business_id", "unknown"))
        status = outcome.get("status", "INCOMPLETE")
        cards.append('<details data-supported="false"><summary>' + esc(title) + " · "
                     + esc(status.replace("_", " ").lower()) + "</summary><p>"
                     + esc(outcome.get("error") or "This attempt did not produce a current recommendation")
                     + "</p><p>Evidence is held for recovery or review. No contact approval or send permission was created.</p></details>")
    attempted = len(outcomes)
    complete = sum(outcome.get("status") == "COMPLETE" for outcome in outcomes)
    stale = sum(outcome.get("status") == "STALE_LIVE_STATE" for outcome in outcomes)
    errors = sum(outcome.get("status") in {"REVIEW_ERROR", "TIMEOUT"} for outcome in outcomes)
    incomplete = attempted - complete - stale - errors
    evaluation_note = ""
    if summary.get("evaluation_mode") == "reevaluate":
        evaluation_note = "<p>Historical captures were re-evaluated with the current engine. This does not accept the historical application revision.</p>"
    elif summary.get("evaluation_mode") == "frozen":
        evaluation_note = "<p>The required frozen source fingerprints were verified. These results remain advisory.</p>"
    return """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<title>Automatic contact review</title><style>body{font:17px system-ui;max-width:1000px;margin:40px auto;padding:0 20px;background:#f4f7fa;color:#192d39}h1{font-size:32px}details{background:white;border:1px solid #bbcbd4;border-radius:10px;margin:12px 0;padding:18px}summary{cursor:pointer;font-weight:650}small{overflow-wrap:anywhere}button{padding:10px 16px;margin:6px;font:inherit}a{color:#14627e}</style>
<h1>Automatic contact review</h1><p>Scout → Identity → Contact verifier → Evidence proofer → Judge</p>
<p>""" + esc(attempted) + " cases attempted · " + esc(complete) + " completed · " + esc(errors) + " errors · " + esc(incomplete) + " incomplete · " + esc(stale) + " stale</p><p>" + esc(supported_count) + " supported recommendations · " + esc(attempted - supported_count) + " exceptions</p>" + evaluation_note + "<p>These are machine recommendations. Human precision labels, release approval and sending permission remain separate. Publication checks use captured markup without proving rendered visibility or individual mailbox delivery.</p><button onclick=\"show('all')\">All cases</button><button onclick=\"show('true')\">Supported</button><button onclick=\"show('false')\">Exceptions</button>" + "".join(cards) + "<script>function show(value){document.querySelectorAll('details').forEach(d=>{d.hidden=value!=='all'&&d.dataset.supported!==value})}</script>"


def current_engine_hashes():
    source_root = Path(__file__).resolve().parents[1]
    return {rel: digest(read_limited(safe_child(source_root, rel))) for rel in REQUIRED_ENGINE_FILES}


def run(packet: Path, output: Path, enable_ai=False, mode="frozen"):
    if mode not in {"frozen", "reevaluate"}:
        raise ValueError("Review mode must be frozen or reevaluate")
    packet, output = packet.resolve(), output.resolve()
    if output == packet or output.is_relative_to(packet) or packet.is_relative_to(output):
        raise ValueError("Output must be separate from the frozen input packet")
    frame_bytes = read_limited(packet / "sample.json")
    frame = json.loads(frame_bytes)
    frame_marker_bytes = read_limited(packet / "FRAME_SHA256.txt")
    if digest(frame_bytes) != frame_marker_bytes.decode().strip():
        raise ValueError("Frozen frame hash changed")
    cases = frame["cases"]
    ids = [case["id"] for case in cases]
    if not 1 <= len(ids) <= 50 or len(set(ids)) != len(ids):
        raise ValueError("Require 1–50 unique frozen cases")
    if any(not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", case_id) for case_id in ids):
        raise ValueError("Unsafe case identifier")
    source_root = Path(__file__).resolve().parents[1]
    declared_engine = frame.get("engine_hashes", {})
    if not isinstance(declared_engine, dict):
        raise ValueError("Engine fingerprints must be a mapping")
    engine_hashes = current_engine_hashes()
    if mode == "frozen":
        if not set(REQUIRED_ENGINE_FILES) <= declared_engine.keys():
            raise ValueError("Frozen engine fingerprints lack required source/configuration coverage")
        for rel, expected in declared_engine.items():
            actual = digest(read_limited(safe_child(source_root, rel)))
            if actual != expected:
                raise ValueError("Frozen engine/configuration changed: " + rel)
            engine_hashes[rel] = actual
    manifest_bytes = read_limited(packet / "PACKET_MANIFEST.json")
    manifest = json.loads(manifest_bytes)
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
            for page in doc["pages"]:
                capture = safe_child(packet / "evidence", page["path"])
                capture_rel = str(capture.relative_to(packet))
                if input_hashes.get(capture_rel) != page["sha256"]:
                    raise ValueError("Frozen manifest does not cover the raw capture")
            row = review_case(business, doc, packet, at)
            save_json(output / "cases" / (business["id"] + ".json"), row)
            rows.append(row)
        advisor = {"status": "NOT_REQUESTED", "model_calls": 0, "cost_usd": 0}
        if enable_ai:
            advisor = ai_advice(rows)
        routes = Counter(row["judge"]["route"] for row in rows)
        summary = {
            "version": VERSION, "evaluated_at": at.isoformat(),
            "mode": "FROZEN_CAPTURE_REPLAY_ADVISORY" if mode == "frozen" else "CURRENT_ENGINE_REEVALUATION_ADVISORY",
            "evaluation_mode": mode,
            "input_packet": str(packet), "frame_sha256": digest(frame_bytes),
            "historical_input_revision": frame["application_revision"],
            "frozen_application_revision": frame["application_revision"] if mode == "frozen" else None,
            "historical_revision_acceptance": False,
            "frozen_engine_fingerprints_verified": mode == "frozen",
            "current_engine_sha256": engine_hashes,
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
        if (read_limited(packet / "PACKET_MANIFEST.json") != manifest_bytes
                or read_limited(packet / "FRAME_SHA256.txt") != frame_marker_bytes):
            raise ValueError("Input packet manifest or frame marker changed during review")
        for rel, expected in engine_hashes.items():
            if digest(read_limited(safe_child(source_root, rel))) != expected:
                raise ValueError("Evaluation engine changed during review: " + rel)
        save_json(output / "ENGINE_SNAPSHOT.json", {
            "evaluation_mode": mode, "historical_input_revision": frame["application_revision"],
            "historical_revision_acceptance": False, "current_engine_sha256": engine_hashes,
        })
        (output / "MODULE_SNAPSHOT.py").write_bytes(Path(__file__).read_bytes())
        output_files = {str(p.relative_to(output)): digest(p.read_bytes())
                        for p in sorted(output.rglob("*")) if p.is_file()}
        save_json(output / "MANIFEST.json", {
            "status": "COMPLETE", "input_sha256": input_hashes,
            "packet_manifest_sha256": digest(manifest_bytes), "frame_marker_sha256": digest(frame_marker_bytes),
            "evaluation_mode": mode, "engine_sha256": engine_hashes,
            "module_sha256": digest(Path(__file__).read_bytes()), "output_sha256": output_files,
        })
        return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("frozen", "reevaluate"), default="frozen",
                        help="Require matching frozen source fingerprints, or explicitly re-evaluate historical captures with the current engine")
    parser.add_argument("--free-ai-advice", action="store_true",
                        help="Explicitly opt in to one existing certified free role-router request")
    args = parser.parse_args()
    print(json.dumps(run(args.packet, args.output, args.free_ai_advice, mode=args.mode), indent=2))


if __name__ == "__main__":
    main()

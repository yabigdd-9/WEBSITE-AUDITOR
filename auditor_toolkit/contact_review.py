"""Compare declared independent labels with a frozen contact pilot, offline.

Reports describe this sample only. They never produce a release receipt, mutate
contact policy or establish deliverability or outreach permission.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date
from pathlib import Path

from email_validator import validate_email

from .identity_review import MAX_CASE_BYTES, _bounded_bytes, build_identity_review


def _load(path):
    raw = _bounded_bytes(Path(path), MAX_CASE_BYTES)
    doc = json.loads(raw)
    if not isinstance(doc, dict):
        raise ValueError("JSON object required")
    return doc, hashlib.sha256(raw).hexdigest()


def _email(value):
    if not isinstance(value, str):
        raise ValueError("Email label must be text")
    return validate_email(value.strip(), check_deliverability=False).normalized


def _interval(tp, fp):
    count = tp + fp
    if not count:
        return None
    proportion = tp / count
    z = 1.959963984540054
    denominator = 1 + z * z / count
    centre = (proportion + z * z / (2 * count)) / denominator
    margin = z * math.sqrt(proportion * (1 - proportion) / count + z * z / (4 * count * count)) / denominator
    return [round(max(0, centre - margin), 6), round(min(1, centre + margin), 6)]


def freeze_contact_dataset(frame_path, captures_root) -> dict:
    frame, frame_hash = _load(frame_path)
    cases = frame.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 50:
        raise ValueError("Frozen frame must contain one to fifty cases")
    expected = {case["id"]: case for case in cases}
    if len(expected) != len(cases):
        raise ValueError("Unique frozen case IDs required")
    evidence = build_identity_review(captures_root)
    if evidence["case_count"] != len(cases):
        raise ValueError("Capture set differs from the frozen frame")
    bindings = []
    for item in evidence["cases"]:
        if item["status"] == "INVALID_EVIDENCE" or item.get("evidence_errors"):
            raise ValueError("Evidence validation failed; freeze held")
        doc, digest = _load(Path(captures_root) / "cases" / item["case_file"])
        if digest != item["case_sha256"]:
            raise ValueError("Case changed during dataset freeze")
        case_id = doc["business"]["id"]
        if case_id not in expected or doc["business"] != expected[case_id]:
            raise ValueError("Capture business metadata differs from the frame")
        bindings.append({"case_id": case_id, "case_sha256": digest})
    if {item["case_id"] for item in bindings} != set(expected):
        raise ValueError("Capture IDs differ from the frame")
    return {"kind": "frozen_contact_review_dataset", "version": 1,
            "frame_sha256": frame_hash, "cases": sorted(bindings, key=lambda item: item["case_id"]),
            "independent_holdout_certified": False, "production_approved": False}


def compare_contact_review(frame_path, captures_root, review_path, dataset_path) -> dict:
    frame, frame_hash = _load(frame_path)
    review, review_hash = _load(review_path)
    dataset, dataset_hash = _load(dataset_path)
    if review.get("frame_sha256") != frame_hash:
        raise ValueError("Review does not bind to the exact frozen frame")
    if dataset.get("frame_sha256") != frame_hash or review.get("frozen_dataset_sha256") != dataset_hash:
        raise ValueError("Review must bind to the exact frozen predictions and evidence dataset")
    reviewer = review.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError("Named reviewer required")
    if review.get("independent_human_review_attested") is not True:
        raise ValueError("Reviewer must explicitly attest to independent human labeling")
    reviewed_at = review.get("review_date")
    if not isinstance(reviewed_at, str):
        raise ValueError("Review date required")
    date.fromisoformat(reviewed_at)
    frame_cases = frame.get("cases")
    labels = review.get("cases")
    if not isinstance(frame_cases, list) or not 1 <= len(frame_cases) <= 50:
        raise ValueError("Frozen frame must contain one to fifty cases")
    if not isinstance(labels, list) or len(labels) != len(frame_cases):
        raise ValueError("Review must retain every frozen case, including unresolved cases")
    expected = {case["id"] for case in frame_cases if isinstance(case, dict)}
    if len(expected) != len(frame_cases) or not all(isinstance(item, str) for item in expected):
        raise ValueError("Unique text case IDs required")
    bindings = dataset.get("cases")
    if not isinstance(bindings, list) or len(bindings) != len(expected):
        raise ValueError("Frozen dataset must retain every case")
    frozen_hashes = {item["case_id"]: item["case_sha256"] for item in bindings}
    if set(frozen_hashes) != expected:
        raise ValueError("Frozen dataset IDs differ from the frame")
    by_id = {}
    for label in labels:
        if not isinstance(label, dict) or label.get("case_id") not in expected:
            raise ValueError("Unknown or malformed review case")
        if label["case_id"] in by_id:
            raise ValueError("Duplicate review case")
        by_id[label["case_id"]] = label
    evidence = build_identity_review(captures_root)
    if evidence["case_count"] != len(frame_cases):
        raise ValueError("Capture set differs from the frozen frame")
    if any(case["status"] == "INVALID_EVIDENCE" or case.get("evidence_errors") for case in evidence["cases"]):
        raise ValueError("Evidence validation failed; contact comparison held")
    captures_root = Path(captures_root).resolve()
    sources = {}
    for case in evidence["cases"]:
        doc, digest = _load(captures_root / "cases" / case["case_file"])
        if digest != case["case_sha256"]:
            raise ValueError("Case changed during review comparison")
        case_id = doc["business"]["id"]
        if case_id not in expected or case_id in sources:
            raise ValueError("Capture IDs differ from the frozen frame")
        if digest != frozen_hashes[case_id]:
            raise ValueError("Frozen evidence or prediction changed after dataset freeze")
        business = next(b for b in frame_cases if b["id"] == case_id)
        if doc["business"] != business:
            raise ValueError("Capture business metadata differs from the frozen frame")
        sources[case_id] = (doc, digest)

    counts = {name: 0 for name in (
        "selected_total", "selected_reviewed", "true_positive", "false_positive",
        "selected_unresolved", "independent_labels_completed", "identity_confirmed",
        "identity_wrong", "identity_unresolved", "cases_with_missed_public_email",
    )}
    rows = []
    for case_id in sorted(expected):
        label = by_id[case_id]
        doc, digest = sources[case_id]
        identity = label.get("identity_label", "")
        if identity not in {"", "CONFIRMED", "WRONG_BUSINESS", "UNRESOLVED"}:
            raise ValueError("Unknown independent identity label")
        emails = label.get("publicly_attributable_emails", "")
        if not isinstance(emails, str):
            raise ValueError("Public attribution labels must be newline-separated email text")
        emails = sorted(set(_email(line) for line in emails.splitlines() if line.strip()))
        references = label.get("evidence_references", "")
        reason = label.get("no_email_or_unresolved_reason", "")
        confirmed_name = label.get("confirmed_business_name", "")
        if not all(isinstance(value, str) for value in (references, reason, confirmed_name)):
            raise ValueError("Review evidence, reason and business name must be text")
        resolved = identity in {"CONFIRMED", "WRONG_BUSINESS"}
        if resolved and not references.strip():
            raise ValueError("Resolved labels need evidence references")
        if identity == "CONFIRMED" and not confirmed_name.strip():
            raise ValueError("Confirmed identity needs the independently observed business name")
        if identity == "CONFIRMED" and not emails and not reason.strip():
            raise ValueError("A confirmed no-email case needs a recorded reason")
        if identity in {"WRONG_BUSINESS", "UNRESOLVED"} and not reason.strip():
            raise ValueError("Wrong or unresolved identity needs a reason")
        selected = (doc.get("result", {}).get("selected") or {}).get("email")
        selected = _email(selected) if selected else None
        outcome = "NOT_SELECTED"
        if selected:
            counts["selected_total"] += 1
            if resolved:
                counts["selected_reviewed"] += 1
                correct = identity == "CONFIRMED" and selected in emails
                counts["true_positive" if correct else "false_positive"] += 1
                outcome = "PUBLIC_ATTRIBUTION_CONFIRMED" if correct else "PUBLIC_ATTRIBUTION_NOT_CONFIRMED"
            else:
                counts["selected_unresolved"] += 1
                outcome = "UNREVIEWED_OR_UNRESOLVED"
        elif identity == "CONFIRMED" and emails:
            counts["cases_with_missed_public_email"] += 1
        if identity:
            counts["independent_labels_completed"] += 1
        if identity == "CONFIRMED":
            counts["identity_confirmed"] += 1
        elif identity == "WRONG_BUSINESS":
            counts["identity_wrong"] += 1
        elif identity == "UNRESOLVED":
            counts["identity_unresolved"] += 1
        rows.append({"case_id": case_id, "case_sha256": digest, "identity_label": identity,
                     "selected_outcome": outcome, "label_resolved": resolved})
    tp, fp = counts["true_positive"], counts["false_positive"]
    all_labeled = counts["independent_labels_completed"] == len(frame_cases)
    all_selected_resolved = counts["selected_unresolved"] == 0
    return {
        "kind": "independent_contact_review_comparison", "version": "contact-review-comparison-v1",
        "frame_sha256": frame_hash, "review_sha256": review_hash,
        "frozen_dataset_sha256": dataset_hash,
        "reviewer_declared": reviewer.strip(), "review_date": reviewed_at,
        "independent_human_review_attested": True,
        "status": "REVIEW_RECORDED_POLICY_UNCHANGED" if all_labeled and all_selected_resolved else "REVIEW_INCOMPLETE_POLICY_UNCHANGED",
        "counts": counts, "rows": rows,
        "reviewed_selection_precision": tp / (tp + fp) if tp + fp else None,
        "precision_95pct_wilson_interval": _interval(tp, fp),
        "all_frozen_cases_labeled": all_labeled,
        "all_selected_cases_resolved": all_selected_resolved,
        "human_review_required": True, "production_approved": False,
        "release_receipt_created": False, "outreach_permission_granted": False,
        "canonical_database_changed": False, "external_sends": 0,
        "limitations": [
            "Reported precision covers reviewed selections only; unresolved selections remain explicitly counted.",
            "Reviewer identity and independence are declared, not independently authenticated by this command.",
            "A newest-first pilot is not a representative population sample or certified holdout.",
            "Public attribution is not mailbox delivery, consent or permission to send.",
        ],
    }

"""Run deterministic golden cases against the current local implementation.

This is a conformance check, not a baseline-versus-challenger comparison. It
uses no model, network, SMTP, database, or target website. Temporary preview
artifacts are created only to exercise the remediation and demo builders.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import mm_challenger

ROOT = Path(__file__).resolve().parents[1]
FIXED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _email_prediction(case: dict) -> tuple[str, dict]:
    import mm_email

    inputs = case["input"]
    catch_all_case = inputs.get("mx") is True and inputs.get("catch_all") is True
    observed_case = inputs.get("first_party_observation") is True
    domain = "example.co.nz"
    identity = {
        "status": "HIGH" if catch_all_case or observed_case else "LOW",
        "evidence_urls": [],
        "accepted_roots": [domain] if catch_all_case or observed_case else [],
        "proposed_root_domain": domain,
    }
    observations = []
    if observed_case:
        identity["evidence_urls"] = [
            "https://example.co.nz/contact",
            "https://example.co.nz/about",
        ]
        for page in identity["evidence_urls"]:
            observations.append(
                {
                    "email": "info@example.co.nz",
                    "method": "mailto",
                    "source_url": page,
                    "observed_at": FIXED_AT.isoformat(),
                    "capture_hash": "synthetic-golden-capture",
                    "capture_path": "fixtures/synthetic/contact.html",
                    "role": "company general",
                    "context": "Contact the Example company team.",
                }
            )
    candidate = {
        "email": "info@example.co.nz" if catch_all_case or observed_case else "jane.doe@example.co.nz",
        "observations": observations,
        "method": "observed" if catch_all_case or observed_case else "CANDIDATE_PATTERN_DERIVED",
    }
    dns = None
    smtp = None
    if inputs.get("catch_all") is True or observed_case:
        stamp = FIXED_AT.isoformat()
        dns = {
            "mx_present": True,
            "domain_accepts_mail": True,
            "domain_resolves": True,
            "mx_hosts": ["mx.example.co.nz"],
            "checked_at": stamp,
        }
        smtp = {
            "result": "accepted",
            "catch_all_status": "yes" if inputs.get("catch_all") is True else "no",
            "checked_at": stamp,
        }
    result = mm_email.verification(candidate, identity, dns=dns, smtp=smtp, at=FIXED_AT)
    if result["catch_all_status"] == "yes":
        return "CATCH_ALL", {"send_enabled": False, "paid_cost_usd": 0}
    if inputs.get("suppressed") is True:
        result = mm_email.verification(candidate, identity, dns=dns, smtp=smtp, suppressed=True, at=FIXED_AT)
        return result["confidence_label"], {"send_enabled": False, "paid_cost_usd": 0}
    if result["confidence_label"] == "VERIFIED_HIGH":
        return "VERIFIED_HIGH", {"send_enabled": False, "paid_cost_usd": 0}
    return "NO_VERIFIED_EMAIL", {"send_enabled": False, "paid_cost_usd": 0}


def _predict(case: dict) -> dict:
    task = case.get("task")
    inputs = case.get("input", {})
    if task == "contact_verification":
        actual, safety = _email_prediction(case)
    elif task == "identity":
        from auditor_toolkit.identity import assess_business_identity, identity_confidence

        if "business_name" in inputs:
            result = assess_business_identity(
                business_name=inputs["business_name"],
                website=inputs["website"],
                legal_name=inputs.get("legal_name"),
                trading_name=inputs.get("trading_name"),
                nzbn_name=inputs.get("nzbn_name"),
                email=inputs.get("email"),
                region_match=inputs.get("region_match"),
                address_match=inputs.get("address_match"),
                phone_match=inputs.get("phone_match"),
                website_brand_match=inputs.get("website_brand_match"),
            )
        else:
            mapping = {
                "domain": "domain_name_match",
                "brand": "website_brand_match",
                "nzbn": "nzbn_match",
                "email_domain": "email_domain_match",
                "region": "region_match",
                "address": "address_match",
                "phone": "phone_match",
            }
            signals = {target: inputs[source] for source, target in mapping.items() if source in inputs}
            result = identity_confidence(signals)
        actual = result["status"]
        safety = {
            "outreach_identity_eligible": result["outreach_identity_eligible"],
            "paid_cost_usd": 0,
        }
    elif task == "remediation":
        from auditor_toolkit.remediation import build_remediation

        report = {
            "run_id": "synthetic-golden-remediation",
            "url": "https://example.co.nz",
            "defects": [{
                "defect_key": inputs["defect_key"],
                **({"remediation_automation": inputs["remediation_automation"]}
                   if inputs.get("remediation_automation") else {}),
            }],
        }
        with tempfile.TemporaryDirectory(prefix="wa-golden-remediation-") as output_dir:
            manifest = build_remediation(report, output_dir)
        item = manifest["items"][0]
        actual = item["classification"]
        safety = {"production_applied": item["production_applied"], "paid_cost_usd": 0}
    elif task == "demo":
        from auditor_toolkit.demo import build_demo
        from auditor_toolkit.remediation import build_remediation

        report = {
            "run_id": "synthetic-golden-demo",
            "url": "https://example.co.nz",
            "defects": [],
        }
        with tempfile.TemporaryDirectory(prefix="wa-golden-demo-") as output_dir:
            remediation = build_remediation(report, Path(output_dir) / "remediation")
            manifest = build_demo(report, remediation, Path(output_dir) / "demo")
        actual = manifest["status"]
        safety = {
            "live_site_changed": manifest["live_site_changed"],
            "send_enabled": False,
            "paid_cost_usd": 0,
        }
    else:
        raise ValueError(f"No deterministic golden adapter for task: {task!r}")

    return {"case_id": case["case_id"], "actual": actual, "safety": safety}


def run(golden_path: str | Path | None = None) -> dict:
    """Return current-code conformance and a digest of the evaluated golden set."""
    path = Path(golden_path) if golden_path else ROOT / "evaluation" / "golden_cases.jsonl"
    raw = path.read_bytes()
    golden = mm_challenger.load_jsonl(path)
    predictions = [_predict(case) for case in golden]
    result = mm_challenger.evaluate(golden, predictions)
    return {
        "kind": "current_implementation_golden_conformance",
        "golden_sha256": hashlib.sha256(raw).hexdigest(),
        "result": result,
        "promotion_recommended": False,
        "promotion_authorized": False,
        "side_effects": {
            "model_calls": 0,
            "network_calls": 0,
            "smtp_calls": 0,
            "database_writes": 0,
            "production_changes": 0,
            "temporary_preview_artifacts": True,
        },
    }


def generate(golden_path: str | Path | None = None) -> tuple[list[dict], dict]:
    """Generate reproducible prediction rows and a local code/data manifest."""
    path = Path(golden_path) if golden_path else ROOT / "evaluation" / "golden_cases.jsonl"
    raw = path.read_bytes()
    golden = mm_challenger.load_jsonl(path)
    predictions = [_predict(case) for case in golden]
    source_paths = {
        "runner": Path(__file__).resolve(),
        "operator_cli": ROOT / "money-machine" / "mm_operator.py",
        "comparator": ROOT / "money-machine" / "mm_challenger.py",
        "email_verifier": ROOT / "money-machine" / "mm_email.py",
        "identity": ROOT / "auditor_toolkit" / "identity.py",
        "remediation": ROOT / "auditor_toolkit" / "remediation.py",
        "demo": ROOT / "auditor_toolkit" / "demo.py",
        "common": ROOT / "auditor_toolkit" / "common.py",
    }
    source_hashes = {
        name: hashlib.sha256(source.read_bytes()).hexdigest()
        for name, source in source_paths.items()
    }
    prediction_bytes = "".join(
        json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
        for row in predictions
    ).encode()
    result = mm_challenger.evaluate(golden, predictions)
    manifest = {
        "kind": "golden_predictions",
        "golden_sha256": hashlib.sha256(raw).hexdigest(),
        "implementation_sources_sha256": source_hashes,
        "implementation_sha256": hashlib.sha256(
            json.dumps(source_hashes, sort_keys=True).encode()
        ).hexdigest(),
        "prediction_sha256": hashlib.sha256(prediction_bytes).hexdigest(),
        "case_count": len(golden),
        "result": result,
        "side_effects": {
            "model_calls": 0,
            "network_calls": 0,
            "smtp_calls": 0,
            "database_writes": 0,
            "production_changes": 0,
        },
        "promotion_authorized": False,
    }
    return predictions, manifest


def write_predictions(
    output_path: str | Path, golden_path: str | Path | None = None
) -> dict:
    """Write prediction JSONL and its manifest without overwriting prior evidence."""
    output = Path(output_path)
    manifest_path = Path(str(output) + ".manifest.json")
    if output.exists() or manifest_path.exists():
        raise FileExistsError("prediction output or manifest already exists")
    predictions, manifest = generate(golden_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            for row in predictions
        ),
        encoding="utf-8",
    )
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return manifest

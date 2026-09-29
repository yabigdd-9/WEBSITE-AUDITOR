"""Deterministic review manifest for v45 intelligence readiness.

The bundle fingerprints the evidence and thresholds used for a human/integrator
review. It is read-only and deliberately excludes timestamps and raw payloads so
identical evidence produces an identical SHA-256 fingerprint.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

import mm_intelligence_calibration as calibration
import mm_intelligence_hard_cases as hard_cases
import mm_intelligence_readiness as readiness

BUNDLE_FORMAT = "v45-intelligence-review-bundle-v1"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _confirmed_fingerprint_rows(
    d: sqlite3.Connection,
    limit: int,
) -> list[dict]:
    rows = calibration.confirmed_examples(d, limit)
    result = []
    for row in rows:
        result.append({
            "ledger_id": int(row["ledger_id"]),
            "prospect_id": int(row["prospect_id"]),
            "decision": row.get("decision"),
            "decision_polarity": row.get("decision_polarity"),
            "confidence": row.get("confidence"),
            "observed_correct": row.get("observed_correct"),
            "confirmation": row.get("confirmation"),
            "confirmation_ledger_id": row.get("confirmation_ledger_id"),
            "later_outcome": row.get("later_outcome"),
            "rule_version": row.get("rule_version"),
            "stage": row.get("stage"),
            "source": row.get("source"),
        })
    return sorted(result, key=lambda row: row["ledger_id"])


def _hard_case_fingerprint_rows(
    d: sqlite3.Connection,
    limit: int,
) -> list[dict]:
    return sorted(
        hard_cases.golden_rows(d, min(max(1, int(limit)), 5000)),
        key=lambda row: row["case_id"],
    )


def build_review_bundle(
    d: sqlite3.Connection,
    *,
    candidate_rule_version: str | None = None,
    holdout_result: dict | None = None,
    min_confirmed: int = 30,
    min_hard_cases: int = 10,
    min_validation_cases: int = 5,
    min_rule_samples: int = 10,
    max_ece: float = 0.15,
    max_brier: float = 0.25,
    drift_window: int = 25,
    drift_min_samples: int = 10,
    limit: int = 5000,
) -> dict:
    """Build a deterministic manifest and fingerprint for review evidence."""
    config = {
        "candidate_rule_version": candidate_rule_version,
        "min_confirmed": int(min_confirmed),
        "min_hard_cases": int(min_hard_cases),
        "min_validation_cases": int(min_validation_cases),
        "min_rule_samples": int(min_rule_samples),
        "max_ece": float(max_ece),
        "max_brier": float(max_brier),
        "drift_window": int(drift_window),
        "drift_min_samples": int(drift_min_samples),
        "limit": int(limit),
    }
    readiness_report = readiness.readiness_report(
        d,
        candidate_rule_version=candidate_rule_version,
        holdout_result=holdout_result,
        min_confirmed=min_confirmed,
        min_hard_cases=min_hard_cases,
        min_validation_cases=min_validation_cases,
        min_rule_samples=min_rule_samples,
        max_ece=max_ece,
        max_brier=max_brier,
        drift_window=drift_window,
        drift_min_samples=drift_min_samples,
        limit=limit,
    )

    confirmed_rows = _confirmed_fingerprint_rows(d, int(limit))
    hard_rows = _hard_case_fingerprint_rows(d, int(limit))
    holdout_hash = _sha(holdout_result) if holdout_result is not None else None

    gate_summary = [
        {
            "gate": gate["gate"],
            "passed": bool(gate["passed"]),
            "observed": gate.get("observed"),
            "required": gate.get("required"),
        }
        for gate in readiness_report["gates"]
    ]

    manifest = {
        "bundle_format": BUNDLE_FORMAT,
        "candidate_rule_version": candidate_rule_version,
        "readiness_status": readiness_report["status"],
        "blocker_count": readiness_report["blocker_count"],
        "gates": gate_summary,
        "configuration": config,
        "evidence": {
            "confirmed_examples_count": len(confirmed_rows),
            "confirmed_examples_sha256": _sha(confirmed_rows),
            "hard_case_count": len(hard_rows),
            "hard_cases_sha256": _sha(hard_rows),
            "holdout_result_present": holdout_result is not None,
            "holdout_result_sha256": holdout_hash,
        },
        "component_versions": {
            "readiness": readiness.RULE_VERSION,
            "hard_cases": hard_cases.RULE_VERSION,
            "bundle": BUNDLE_FORMAT,
        },
        "review_only": True,
        "human_or_integrator_decision_required": True,
        "promotion_authorized": False,
        "merge_authority": False,
        "deployment_authorized": False,
        "automatic_rule_change": False,
        "automatic_source_change": False,
        "paid_calls": 0,
        "external_sends": 0,
    }
    fingerprint = _sha(manifest)

    return {
        "manifest": manifest,
        "fingerprint_sha256": fingerprint,
        "canonical_manifest_bytes": len(_canonical(manifest)),
        "readiness": {
            "status": readiness_report["status"],
            "blockers": readiness_report["blockers"],
            "blocker_count": readiness_report["blocker_count"],
        },
        "raw_payloads_included": False,
        "review_only": True,
        "promotion_authorized": False,
        "merge_authority": False,
        "deployment_authorized": False,
        "paid_calls": 0,
        "external_sends": 0,
    }


def verify_review_bundle(bundle: dict) -> dict:
    """Verify an in-memory review bundle fingerprint without any I/O."""
    manifest = bundle.get("manifest")
    claimed = str(bundle.get("fingerprint_sha256") or "")
    if not isinstance(manifest, dict) or not claimed:
        return {
            "valid": False,
            "reason": "missing_manifest_or_fingerprint",
        }
    actual = _sha(manifest)
    return {
        "valid": actual == claimed,
        "claimed_sha256": claimed,
        "actual_sha256": actual,
        "reason": "ok" if actual == claimed else "fingerprint_mismatch",
    }

"""Fail-closed promotion-readiness synthesis for v45 intelligence.

This module combines existing read-only intelligence diagnostics into one
review-readiness report. It never promotes, merges, deploys, changes rules,
changes discovery routing, calls models, spends money, or sends externally.
"""
from __future__ import annotations

import sqlite3
from typing import Any

import mm_intelligence_calibration as calibration
import mm_intelligence_drift as drift
import mm_intelligence_hard_cases as hard_cases
import mm_intelligence_strategy as strategy

RULE_VERSION = "v45-promotion-readiness-v1"


def _gate(name: str, passed: bool, detail: str, observed: Any = None,
          required: Any = None) -> dict:
    return {
        "gate": name,
        "passed": bool(passed),
        "detail": detail,
        "observed": observed,
        "required": required,
    }


def _holdout_gate(
    holdout_result: dict | None,
    min_validation_cases: int,
) -> list[dict]:
    gates = []
    if not isinstance(holdout_result, dict):
        gates.append(_gate(
            "holdout_present",
            False,
            "A deterministic challenger holdout evaluation is required.",
            observed=False,
            required=True,
        ))
        return gates

    split = holdout_result.get("split") or {}
    challenger = holdout_result.get("challenger") or {}
    validation_count = int(split.get("validation_count") or 0)
    safety_failures = int(challenger.get("safety_failures") or 0)
    recommendation_basis = holdout_result.get("recommendation_basis")
    recommended = holdout_result.get("promotion_recommended") is True

    gates.append(_gate(
        "holdout_present",
        True,
        "A holdout result was supplied.",
        observed=True,
        required=True,
    ))
    gates.append(_gate(
        "holdout_validation_size",
        validation_count >= min_validation_cases,
        "Holdout must contain enough unseen confirmed hard cases.",
        observed=validation_count,
        required=min_validation_cases,
    ))
    gates.append(_gate(
        "holdout_recommendation_basis",
        recommendation_basis == "validation_holdout_only",
        "Recommendation must be based on the deterministic validation holdout.",
        observed=recommendation_basis,
        required="validation_holdout_only",
    ))
    gates.append(_gate(
        "holdout_safety",
        safety_failures == 0,
        "Challenger must have zero holdout safety failures.",
        observed=safety_failures,
        required=0,
    ))
    gates.append(_gate(
        "holdout_improvement",
        recommended,
        "Existing challenger evaluator must recommend improvement on holdout.",
        observed=recommended,
        required=True,
    ))
    return gates


def readiness_report(
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
    """Synthesize evidence required before a human/integrator review."""
    minimum_confirmed = max(1, int(min_confirmed))
    minimum_hard = max(1, int(min_hard_cases))
    minimum_validation = max(1, int(min_validation_cases))
    minimum_rule = max(1, int(min_rule_samples))
    maximum_ece = max(0.0, float(max_ece))
    maximum_brier = max(0.0, float(max_brier))

    calibration_report = calibration.calibration_report(
        d,
        limit=limit,
        min_samples=minimum_confirmed,
    )
    drift_report = drift.drift_report(
        d,
        window=drift_window,
        min_samples=drift_min_samples,
        limit=limit,
    )
    hard_case_report = hard_cases.hard_cases(
        d,
        limit=min(max(1, int(limit)), 5000),
    )
    strategy_report = strategy.rule_version_report(
        d,
        limit=limit,
        min_samples=minimum_rule,
    )

    confirmed = int(calibration_report.get("confirmed_examples") or 0)
    hard_count = int(hard_case_report.get("count") or 0)
    ece = calibration_report.get("expected_calibration_error")
    brier = calibration_report.get("brier_score")

    gates = [
        _gate(
            "confirmed_sample_size",
            confirmed >= minimum_confirmed,
            "Enough confirmed examples must exist to evaluate reliability.",
            observed=confirmed,
            required=minimum_confirmed,
        ),
        _gate(
            "calibration_status",
            calibration_report.get("status") == "MEASURED",
            "Calibration must be measured rather than low-sample or absent.",
            observed=calibration_report.get("status"),
            required="MEASURED",
        ),
        _gate(
            "expected_calibration_error",
            isinstance(ece, (int, float)) and ece <= maximum_ece,
            "Expected calibration error must be below the review threshold.",
            observed=ece,
            required={"max": maximum_ece},
        ),
        _gate(
            "brier_score",
            isinstance(brier, (int, float)) and brier <= maximum_brier,
            "Brier score must be below the review threshold.",
            observed=brier,
            required={"max": maximum_brier},
        ),
        _gate(
            "drift_clear",
            drift_report.get("status") == "STABLE",
            "Recent confirmed decisions must not show unresolved drift.",
            observed={
                "status": drift_report.get("status"),
                "flags": list(drift_report.get("flags") or []),
            },
            required={"status": "STABLE", "flags": []},
        ),
        _gate(
            "confirmed_hard_case_size",
            hard_count >= minimum_hard,
            "Enough confirmed errors must exist to challenge proposed rules.",
            observed=hard_count,
            required=minimum_hard,
        ),
    ]

    candidate = None
    if candidate_rule_version:
        versions = strategy_report.get("versions") or {}
        candidate = versions.get(candidate_rule_version)
        gates.append(_gate(
            "candidate_rule_observed",
            candidate is not None,
            "Candidate rule version must have confirmed historical evidence.",
            observed=candidate_rule_version if candidate is not None else None,
            required=candidate_rule_version,
        ))
        gates.append(_gate(
            "candidate_rule_sample_size",
            bool(candidate)
            and int(candidate.get("confirmed_examples") or 0) >= minimum_rule,
            "Candidate rule version needs enough confirmed examples.",
            observed=(
                int(candidate.get("confirmed_examples") or 0)
                if candidate
                else 0
            ),
            required=minimum_rule,
        ))
    else:
        gates.append(_gate(
            "candidate_rule_specified",
            False,
            "A candidate rule version must be named for promotion review.",
            observed=None,
            required="candidate_rule_version",
        ))

    gates.extend(_holdout_gate(holdout_result, minimum_validation))

    blockers = [
        {
            "gate": item["gate"],
            "detail": item["detail"],
            "observed": item["observed"],
            "required": item["required"],
        }
        for item in gates
        if not item["passed"]
    ]
    status = (
        "READY_FOR_HUMAN_REVIEW"
        if not blockers
        else "NOT_READY_FOR_HUMAN_REVIEW"
    )

    return {
        "status": status,
        "candidate_rule_version": candidate_rule_version,
        "candidate_rule_metrics": candidate,
        "gates": gates,
        "blockers": blockers,
        "blocker_count": len(blockers),
        "evidence": {
            "calibration": calibration_report,
            "drift": drift_report,
            "hard_cases": {
                "count": hard_case_report.get("count", 0),
                "by_type": hard_case_report.get("by_type", {}),
                "by_rule_version": hard_case_report.get(
                    "by_rule_version",
                    {},
                ),
            },
            "rule_versions": strategy_report,
            "holdout": holdout_result,
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
        "rule_version": RULE_VERSION,
    }

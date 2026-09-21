"""P18 measured challenger evaluation.

No code modification, git write, merge, deployment or send action exists here.
A challenger can only earn a recommendation for separate human/integrator review.
"""
from __future__ import annotations

import json
from pathlib import Path


def load_jsonl(path):
    rows = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict) or not value.get("case_id"):
            raise ValueError(f"Invalid JSONL row {number}")
        rows.append(value)
    if not rows:
        raise ValueError("Golden/evaluation file is empty")
    return rows


def evaluate(golden_rows: list[dict], prediction_rows: list[dict]) -> dict:
    expected = {row["case_id"]: row for row in golden_rows}
    predictions = {row["case_id"]: row for row in prediction_rows}
    if len(predictions) != len(prediction_rows):
        raise ValueError("Duplicate prediction case_id")
    details = []
    correct = 0
    safety_failures = 0
    for case_id, case in expected.items():
        pred = predictions.get(case_id)
        if pred is None:
            details.append({"case_id": case_id, "correct": False, "reason": "missing_prediction"})
            continue
        target = case.get("expected")
        actual = pred.get("actual")
        safety_expected = case.get("safety", {})
        safety_actual = pred.get("safety", {})
        safe = all(safety_actual.get(k) == v for k, v in safety_expected.items())
        if not safe:
            safety_failures += 1
        match = actual == target and safe
        correct += int(match)
        details.append(
            {
                "case_id": case_id,
                "correct": match,
                "expected": target,
                "actual": actual,
                "safety_ok": safe,
            }
        )
    total = len(expected)
    return {
        "cases": total,
        "correct": correct,
        "accuracy": round(correct / total, 6),
        "safety_failures": safety_failures,
        "details": details,
    }


def compare(golden_rows, baseline_rows, challenger_rows, min_improvement=0.01):
    baseline = evaluate(golden_rows, baseline_rows)
    challenger = evaluate(golden_rows, challenger_rows)
    improvement = round(challenger["accuracy"] - baseline["accuracy"], 6)
    eligible = (
        challenger["safety_failures"] == 0
        and improvement >= float(min_improvement)
        and challenger["accuracy"] >= baseline["accuracy"]
    )
    return {
        "baseline": baseline,
        "challenger": challenger,
        "improvement": improvement,
        "minimum_improvement": float(min_improvement),
        "promotion_recommended": eligible,
        "promotion_authorized": False,
        "merge_authority": False,
        "direct_master_write": False,
        "requires_integrator_review": True,
        "reason": (
            "measurable improvement with no safety regression"
            if eligible
            else "no eligible measurable improvement or safety regression present"
        ),
    }

"""Auditable NZD scenarios, never a measurement of defect-caused lost revenue.

No default industry multipliers: every quantified effect must be supplied, attributed
and reviewed. Repeated findings are grouped by defect key; overlapping effects use
max-per-segment rather than addition. Disjoint segment shares cannot exceed 100%.
"""

from __future__ import annotations

import csv
import io
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

SCENARIOS = ("low", "high")
DISCLAIMER = (
    "Scenario only, not measured lost revenue or a recovery guarantee. "
    "Audit evidence establishes the defect; assumptions establish its modeled effect."
)


def number(value: Any, name: str, maximum=None) -> Decimal:
    if maximum is None:
        maximum = Decimal("1000000000")
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite non-negative number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{name} must be a finite non-negative number") from None
    if not result.is_finite() or result < 0 or (maximum is not None and result > maximum):
        raise ValueError(f"{name} outside allowed range")
    return result


def amount(value):
    return (
        str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) if value is not None else None
    )


def bounds(value, name, maximum=None):
    if not isinstance(value, dict) or set(value) != set(SCENARIOS):
        raise ValueError(f"{name} requires low and high values")
    result = {k: number(value[k], f"{name}.{k}", maximum) for k in SCENARIOS}
    if result["low"] > result["high"]:
        raise ValueError(f"{name}.low cannot exceed high")
    return result


def calculate_revenue(report, config=None):
    config = config or {}
    if not isinstance(config, dict) or not isinstance(report.get("defects"), list):
        raise ValueError("Expected a scenario mapping and an audit defects array")
    if config.get("currency", "NZD") != "NZD":
        raise ValueError("This calculator accepts NZD only; no implicit FX conversion")
    base_names = ("monthly_visitors", "baseline_conversion_rate", "value_per_conversion_nzd")
    values = {
        k: number(config[k], k, 1 if k == "baseline_conversion_rate" else None)
        for k in base_names
        if config.get(k) is not None
    }
    missing = [k for k in base_names if k not in values]
    margin = (
        number(config["contribution_margin"], "contribution_margin", 1)
        if config.get("contribution_margin") is not None
        else None
    )
    hourly = (
        number(config["hourly_rate_nzd"], "hourly_rate_nzd")
        if config.get("hourly_rate_nzd") is not None
        else None
    )
    months = number(config.get("horizon_months", 12), "horizon_months", 120)
    if months == 0:
        raise ValueError("horizon_months must be positive")
    segments = config.get("segments", {"all": 1})
    if not isinstance(segments, dict) or not segments:
        raise ValueError("segments must be a nonempty mapping of disjoint traffic shares")
    shares = {str(k): number(v, f"segments.{k}", 1) for k, v in segments.items()}
    if sum(shares.values()) > 1:
        raise ValueError(
            "Disjoint segment shares exceed 100%; overlapping audiences cannot be added"
        )
    rules = config.get("impacts", {})
    if not isinstance(rules, dict):
        raise ValueError("impacts must map exact defect_key values to reviewed assumptions")
    validated = {}
    for key, rule in rules.items():
        if not isinstance(rule, dict):
            raise ValueError(f"Invalid impact rule {key}")
        if rule.get("segment", "all") not in shares:
            raise ValueError(f"Unknown segment for {key}")
        effect = bounds(rule["relative_conversion_loss"], f"{key}.relative_conversion_loss", 1)
        recovery = bounds(
            rule.get("recovery_fraction", {"low": 0, "high": 1}), f"{key}.recovery_fraction", 1
        )
        hours = (
            bounds(rule["fix_hours"], f"{key}.fix_hours")
            if rule.get("fix_hours") is not None
            else None
        )
        for field in ("source", "rationale", "reviewed_by"):
            if not isinstance(rule.get(field), str) or not rule[field].strip():
                raise ValueError(f"{key} needs {field}; no unreviewed default multipliers")
        validated[key] = (effect, recovery, hours)
    grouped = {}
    for d in report["defects"]:
        if not isinstance(d, dict) or not isinstance(d.get("defect_key"), str):
            raise ValueError("Each finding needs an explicit defect_key; no keyword guessing")
        grouped.setdefault(d["defect_key"], []).append(d)
    baseline = (
        None
        if missing
        else values["monthly_visitors"]
        * values["baseline_conversion_rate"]
        * values["value_per_conversion_nzd"]
    )
    totals = {
        name: {scenario: Decimal(0) for scenario in SCENARIOS}
        for name in ("risk", "recovered", "cost")
    }
    segment_effects = {
        k: {
            "risk": {s: Decimal(0) for s in SCENARIOS},
            "recovered": {s: Decimal(0) for s in SCENARIOS},
        }
        for k in shares
    }
    rows, unquantified = [], []
    for key, findings in sorted(grouped.items()):
        ids = sorted(
            {str(d.get("finding_id") or key + ":" + str(d.get("source_url", ""))) for d in findings}
        )
        row = {
            "defect_key": key,
            "finding_ids": ids,
            "defect": str(findings[0].get("defect", key)),
            "evidence_urls": sorted({str(d.get("source_url", "")) for d in findings}),
            "source_run_id": report.get("run_id"),
            "status": "unquantified",
            "risk_nzd_monthly": None,
            "recovered_nzd_monthly": None,
            "fix_cost_nzd": None,
        }
        if key not in validated or baseline is None:
            row["reason"] = (
                "Missing baseline inputs" if baseline is None else "No reviewed effect assumption"
            )
            unquantified.append(key)
            rows.append(row)
            continue
        rule = rules[key]
        effect, recovery, hours = validated[key]
        segment = rule.get("segment", "all")
        risks = {s: baseline * shares[segment] * effect[s] for s in SCENARIOS}
        recovered = {s: risks[s] * recovery[s] for s in SCENARIOS}
        cost = (
            {s: hours[s] * hourly for s in SCENARIOS}
            if hours is not None and hourly is not None
            else None
        )
        for s in SCENARIOS:
            segment_effects[segment]["risk"][s] = max(segment_effects[segment]["risk"][s], risks[s])
            segment_effects[segment]["recovered"][s] = max(
                segment_effects[segment]["recovered"][s], recovered[s]
            )
            if cost is not None:
                totals["cost"][s] += cost[s]
        row.update(
            status="scenario",
            segment=segment,
            assumptions=rule,
            risk_nzd_monthly={s: amount(risks[s]) for s in SCENARIOS},
            recovered_nzd_monthly={s: amount(recovered[s]) for s in SCENARIOS},
            fix_cost_nzd={s: amount(cost[s]) for s in SCENARIOS} if cost is not None else None,
        )
        rows.append(row)
    modeled = [r for r in rows if r["status"] == "scenario"]
    ready = baseline is not None and (bool(modeled) or not rows)
    for segment in segment_effects.values():
        for s in SCENARIOS:
            totals["risk"][s] += segment["risk"][s]
            totals["recovered"][s] += segment["recovered"][s]
    cost_known = bool(modeled) and all(r["fix_cost_nzd"] is not None for r in modeled)
    # Profit-based ROI: low outcome uses high cost, and high outcome uses low cost.
    roi, payback = None, None
    if ready and cost_known and margin is not None:
        roi, payback = {}, {}
        for s, cost_side in (("low", "high"), ("high", "low")):
            cost = totals["cost"][cost_side]
            contribution = totals["recovered"][s] * margin
            roi[s] = amount(((contribution * months - cost) / cost) * 100) if cost else None
            payback[s] = amount(cost / contribution) if contribution else None
    return {
        "schema_version": 1,
        "kind": "revenue_scenario",
        "currency": "NZD",
        "source_run_id": report.get("run_id"),
        "source_audit_status": report.get("status", "unknown"),
        "url": report.get("url"),
        "status": "scenario" if ready else "unquantified",
        "review_required": True,
        "disclaimer": DISCLAIMER,
        "missing_inputs": missing,
        "assumptions": config,
        "baseline_nzd_monthly": amount(baseline),
        "revenue_at_risk_nzd_monthly": {s: amount(totals["risk"][s]) for s in SCENARIOS}
        if ready
        else None,
        "potential_recovery_nzd_monthly": {s: amount(totals["recovered"][s]) for s in SCENARIOS}
        if ready
        else None,
        "modeled_risk_percent": {s: amount(100 * totals["risk"][s] / baseline) for s in SCENARIOS}
        if ready and baseline
        else None,
        "fix_cost_nzd": {s: amount(totals["cost"][s]) for s in SCENARIOS} if cost_known else None,
        "profit_roi_percent": roi,
        "payback_months": payback,
        "horizon_months": str(months),
        "modeled_defect_types": len(modeled),
        "unquantified_defect_keys": unquantified,
        "coverage": "partial"
        if unquantified or report.get("status") != "complete"
        else "complete_for_supplied_assumptions",
        "aggregation": "Maximum overlapping effect per disjoint traffic segment. Row values must not be summed. Fix costs are per defect type across all occurrences.",
        "rows": rows,
    }


def roi_csv(result):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "Defect",
            "Status",
            "Risk low NZD/month",
            "Risk high NZD/month",
            "Potential recovery low",
            "Potential recovery high",
            "Fix cost low",
            "Fix cost high",
        ]
    )
    for row in result["rows"]:
        label = row["defect"]
        if label.lstrip().startswith(("=", "+", "-", "@")):
            label = "'" + label
        writer.writerow(
            [label, row["status"]]
            + [
                (row[field] or {}).get(s, "")
                for field in ("risk_nzd_monthly", "recovered_nzd_monthly", "fix_cost_nzd")
                for s in SCENARIOS
            ]
        )
    return output.getvalue()

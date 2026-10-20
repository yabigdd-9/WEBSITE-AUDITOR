"""Saved canonical observations; no crawling, score invention or business ranking."""

from __future__ import annotations

import hashlib
import html
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .common import atomic_write_json, atomic_write_text

SETTINGS = (
    "profile", "browser", "tls", "timeout", "deep", "max_pages", "max_depth",
    "max_links", "max_bytes", "respect_robots", "cache", "external_tools",
    "allow_private", "screenshot_diff", "use_gotenberg",
)
LIMIT = 100
BOOLEAN_SETTINGS = {
    "browser", "tls", "deep", "respect_robots", "cache", "external_tools",
    "allow_private", "screenshot_diff", "use_gotenberg",
}


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def measurement_contract(options: Any) -> dict[str, Any]:
    """Bind scope and toolkit source; presentation/price/AI options are excluded.

    This records settings, not identical networks, browsers, hardware or field
    conditions. Those environmental limits remain explicit in every comparison.
    """
    root = Path(__file__).resolve().parent
    sources = {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*.py"))
    }
    axe = root / "assets/axe.min.js"
    if axe.is_file():
        sources["assets/axe.min.js"] = hashlib.sha256(axe.read_bytes()).hexdigest()
    return {
        "version": 1,
        "settings": {key: getattr(options, key) for key in SETTINGS},
        "toolkit_source_sha256": _digest(sources),
        "limitation": "Matching recorded scope/source does not establish identical lab or field conditions.",
    }


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(UTC) if parsed.tzinfo else None
    except ValueError:
        return None


def utc_timestamp(value: Any) -> str | None:
    when = _timestamp(value)
    return when.isoformat(timespec="microseconds") if when else None


def _health(report: dict[str, Any]) -> float | int | None:
    value = report.get("health_score")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if 0 <= value <= 100 and math.isfinite(value) else None


def _settings_valid(settings: Any) -> bool:
    if not isinstance(settings, dict) or set(settings) != set(SETTINGS):
        return False
    if not isinstance(settings["profile"], str) or not settings["profile"]:
        return False
    if any(type(settings[key]) is not bool for key in BOOLEAN_SETTINGS):
        return False
    if any(type(settings[key]) is not int or settings[key] < 0 for key in
           ("max_pages", "max_depth", "max_links", "max_bytes")):
        return False
    timeout = settings["timeout"]
    return (type(timeout) in {int, float} and 0 < timeout <= 60 and math.isfinite(timeout)
            and settings["max_pages"] > 0 and settings["max_bytes"] > 0)


def _basis(report: dict[str, Any]) -> tuple[str | None, list[str]]:
    reasons = []
    if report.get("status") != "complete":
        reasons.append("audit_incomplete")
    if _health(report) is None:
        reasons.append("health_unavailable_or_invalid")
    if _timestamp(report.get("timestamp")) is None:
        reasons.append("timestamp_unavailable_or_invalid")
    checks = report.get("checks")
    registry = report.get("check_registry")
    scope = {}
    if not isinstance(checks, dict) or not checks or not isinstance(registry, dict):
        reasons.append("check_provenance_missing")
    else:
        required = passed = 0
        for name, check in checks.items():
            definition = registry.get(name)
            if (not isinstance(check, dict) or not isinstance(definition, dict)
                    or not isinstance(check.get("required"), bool)
                    or check.get("status") not in {"ok", "skipped", "error"}
                    or not isinstance(definition.get("version"), str) or not definition["version"]):
                reasons.append("check_provenance_invalid")
                continue
            required += int(check["required"])
            passed += int(check["required"] and check["status"] == "ok")
            if check["status"] == "error" or (check["required"] and check["status"] != "ok"):
                reasons.append("check_coverage_incomplete")
            scope[name] = {key: definition.get(key) for key in ("version", "mode", "category")}
            scope[name].update(status=check["status"], required=check["required"])
        coverage = report.get("coverage")
        if (not required or not isinstance(coverage, dict)
                or type(coverage.get("required")) is not int or type(coverage.get("passed")) is not int
                or coverage.get("required") != required or coverage.get("passed") != passed):
            reasons.append("coverage_provenance_invalid")
    contract = report.get("measurement_contract")
    if (not isinstance(contract, dict) or type(contract.get("version")) is not int or contract["version"] != 1
            or not _settings_valid(contract.get("settings"))
            or not isinstance(contract.get("toolkit_source_sha256"), str)
            or len(contract["toolkit_source_sha256"]) != 64
            or any(c not in "0123456789abcdef" for c in contract["toolkit_source_sha256"])
            or contract["settings"].get("profile") != report.get("profile")):
        reasons.append("measurement_contract_missing_or_invalid")
    scoring = report.get("scoring")
    if (not isinstance(scoring, dict) or not isinstance(scoring.get("method"), str) or not scoring["method"]
            or not isinstance(scoring.get("weights"), dict)
            or set(scoring["weights"]) != {"low", "medium", "high", "critical"}
            or any(type(value) not in {int, float} or not 0 < value <= 100 or not math.isfinite(value)
                   for value in scoring["weights"].values())):
        reasons.append("scoring_provenance_missing")
    if (not isinstance(report.get("profile"), str) or not report["profile"]
            or type(report.get("schema_version")) is not int or report["schema_version"] <= 0):
        reasons.append("profile_or_schema_missing")
    if reasons:
        return None, sorted(set(reasons))
    return _digest({
        "schema": report["schema_version"], "profile": report["profile"],
        "checks": scope, "scoring": scoring, "contract": contract,
    }), []


def _row(report: dict[str, Any]) -> dict[str, Any]:
    if (not isinstance(report, dict) or not isinstance(report.get("run_id"), str)
            or not report["run_id"] or not isinstance(report.get("url"), str)):
        raise ValueError("Each comparison input needs a canonical run ID and URL")
    url = report["url"]
    try:
        parsed = urlsplit(url)
        valid = (bool(url) and len(url) <= 8192 and not any(ord(c) < 32 or ord(c) == 127 for c in url)
                 and parsed.scheme in {"http", "https"} and bool(parsed.hostname)
                 and parsed.username is None and parsed.password is None)
        _ = parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Comparison URLs must be absolute HTTP(S) without credentials or control characters")
    basis, reasons = _basis(report)
    return {
        "run_id": report["run_id"], "url": report["url"],
        "timestamp": report.get("timestamp"), "profile": report.get("profile"),
        "status": report.get("status"), "coverage": report.get("coverage"),
        "finding_count": len(report["defects"]) if isinstance(report.get("defects"), list) else None,
        "reported_health": _health(report) if report.get("status") == "complete" else None,
        "basis_sha256": basis, "held_reasons": reasons,
        "observation_sha256": _digest({key: report.get(key) for key in (
            "run_id", "url", "timestamp", "profile", "schema_version", "status",
            "health_score", "coverage", "checks", "check_registry", "scoring",
            "measurement_contract", "defects", "evidence",
        )}),
    }


def build_comparison(reports: list[dict[str, Any]]) -> dict[str, Any]:
    if not 2 <= len(reports) <= LIMIT:
        raise ValueError("Comparison requires 2–100 saved canonical reports")
    rows = [_row(report) for report in reports]
    if len({row["run_id"] for row in rows}) != len(rows):
        raise ValueError("Duplicate run IDs are not separate comparison observations")
    target = rows[0]
    for row in rows:
        allowed = bool(target["basis_sha256"] and row["basis_sha256"] == target["basis_sha256"])
        if not target["basis_sha256"] and row is not target:
            row["held_reasons"].append("target_comparison_held")
        elif row["basis_sha256"] and not allowed:
            row["held_reasons"].append("scope_source_or_scoring_mismatch")
        row["comparison_allowed"] = allowed
        row["health_delta_from_target"] = (
            row["reported_health"] - target["reported_health"] if allowed else None
        )
    comparable = all(row["comparison_allowed"] for row in rows)
    average = sum(row["reported_health"] for row in rows[1:]) / (len(rows) - 1) if comparable else None
    return {
        "version": 1, "kind": "saved_audit_comparison", "target_run_id": target["run_id"],
        "status": "comparable" if comparable else "held",
        "summary": {
            "comparison_count": len(rows) - 1,
            "mean_comparison_health": average,
            "mean_health_delta_from_target": average - target["reported_health"] if average is not None else None,
            "aggregation_policy": "All selected comparison observations must match; no silent exclusion of held rows.",
        },
        "rows": rows,
        "limitations": [
            "Reported heuristic scores describe captured audit findings; they do not rank business quality or revenue.",
            "Matching settings/source/check coverage is not proof of identical browsers, hardware, networks or field conditions.",
            "Older reports without a measurement contract retain observations but have no asserted score delta.",
        ],
    }


def render_comparison_html(document: dict[str, Any]) -> str:
    escape = lambda value: html.escape(str(value))  # noqa: E731
    rows = []
    for index, row in enumerate(document["rows"]):
        delta = row["health_delta_from_target"]
        rows.append(
            f"<tr><td>{'Target' if index == 0 else 'Comparison'}<br>{escape(row['url'])}</td>"
            f"<td>{escape(row['timestamp'])}<br>{escape(row['run_id'])}</td>"
            f"<td>{escape(row['profile'])}<br>{escape(row['status'])}</td>"
            f"<td>{escape(row['coverage'])}</td><td>{escape(row['finding_count'])}</td>"
            f"<td>{escape(row['reported_health'])}</td>"
            f"<td>{escape(delta) if delta is not None else 'Unavailable'}</td>"
            f"<td>{escape(', '.join(row['held_reasons']) or 'Matching recorded basis')}</td></tr>"
        )
    notes = "".join(f"<li>{escape(note)}</li>" for note in document["limitations"])
    summary = document["summary"]
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Saved audit comparison</title><style>body{font-family:system-ui;margin:2rem}'
        'table{border-collapse:collapse;width:100%}th,td{padding:.6rem;border:1px solid #ccd;'
        'text-align:left;overflow-wrap:anywhere}</style><h1>Saved audit comparison</h1>'
        f"<p>Status: {escape(document['status'])}</p><ul>{notes}</ul>"
        f"<p>Comparison mean health: {escape(summary['mean_comparison_health'])}; "
        f"difference from target: {escape(summary['mean_health_delta_from_target'])}. "
        f"{escape(summary['aggregation_policy'])}</p>"
        '<table><thead><tr><th>Site</th><th>Observation</th><th>Profile / status</th>'
        '<th>Coverage</th><th>Recorded findings</th><th>Reported health</th><th>Health difference from target</th>'
        f"<th>Comparison evidence</th></tr></thead><tbody>{''.join(rows)}</tbody></table></html>"
    )


def write_comparison(reports: list[dict[str, Any]], output: Path) -> dict[str, Any]:
    document = build_comparison(reports)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    atomic_write_json(output / "comparison.json", document)
    atomic_write_text(output / "comparison.html", render_comparison_html(document))
    return {
        "status": document["status"], "json": str(output / "comparison.json"),
        "html": str(output / "comparison.html"), "target_run_id": document["target_run_id"],
    }


def _finding_ids(report: dict[str, Any]) -> set[str] | None:
    records = report.get("defects")
    if not isinstance(records, list) or type(report.get("defect_count")) is not int:
        return None
    if report["defect_count"] != len(records):
        return None
    if any(not isinstance(item, dict) or not isinstance(item.get("finding_id"), str)
           or not item["finding_id"] for item in records):
        return None
    identities = {item["finding_id"] for item in records}
    return identities if len(identities) == len(records) else None


def _matching_history(current: dict[str, Any], previous: list[dict[str, Any]]):
    if len(previous) > 1000:
        raise ValueError("Finding history is bounded to 1000 prior observations")
    basis, reasons = _basis(current)
    identities = _finding_ids(current)
    if identities is None:
        reasons.append("finding_inventory_invalid")
    eligible = []
    when = _timestamp(current.get("timestamp"))
    if basis and identities is not None:
        for report in previous:
            if not isinstance(report, dict):
                continue
            prior_when = _timestamp(report.get("timestamp"))
            if (not isinstance(report.get("run_id"), str) or not report["run_id"]
                    or report["run_id"] == current["run_id"]
                    or report.get("url") != current["url"] or report.get("profile") != current["profile"]
                    or prior_when is None or prior_when >= when):
                continue
            prior_basis, _ = _basis(report)
            prior_ids = _finding_ids(report)
            if prior_basis == basis and prior_ids is not None:
                eligible.append((report, prior_ids))
    eligible.sort(key=lambda item: (_timestamp(item[0]["timestamp"]), item[0]["run_id"]), reverse=True)
    if not eligible:
        reasons.append("no_compatible_prior_audit")
    return identities, basis, eligible, sorted(set(reasons))


def compare_finding_history(current: dict[str, Any], previous: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify findings only against complete, earlier, matching observations."""
    identities, basis, eligible, reasons = _matching_history(current, previous)
    result = {
        "status": "held", "baseline": None, "new": [], "persistent": [],
        "regressed": [], "resolved": [], "comparison_assessed": False,
        "resolution_assessed": False, "observed_current": sorted(identities or []),
        "held_reasons": reasons, "basis_sha256": basis,
        "eligible_prior_count": len(eligible), "considered_prior_count": len(previous),
        "limitation": "Labels describe matching captured audit observations, not proof of who performed a fix or business impact.",
    }
    if identities is None or not basis or not eligible:
        return result
    baseline, old = eligible[0]
    historic = set().union(*(old_ids for _, old_ids in eligible))
    result.update(
        status="assessed", baseline=baseline["run_id"], new=sorted(identities - old - historic),
        persistent=sorted(identities & old), regressed=sorted((identities - old) & historic),
        resolved=sorted(old - identities), comparison_assessed=True, resolution_assessed=True,
        held_reasons=[],
    )
    return result


def verification_evidence(run: dict[str, Any], previous: list[dict[str, Any]], identity: str) -> dict[str, Any]:
    """Return traceable detection evidence; callers still authorize the transition."""
    identities, basis, eligible, _ = _matching_history(run, previous)
    detection = next((report for report, old_ids in eligible if identity in old_ids), None)
    if identities is None or not basis or identity in identities or detection is None:
        raise ValueError("Verification requires complete matching audits after detection and without the finding")
    return {"detection_run": detection["run_id"], "verification_basis_sha256": basis}


def build_trend(current: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    if len(history) >= LIMIT:
        raise ValueError("History trend is bounded to 99 previous runs and one current run")
    reference = _row(current)
    rows = {}
    for report in history + [current]:
        row = _row(report)
        if (_timestamp(reference["timestamp"]) and _timestamp(row["timestamp"])
                and _timestamp(row["timestamp"]) > _timestamp(reference["timestamp"])):
            raise ValueError("History cannot contain an observation newer than the current run")
        if row["url"] != reference["url"] or row["profile"] != reference["profile"]:
            raise ValueError("Trend inputs must have the exact same URL and profile")
        if row["run_id"] in rows and row["observation_sha256"] != rows[row["run_id"]]["observation_sha256"]:
            raise ValueError("A run ID cannot refer to conflicting history records")
        rows[row["run_id"]] = row
    ordered = sorted(rows.values(), key=lambda row: (
        _timestamp(row["timestamp"]) or datetime.max.replace(tzinfo=UTC), row["run_id"]
    ))
    basis_row = reference if reference["basis_sha256"] else next(
        (row for row in reversed(ordered) if row["basis_sha256"]), reference
    )
    for row in ordered:
        comparable = bool(basis_row["basis_sha256"] and row["basis_sha256"] == basis_row["basis_sha256"])
        if row["basis_sha256"] and not comparable:
            row["held_reasons"].append("scope_source_or_scoring_mismatch")
        row["plotted_health"] = row["reported_health"] if comparable else None
    complete_series = (len(ordered) > 1
                       and all(row["plotted_health"] is not None for row in ordered)
                       and _timestamp(ordered[0]["timestamp"]) < _timestamp(ordered[-1]["timestamp"]))
    return {
        "version": 1, "kind": "exact_url_profile_history", "url": reference["url"],
        "profile": reference["profile"], "current_run_id": reference["run_id"],
        "basis_run_id": basis_row["run_id"] if basis_row["basis_sha256"] else None,
        "points": ordered, "maximum_runs": LIMIT,
        "summary": {
            "starting_health": ordered[0]["plotted_health"],
            "current_health": next(row["plotted_health"] for row in ordered if row["run_id"] == reference["run_id"]),
            "health_change": ordered[-1]["plotted_health"] - ordered[0]["plotted_health"] if complete_series else None,
            "change_assessed": complete_series,
        },
        "limitation": "Only matching recorded measurement bases are plotted; held runs break the line. Lab/field conditions are not established.",
    }


def render_history_svg(trend: dict[str, Any]) -> str:
    points = [row for row in trend["points"] if _timestamp(row["timestamp"]) is not None]
    start = _timestamp(points[0]["timestamp"]) if points else None
    end = _timestamp(points[-1]["timestamp"]) if points else None
    elapsed = (end - start).total_seconds() if start and end else 0
    markup = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="260" viewBox="0 0 720 260" role="img" aria-labelledby="title desc">',
        '<title id="title">Recorded audit health over time</title>',
        f"<desc id=\"desc\">{html.escape(trend['limitation'])}</desc>",
        '<rect width="720" height="260" fill="white"/>',
        '<text x="50" y="22" font-family="sans-serif" font-size="14">Recorded health • higher is fewer weighted findings</text>',
    ]
    for value in (0, 50, 100):
        y = 195 - value * 1.5
        markup.append(f'<path d="M50 {y} H680" stroke="#d9e2ec"/><text x="12" y="{y + 4}" font-size="12">{value}</text>')
    previous = None
    measured = 0
    for row in points:
        when = _timestamp(row["timestamp"])
        x = 50 + 630 * (when - start).total_seconds() / elapsed if elapsed else 365
        value = row["plotted_health"]
        title = html.escape(f"{row['timestamp']} — {row['run_id']} — " + (
            f"health {value}" if value is not None else ", ".join(row["held_reasons"])
        ))
        if value is None:
            previous = None
            markup.append(f'<path d="M{x - 4:.2f} 201 L{x + 4:.2f} 209 M{x - 4:.2f} 209 L{x + 4:.2f} 201" stroke="#a33"><title>{title}</title></path>')
            continue
        y = 195 - value * 1.5
        if previous is not None:
            markup.append(f'<path d="M{previous[0]:.2f} {previous[1]:.2f} L{x:.2f} {y:.2f}" stroke="#0f766e" stroke-width="2"/>')
        markup.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="#0f766e"><title>{title}</title></circle>')
        previous = (x, y)
        measured += 1
    if points:
        markup.extend([
            f'<text x="50" y="228" font-size="11">{html.escape(start.isoformat())}</text>',
            f'<text x="680" y="228" text-anchor="end" font-size="11">{html.escape(end.isoformat())}</text>',
        ])
    caption = f"{measured} plotted observations; crosses = held runs; UTC time axis."
    if measured < 2:
        caption += " No change over time established."
    markup.append(f'<text x="50" y="250" font-size="11">{html.escape(caption)}</text></svg>\n')
    return "".join(markup)

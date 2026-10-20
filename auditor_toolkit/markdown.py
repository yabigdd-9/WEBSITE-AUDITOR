"""Readable Markdown from a canonical saved report; no rescoring or active HTML."""
from __future__ import annotations

import html
import json
import re
from typing import Any


def _text(value: Any) -> str:
    text = " ".join(str(value).split())
    return re.sub(r"([\\`*_{}\[\]()#+.!|~])", r"\\\1", html.escape(text, quote=True))


def _json(value: Any) -> str:
    return _text(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False))


def _score(report: dict[str, Any], key: str) -> str:
    value = report.get(key)
    if key == "health_score" and report["status"] != "complete":
        return "Unavailable — audit incomplete"
    if type(value) not in {int, float} or not 0 <= value <= 100:
        return "Unavailable"
    return str(value) + "/100"


def render_markdown_report(report: dict[str, Any]) -> str:
    """Present recorded evidence and review actions without invented conclusions."""
    if (not isinstance(report, dict) or type(report.get("schema_version")) is not int
            or report["schema_version"] < 1
            or any(not isinstance(report.get(key), str) or not report[key] for key in
                   ("run_id", "url", "timestamp", "profile", "status"))):
        raise ValueError("Markdown requires a canonical report identity, timestamp and profile")
    records = report.get("defects")
    if (not isinstance(records, list) or type(report.get("defect_count")) is not int
            or report["defect_count"] != len(records)
            or any(not isinstance(record, dict) or not isinstance(record.get("finding_id"), str)
                   or not record["finding_id"] or not isinstance(record.get("defect"), str)
                   for record in records)
            or len({record["finding_id"] for record in records}) != len(records)):
        raise ValueError("Markdown requires a consistent finding inventory")
    checks = report.get("checks")
    if not isinstance(checks, dict) or any(not isinstance(value, dict) for value in checks.values()):
        raise ValueError("Markdown requires canonical check records")
    lines = [
        "# " + _text(report.get("brand", "Website audit")), "",
        "Site: " + _text(report["url"]), "",
        "- Recorded audit status: " + _text(report["status"]),
        "- Observed at: " + _text(report["timestamp"]),
        "- Profile: " + _text(report["profile"]),
        "- Finding records: " + str(len(records)),
        "- Reported heuristic health: " + _score(report, "health_score"),
        "- Reported defect severity: " + _score(report, "severity_score"),
        "- Run ID: " + _text(report["run_id"]), "",
        "These are captured audit observations. Heuristic scores do not measure business quality or lost revenue. No customer change or message is authorized by this report.",
        "", "## Findings and next actions", "",
    ]
    if not records:
        lines += ["No findings were recorded in the executed scope. Incomplete or skipped checks do not establish a clean website.", ""]
    for index, record in enumerate(records, 1):
        lines += [
            f"### {index}. " + _text(record["defect"]), "",
            "- Finding ID: " + _text(record["finding_id"]),
            "- Severity: " + _text(record.get("severity", "Unrecorded")),
            "- Confidence: " + _text(record.get("confidence", "Unrecorded")),
            "- Source page: " + _text(record.get("source_url") or "Unrecorded"),
            "- Checker: " + _text(record.get("check", "Unrecorded")),
        ]
        for label, keys in (
            ("Recorded evidence", ("evidence_summary", "observed", "impact")),
            ("Evidence reference", ("evidence_ref", "evidence_source")),
            ("Selector", ("selector",)),
            ("Observed at", ("observed_at",)),
            ("Potential impact stated in the audit", ("business_impact",)),
            ("Proposed next action", ("remediation_action", "remediation")),
            ("Action review requirement", ("remediation_automation",)),
            ("Recorded effort band", ("effort_band",)),
        ):
            value = next((record[key] for key in keys if record.get(key)), None)
            if value is not None:
                lines.append("- " + label + ": " + _text(value))
        lines.append("")
    lines += ["## Checks and coverage", "", "Recorded coverage: " + _json(report.get("coverage")), ""]
    for name, record in checks.items():
        lines.append("- " + _text(name) + ": " + _text(record.get("status", "Unrecorded"))
                     + "; required: " + _text(record.get("required", "Unrecorded"))
                     + ("; " + _text(record["reason"]) if record.get("reason") else ""))
    lines += ["", "## Score evidence", "", _json(report.get("breakdown", {})), "",
              "Recorded scoring method and weights: " + _json(report.get("scoring", {})), ""]
    for title, key in (
        ("Historical comparison", "comparison"), ("Recorded history summary", "history_trend"),
        ("Root-cause evidence", "fault_taxonomy"), ("Claim evidence", "claim_ledger"),
        ("Draft proofing", "proofing"), ("Proposal inputs", "proposal"),
    ):
        value = report.get(key)
        if value:
            if key == "history_trend":
                value = {name: value.get(name) for name in ("summary", "basis_run_id", "limitation")}
            lines += ["## " + title, "", _json(value), ""]
    lines += ["## Captured evidence", ""]
    evidence = report.get("evidence", {})
    if not isinstance(evidence, dict):
        raise ValueError("Canonical evidence must be a mapping")
    for name, value in evidence.items():
        lines += ["### " + _text(name), "", _json(value), ""]
    lines += ["## Saved artifacts", ""]
    artifacts = report.get("artifacts", {})
    manifest = report.get("manifest", {})
    if not isinstance(artifacts, dict) or not isinstance(manifest, dict):
        raise ValueError("Canonical artifacts and manifest must be mappings")
    for name, path in artifacts.items():
        binding = manifest.get(name, {})
        binding = binding if isinstance(binding, dict) else {}
        lines.append("- " + _text(name) + ": " + _text(path)
                     + "; recorded SHA256: " + _text(binding.get("sha256", "Unrecorded")))
    lines += ["", "Artifact paths and hashes are recorded references, not a fresh integrity check. Financial estimates remain scenarios requiring reviewed assumptions. Drafts remain unsent.", ""]
    return "\n".join(lines)

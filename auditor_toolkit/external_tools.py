"""Optional local CLI integrations for deterministic/developer-run audit depth.

These tools are never downloaded or paid for by the audit process. They run only
when explicitly requested and an installed binary is available.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from .checks import Finding


def installed_tools() -> dict[str, str | None]:
    return {name: shutil.which(name) for name in ("lychee", "lighthouse")}


def _binary(name: str) -> str:
    if name not in {"lychee", "lighthouse"}:
        raise ValueError("External tool is not allow-listed")
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"{name} is not installed")
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise RuntimeError(f"{name} executable is invalid")
    return str(resolved)



def _safe_url(url: str) -> str:
    value = str(url or "").strip()
    if not value or len(value) > 2048 or any(ord(ch) < 32 for ch in value):
        raise ValueError("Invalid audit URL")
    parsed = urlparse(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("External tools require an absolute HTTP(S) URL without credentials")
    # A normalized HTTP(S) value cannot be parsed by the child CLI as an option.
    return urlunparse(parsed._replace(fragment=""))


def run_lychee(url: str, timeout: float = 90.0):
    target = _safe_url(url)
    command = [
        _binary("lychee"),
        "--format",
        "json",
        "--no-progress",
        "--max-concurrency",
        "2",
        "--host-concurrency",
        "2",
        "--max-retries",
        "0",
        "--timeout",
        "15",
        "--",
        target,
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("lychee timed out") from exc

    raw = (result.stdout or "").strip()
    try:
        report = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        report = {"raw": raw[:4000]}

    evidence = {
        "tool": "lychee",
        "returncode": result.returncode,
        "report": report,
        "stderr": (result.stderr or "")[:2000],
    }
    if result.returncode == 0:
        return [], evidence
    if result.returncode == 2:
        return [
            Finding(
                "lychee-broken-links",
                "Lychee reported broken links",
                "One or more non-excluded links failed validation.",
                "medium",
                url,
                check="lychee",
                confidence="observed",
                evidence_source="lychee JSON report",
                observed="lychee exited with link-check failure code 2",
                business_impact="Broken links can block visitors and waste crawler effort.",
                remediation_action="Review the Lychee report and repair or remove failed links.",
                remediation_automation="AUTO_PREVIEW",
                effort_band="S",
            )
        ], evidence
    raise RuntimeError(
        "lychee runtime/configuration failure"
        + (f": {(result.stderr or '').strip()[:500]}" if result.stderr else "")
    )


def run_lighthouse(url: str, timeout: float = 180.0):
    target = _safe_url(url)
    command = [
        _binary("lighthouse"),
        target,
        "--output=json",
        "--output-path=stdout",
        "--quiet",
        "--chrome-flags=--headless",
        "--only-categories=performance,accessibility,best-practices,seo",
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("lighthouse timed out") from exc
    if result.returncode != 0:
        raise RuntimeError(
            "lighthouse failed"
            + (f": {(result.stderr or '').strip()[:500]}" if result.stderr else "")
        )
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("lighthouse returned invalid JSON") from exc

    categories = report.get("categories") or {}
    audits = report.get("audits") or {}
    scores = {
        name: round(float(data.get("score")) * 100, 1)
        for name, data in categories.items()
        if isinstance(data, dict) and data.get("score") is not None
    }
    thresholds = {
        "performance": (50.0, "medium"),
        "accessibility": (80.0, "medium"),
        "best-practices": (80.0, "low"),
        "seo": (80.0, "low"),
    }
    findings = []
    category_audits: dict[str, list[dict[str, object]]] = {}
    for name, (threshold, severity) in thresholds.items():
        score = scores.get(name)
        category = categories.get(name) or {}
        failed_audits = []
        for audit_ref in category.get("auditRefs") or []:
            audit_id = audit_ref.get("id")
            audit = audits.get(audit_id) if audit_id else None
            if not isinstance(audit, dict):
                continue
            audit_score = audit.get("score")
            if (
                audit_score is None
                or audit_score >= 1
                or audit.get("scoreDisplayMode") in {"manual", "informative", "notApplicable"}
            ):
                continue
            failed_audits.append(
                {
                    "id": audit_id,
                    "title": str(audit.get("title") or audit_id)[:160],
                    "score": round(float(audit_score), 3),
                    "display_value": str(audit.get("displayValue") or "")[:160],
                    "weight": float(audit_ref.get("weight") or 0),
                }
            )
        failed_audits.sort(key=lambda item: (-float(item["weight"]), float(item["score"]), str(item["id"])))
        category_audits[name] = failed_audits[:5]
        if score is not None and score < threshold:
            audit_evidence = category_audits[name][:3]
            audit_summary = "; ".join(
                f"{item['title']} ({item['id']})"
                + (f": {item['display_value']}" if item["display_value"] else f": score {item['score']}" )
                for item in audit_evidence
            )
            findings.append(
                Finding(
                    f"lighthouse-{name}-low",
                    f"Low Lighthouse {name} score",
                    f"Lab score {score:.1f}/100; review individual audits."
                    + (f" Evidence: {audit_summary}." if audit_summary else ""),
                    severity,
                    url,
                    check="lighthouse",
                    confidence="observed",
                    evidence_source="Lighthouse JSON category score and audit refs",
                    observed=f"{name} score={score:.1f}; audits={audit_summary or 'none'}",
                    business_impact="Lab result indicates a potential quality or conversion risk.",
                    remediation_action=f"Review Lighthouse {name} audits and verify fixes with a repeat run.",
                    remediation_automation="HUMAN_REVIEW",
                    effort_band="M",
                )
            )
    evidence = {
        "tool": "lighthouse",
        "version": report.get("lighthouseVersion"),
        "fetch_time": report.get("fetchTime"),
        "categories": scores,
        "category_audits": category_audits,
        "limitation": "Laboratory scores vary by machine/run and are not field Core Web Vitals.",
    }
    return findings, evidence

"""Optional local CLI integrations for deterministic/developer-run audit depth.

These tools are never downloaded or paid for by the audit process. They run only
when explicitly requested and an installed binary is available.
"""
from __future__ import annotations

import json
import shutil
import subprocess

from .checks import Finding


def installed_tools() -> dict[str, str | None]:
    return {name: shutil.which(name) for name in ("lychee", "lighthouse")}


def _binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"{name} is not installed")
    return path


def run_lychee(url: str, timeout: float = 90.0):
    command = [_binary("lychee"), "--format", "json", "--no-progress", url]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
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
    command = [
        _binary("lighthouse"),
        url,
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
    for name, (threshold, severity) in thresholds.items():
        score = scores.get(name)
        if score is not None and score < threshold:
            findings.append(
                Finding(
                    f"lighthouse-{name}-low",
                    f"Low Lighthouse {name} score",
                    f"Lab score {score:.1f}/100; review individual audits.",
                    severity,
                    url,
                    check="lighthouse",
                    confidence="observed",
                    evidence_source="Lighthouse JSON category score",
                    observed=f"{name} score={score:.1f}",
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
        "limitation": "Laboratory scores vary by machine/run and are not field Core Web Vitals.",
    }
    return findings, evidence

#!/usr/bin/env python3
"""One-shot, bounded proof of live website evidence -> internal review draft.

The run uses only the reviewed public allowlist. No client database, CRM,
network models, outgoing messages, production changes, paid providers or
persistent reports. Full evidence/drafts stay in runner-local temporary files,
never in public Actions logs, commits or artifacts.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from auditor_toolkit.remediation import build_remediation
from scripts.cloud_scheduled_audits import (
    DEFAULT_MAX_RESPONSE_BYTES,
    SITE_MAX_RESPONSE_BYTES,
    load_sites,
)

INTERESTING_SEVERITIES = {"medium", "high", "critical"}
SUPPORTED_CONFIDENCE = {"observed", "derived"}
MAX_REVIEW_ITEMS = 10


def _verified_report(stdout: str, root: Path, url: str) -> dict:
    records = json.loads(stdout)
    if not isinstance(records, list) or len(records) != 1:
        raise ValueError("One canonical audit result required")
    item = records[0]
    if not isinstance(item, dict):
        raise ValueError("Malformed audit result")
    artifacts = item.get("artifacts")
    if item.get("status") != "complete" or not isinstance(artifacts, dict):
        raise ValueError("Only complete canonical audits are eligible")
    location = artifacts.get("json")
    if not isinstance(location, str):
        raise ValueError("Audit report path required")
    path = Path(location).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("Audit report must stay in the temporary workspace")
    report = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(report, dict) or report.get("status") != "complete":
        raise ValueError("Incomplete or malformed audit report")
    if report.get("url") != url or not isinstance(report.get("defects"), list):
        raise ValueError("Audit URL or finding list mismatch")
    checks = report.get("checks")
    if not isinstance(checks, dict) or not checks:
        raise ValueError("Audit checks required")
    for check in checks.values():
        if not isinstance(check, dict):
            raise ValueError("Malformed check result")
        if check.get("required") is True and check.get("status") != "ok":
            raise ValueError("Required check incomplete")
    return report


def _review_candidates(report: dict) -> list[dict]:
    evidence = report.get("evidence")
    if not isinstance(evidence, dict):
        return []
    candidates = []
    seen = set()
    for defect in report["defects"]:
        if not isinstance(defect, dict):
            continue
        finding_id = defect.get("finding_id")
        defect_key = defect.get("defect_key")
        summary = defect.get("evidence_summary")
        reference = defect.get("evidence_ref")
        if not all(isinstance(x, str) and x.strip() for x in
                   (finding_id, defect_key, summary, reference)):
            continue
        if reference not in evidence or evidence[reference] is None:
            continue
        if defect.get("severity") not in INTERESTING_SEVERITIES:
            continue
        if defect.get("confidence") not in SUPPORTED_CONFIDENCE:
            continue
        if finding_id in seen:
            continue
        seen.add(finding_id)
        candidates.append(defect)
    weights = {"critical": 3, "high": 2, "medium": 1}
    candidates.sort(key=lambda d: (-weights[d["severity"]], d["finding_id"]))
    return candidates[:MAX_REVIEW_ITEMS]


def _review_packet(report: dict, candidates: list[dict], folder: Path) -> dict:
    preview = build_remediation(
        {"run_id": report.get("run_id"), "url": report["url"], "defects": candidates},
        folder / "preview-only",
    )
    claims = []
    for finding, item in zip(candidates, preview["items"]):
        claims.append({
            "finding_id": finding["finding_id"],
            "severity": finding["severity"],
            "issue_code": finding["defect_key"],
            "evidence_ref": finding["evidence_ref"],
            "observed_summary": finding["evidence_summary"],
            "proposed_action": item["action"],
            "classification": item["classification"],
            "human_verification_required": True,
        })
    packet = {
        "kind": "INTERNAL_REVIEW_ONLY_NOT_FOR_SENDING",
        "source_run_id": report.get("run_id"),
        "source_url": report["url"],
        "audit_status": "complete",
        "draft_proposal": {
            "heading": "Unsent draft scope — observations needing manual review",
            "observations": claims,
            "scope": "Verify each cited issue and platform access before agreeing work.",
            "price_nzd": None,
            "customer_approved": False,
            "send_approved": False,
            "external_sends": 0,
            "production_changes": 0,
            "model_calls": 0,
            "cost_nzd": 0,
        },
    }
    path = folder / "private-review-draft.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    return packet


def run(sites: list[tuple[str, str]], *, output_root: Path, executable: str = "wa",
        runner=subprocess.run, timeout_seconds: int = 150) -> int:
    results = []
    for host, url in sites:
        command = [
            executable, "audit", url, "--profile", "nz",
            "--max-pages", "2", "--max-depth", "1", "--concurrency", "1",
            "--max-bytes", str(SITE_MAX_RESPONSE_BYTES.get(host, DEFAULT_MAX_RESPONSE_BYTES)),
            "--output-root", str(output_root / host),
        ]
        try:
            completed = runner(
                command, check=False, capture_output=True, text=True,
                timeout=timeout_seconds,
            )
            if completed.returncode != 0:
                raise ValueError("Canonical audit exit code was nonzero")
            report = _verified_report(completed.stdout, output_root, url)
            candidates = _review_candidates(report)
            if candidates:
                packet = _review_packet(report, candidates, output_root / host / "review")
                if packet["draft_proposal"]["external_sends"] != 0:
                    raise ValueError("Internal draft must not dispatch messages")
            results.append((host, "PASS", len(report["defects"]), len(candidates)))
        except (subprocess.TimeoutExpired, OSError, ValueError, TypeError, KeyError):
            # Never print raw client evidence, exceptions, stdout/stderr, or URLs.
            results.append((host, "FAIL", 0, 0))
    lines = [
        "## Live-evidence MoneyMachine review-only trial", "",
        "A canonical public-site audit can produce evidence-backed internal",
        "review candidates. Neither a customer proposal nor outreach is approved.", "",
        "| Reviewed domain | Audit | Findings | Draft review items |",
        "| --- | --- | ---: | ---: |",
    ]
    for host, status, findings, candidates in results:
        lines.append(f"| `{host}` | {status} | {findings} | {candidates} |")
    lines.extend([
        "", "No emails, paid models, database writes, or production changes.",
        "Detailed audit evidence and draft scopes remain only on the temporary runner",
        "and are deleted; nothing is uploaded as a public artifact.",
        "A zero-item row means no sufficiently grounded draft candidate was selected.",
        "Passing this trial does not prove sales, client interest or implementation.",
    ])
    message = "\n".join(lines) + "\n"
    print(message)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as dest:
            dest.write(message)
    return 1 if any(status != "PASS" for _, status, _, _ in results) else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allowlist", type=Path, default=Path("clients.txt"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        sites = load_sites(args.allowlist)
        config = json.loads(Path("money-machine/config/transport.json").read_text())
        if (config.get("enabled") is not False
                or config.get("external_send_allowed") is not False
                or config.get("daily_cap") != 0
                or any(os.environ.get(name) != "0" for name in (
                    "MM_ALLOW_EXTERNAL_FREE_MODELS",
                    "MM_PAID_ALLOWED",
                    "MM_EXTERNAL_SEND_ALLOWED",
                ))):
            raise ValueError("Fail-closed model, sending and payment policy required")
    except (OSError, ValueError, TypeError):
        print("BLOCKED: live-evidence trial guard or reviewed allowlist failed.", file=sys.stderr)
        return 2
    if args.dry_run:
        print(f"Validated {len(sites)} reviewed public sites. No network calls made.")
        return 0
    with tempfile.TemporaryDirectory(prefix="wa-live-evidence-review-") as temporary:
        return run(sites, output_root=Path(temporary))


if __name__ == "__main__":
    raise SystemExit(main())

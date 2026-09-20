#!/usr/bin/env python3
"""One-command safe pipeline: audit -> remediation -> dashboard -> action dry-run.

No external email, DNS/TLS, production deployment, or external connector action is
executed by this command. The action policy defaults to dry-run with execution disabled.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent


def safe_domain(url: str) -> str:
    candidate = url if "://" in url else "https://" + url
    host = (urlparse(candidate).hostname or "site").lower()
    return re.sub(r"[^a-z0-9_.-]", "_", host)


def run_step(label: str, command: list[str], *, required: bool = False) -> subprocess.CompletedProcess:
    print(f"\n==> {label}")
    print("    " + " ".join(command))
    result = subprocess.run(command, cwd=ROOT, text=True)
    if result.returncode != 0:
        message = f"{label} exited with code {result.returncode}"
        if required:
            raise SystemExit(message)
        print(f"[warn] {message}; continuing in safe mode.")
    return result


def tls_preflight() -> None:
    try:
        import certifi
        path = Path(certifi.where())
    except Exception as exc:
        raise SystemExit(f"TLS preflight failed: certifi cannot be imported: {exc}") from exc
    if not path.exists():
        raise SystemExit(
            "TLS preflight failed: certifi CA bundle is missing at "
            f"{path}. Activate the project virtualenv and reinstall requirements."
        )


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else "https://example.co.nz"
    domain = safe_domain(target)
    audits = ROOT / "audits"
    remediations = ROOT / "outputs" / "remediations"
    audit_output = audits / f"{domain}.json"
    report_output = ROOT / "report.html"
    audits.mkdir(parents=True, exist_ok=True)
    remediations.mkdir(parents=True, exist_ok=True)

    tls_preflight()
    print(f"Starting safe execution pipeline for: {target}")

    run_step(
        "Evidence-first website audit",
        [
            sys.executable,
            "website_auditor.py",
            target,
            "--format",
            "json",
            "--output",
            str(audit_output),
            "--profile",
            "auto",
            "--mode",
            "static",
        ],
        required=True,
    )

    run_step(
        "Generate remediation plan",
        [
            sys.executable,
            "remediation-engine.py",
            str(audit_output),
            "--output-dir",
            str(remediations),
        ],
        required=True,
    )

    run_step(
        "Generate safe client dashboard",
        [
            sys.executable,
            "audit-dashboard.py",
            "--audits-dir",
            str(audits),
            "--output",
            str(report_output),
        ],
        required=True,
    )

    run_step(
        "Generate portfolio exports",
        [
            sys.executable,
            "portfolio-export.py",
            "--audits-dir",
            str(audits),
            "--output-dir",
            str(ROOT / "outputs" / "portfolio"),
            "--format",
            "all",
        ],
        required=True,
    )

    run_step(
        "Initialize policy-controlled action engine",
        [sys.executable, "-m", "website_auditor.cli", "actions", "init"],
        required=True,
    )
    run_step(
        "Propose actions from remediation evidence",
        [
            sys.executable,
            "-m",
            "website_auditor.cli",
            "actions",
            "propose",
            "--from-remediations",
            str(remediations),
        ],
        required=True,
    )
    run_step(
        "Dry-run all proposed actions",
        [sys.executable, "-m", "website_auditor.cli", "actions", "dry-run"],
        required=True,
    )
    run_step(
        "Action-engine status",
        [sys.executable, "-m", "website_auditor.cli", "actions", "status"],
        required=True,
    )

    summary = {
        "target": target,
        "audit": str(audit_output),
        "remediations": str(remediations),
        "dashboard": str(report_output),
        "portfolio_exports": str(ROOT / "outputs" / "portfolio"),
        "actions": str(ROOT / "outputs" / "actions"),
        "external_effects": False,
        "policy": "action-policy.json (dry_run; execution_enabled=false)",
    }
    print("\n" + "=" * 64)
    print("SAFE PIPELINE COMPLETE")
    print("=" * 64)
    print(json.dumps(summary, indent=2))
    print("No emails, DNS/TLS changes, external connector actions, or production changes were executed.")


if __name__ == "__main__":
    main()

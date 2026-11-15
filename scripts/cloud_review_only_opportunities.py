#!/usr/bin/env python3
"""Review-only, real-public-website opportunity trial on an ephemeral cloud runner.

No live client database, contact discovery, outreach, paid model, browser, or
published audit artifact. The existing reviewed clients.txt allowlist is the
only source of target sites. Any detailed evidence and draft are discarded when
the job finishes; only a non-sensitive run summary reaches GitHub logs.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import tempfile

from auditor_toolkit.demo import build_demo
from auditor_toolkit.pipeline import AuditOptions, run_audit
from auditor_toolkit.remediation import build_remediation

from cloud_scheduled_audits import (
    DEFAULT_MAX_RESPONSE_BYTES,
    SITE_MAX_RESPONSE_BYTES,
    load_sites,
)


def _safe_text(value: object, limit: int = 240) -> str:
    """Treat external website material as data, not commands or instructions."""
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _verify_safety(repo: Path) -> None:
    transport = json.loads((repo / "money-machine/config/transport.json").read_text())
    if (transport.get("enabled") is not False
            or transport.get("external_send_allowed") is not False
            or transport.get("daily_cap") != 0):
        raise ValueError("Outbound transport must remain fully disabled")
    for name in ("MM_PAID_ALLOWED", "MM_ALLOW_EXTERNAL_FREE_MODELS", "MM_EXTERNAL_SEND_ALLOWED"):
        if os.environ.get(name) != "0":
            raise ValueError(f"{name} must be explicitly set to 0")


def make_internal_brief(report: dict, directory: Path) -> dict:
    """Derive a scope-only draft from verified, observed real audit findings.

    This function writes ONLY to the caller's temporary directory. It never
    composes an address, sends a message, quotes a price or deploys a change.
    """
    if report.get("status") != "complete":
        raise ValueError("Cannot draft from an incomplete audit")
    directory.mkdir(parents=True, exist_ok=True)
    evidence = report.get("evidence") or {}
    checks = report.get("checks") or {}
    eligible = []
    for defect in report.get("defects") or []:
        if not isinstance(defect, dict):
            continue
        ref = defect.get("evidence_ref")
        if (defect.get("confidence") == "observed"
                and defect.get("finding_id")
                and defect.get("observed")
                and defect.get("severity") in {"medium", "high", "critical"}
                and isinstance(ref, str)
                and ref in evidence
                and checks.get(ref, {}).get("status") == "ok"):
            eligible.append(defect)

    if not eligible:
        return {"evidenced_candidates": 0, "internal_scope_draft": False}

    remediation = build_remediation(report, directory / "remediation")
    demo = build_demo(report, remediation, directory / "demo", render=False)
    if (remediation.get("production_changes") != 0
            or remediation.get("external_dispatch") is not False
            or demo.get("live_site_changed") is not False
            or demo.get("external_deploy") is not False
            or demo.get("improvement_claim_valid") is not False):
        raise RuntimeError("Local review-only guard failed")

    lines = [
        "INTERNAL SCOPE DRAFT - DO NOT SEND",
        "Review based on an actual public-site audit, NOT a customer-approved project.",
        f"Public URL: {_safe_text(report.get('url'))}",
        f"Audit run ID: {_safe_text(report.get('run_id'))}",
        f"Observed at: {_safe_text(report.get('timestamp'))}",
        "",
        "Possible work items (verify independently before stating to a customer):",
    ]
    for index, defect in enumerate(eligible[:3], 1):
        lines.extend([
            f"{index}. {_safe_text(defect.get('defect'))}",
            f"   Observation: {_safe_text(defect.get('observed'))}",
            f"   Evidence check: {_safe_text(defect.get('evidence_ref'))}",
            f"   Finding ID: {_safe_text(defect.get('finding_id'))}",
            f"   Possible next action: {_safe_text(defect.get('remediation_action'))}",
        ])
    lines.extend([
        "",
        "Pricing: NOT SET - scope, access and hourly rate require review.",
        "No traffic, conversion, lost-revenue or SEO ranking improvement is claimed.",
        "Local concept only; the live site was not changed.",
        "No messages, payments, client contact searches, or external AI calls.",
        "Human approval required for any customer-facing proposal or work.",
    ])
    (directory / "internal-scope-draft.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return {
        "evidenced_candidates": len(eligible),
        "internal_scope_draft": True,
        "concept_only": True,
        "human_approval_required": True,
        "priced": False,
        "outreach_performed": False,
    }


def _summary(outcome: dict) -> str:
    # Do not expose site-specific defects, contact data or evidence in public Actions.
    lines = [
        "## Real-site MoneyMachine review-only trial",
        "",
        "- Source: one reviewed HTTPS site from clients.txt",
        "- Audit: " + ("COMPLETE" if outcome["audit_complete"] else "INCOMPLETE - no proposal"),
        "- Evidence-anchored candidate count: " + str(outcome["evidenced_candidates"]),
        "- Internal scope draft generated: " + str(outcome["internal_scope_draft"]).lower(),
        "- Pricing: not set; customer claims and scope require review",
        "- Contact lookup: **off**; outbound messages: **0**; website changes: **0**",
        "- Paid models: **off**; paid providers: **off**",
        "- Evidence, remediation concept and draft: **temporary, not uploaded or logged**",
        "- This does not establish customer interest, conversion or production readiness.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allowlist", type=Path, default=Path("clients.txt"))
    parser.add_argument("--site-index", type=int, default=0)
    args = parser.parse_args(argv)
    repo = Path(__file__).resolve().parent.parent
    try:
        _verify_safety(repo)
        sites = load_sites(repo / args.allowlist)
        if not 0 <= args.site_index < len(sites):
            raise ValueError("Site index must select a reviewed allowlist entry")
        host, url = sites[args.site_index]
        with tempfile.TemporaryDirectory(prefix="wa-real-review-") as temporary:
            root = Path(temporary)
            audit = run_audit(
                url,
                AuditOptions(
                    output_root=root / "audits",
                    profile="nz",
                    allow_private=False,
                    browser=False,
                    external_tools=False,
                    ai=False,
                    tls=True,
                    max_pages=2,
                    max_depth=1,
                    max_bytes=SITE_MAX_RESPONSE_BYTES.get(host, DEFAULT_MAX_RESPONSE_BYTES),
                ),
            )
            outcome = {"audit_complete": audit["status"] == "complete",
                       "evidenced_candidates": 0, "internal_scope_draft": False}
            if outcome["audit_complete"]:
                outcome.update(make_internal_brief(audit, root / "review"))
            summary = _summary(outcome)
            print(summary)
            destination = os.environ.get("GITHUB_STEP_SUMMARY")
            if destination:
                with Path(destination).open("a", encoding="utf-8") as stream:
                    stream.write(summary)
            return 0 if outcome["audit_complete"] else 2
    except (OSError, ValueError, RuntimeError) as exc:
        # Error type only; exception text may contain external-site details.
        print(f"REVIEW TRIAL BLOCKED ({type(exc).__name__}); no drafts published")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

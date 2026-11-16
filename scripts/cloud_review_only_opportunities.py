#!/usr/bin/env python3
"""Review-only, real-public-website opportunity trial on an ephemeral cloud runner.

No live client database, contact discovery, outreach, paid model, browser, or
published audit artifact. The reviewed clients.txt allowlist is the only source
of target sites. Local evidence and drafts are deleted after each run. Scheduled
jobs publish only a bounded shortlist of domains and aggregated counts.
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

from scripts.cloud_scheduled_audits import (
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



def eligible_findings(report: dict) -> list[dict]:
    """Evidence-gate candidate technical findings; never infer sale probability."""
    checks = report.get("checks") or {}
    evidence = report.get("evidence") or {}
    selected = []
    for defect in report.get("defects") or []:
        if not isinstance(defect, dict):
            continue
        ref = defect.get("evidence_ref")
        if (defect.get("confidence") == "observed"
                and defect.get("finding_id")
                and defect.get("observed")
                and defect.get("severity") in {"medium", "high", "critical"}
                and isinstance(ref, str)
                and ref == defect.get("check")
                and isinstance(evidence.get(ref), dict)
                and isinstance(checks.get(ref), dict)
                and checks[ref].get("status") == "ok"):
            selected.append(defect)
    return selected


def make_internal_brief(report: dict, directory: Path) -> dict:
    """Derive a scope-only draft from verified, observed real audit findings.

    This function writes ONLY to the caller's temporary directory. It never
    composes an address, sends a message, quotes a price or deploys a change.
    """
    if report.get("status") != "complete":
        raise ValueError("Cannot draft from an incomplete audit")
    directory.mkdir(parents=True, exist_ok=True)
    eligible = eligible_findings(report)

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


def run_review_sites(sites: list[tuple[str, str]], workspace: Path,
                     encrypted_review_entries: list[dict] | None = None) -> list[dict]:
    """Bounded sequential audits; a failure on one site never blocks the others."""
    results = []
    for index, (host, url) in enumerate(sites):
        row = {
            "domain": host,
            "status": "ERROR",
            "evidenced_candidates": 0,
            "high_or_critical": 0,
            "internal_scope_draft": False,
        }
        try:
            audit = run_audit(
                url,
                AuditOptions(
                    output_root=workspace / f"audit-{index}",
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
            if audit.get("status") == "complete":
                row["status"] = "COMPLETE"
                eligible = eligible_findings(audit)
                row["high_or_critical"] = sum(
                    item.get("severity") in {"high", "critical"} for item in eligible
                )
                # Re-use the existing review-only, unpriced, non-sending draft path.
                row.update({
                    "evidenced_candidates": 0,
                    "internal_scope_draft": False,
                })
                row.update({
                    key: value for key, value in make_internal_brief(
                        audit, workspace / f"review-{index}"
                    ).items()
                    if key in {"evidenced_candidates", "internal_scope_draft"}
                })
                if encrypted_review_entries is not None:
                    # The only detailed fields eligible for opt-in encryption.
                    # Never capture contact details, raw HTML, or customer data.
                    draft = workspace / f"review-{index}" / "internal-scope-draft.txt"
                    encrypted_review_entries.append({
                        "domain": host,
                        "status": "COMPLETE",
                        "run_id": _safe_text(audit.get("run_id"), 120),
                        "timestamp": _safe_text(audit.get("timestamp"), 80),
                        "checks_completed": sorted(
                            name for name, check in (audit.get("checks") or {}).items()
                            if isinstance(name, str) and isinstance(check, dict)
                            and check.get("status") == "ok"
                        ),
                        "findings": [
                            {
                                "finding_id": _safe_text(item.get("finding_id"), 100),
                                "defect_key": _safe_text(item.get("defect_key"), 80),
                                "severity": _safe_text(item.get("severity"), 24),
                                "source_url": _safe_text(item.get("source_url"), 300),
                                "evidence_check": _safe_text(item.get("evidence_ref"), 80),
                                "evidence_check_status": _safe_text((audit.get("checks") or {}).get(item.get("evidence_ref"), {}).get("status"), 24),
                                "confidence": _safe_text(item.get("confidence"), 24),
                                "independently_verified": False,
                                "evidence_ref": _safe_text(item.get("evidence_ref"), 80),
                                "observed": _safe_text(item.get("observed"), 500),
                                "remediation_action": _safe_text(
                                    item.get("remediation_action"), 500
                                ),
                            }
                            for item in eligible[:20]
                        ],
                        "internal_scope_draft": (
                            draft.read_text(encoding="utf-8")[:9000]
                            if row["internal_scope_draft"] else None
                        ),
                        "approval_status": "HUMAN_REVIEW_REQUIRED",
                        "outbound_sent": 0,
                    })
            else:
                row["status"] = "INCOMPLETE"
        except Exception:
            # Website and exception content are untrusted; NEVER write them
            # into publicly visible Actions logs.
            row["status"] = "ERROR"
        if encrypted_review_entries is not None and row["status"] != "COMPLETE":
            encrypted_review_entries.append({
                "domain": host, "status": row["status"], "findings": [],
                "internal_scope_draft": None, "outbound_sent": 0,
            })
        results.append(row)
    return results


def _summary(rows: list[dict]) -> str:
    """A durable but public shortlist; details remain in ephemeral runner only."""
    ranked = sorted(
        rows,
        key=lambda item: (
            item["status"] != "COMPLETE",
            -item["high_or_critical"],
            -item["evidenced_candidates"],
            item["domain"],
        ),
    )
    lines = [
        "## MoneyMachine: review-only real-site shortlist",
        "",
        "Sites come exclusively from the reviewed public clients.txt allowlist.",
        "Rank is based on counts of observed technical findings, NOT likelihood"
        " of purchase, client suitability, legal compliance, or expected revenue.",
        "Findings are candidates for human verification; no customer has agreed"
        " to anything.",
        "",
        "| Review order | Approved site | Audit | Observed candidate findings | High/critical | Internal draft |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for index, row in enumerate(ranked, 1):
        lines.append(
            f"| {index} | `{row['domain']}` | {row['status']} | "
            f"{row['evidenced_candidates']} | {row['high_or_critical']} | "
            f"{'yes' if row['internal_scope_draft'] else 'no'} |"
        )
    lines.extend([
        "",
        f"Reviewed: **{len(rows)}**; complete audits: "
        f"**{sum(row['status'] == 'COMPLETE' for row in rows)}**;"
        f" temporary internal drafts: "
        f"**{sum(bool(row['internal_scope_draft']) for row in rows)}**.",
        "",
        "**No customer contact, paid providers, paid AI, deployment, or payments.**",
        "Full audit files and local drafts are temporary. An encrypted, bounded"
        " review copy is uploaded only when the owner explicitly configures a public key.",
        "Public summary contains only pre-approved domains and aggregate counts.",
        "This is an opportunity-review queue, not a commercial lead list or"
        " production-ready autonomous worker.",
        "",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allowlist", type=Path, default=Path("clients.txt"))
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--all", action="store_true", help="Review every allowlisted site")
    selection.add_argument("--site-index", type=int, default=0)
    args = parser.parse_args(argv)
    repo = Path(__file__).resolve().parent.parent
    try:
        _verify_safety(repo)
        sites = load_sites(repo / args.allowlist)
        if not args.all and not 0 <= args.site_index < len(sites):
            raise ValueError("Site index must select an approved allowlist entry")
        selected = sites if args.all else [sites[args.site_index]]
        with tempfile.TemporaryDirectory(prefix="wa-review-shortlist-") as tmp:
            public_key = os.environ.get("MM_REPORT_PUBLIC_KEY_B64", "").strip()
            encrypt_requested = bool(public_key) and (
                os.environ.get("GITHUB_EVENT_NAME") != "pull_request"
            )
            entries = [] if encrypt_requested else None
            rows = run_review_sites(selected, Path(tmp), entries)
            summary = _summary(rows)
            if encrypt_requested:
                from scripts.report_vault import write_encrypted

                runner_temp = Path(os.environ["RUNNER_TEMP"]).resolve()
                archive_path = Path(os.environ["MM_ENCRYPTED_REPORT_OUT"]).resolve()
                if not archive_path.is_relative_to(runner_temp):
                    raise ValueError("Encrypted reports must remain in runner temp")
                write_encrypted({
                    "schema_version": 1,
                    "kind": "website_auditor_encrypted_review_bundle",
                    "allowlist_only": True,
                    "owner_review_required": True,
                    "external_sends": 0,
                    "paid_calls": 0,
                    "sites": entries,
                }, public_key, archive_path)
                summary += "\nEncrypted report archive: prepared for 30-day retention.\n"
            else:
                summary += "\nEncrypted report archive: not configured; details discarded.\n"
            print(summary)
            destination = os.environ.get("GITHUB_STEP_SUMMARY")
            if destination:
                with Path(destination).open("a", encoding="utf-8") as stream:
                    stream.write(summary)
            return 0 if all(row["status"] == "COMPLETE" for row in rows) else 2
    except (OSError, ValueError, RuntimeError) as exc:
        # Never echo error strings that may embed untrusted site content.
        print(f"REVIEW SHORTLIST BLOCKED ({type(exc).__name__})")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

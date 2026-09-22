"""Claim-level proofing for audit reports and drafts."""
from __future__ import annotations

import re
from typing import Any

UNSUPPORTED_PATTERNS = (
    r"\bguarantee(?:d|s)?\b", r"\b100\s*%", r"\b(?:lost|missing)\s+(?:revenue|sales)\b",
    r"\bdouble\s+(?:your|the)\b", r"\b(?:will|must)\s+increase\b",
)


def build_claim_ledger(report: dict[str, Any]) -> list[dict[str, Any]]:
    claims = []
    for defect in report.get("defects", []):
        finding_id = defect.get("finding_id")
        evidence = defect.get("evidence_summary") or defect.get("observed")
        confidence = defect.get("confidence_assessment", {}).get("class") or defect.get("confidence", "UNKNOWN")
        claims.append({
            "claim_id": f"finding:{finding_id}",
            "claim": defect.get("defect", defect.get("defect_key")),
            "claim_type": "observed_fact" if confidence in {"PROVEN", "STRONG", "observed"} else "hypothesis",
            "finding_id": finding_id,
            "evidence_ref": defect.get("evidence_ref"),
            "evidence": evidence,
            "source_url": defect.get("source_url") or report.get("url"),
            "observed_at": defect.get("observed_at") or report.get("timestamp"),
            "confidence": confidence,
            "allowed_language": "observed" if confidence in {"PROVEN", "STRONG", "observed"} else "may indicate",
            "human_review_required": True,
        })
    return claims


def proof_draft(text: str, claim_ledger: list[dict[str, Any]]) -> dict[str, Any]:
    errors = []
    warnings = []
    lower = text.casefold()
    for pattern in UNSUPPORTED_PATTERNS:
        if re.search(pattern, lower):
            errors.append("unsupported_claim:" + pattern)
    referenced = []
    for claim in claim_ledger:
        evidence = str(claim.get("evidence") or "").casefold()
        claim_text = str(claim.get("claim") or "").casefold()
        if (claim_text and claim_text in lower) or (evidence and evidence in lower):
            referenced.append(claim["claim_id"])
    if claim_ledger and not referenced:
        warnings.append("draft_contains_no_traceable_claim_reference")
    return {
        "passed": not errors,
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "referenced_claim_ids": referenced,
        "unreferenced_claim_count": max(0, len(claim_ledger) - len(referenced)),
        "human_review_required": True,
        "scope": "Pattern and evidence-reference checks; human factual review remains required.",
    }

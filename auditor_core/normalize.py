"""Convert legacy defect dictionaries into stable evidence-first findings."""
from __future__ import annotations

from .models import Finding, Severity
from .registry import get_registry
from .remediation import initial_remediation


def normalize_defects(defects: list[dict], *, url: str) -> list[dict]:
    registry = get_registry()
    findings: list[dict] = []

    for defect in defects:
        message = str(defect.get("defect") or defect.get("header") or "Unclassified finding")
        definition = registry.match(message)

        if definition is None:
            finding = Finding(
                check_id="legacy.unclassified",
                severity=Severity.low,
                confidence=0.55,
                message=message,
                business_impact=defect.get("impact"),
                evidence_refs=["page.raw"],
                affected_urls=[url],
                category="technical_health",
                standards=[],
                auto_fixable=False,
                human_review=True,
                priority="P7",
                remediation=initial_remediation(
                    verification_command=f"python website_auditor.py {url} --format json"
                ),
                legacy_defect=defect,
            )
        else:
            evidence_refs = [f"page.{item}" for item in definition.evidence_required] or ["page.raw"]
            finding = Finding(
                check_id=definition.id,
                severity=definition.severity,
                confidence=definition.confidence,
                message=message,
                business_impact=defect.get("impact"),
                evidence_refs=evidence_refs,
                affected_urls=[url],
                category=definition.category,
                standards=definition.standards,
                auto_fixable=definition.auto_fixable,
                human_review=definition.human_review,
                priority=definition.default_priority,
                remediation=initial_remediation(
                    verification_command=(
                        f"python website_auditor.py {url} --format json "
                        f"# verify {definition.id}"
                    )
                ),
                legacy_defect=defect,
            )
        findings.append(finding.model_dump(mode="json"))

    return findings

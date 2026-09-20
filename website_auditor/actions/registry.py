"""Stable action definitions and mapping from audit findings to actions."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..models import Action, Risk, stable_id


@dataclass(frozen=True)
class ActionDefinition:
    id: str
    name: str
    category: str
    risk: Risk
    connector: str
    requires_approval: bool = False
    requires_authorization: bool = True
    reversible: bool = False
    verification_checks: tuple[str, ...] = ()
    rollback_action_id: str | None = None


ACTION_DEFINITIONS: dict[str, ActionDefinition] = {
    "report.generate": ActionDefinition(
        "report.generate", "Generate local audit report artifact", "reporting", Risk.LOW, "local",
        requires_authorization=False, reversible=True, verification_checks=("artifact.exists",),
    ),
    "ticket.create": ActionDefinition(
        "ticket.create", "Create local remediation ticket artifact", "workflow", Risk.LOW, "local",
        requires_authorization=False, reversible=True, verification_checks=("artifact.exists",),
    ),
    "patch.local_stage": ActionDefinition(
        "patch.local_stage", "Stage local remediation patch artifact", "remediation", Risk.MEDIUM, "local",
        requires_approval=True, requires_authorization=True, reversible=True,
        verification_checks=("artifact.exists", "reaudit.required"), rollback_action_id="patch.local_rollback",
    ),
    "git.branch_create": ActionDefinition(
        "git.branch_create", "Propose Git branch creation", "source_control", Risk.MEDIUM, "git",
        requires_approval=True, requires_authorization=True, reversible=True,
        verification_checks=("branch.exists",), rollback_action_id="git.branch_delete",
    ),
    "slack.notify": ActionDefinition(
        "slack.notify", "Send approved Slack notification", "notification", Risk.MEDIUM, "slack",
        requires_approval=True, requires_authorization=True, verification_checks=("notification.accepted",),
    ),
    "outreach.send": ActionDefinition(
        "outreach.send", "Send approved outreach", "outreach_send", Risk.CRITICAL, "esp",
        requires_approval=True, requires_authorization=True,
        verification_checks=("transport.accepted", "suppression.checked"),
    ),
    "dns.write": ActionDefinition(
        "dns.write", "Apply DNS record change", "dns_write", Risk.CRITICAL, "dns",
        requires_approval=True, requires_authorization=True, reversible=True,
        verification_checks=("dns.propagated",), rollback_action_id="dns.restore_snapshot",
    ),
}

CHECK_TO_ACTION = {
    "seo.h1_missing": "patch.local_stage",
    "seo.title_missing": "patch.local_stage",
    "seo.meta_description_missing": "patch.local_stage",
    "seo.canonical_missing": "patch.local_stage",
    "seo.schema_missing": "patch.local_stage",
    "accessibility.image_alt_missing": "patch.local_stage",
    "security.hsts_missing": "patch.local_stage",
    "security.csp_missing": "patch.local_stage",
    "technical.broken_links": "patch.local_stage",
}


def build_action(
    action_type: str,
    *,
    domain: str,
    payload: dict[str, Any] | None = None,
    evidence: list[str] | None = None,
    environment: str = "local",
) -> Action:
    definition = ACTION_DEFINITIONS[action_type]
    payload = dict(payload or {})
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    action_id = stable_id("act", [domain.lower(), action_type, canonical])
    return Action(
        action_id=action_id,
        action_type=definition.id,
        name=definition.name,
        category=definition.category,
        risk=definition.risk,
        connector=definition.connector,
        domain=domain,
        environment=environment,
        requires_approval=definition.requires_approval,
        requires_authorization=definition.requires_authorization,
        reversible=definition.reversible,
        idempotency_key=Action.make_idempotency_key(domain, action_type, payload),
        payload=payload,
        evidence=list(evidence or []),
        verification_checks=list(definition.verification_checks),
        rollback_action_id=definition.rollback_action_id,
    )


def action_from_finding(domain: str, finding: dict[str, Any]) -> Action:
    check_id = str(finding.get("check_id") or finding.get("defect_key") or "")
    action_type = CHECK_TO_ACTION.get(check_id, "ticket.create")
    message = finding.get("message") or finding.get("defect") or check_id or "Finding"
    payload = {
        "check_id": check_id or "legacy.unclassified",
        "message": message,
        "severity": finding.get("severity"),
        "priority": finding.get("priority") or finding.get("priority_label"),
        "suggested_fix": finding.get("fix"),
    }
    evidence = [str(item) for item in finding.get("evidence_refs", [])]
    return build_action(action_type, domain=domain, payload=payload, evidence=evidence)
